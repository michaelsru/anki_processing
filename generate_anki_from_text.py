#!/usr/bin/env python

import genanki
import random
import sys
import os
from datetime import datetime

# Define Models Globally
BASIC_MODEL_ID = 1607392319
BASIC_MODEL = genanki.Model(
    model_id=BASIC_MODEL_ID,
    name='Basic Model',
    fields=[{'name': 'Front'}, {'name': 'Back'}],
    templates=[{
        'name': 'Card 1',
        'qfmt': '{{Front}}',
        'afmt': '{{Front}}<hr>{{Back}}',
    }],
)

CLOZE_MODEL_ID = 9988776655  # Fixed ID for Cloze model
CLOZE_MODEL = genanki.Model(
    model_id=CLOZE_MODEL_ID,
    name='Cloze Model',
    fields=[{'name': 'Text'}, {'name': 'Extra'}],
    templates=[{
        'name': 'Cloze Card',
        'qfmt': '{{cloze:Text}}',
        'afmt': '{{cloze:Text}}<br><br>{{Extra}}',
    }],
    css="""
    .card {
        font-family: arial;
        font-size: 20px;
        text-align: left;
        color: black;
        background-color: white;
    }
    .cloze {
        font-weight: bold;
        color: lightblue;
    }
    """,
)

def create_deck(deck_name, cards):
    """Creates a single deck containing both Basic and Cloze cards."""
    deck = genanki.Deck(random.randrange(1 << 30, 1 << 31), deck_name)

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
                guid = genanki.guid_for(line, CLOZE_MODEL_ID)
            
            deck.add_note(genanki.Note(
                model=CLOZE_MODEL,
                fields=[line, ""],
                guid=guid
            ))
            
        elif "::" in line:
            # Basic Card
            front, back = line.split("::", 1)
            front = front.strip()
            back = back.strip()
            
            # If no GUID provided, generate one based on Front field
            if not guid:
                guid = genanki.guid_for(front, BASIC_MODEL_ID)
                
            deck.add_note(genanki.Note(
                model=BASIC_MODEL,
                fields=[front, back],
                guid=guid
            ))
        else:
            print(f"⚠️ Skipping invalid line: {line}")

    return deck

def parse_arguments():
    """Parse and validate command line arguments."""
    if len(sys.argv) < 2:
        print("Usage: python generate_anki_from_text.py <cards.txt>")
        sys.exit(1)
    
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

def export_deck(deck, filename):
    """Export a deck to an .apkg file and print confirmation."""
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
        
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_filename = f"{deck_name}_{date_str}.apkg"
    
    export_deck(deck, output_filename)

if __name__ == '__main__':
    main()
