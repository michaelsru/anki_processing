import os
import sys
import tempfile
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import card_format as cf
import check_overlap as co


class TestGuidCollisions(unittest.TestCase):
    def test_bracket_guid_collision_detected(self):
        line = ('[Embedded] [Pr0gsJ]<qW] [mid:9988776655:2] {{c1::JTAG/SWD}} '
                'are hardware debug interfaces.')
        corpus = [cf.parse_card_line(line)]
        cands = [cf.parse_card_line(line.replace('debug', 'programming'))]
        collisions = co.find_guid_collisions(cands, corpus)
        self.assertEqual([c['guid'] for c in collisions], ['Pr0gsJ]<qW'])


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
        a, b = cf.parse_card_line(c1), cf.parse_card_line(c2)
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

    def test_cloze_rewrite_of_basic_card_flagged(self):
        """A cloze card keeps its answer in the front, so fronts alone don't match."""
        s = self._score(
            '[D] [n] A watchdog timer {{c1::resets the system if software fails '
            'to kick it within a set time}}.',
            '[D] [o] What is a Watchdog Timer? :: A hardware counter that resets the '
            'system if software gets stuck and fails to "kick" or "feed" it within a set time.')
        self.assertTrue(co.is_flagged(s, co.DEFAULT_THRESHOLD))

    def test_question_boilerplate_not_flagged(self):
        s = self._score(
            '[D] [g1] What does APN stand for? :: Access Point Name.',
            '[D] [g2] What does LIFO stand for in regard to a Stack? :: Last In First Out')
        self.assertFalse(co.is_flagged(s, co.DEFAULT_THRESHOLD))

    def test_two_shared_words_not_flagged(self):
        """Half the candidate's words match, but only two words, so no flag."""
        s = self._score(
            '[D] [g1] What does SPI stand for? :: Serial Peripheral',
            '[D] [g2] What does UART stand for on serial links? :: '
            'Universal Asynchronous Receiver Transmitter')
        self.assertEqual((s['score'], s['shared']), (0.5, 2))
        self.assertFalse(co.is_flagged(s, co.DEFAULT_THRESHOLD))

    def test_exact_duplicate_of_tiny_card_flagged(self):
        s = self._score('[D] [g1] What is DRAM? :: Volatile.',
                        '[D] [g2] What is DRAM? :: Volatile.')
        self.assertEqual(s['shared'], 2)
        self.assertTrue(co.is_flagged(s, co.DEFAULT_THRESHOLD))

    def test_reverse_card_pair_flagged_as_swapped(self):
        s = self._score(
            '[D] [g1] sem_wait :: Decrements a semaphore count, blocking while it is zero',
            '[D] [g2] Which POSIX call decrements a semaphore count, blocking while it '
            'is zero? :: sem_wait')
        self.assertTrue(co.is_flagged(s, co.DEFAULT_THRESHOLD))
        self.assertTrue(s['swapped'])

    def test_same_sided_duplicate_not_swapped(self):
        s = self._score(
            '[D] [g1] What speed is I2C standard mode? :: 100 kHz',
            '[D] [g2] What is the standard-mode clock speed of I2C? :: 100 kHz')
        self.assertFalse(s['swapped'])

    def test_duplicate_whose_sides_share_words_not_swapped(self):
        line = ('[D] [g1] Where do the Android/fastboot USB udev rules live? :: '
                '<code>/etc/udev/rules.d/51-android.rules</code>')
        s = self._score(line, line)
        self.assertTrue(co.is_flagged(s, co.DEFAULT_THRESHOLD))
        self.assertFalse(s['swapped'])

    def test_cloze_card_never_swapped(self):
        s = self._score(
            '[D] [g1] {{c1::sem_wait}} :: Decrements a semaphore count while zero',
            '[D] [g2] Decrements a semaphore count while zero :: sem_wait')
        self.assertFalse(s['swapped'])

    def test_report_labels_swapped_match_only(self):
        reverse = cf.parse_card_line(
            '[D] [g1] sem_wait :: Decrements a semaphore count, blocking while it is zero')
        reverse['lineno'] = 1
        same = cf.parse_card_line('[D] [g3] What speed is I2C standard mode? :: 100 kHz')
        same['lineno'] = 2
        corpus = [cf.parse_card_line(l) for l in (
            '[D] [g2] Which POSIX call decrements a semaphore count, blocking while it '
            'is zero? :: sem_wait',
            '[D] [g4] What is the standard-mode clock speed of I2C? :: 100 kHz')]
        results = co.find_overlaps([reverse, same], corpus, co.DEFAULT_THRESHOLD)
        lines = co.format_report(results, [reverse, same], corpus,
                                 co.DEFAULT_THRESHOLD).splitlines()
        labelled = [l for l in lines if 'same words, swapped sides' in l]
        self.assertEqual(len(labelled), 1)
        self.assertIn('[g2]', labelled[0])
        self.assertTrue(any('[g4]' in l for l in lines))

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
        cands = cf.load_cards(self.cand)
        corpus = cf.load_cards(self.corpus)
        self.assertEqual(co.find_guid_collisions(cands, corpus), [])

        with open(self.cand, 'a') as f:
            f.write('[D] [c1] Reused guid :: Bad.\n')
        collisions = co.find_guid_collisions(cf.load_cards(self.cand), corpus)
        self.assertEqual(len(collisions), 1)
        self.assertEqual(collisions[0]['guid'], 'c1')

    def test_annotate_is_idempotent(self):
        corpus = cf.load_cards(self.corpus)
        for _ in range(3):
            results = co.find_overlaps(cf.load_cards(self.cand), corpus,
                                       co.DEFAULT_THRESHOLD)
            co.annotate_file(self.cand, results)
        with open(self.cand) as f:
            lines = f.readlines()
        self.assertEqual(sum(1 for l in lines if l.startswith('# OVERLAP')), 1)

    def test_annotations_are_inert_comments(self):
        """Annotated files must not turn annotations into cards."""
        corpus = cf.load_cards(self.corpus)
        results = co.find_overlaps(cf.load_cards(self.cand), corpus, co.DEFAULT_THRESHOLD)
        co.annotate_file(self.cand, results)
        reparsed = cf.load_cards(self.cand)
        self.assertEqual(len(reparsed), 2)
        for c in reparsed:
            self.assertFalse(c['raw'].startswith('#'))

    def test_clean_removes_annotations(self):
        corpus = cf.load_cards(self.corpus)
        results = co.find_overlaps(cf.load_cards(self.cand), corpus, co.DEFAULT_THRESHOLD)
        co.annotate_file(self.cand, results)
        removed = co.strip_annotations(self.cand)
        self.assertEqual(removed, 1)
        with open(self.cand) as f:
            self.assertNotIn('# OVERLAP', f.read())

    def test_dropped_cards_survive_clean_and_reannotate(self):
        """--strict comments a card out as '# OVERLAP-DROPPED <card>'. That line
        is the only copy of the card left, so --clean and later annotation runs
        must keep it."""
        corpus = cf.load_cards(self.corpus)
        results = co.find_overlaps(cf.load_cards(self.cand), corpus, co.DEFAULT_THRESHOLD)
        co.comment_out_flagged(self.cand, results)
        dropped = '# OVERLAP-DROPPED [D] [n1] Define priority inversion. :: A low-priority task holds a lock.\n'
        with open(self.cand) as f:
            self.assertIn(dropped, f.readlines())

        self.assertEqual(co.strip_annotations(self.cand), 0)
        with open(self.cand) as f:
            self.assertIn(dropped, f.readlines())

        results = co.find_overlaps(cf.load_cards(self.cand), corpus, co.DEFAULT_THRESHOLD)
        co.annotate_file(self.cand, results)
        with open(self.cand) as f:
            self.assertIn(dropped, f.readlines())

        co.comment_out_flagged(self.cand, results)
        with open(self.cand) as f:
            self.assertIn(dropped, f.readlines())

    def test_candidate_vs_candidate_dedup(self):
        with open(self.cand, 'w') as f:
            f.write('[D] [n1] What speed is I2C standard mode? :: 100 kHz\n')
            f.write('[D] [n2] What is the I2C standard mode speed? :: 100 kHz\n')
        results = co.find_overlaps(cf.load_cards(self.cand), [], co.DEFAULT_THRESHOLD)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]['matches'][0]['source'], 'candidate')


if __name__ == '__main__':
    unittest.main()
