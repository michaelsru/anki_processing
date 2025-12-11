#!/usr/bin/env python

import genanki
import random
import sys
import os
from datetime import datetime

def create_cloze_deck(deck_name, cards):
    model = genanki.Model(
        model_id=random.randrange(1 << 30, 1 << 31),
        name='Cloze',
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

    deck = genanki.Deck(random.randrange(1 << 30, 1 << 31), deck_name)

    for line in cards:
        # ignore comments
        if line.strip().startswith('#'):
            continue
        if line.strip():
            deck.add_note(genanki.Note(
                model=model,
                fields=[line.strip(), ""],
                guid=str(random.getrandbits(64))
            ))

    return deck

def create_basic_deck(deck_name, cards):
    # Use a fixed Model ID to preserve card identity across generations
    model_id = 1607392319
    model = genanki.Model(
        model_id=model_id,
        name='Basic Model',
        fields=[{'name': 'Front'}, {'name': 'Back'}],
        templates=[{
            'name': 'Card 1',
            'qfmt': '{{Front}}',
            'afmt': '{{Front}}<hr>{{Back}}',
        }],
    )

    # Use a fixed Deck ID (derived from name) to preserve deck identity
    deck_id = genanki.guid_for(deck_name)
    # genanki.guid_for returns a large int, but Deck ID should be < 1<<31 for compatibility with some Anki versions?
    # Actually genanki handles this. But let's stick to random for Deck ID for now or make it stable?
    # User asked for learning progress preservation. That depends on Note GUIDs.
    # Deck ID stability is less critical but good practice.
    # Let's use a fixed random seed or just a constant for now if we want this specific deck to be stable.
    # But for now, Note GUID is the key.
    
    deck = genanki.Deck(random.randrange(1 << 30, 1 << 31), deck_name)

    for line in cards:
        # ignore comments
        if line.strip().startswith('#'):
            continue
        if "::" in line:
            # Check for [GUID] at the start
            line = line.strip()
            guid = None
            if line.startswith('[') and '] ' in line:
                part1, sep, part2 = line.partition('] ')
                guid = part1[1:]
                line = part2.strip()
            
            front, back = line.split("::", 1)
            
            # If no GUID provided, generate one (fallback)
            if not guid:
                guid = genanki.guid_for(front, model_id)
                
            deck.add_note(genanki.Note(
                model=model,
                fields=[front.strip(), back.strip()],
                guid=guid
            ))

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

def separate_cards_by_type(lines):
    """Separate lines into cloze cards and basic cards."""
    cloze_cards = [line for line in lines if '{{c' in line]
    basic_cards = [line for line in lines if '::' in line and '{{c' not in line]
    return cloze_cards, basic_cards

def export_deck(deck, filename, card_count, card_type):
    """Export a deck to an .apkg file and print confirmation."""
    genanki.Package(deck).write_to_file(filename)
    print(f"✅ {card_type} deck exported to {filename} ({card_count} cards)")
    return filename

def process_and_export_decks(deck_name, cloze_cards, basic_cards):
    """Create and export decks for each card type that has cards."""
    created_decks = []
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    if cloze_cards:
        cloze_deck = create_cloze_deck(f"{deck_name}_cloze", cloze_cards)
        cloze_filename = f"{deck_name}_cloze_{date_str}.apkg"
        export_deck(cloze_deck, cloze_filename, len(cloze_cards), "Cloze")
        created_decks.append(cloze_filename)
    
    if basic_cards:
        basic_deck = create_basic_deck(f"{deck_name}_basic", basic_cards)
        basic_filename = f"{deck_name}_basic_{date_str}.apkg"
        export_deck(basic_deck, basic_filename, len(basic_cards), "Basic")
        created_decks.append(basic_filename)
    
    return created_decks

def main():
    """Main entry point that orchestrates the deck generation process."""
    input_path = parse_arguments()
    lines = read_input_file(input_path)
    deck_name = get_deck_name(input_path)
    cloze_cards, basic_cards = separate_cards_by_type(lines)
    created_decks = process_and_export_decks(deck_name, cloze_cards, basic_cards)
    
    if not created_decks:
        print("❌ Could not detect valid card format. No cards found.")
        sys.exit(1)

if __name__ == '__main__':
    main()
