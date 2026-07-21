#!/usr/bin/env python

import genanki
import random
import re
import sys
import os
from datetime import datetime
from verify_guids import verify

# Matches: [DeckName] [GUID] content  (GUID may contain ] so use non-greedy .+?)
_DECK_GUID_RE = re.compile(r'^\[([^\]]+)\]\s+\[(.+?)\]\s+(.*)')

# Matches: [GUID] remainder  (used inside create_deck after deck prefix is stripped)
_GUID_RE = re.compile(r'^\[(.+?)\]\s+(.*)')

def parse_deck_prefix(line):
    """Strip optional [DeckName] prefix from a line.
    Returns (deck_name_or_None, remaining_line_with_guid_intact).
    """
    m = _DECK_GUID_RE.match(line)
    if m:
        deck_name, guid, content = m.group(1), m.group(2), m.group(3)
        return deck_name, f"[{guid}] {content}"
    
    # Fallback: single bracket [DeckName] without a GUID
    m2 = re.match(r'^\[([^\]]+)\]\s+(.*)', line)
    if m2:
        val = m2.group(1)
        # Heuristic to distinguish DeckName from legacy GUID:
        # Deck names usually contain '::', spaces, or are plain words/alphanumeric.
        # GUIDs are either all digits (genanki) or random base91 with symbols.
        if '::' in val or ' ' in val or val.replace('_', '').replace('-', '').isalnum():
            return val, m2.group(2)

    return None, line

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

def create_basic_model(num_fields, model_id=None):
    """Creates a Basic model with num_fields."""
    if model_id is None:
        model_id = 1607392319 + num_fields
    fields = [{'name': f'Field {i+1}'} for i in range(num_fields)]

    back_fmt = '{{FrontSide}}<hr><div class="answer">'
    for i in range(1, num_fields):
        back_fmt += f'{{{{Field {i+1}}}}}<br>'
    back_fmt += '</div>'

    return genanki.Model(
        model_id=model_id,
        name=f'Basic Model ({num_fields} fields)',
        fields=fields,
        templates=[{'name': 'Card 1', 'qfmt': '{{Field 1}}', 'afmt': back_fmt}],
        css=SHARED_CSS
    )

def create_cloze_model(num_fields, model_id=None):
    """Creates a Cloze model with num_fields."""
    if model_id is None:
        model_id = 9988776655 + num_fields
    num_fields = max(2, num_fields)

    fields = [{'name': 'Text'}, {'name': 'Extra'}]
    for i in range(2, num_fields):
        fields.append({'name': f'Field {i+1}'})

    back_fmt = '{{cloze:Text}}<br><br>{{Extra}}'
    for i in range(2, num_fields):
        back_fmt += f'<br>{{{{Field {i+1}}}}}'

    return genanki.Model(
        model_id=model_id,
        name=f'Cloze Model ({num_fields} fields)',
        fields=fields,
        templates=[{'name': 'Cloze Card', 'qfmt': '{{cloze:Text}}', 'afmt': back_fmt}],
        css=SHARED_CSS,
        model_type=genanki.Model.CLOZE
    )

def create_deck(deck_name, cards):
    """Creates a single deck containing both Basic and Cloze cards.
    Preserves original model IDs from [mid:ID] tags when present.
    """
    deck = genanki.Deck(random.randrange(1 << 30, 1 << 31), deck_name)

    # --- Pass 1: parse every line, collect per-mid field counts ---
    # mid_meta: {mid: {'is_cloze': bool, 'max_fields': int}}
    parsed = []   # list of (guid, mid, is_cloze, fields)
    mid_meta = {}

    for line in cards:
        if line.strip().startswith('#') or not line.strip():
            continue
        line = line.strip()

        # Extract [GUID] — use non-greedy regex so ] inside GUIDs doesn't confuse the match
        guid = None
        m = _GUID_RE.match(line)
        if m:
            guid = m.group(1)
            line = m.group(2).strip()

        # Extract optional [mid:ID:COUNT]  — COUNT is the model's declared field count
        mid = None
        field_count = None
        if line.startswith('[mid:') and ']' in line:
            end = line.index(']')
            parts = line[5:end].split(':', 1)
            try:
                mid = int(parts[0])
                if len(parts) > 1:
                    field_count = int(parts[1])
            except ValueError:
                pass
            line = line[end + 1:].strip()

        if not line:
            continue

        is_cloze = '{{c' in line
        if is_cloze or '::' in line:
            fields = [f.strip() for f in line.split(' :: ')]
            # Fallback bare split only for basic cards — never split inside {{c1::text}}
            if not is_cloze and len(fields) == 1 and '::' in line:
                fields = [f.strip() for f in line.split('::')]
        else:
            print(f"⚠️ Skipping invalid line: {line}")
            continue

        key = (mid, is_cloze)
        # field_count from tag is authoritative; fall back to observed field count
        fc = field_count or len(fields)
        if key not in mid_meta:
            mid_meta[key] = {'is_cloze': is_cloze, 'max_fields': fc}
        else:
            mid_meta[key]['max_fields'] = max(mid_meta[key]['max_fields'], fc)

        parsed.append((guid, mid, is_cloze, fields))

    # --- Build one model per (mid, is_cloze) pair ---
    models = {}
    for (mid, is_cloze), meta in mid_meta.items():
        if is_cloze:
            models[(mid, is_cloze)] = create_cloze_model(meta['max_fields'], model_id=mid)
        else:
            models[(mid, is_cloze)] = create_basic_model(meta['max_fields'], model_id=mid)

    # --- Pass 2: create notes ---
    for guid, mid, is_cloze, fields in parsed:
        key = (mid, is_cloze)
        model = models[key]
        max_fields = mid_meta[key]['max_fields']

        while len(fields) < max_fields:
            fields.append('')

        if not guid:
            guid = genanki.guid_for(fields[0], model.model_id)

        deck.add_note(genanki.Note(model=model, fields=fields, guid=guid))

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
    fallback_deck = get_deck_name(input_path)

    # Group lines by deck name parsed from [DeckName] prefix.
    # Lines without a prefix fall back to the filename-derived deck name.
    deck_lines: dict[str, list[str]] = {}
    for line in lines:
        if line.startswith('#'):
            continue
        deck_name, stripped = parse_deck_prefix(line)
        key = deck_name or fallback_deck
        deck_lines.setdefault(key, []).append(stripped)

    if not deck_lines:
        print("❌ No valid cards found.")
        sys.exit(1)

    output_dir = "generated_decks"
    os.makedirs(output_dir, exist_ok=True)
    archive_all_decks(output_dir)

    decks = []
    for deck_name, card_lines in deck_lines.items():
        deck = create_deck(deck_name, card_lines)
        if deck.notes:
            decks.append(deck)
            print(f"  {deck_name}: {len(deck.notes)} cards")

    if not decks:
        print("❌ No valid cards found.")
        sys.exit(1)

    date_str = datetime.now().strftime("%Y-%m-%d")
    safe_name = re.sub(r'[^\w]', '_', fallback_deck)
    output_filename = os.path.join(output_dir, f"{safe_name}_{date_str}.apkg")

    genanki.Package(decks).write_to_file(output_filename)
    total = sum(len(d.notes) for d in decks)
    print(f"✅ Exported {total} cards across {len(decks)} deck(s) → {output_filename}")

if __name__ == '__main__':
    main()
