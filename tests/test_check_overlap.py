import os
import sys
import tempfile
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import check_overlap as co


class TestParsing(unittest.TestCase):
    def test_full_prefix(self):
        c = co.parse_card_line('[Deck::Sub] [g1] [mid:9999:2] Question :: Answer')
        self.assertEqual(c['deck'], 'Deck::Sub')
        self.assertEqual(c['guid'], 'g1')
        self.assertEqual(c['mid'], 'mid:9999:2')
        self.assertEqual(c['front'], 'Question')
        self.assertEqual(c['back'], 'Answer')

    def test_no_prefix(self):
        c = co.parse_card_line('Question :: Answer')
        self.assertIsNone(c['deck'])
        self.assertIsNone(c['guid'])
        self.assertEqual(c['front'], 'Question')

    def test_deck_only(self):
        c = co.parse_card_line('[My Deck] Question :: Answer')
        self.assertEqual(c['deck'], 'My Deck')
        self.assertIsNone(c['guid'])

    def test_comments_and_blanks_skipped(self):
        self.assertIsNone(co.parse_card_line('# a comment'))
        self.assertIsNone(co.parse_card_line('   '))
        self.assertIsNone(co.parse_card_line('# OVERLAP front=1.0 [D] [g] text :: more'))

    def test_multiple_fields_joined_into_back(self):
        c = co.parse_card_line('[D] [g] One :: Two :: Three')
        self.assertEqual(c['front'], 'One')
        self.assertEqual(c['back'], 'Two Three')

    def test_malformed_guid_bracket_is_not_swallowed(self):
        """A GUID containing ']' is left in the content rather than truncated."""
        c = co.parse_card_line('[Deck] [ab]cd] Front :: Back')
        self.assertEqual(c['deck'], 'Deck')
        self.assertIn('ab', c['front'])


class TestNormalization(unittest.TestCase):
    def test_cloze_unwrap_drops_hint(self):
        self.assertEqual(co.unwrap_cloze('{{c1::answer::hint}}'), 'answer')

    def test_cloze_unwrap_multiple(self):
        self.assertEqual(co.unwrap_cloze('{{c1::a}} and {{c2::b}}'), 'a and b')

    def test_cloze_nested_does_not_crash(self):
        self.assertIsInstance(co.unwrap_cloze('{{c1::foo {{c2::bar}} baz}}'), str)

    def test_html_tags_removed(self):
        tokens = co.tokenize('<ul><li>Running</li></ul>')
        self.assertIn('running', tokens)
        self.assertNotIn('li', tokens)
        self.assertNotIn('ul', tokens)

    def test_entities_unescaped(self):
        self.assertNotIn('mdash', co.tokenize('A &mdash; B'))

    def test_digits_are_kept(self):
        """100 kHz vs 400 kHz is the whole difference between two I2C cards."""
        self.assertIn('100', co.tokenize('100 kHz'))
        self.assertNotEqual(co.tokenize('100 kHz'), co.tokenize('400 kHz'))

    def test_stopwords_removed(self):
        self.assertNotIn('what', co.tokenize('What is the answer'))

    def test_all_stopword_text_falls_back(self):
        self.assertTrue(co.tokenize('what is the'))


