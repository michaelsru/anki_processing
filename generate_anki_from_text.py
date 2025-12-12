#!/usr/bin/env python

import genanki
import random
import sys
import os
from datetime import datetime
from verify_guids import verify

# Define Models Globally
SHARED_CSS = """
.card {
    font-family: arial;
    font-size: 20px;
    text-align: left;
    color: black;
    background-color: white;
    line-height: 1.5;
    padding: 20px;
}
.cloze {
    font-weight: bold;
    color: blue;
}
.answer {
    color: blue;
}
"""

def create_basic_model(num_fields):
    """Creates a Basic model with num_fields."""
    fields = [{'name': f'Field {i+1}'} for i in range(num_fields)]
    
    # Build Back template: Field 2 <br> Field 3 ...
    back_fmt = '{{FrontSide}}<hr><div class="answer">'
    for i in range(1, num_fields):
        back_fmt += f'{{{{Field {i+1}}}}}<br>'
    back_fmt += '</div>'
    
    return genanki.Model(
        model_id=1607392319 + num_fields, # Ensure unique ID per field count
        name=f'Basic Model ({num_fields} fields)',
        fields=fields,
        templates=[{
            'name': 'Card 1',
            'qfmt': '{{Field 1}}',
            'afmt': back_fmt,
        }],
        css=SHARED_CSS
    )

def create_cloze_model(num_fields):
    """Creates a Cloze model with num_fields."""
    # Ensure at least 2 fields (Text, Extra)
    num_fields = max(2, num_fields)
    
    fields = [{'name': 'Text'}, {'name': 'Extra'}]
    for i in range(2, num_fields):
        fields.append({'name': f'Field {i+1}'})
        
    # Build Back template: Extra <br> Field 3 ...
    back_fmt = '{{cloze:Text}}<br><br>{{Extra}}'
    for i in range(2, num_fields):
        back_fmt += f'<br>{{{{Field {i+1}}}}}'
        
    return genanki.Model(
        model_id=9988776655 + num_fields,
        name=f'Cloze Model ({num_fields} fields)',
        fields=fields,
        templates=[{
            'name': 'Cloze Card',
            'qfmt': '{{cloze:Text}}',
            'afmt': back_fmt,
        }],
        css=SHARED_CSS,
        model_type=genanki.Model.CLOZE
    )

def analyze_field_counts(cards):
    """Scans all cards to find max field counts for Basic and Cloze types."""
    max_basic = 2
    max_cloze = 2
    
    for line in cards:
        if line.strip().startswith('#') or not line.strip():
            continue
            
        line = line.strip()
        if line.startswith('[') and '] ' in line:
            _, _, line = line.partition('] ')
            line = line.strip()
            
        fields = line.split(" :: ")
        # Fallback split check
        if len(fields) == 1 and "::" in line and not "{{c" in line:
             fields = line.split("::")
             
        count = len(fields)
        
        if '{{c' in line:
            max_cloze = max(max_cloze, count)
        else:
            max_basic = max(max_basic, count)
            
    return max_basic, max_cloze

