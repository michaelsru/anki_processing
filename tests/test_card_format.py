import os
import sys
import tempfile
import unittest

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import card_format as cf


class TestParsing(unittest.TestCase):
    def test_full_prefix(self):
        c = cf.parse_card_line('[Deck::Sub] [g1] [mid:9999:2] Question :: Answer')
        self.assertEqual(c['deck'], 'Deck::Sub')
        self.assertEqual(c['guid'], 'g1')
        self.assertEqual(c['mid'], 'mid:9999:2')
        self.assertEqual(c['mid_id'], 9999)
        self.assertEqual(c['mid_count'], 2)
        self.assertEqual(c['fields'], ['Question', 'Answer'])
        self.assertEqual(c['front'], 'Question')
        self.assertEqual(c['back'], 'Answer')

    def test_no_prefix(self):
        c = cf.parse_card_line('Question :: Answer')
        self.assertIsNone(c['deck'])
        self.assertIsNone(c['guid'])
        self.assertIsNone(c['mid'])
        self.assertIsNone(c['mid_id'])
        self.assertIsNone(c['mid_count'])
        self.assertEqual(c['front'], 'Question')

    def test_deck_only(self):
        c = cf.parse_card_line('[My Deck] Question :: Answer')
        self.assertEqual(c['deck'], 'My Deck')
        self.assertIsNone(c['guid'])

    def test_lone_alphanumeric_bracket_is_a_deck(self):
        """The documented deck-first rule from template_cards.txt rule 1."""
        c = cf.parse_card_line('[15938472] Front :: Back')
        self.assertEqual(c['deck'], '15938472')
        self.assertIsNone(c['guid'])

    def test_deck_like_guid_before_mid_tag(self):
        """[g1] [mid:1:2] has no deck-shaped second group, so the mid tag must
        not be read as the GUID."""
        c = cf.parse_card_line('[g1] [mid:1:2] Q :: A')
        self.assertNotEqual(c['guid'], 'mid:1:2')
        self.assertEqual(c['deck'], 'g1')
        self.assertEqual(c['mid_id'], 1)
        self.assertEqual(c['mid_count'], 2)
        self.assertEqual(c['fields'], ['Q', 'A'])

    def test_comments_and_blanks_skipped(self):
        self.assertIsNone(cf.parse_card_line('# a comment'))
        self.assertIsNone(cf.parse_card_line('   '))
        self.assertIsNone(cf.parse_card_line('# OVERLAP front=1.0 [D] [g] text :: more'))

    def test_brackets_without_content_skipped(self):
        self.assertIsNone(cf.parse_card_line('[D] [g]'))

    def test_multiple_fields_joined_into_back(self):
        c = cf.parse_card_line('[D] [g] One :: Two :: Three')
        self.assertEqual(c['fields'], ['One', 'Two', 'Three'])
        self.assertEqual(c['front'], 'One')
        self.assertEqual(c['back'], 'Two Three')

    def test_guid_with_unbalanced_brackets(self):
        c = cf.parse_card_line('[Deck] [Pr0gsJ]<qW] [mid:1:2] Front :: Back')
        self.assertEqual(c['deck'], 'Deck')
        self.assertEqual(c['guid'], 'Pr0gsJ]<qW')
        self.assertEqual(c['mid'], 'mid:1:2')
        self.assertEqual(c['front'], 'Front')

    def test_guid_ending_in_bracket(self):
        c = cf.parse_card_line('[D] [ab]] Q :: A')
        self.assertEqual(c['guid'], 'ab]')
        self.assertEqual(c['front'], 'Q')

    def test_cloze_line_is_one_field(self):
        c = cf.parse_card_line('[D] [g] {{c1::answer}} is the answer')
        self.assertEqual(c['fields'], ['{{c1::answer}} is the answer'])

    def test_bare_double_colon_splits_basic_only(self):
        self.assertEqual(cf.parse_card_line('[D] [g] Q::A')['fields'], ['Q', 'A'])
        self.assertEqual(cf.parse_card_line('[D] [g] {{c1::A}}')['fields'], ['{{c1::A}}'])

    def test_mid_tag_without_count(self):
        c = cf.parse_card_line('[D] [g] [mid:42] Q :: A')
        self.assertEqual(c['mid_id'], 42)
        self.assertIsNone(c['mid_count'])

    def test_malformed_mid_tag_is_untagged(self):
        c = cf.parse_card_line('[D] [g] [mid:abc:2] Q :: A')
        self.assertEqual(c['mid'], 'mid:abc:2')
        self.assertIsNone(c['mid_id'])
        self.assertIsNone(c['mid_count'])
        self.assertEqual(c['fields'], ['Q', 'A'])


class TestRoundTrip(unittest.TestCase):
    def _round_trip(self, deck, guid, mid_id, count, fields):
        line = cf.format_card_line(deck, guid, mid_id, count, fields)
        self.assertNotIn('\n', line)
        c = cf.parse_card_line(line)
        self.assertEqual((c['deck'], c['guid'], c['mid_id'], c['mid_count']),
                         (deck, guid, mid_id, count))
        return c

    def test_basic_with_bracket_guid(self):
        c = self._round_trip('Embedded::Debug', 'Pr0gsJ]<qW', 1784593775130, 2,
                             ['What is JTAG?', 'A debug port.'])
        self.assertEqual(c['fields'], ['What is JTAG?', 'A debug port.'])

    def test_cloze(self):
        c = self._round_trip('Embedded', 'h7<A9Y*^hd', 9988776655, 2,
                             ['{{c1::Flash}} holds the bootloader.', 'Extra'])
        self.assertEqual(c['fields'], ['{{c1::Flash}} holds the bootloader.', 'Extra'])

    def test_trailing_empty_fields_carried_by_count(self):
        c = self._round_trip('D', 'g', 7, 3, ['Q', '', ''])
        self.assertEqual(c['fields'], ['Q'])
        self.assertEqual(c['mid_count'], 3)

    def test_newlines_flattened(self):
        c = self._round_trip('D', 'g', 7, 2, ['line one\nline two', 'A'])
        self.assertEqual(c['fields'], ['line one line two', 'A'])

    def test_exact_text(self):
        self.assertEqual(
            cf.format_card_line('Embedded', '3&oklodda', 9988776655, 2,
                                ['The {{c1::SP}} is first.', '']),
            '[Embedded] [3&oklodda] [mid:9988776655:2] The {{c1::SP}} is first.')


class TestLoadCards(unittest.TestCase):
    def test_lineno_attached_and_comments_skipped(self):
        tmp = tempfile.mkdtemp()
        path = os.path.join(tmp, 'cards.txt')
        with open(path, 'w') as f:
            f.write('# header\n\n[D] [a] Q1 :: A1\n# OVERLAP note\n[D] [b] Q2 :: A2\n')
        cards = cf.load_cards(path)
        self.assertEqual([(c['guid'], c['lineno']) for c in cards], [('a', 3), ('b', 5)])


if __name__ == '__main__':
    unittest.main()
