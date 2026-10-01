import contextlib
import io
import os
import sys
import tempfile
import unittest
import zipfile

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import genanki

import anki_unpacker
import card_format
import dump_apkg
import generate_anki_from_text
import verify_guids


class TestRoundTrip(unittest.TestCase):
    def test_generate_then_dump_preserves_every_note(self):
        basic_2 = generate_anki_from_text.BASIC_MODEL_ID_BASE + 2
        cloze_2 = generate_anki_from_text.CLOZE_MODEL_ID_BASE + 2
        lines = [
            '[Deck::One] [Pr0gsJ]<qW] What is JTAG? :: A debug port.',
            '[Deck::One] [c1] {{c1::Flash}} holds the bootloader.',
            '[Deck Two] [t1] [mid:1751847093121:2] What does mid preserve? :: The notetype id.',
            '[Deck Two] Derived guid card :: Answer',
        ]
        tmp = tempfile.mkdtemp()
        src = os.path.join(tmp, 'cards.txt')
        with open(src, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines) + '\n')
        review = os.path.join(tmp, 'review')
        with contextlib.redirect_stdout(io.StringIO()):
            apkg = generate_anki_from_text.generate(src, os.path.join(tmp, 'out'))
            dump_apkg.unpack_and_review(apkg, review)

        dumped = os.path.join(review, 'cards.txt')
        with open(dumped, encoding='utf-8') as f:
            self.assertTrue(f.read().endswith('\n'))
        by_guid = {c['guid']: (c['deck'], c['mid_id'], c['mid_count'], c['fields'])
                   for c in card_format.load_cards(dumped)}
        self.assertEqual(by_guid, {
            'Pr0gsJ]<qW': ('Deck::One', basic_2, 2, ['What is JTAG?', 'A debug port.']),
            'c1': ('Deck::One', cloze_2, 2, ['{{c1::Flash}} holds the bootloader.']),
            't1': ('Deck Two', 1751847093121, 2, ['What does mid preserve?', 'The notetype id.']),
            genanki.guid_for('Derived guid card', basic_2):
                ('Deck Two', basic_2, 2, ['Derived guid card', 'Answer']),
        })
        self.assertTrue(os.path.exists(os.path.join(review, 'index.html')))

        with contextlib.redirect_stdout(io.StringIO()):
            counts = verify_guids.verify(dumped, apkg)
        self.assertEqual(counts, {'matched': 4, 'missing': 0, 'unexpected': 0})


class TestGenerateText(unittest.TestCase):
    def test_file_ends_with_newline(self):
        """`cat cards.txt other.txt` must not glue the last card to the next file's first."""
        tmp = tempfile.mkdtemp()
        dump_apkg._generate_text([('Q\x1fA', 'g1', 'Deck', 7, 2),
                                  ('{{c1::X}}\x1f', 'g2', 'Deck', 8, 2)], tmp)
        with open(os.path.join(tmp, 'cards.txt'), encoding='utf-8') as f:
            text = f.read()
        self.assertEqual(text, '[Deck] [g1] [mid:7:2] Q :: A\n'
                               '[Deck] [g2] [mid:8:2] {{c1::X}}\n')


class TestExportMedia(unittest.TestCase):
    def test_meta_entry_is_not_media(self):
        """Modern exports carry a 2-byte protobuf `meta` entry beside the media
        map. It is package metadata, not a media file."""
        tmp = tempfile.mkdtemp()
        apkg = os.path.join(tmp, 'x.apkg')
        with zipfile.ZipFile(apkg, 'w') as z:
            z.writestr('meta', b'\x08\x03')
            z.writestr('collection.anki2', b'')
            z.writestr('media', '{"0": "pic.png"}')
            z.writestr('0', b'PNG')
        unpacker = anki_unpacker.AnkiDeckUnpacker(apkg)
        try:
            unpacker.unpack()
            media_dir = os.path.join(tmp, 'media')
            unpacker.export_media(media_dir)
        finally:
            unpacker.close()
        self.assertEqual(os.listdir(media_dir), ['pic.png'])


if __name__ == '__main__':
    unittest.main()