def create_deck(deck_name, cards):
    """Creates a single deck containing both Basic and Cloze cards."""
    deck = genanki.Deck(random.randrange(1 << 30, 1 << 31), deck_name)
    
    # 1. Analyze cards to determine model requirements
    num_basic, num_cloze = analyze_field_counts(cards)
    
    basic_model = create_basic_model(num_basic)
    cloze_model = create_cloze_model(num_cloze)

    for line in cards:
        # ignore comments
        if line.strip().startswith('#'):
            continue
        
        line = line.strip()
        if not line:
            continue

        # Check for [GUID] at the start
        guid = None
        if line.startswith('[') and '] ' in line:
            part1, sep, part2 = line.partition('] ')
            guid = part1[1:]
            line = part2.strip()

        # Determine Card Type
        if '{{c' in line:
            # Cloze Card
            # If no GUID provided, generate one based on content
            if not guid:
                guid = genanki.guid_for(line, cloze_model.model_id)
            
            fields = line.split(" :: ")
            fields = [f.strip() for f in fields]
            
            # Pad fields
            while len(fields) < num_cloze:
                fields.append("")
                
            deck.add_note(genanki.Note(
                model=cloze_model,
                fields=fields,
                guid=guid
            ))
            
        elif "::" in line:
            # Basic Card
            # Basic/Generic Card
            fields = line.split(" :: ")
            # Fallback for Basic cards with no spaces around :: if strict split fails to find multiple fields
            if len(fields) == 1 and "::" in line:
                 fields = line.split("::")

            fields = [f.strip() for f in fields]
            
            # Pad fields
            while len(fields) < num_basic:
                fields.append("")
            
            # If no GUID provided, generate one based on Front field
            if not guid:
                guid = genanki.guid_for(fields[0], basic_model.model_id)
                
            deck.add_note(genanki.Note(
                model=basic_model,
                fields=fields,
                guid=guid
            ))
        else:
            print(f"⚠️ Skipping invalid line: {line}")

    return deck

def parse_arguments():
    """Parse and validate command line arguments."""
    if len(sys.argv) < 2:
        default_path = os.path.join("anki_review_output", "cards.txt")
        print(f"ℹ️  No input file specified. Defaulting to: {default_path}")
        input_path = default_path
    else:
        input_path = sys.argv[1]
    
    if not os.path.exists(input_path):
        print(f"❌ File not found: {input_path}")
        sys.exit(1)
    
    return input_path

def read_input_file(input_path):
    """Read and return non-empty lines from the input file."""
    with open(input_path, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def get_deck_name(input_path):
    """Extract deck name from file path (filename without extension)."""
    return os.path.splitext(os.path.basename(input_path))[0]

def archive_all_decks(output_dir):
    """Move all existing .apkg files in output_dir to the archive folder."""
    if not os.path.exists(output_dir):
        return

    archive_dir = os.path.join(output_dir, "archive")
    if not os.path.exists(archive_dir):
        os.makedirs(archive_dir)

    for filename in os.listdir(output_dir):
        filepath = os.path.join(output_dir, filename)
        
        # Skip directories and non-apkg files
        if os.path.isdir(filepath) or not filename.endswith(".apkg"):
            continue

        target_path = os.path.join(archive_dir, filename)
        
        # If file exists in archive, append counter
        if os.path.exists(target_path):
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(os.path.join(archive_dir, f"{base}_{counter}{ext}")):
                counter += 1
            target_path = os.path.join(archive_dir, f"{base}_{counter}{ext}")

        os.rename(filepath, target_path)
        print(f"📦 Archived: {filename} -> {target_path}")

def export_deck(deck, filename):
    """Export a deck to an .apkg file and print confirmation."""
    # Archive all existing decks in the output directory before saving the new one
    output_dir = os.path.dirname(filename)
    archive_all_decks(output_dir)
    
    genanki.Package(deck).write_to_file(filename)
    print(f"✅ Deck exported to {filename} ({len(deck.notes)} cards)")
    return filename

def main():
    """Main entry point that orchestrates the deck generation process."""
    input_path = parse_arguments()
    lines = read_input_file(input_path)
    deck_name = get_deck_name(input_path)
    
    deck = create_deck(deck_name, lines)
    
    if len(deck.notes) == 0:
        print("❌ No valid cards found.")
        sys.exit(1)
        
    output_dir = "generated_decks"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_filename = os.path.join(output_dir, f"{deck_name}_{date_str}.apkg")
    
    export_deck(deck, output_filename)

    # Verify GUIDs
    print("\n--- Verifying GUIDs ---")
    try:
        verify(input_path, output_filename)
    except ImportError:
        print("Warning: verify_guids module not found. Skipping verification.")
    except Exception as e:
        print(f"Warning: Verification failed: {e}")

if __name__ == '__main__':
    main()
