import os
import sys
import tempfile
import unittest
import zipfile

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anki_unpacker
import dump_apkg


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