class TestScoring(unittest.TestCase):
    def _score(self, c1, c2):
        a, b = co.parse_card_line(c1), co.parse_card_line(c2)
        return co.score_pair(co.tokens_for(a), co.tokens_for(b))

    def test_near_identical_flagged(self):
        s = self._score(
            '[D] [g1] What speed is I2C standard mode? :: 100 kHz',
            '[D] [g2] What is the standard-mode clock speed of I2C? :: 100 kHz')
        self.assertTrue(co.is_flagged(s, co.DEFAULT_THRESHOLD))

    def test_unrelated_not_flagged(self):
        s = self._score(
            '[D] [g1] How many bits is an I2C address? :: 7 bits',
            '[D] [g2] What is priority inversion? :: A low-priority task holds a lock.')
        self.assertFalse(co.is_flagged(s, co.DEFAULT_THRESHOLD))

    def test_reverse_card_pair_not_flagged(self):
        """Shared back with a different front is an intentional reverse card."""
        s = self._score(
            '[D] [g1] semaphore: decrements the count, blocking while zero :: sem_wait',
            '[D] [g2] Name three RTOS task states :: decrements the count, blocking while zero')
        self.assertFalse(co.is_flagged(s, co.DEFAULT_THRESHOLD))

    def test_containment_is_asymmetric(self):
        self.assertEqual(co.containment({'a'}, {'a', 'b', 'c'}), 1.0)
        self.assertAlmostEqual(co.containment({'a', 'b', 'c'}, {'a'}), 1 / 3)

    def test_empty_sets(self):
        self.assertEqual(co.containment(set(), {'a'}), 0.0)
        self.assertEqual(co.jaccard(set(), set()), 0.0)


class TestFileOperations(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.corpus = os.path.join(self.tmp, 'corpus.txt')
        self.cand = os.path.join(self.tmp, 'cand.txt')
        with open(self.corpus, 'w') as f:
            f.write('[D] [c1] What is priority inversion? :: A low-priority task holds a lock.\n')
        with open(self.cand, 'w') as f:
            f.write('# header comment\n')
            f.write('[D] [n1] Define priority inversion. :: A low-priority task holds a lock.\n')
            f.write('[D] [n2] How many wires does SPI use? :: Four.\n')

    def test_guid_collision_detected(self):
        cands = co.load_cards(self.cand)
        corpus = co.load_cards(self.corpus)
        self.assertEqual(co.find_guid_collisions(cands, corpus), [])

        with open(self.cand, 'a') as f:
            f.write('[D] [c1] Reused guid :: Bad.\n')
        collisions = co.find_guid_collisions(co.load_cards(self.cand), corpus)
        self.assertEqual(len(collisions), 1)
        self.assertEqual(collisions[0]['guid'], 'c1')

    def test_annotate_is_idempotent(self):
        corpus = co.load_cards(self.corpus)
        for _ in range(3):
            results = co.find_overlaps(co.load_cards(self.cand), corpus,
                                       co.DEFAULT_THRESHOLD)
            co.annotate_file(self.cand, results)
        with open(self.cand) as f:
            lines = f.readlines()
        self.assertEqual(sum(1 for l in lines if l.startswith('# OVERLAP')), 1)

    def test_annotations_are_inert_comments(self):
        """Annotated files must not turn annotations into cards."""
        corpus = co.load_cards(self.corpus)
        results = co.find_overlaps(co.load_cards(self.cand), corpus, co.DEFAULT_THRESHOLD)
        co.annotate_file(self.cand, results)
        reparsed = co.load_cards(self.cand)
        self.assertEqual(len(reparsed), 2)
        for c in reparsed:
            self.assertFalse(c['raw'].startswith('#'))

    def test_clean_removes_annotations(self):
        corpus = co.load_cards(self.corpus)
        results = co.find_overlaps(co.load_cards(self.cand), corpus, co.DEFAULT_THRESHOLD)
        co.annotate_file(self.cand, results)
        removed = co.strip_annotations(self.cand)
        self.assertEqual(removed, 1)
        with open(self.cand) as f:
            self.assertNotIn('# OVERLAP', f.read())

    def test_candidate_vs_candidate_dedup(self):
        with open(self.cand, 'w') as f:
            f.write('[D] [n1] What speed is I2C standard mode? :: 100 kHz\n')
            f.write('[D] [n2] What is the I2C standard mode speed? :: 100 kHz\n')
        results = co.find_overlaps(co.load_cards(self.cand), [], co.DEFAULT_THRESHOLD)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['matches'][0]['source'], 'candidate')


if __name__ == '__main__':
    unittest.main()
