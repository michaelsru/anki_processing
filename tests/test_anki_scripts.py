import unittest
from unittest.mock import MagicMock, patch, mock_open
import sys
import os

# Add parent directory to path to import scripts
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generate_anki_from_text
import dump_apkg

class TestGenerateAnkiFromText(unittest.TestCase):
    def setUp(self):
        self.maxDiff = None

    def test_create_deck_basic_card(self):
        """Test that a basic card line produces a Basic note with correct fields."""
        cards = ["Question :: Answer"]
        
        # We need to mock genanki to avoid actual deck creation issues and to check calls
        with patch('generate_anki_from_text.genanki') as mock_genanki:
            # Setup mock deck
            mock_deck = MagicMock()
            mock_deck.notes = []
            mock_genanki.Deck.return_value = mock_deck
            
            # Setup mock Note
            mock_note = MagicMock()
            mock_genanki.Note.return_value = mock_note

            deck = generate_anki_from_text.create_deck("Test Deck", cards)
            
            # Check Note creation
            # Check Note creation
            mock_genanki.Note.assert_called()
            call_args = mock_genanki.Note.call_args[1]
            fields = call_args['fields']
            model = call_args['model']
            
            self.assertEqual(fields, ['Question', 'Answer'])
            
            # Verify Model was created with 2 fields
            # We check if ANY call to genanki.Model had fields of length 2
            found_model = False
            for call in mock_genanki.Model.call_args_list:
                _, kwargs = call
                if len(kwargs.get('fields', [])) == 2:
                    found_model = True
                    break
            self.assertTrue(found_model, "Create Model with 2 fields not found")
            
            mock_deck.add_note.assert_called_with(mock_note)
            
    def test_create_deck_3_fields(self):
        """Test card with 3 fields."""
        cards = ["Field1 :: Field2 :: Field3"]
        
        with patch('generate_anki_from_text.genanki') as mock_genanki:
            mock_deck = MagicMock()
            mock_deck.notes = []
            mock_genanki.Deck.return_value = mock_deck
            mock_note = MagicMock()
            mock_genanki.Note.return_value = mock_note

            deck = generate_anki_from_text.create_deck("Test Deck", cards)
            
            mock_genanki.Note.assert_called()
            call_args = mock_genanki.Note.call_args[1]
            fields = call_args['fields']
            model = call_args['model']
            
            self.assertEqual(fields, ['Field1', 'Field2', 'Field3'])
            # Verify dynamic model created with 3 fields
            found_model = False
            for call in mock_genanki.Model.call_args_list:
                _, kwargs = call
                m_fields = kwargs.get('fields', [])
                if len(m_fields) == 3:
                     # Check names
                     if m_fields[0]['name'] == 'Field 1' and m_fields[2]['name'] == 'Field 3':
                        found_model = True
                        break
            self.assertTrue(found_model, "Create Model with 3 fields not found")

    def test_create_deck_cloze_card(self):
        """Test that a cloze card line produces a Cloze note."""
        cards = ["{{c1::Cloze}} deletion"]
        
        with patch('generate_anki_from_text.genanki') as mock_genanki:
            mock_deck = MagicMock()
            mock_deck.notes = []
            mock_genanki.Deck.return_value = mock_deck
            
            mock_note = MagicMock()
            mock_genanki.Note.return_value = mock_note

            deck = generate_anki_from_text.create_deck("Test Deck", cards)
            
            mock_genanki.Note.assert_called()
            call_args = mock_genanki.Note.call_args[1]
            fields = call_args['fields']
            model = call_args['model']
            
            self.assertEqual(fields, ['{{c1::Cloze}} deletion', ''])
            self.assertEqual(fields, ['{{c1::Cloze}} deletion', ''])
            # Verify Model creation
            found_model = False
            for call in mock_genanki.Model.call_args_list:
                _, kwargs = call
                if len(kwargs.get('fields', [])) == 2:
                    found_model = True
            self.assertTrue(found_model)

    def test_create_deck_cloze_with_extra(self):
        """Test cloze card with extra field."""
        cards = ["{{c1::Cloze}} :: Extra Info"]
        
        with patch('generate_anki_from_text.genanki') as mock_genanki:
            mock_deck = MagicMock()
            mock_deck.notes = []
            mock_genanki.Deck.return_value = mock_deck
            
            generate_anki_from_text.create_deck("Test Deck", cards)
            
            mock_genanki.Note.assert_called()
            call_args = mock_genanki.Note.call_args[1]
            fields = call_args['fields']
            model = call_args['model']
            
            self.assertEqual(fields, ['{{c1::Cloze}}', 'Extra Info'])
            self.assertEqual(fields, ['{{c1::Cloze}}', 'Extra Info'])
            found_model = False
            for call in mock_genanki.Model.call_args_list:
                _, kwargs = call
                if len(kwargs.get('fields', [])) == 2:
                    found_model = True
            self.assertTrue(found_model)

    def test_create_deck_with_guid(self):
        """Test parsing of explicit GUID."""
        guid = "1234567890"
        cards = [f"[{guid}] Question :: Answer"]
        
        with patch('generate_anki_from_text.genanki') as mock_genanki:
            mock_deck = MagicMock()
            mock_deck.notes = []
            mock_genanki.Deck.return_value = mock_deck
            
            generate_anki_from_text.create_deck("Test Deck", cards)
            
            mock_genanki.Note.assert_called()
            call_args = mock_genanki.Note.call_args[1]
            self.assertEqual(str(call_args['guid']), guid)
            self.assertEqual(call_args['fields'], ['Question', 'Answer'])

    def test_skip_comments_and_empty(self):
        """Test skipping comments and empty lines."""
        cards = ["# Comment", "", "  ", "Valid :: Card"]
        
        with patch('generate_anki_from_text.genanki') as mock_genanki:
            mock_deck = MagicMock()
            mock_deck.notes = []
            mock_genanki.Deck.return_value = mock_deck
            
            generate_anki_from_text.create_deck("Test Deck", cards)
            
            # Should only be called once for "Valid :: Card"
            self.assertEqual(mock_genanki.Note.call_count, 1)


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
