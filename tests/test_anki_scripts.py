import contextlib
import glob
import io
import json
import sqlite3
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch, mock_open
import sys
import os

# Add parent directory to path to import scripts
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(REPO)

import genanki

import generate_anki_from_text
import dump_apkg


def notes_in_apkg(apkg_path):
    """Read (deck name, guid, mid, fields) per note straight from the package's
    SQLite, independent of every parser in the repo."""
    with tempfile.TemporaryDirectory() as tmp:
        with zipfile.ZipFile(apkg_path) as z:
            z.extract('collection.anki2', tmp)
        conn = sqlite3.connect(os.path.join(tmp, 'collection.anki2'))
        try:
            decks = json.loads(conn.execute('SELECT decks FROM col').fetchone()[0])
            rows = conn.execute(
                'SELECT n.guid, n.mid, n.flds, MIN(c.did) FROM notes n '
                'JOIN cards c ON c.nid = n.id GROUP BY n.id').fetchall()
        finally:
            conn.close()
    return [(decks[str(did)]['name'], guid, mid, flds.split('\x1f'))
            for guid, mid, flds, did in rows]


def run_generator_cli(lines, cwd):
    """Run generate_anki_from_text.py on a cards file inside `cwd`, so its
    generated_decks/ lands there. Returns (completed process, apkg paths)."""
    src = os.path.join(cwd, 'cards.txt')
    with open(src, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    proc = subprocess.run(
        [sys.executable, os.path.join(REPO, 'generate_anki_from_text.py'), src],
        cwd=cwd, capture_output=True, text=True)
    return proc, glob.glob(os.path.join(cwd, 'generated_decks', '*.apkg'))


class TestGeneratorCli(unittest.TestCase):
    def test_deck_like_guid_then_mid_tag(self):
        """[g1] [mid:1:2] Q :: A has a deck-shaped first group and no GUID. The
        deck-first rule makes g1 the deck; the mid tag is never the GUID."""
        with tempfile.TemporaryDirectory() as tmp:
            proc, apkgs = run_generator_cli(['[g1] [mid:1:2] Q :: A'], tmp)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertEqual(len(apkgs), 1)
            notes = notes_in_apkg(apkgs[0])
        self.assertEqual(notes, [('g1', genanki.guid_for('Q', 1), 1, ['Q', 'A'])])


def generate_from_lines(lines, tmp, name='cards.txt'):
    """Write `lines` to <tmp>/<name>, generate into <tmp>/out, return the notes."""
    src = os.path.join(tmp, name)
    with open(src, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    with contextlib.redirect_stdout(io.StringIO()):
        apkg = generate_anki_from_text.generate(src, os.path.join(tmp, 'out'))
    return notes_in_apkg(apkg)


BASIC_2 = generate_anki_from_text.BASIC_MODEL_ID_BASE + 2
BASIC_3 = generate_anki_from_text.BASIC_MODEL_ID_BASE + 3
CLOZE_2 = generate_anki_from_text.CLOZE_MODEL_ID_BASE + 2


class TestGenerateAnkiFromText(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None
        self.tmp = tempfile.mkdtemp()

    def _notes(self, *lines, **kw):
        return generate_from_lines(lines, self.tmp, **kw)

    def test_basic_card(self):
        notes = self._notes('[D] Question :: Answer')
        self.assertEqual(notes, [('D', genanki.guid_for('Question', BASIC_2), BASIC_2,
                                  ['Question', 'Answer'])])

    def test_untagged_basic_cards_in_a_deck_share_the_widest_model(self):
        notes = self._notes('[D] [a] F1 :: F2 :: F3', '[D] [b] Q :: A')
        self.assertEqual(sorted(notes), [('D', 'a', BASIC_3, ['F1', 'F2', 'F3']),
                                         ('D', 'b', BASIC_3, ['Q', 'A', ''])])

    def test_cloze_card_gets_extra_field_and_cloze_model(self):
        notes = self._notes('[D] [c] {{c1::Cloze}} deletion')
        self.assertEqual(notes, [('D', 'c', CLOZE_2, ['{{c1::Cloze}} deletion', ''])])
        models = generate_anki_from_text.build_models(
            generate_anki_from_text.read_cards(os.path.join(self.tmp, 'cards.txt')))
        self.assertEqual(models[('deck', 'D', True)].model_type, genanki.Model.CLOZE)

    def test_cloze_with_extra(self):
        notes = self._notes('[D] [c] {{c1::Cloze}} :: Extra Info')
        self.assertEqual(notes[0][3], ['{{c1::Cloze}}', 'Extra Info'])

    def test_explicit_guid_kept_including_brackets(self):
        notes = self._notes('[D] [1234567890] Question :: Answer',
                            '[D] [Pr0gsJ]<qW] [mid:1:2] Q :: A')
        self.assertEqual(sorted(n[1] for n in notes), ['1234567890', 'Pr0gsJ]<qW'])

    def test_comments_and_blank_lines_skipped(self):
        notes = self._notes('# Comment', '', '  ', '[D] Valid :: Card')
        self.assertEqual([n[3] for n in notes], [['Valid', 'Card']])

    def test_single_field_basic_line_needs_a_mid_tag(self):
        notes = self._notes('[D] no separator here', '[D] [g] [mid:5:2] Q')
        self.assertEqual(notes, [('D', 'g', 5, ['Q', ''])])

    def test_unprefixed_line_lands_in_deck_named_after_file(self):
        notes = self._notes('Question :: Answer', name='my-topic.txt')
        self.assertEqual(notes[0][0], 'my-topic')

    def test_explicit_mid_is_one_model_across_decks(self):
        """Anki keeps notetypes per collection, so a mid used in two decks must
        describe one model. The narrower deck's note is padded to it."""
        notes = self._notes('[A] [g1] [mid:7:2] Q :: A', '[B] [g2] [mid:7:3] Q :: A :: C')
        self.assertEqual(sorted(notes), [('A', 'g1', 7, ['Q', 'A', '']),
                                         ('B', 'g2', 7, ['Q', 'A', 'C'])])

    def test_no_cards_raises(self):
        with self.assertRaises(ValueError):
            self._notes('# only a comment')


class TestDumpApkg(unittest.TestCase):
    @patch('dump_apkg.AnkiDeckUnpacker')
    @patch('dump_apkg.verify') # Mock verify to do nothing
    @patch('builtins.print') # Suppress print
    def test_generate_text_output(self, mock_print, mock_verify, mock_unpacker_cls):
        """Test correctly formatting text output from notes."""
        mock_unpacker = mock_unpacker_cls.return_value
        # Mock notes: [(fields_string, guid), ...]
        # Fields are separated by \x1f
        mock_unpacker.get_notes.return_value = [
            ("Question\x1fAnswer", "12345"),
            ("Front\x1fExtra\x1fBack", "67890") # Complex card
        ]
        
        # Mock opening file
        m = mock_open()
        with patch('builtins.open', m):
            dump_apkg.unpack_and_review("fake.apkg", "output_dir")
            
        # Check file write for cards.txt
        # The script writes multiple files (html and txt). We need to validte the calls.
        # dump_apkg opens: 
        # 1. html_path (w)
        # 2. txt_path (w)
        
        # We can iterate through mock calls to open() to find the one for cards.txt
        # effectively we just check if any write call contained the expected string
        
        handle = m()
        write_calls = handle.write.call_args_list
        all_written_content = "".join([call[0][0] for call in write_calls])
        
        self.assertIn("[12345] Question :: Answer", all_written_content)
        # For multi-field cards, logic is: all fields joined by ::
        self.assertIn("[67890] Front :: Extra :: Back", all_written_content)

    @patch('dump_apkg.AnkiDeckUnpacker')
    @patch('dump_apkg.verify')
    @patch('builtins.print')
    def test_generate_html_output(self, mock_print, mock_verify, mock_unpacker_cls):
        """Test HTML generation handles media paths."""
        mock_unpacker = mock_unpacker_cls.return_value
        mock_unpacker.get_notes.return_value = [
            ('Question <img src="image.jpg">', "111")
        ]
        
        m = mock_open()
        with patch('builtins.open', m):
            dump_apkg.unpack_and_review("fake.apkg", "output_dir")
            
        handle = m()
        write_calls = handle.write.call_args_list
        all_written_content = "".join([call[0][0] for call in write_calls])
        
        # Check for media path replacement in HTML
        self.assertIn('src="media/image.jpg"', all_written_content)
        self.assertIn('data-guid="111"', all_written_content)

if __name__ == '__main__':
    unittest.main()
