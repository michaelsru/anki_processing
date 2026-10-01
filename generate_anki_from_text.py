#!/usr/bin/env python

import genanki
import random
import re
import sys
import os
from datetime import datetime

from card_format import FIELD_SEP, load_cards

# Untagged cards get a model id derived from their width, so the id itself
# says how many fields the model has. template_cards.txt rule 3 documents
# both bases.
BASIC_MODEL_ID_BASE = 1607392319
CLOZE_MODEL_ID_BASE = 9988776655

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
        model_id = BASIC_MODEL_ID_BASE + num_fields
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
        model_id = CLOZE_MODEL_ID_BASE + num_fields
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

def is_cloze(card):
    """template_cards.txt rule 4: '{{c' anywhere in the content makes a cloze card."""
    return '{{c' in FIELD_SEP.join(card['fields'])

def model_key(card):
    """Which model a card belongs to.

    Anki stores notetypes per collection, so a tagged mid names one model for
    the whole file. Untagged cards share one model per deck and type, sized to
    the deck's widest line, as template_cards.txt rule 3 documents.
    """
    if card['mid_id'] is not None:
        return ('mid', card['mid_id'])
    return ('deck', card['deck'], is_cloze(card))

def build_models(cards, source):
    """Build every model the cards need, keyed by model_key.

    Raises ValueError naming `source` and every offending line when the tags
    contradict each other, because genanki either fails later with no line
    number or silently keeps one of two models that share an id.
    """
    groups = {}
    for card in cards:
        groups.setdefault(model_key(card), []).append(card)

    problems = []
    def problem(card, text):
        problems.append((card['lineno'], f"{source}:{card['lineno']}: {text}"))

    specs = {}
    for key, group in groups.items():
        for c in group:
            if c['mid_count'] is not None and len(c['fields']) > c['mid_count']:
                problem(c, f"{len(c['fields'])} fields but the mid tag declares {c['mid_count']}; "
                           "bump the count on this line")
        types = {is_cloze(c) for c in group}
        if len(types) > 1:
            for c in group:
                kind = 'cloze' if is_cloze(c) else 'basic'
                problem(c, f"[mid:{key[1]}] is used by both cloze and basic lines (this one is {kind})")
            continue
        cloze = types.pop()
        width = max(len(c['fields']) for c in group)
        width = max([width] + [c['mid_count'] for c in group if c['mid_count']])
        if cloze:
            width = max(2, width)
        if key[0] == 'mid':
            model_id = key[1]
        else:
            model_id = (CLOZE_MODEL_ID_BASE if cloze else BASIC_MODEL_ID_BASE) + width
        specs[key] = (model_id, cloze, width)

    by_id = {}
    for key, spec in specs.items():
        by_id.setdefault(spec[0], []).append(key)
    for model_id, keys in by_id.items():
        if len({specs[k][1:] for k in keys}) > 1:
            for k in keys:
                for c in groups[k]:
                    problem(c, f"model id {model_id} would need {specs[k][2]} "
                               f"{'cloze' if specs[k][1] else 'basic'} fields here but a different "
                               "shape elsewhere; untagged cards derive their id from their width")

    if problems:
        raise ValueError("\n".join(text for _, text in sorted(problems)))

    models = {}
    for key, (model_id, cloze, width) in specs.items():
        make = create_cloze_model if cloze else create_basic_model
        models[key] = make(width, model_id=model_id)
    return models

def create_deck(deck_name, cards, models):
    """Create one deck from card dicts whose models build_models already made."""
    deck = genanki.Deck(random.randrange(1 << 30, 1 << 31), deck_name)

    for card in cards:
        model = models[model_key(card)]
        fields = card['fields'] + [''] * (len(model.fields) - len(card['fields']))
        guid = card['guid'] or genanki.guid_for(fields[0], model.model_id)
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

def read_cards(input_path):
    """Load the file's cards, with the filename as the deck for unprefixed lines.

    A basic line with a single field and no mid tag is almost always a missing
    ' :: ', so it is skipped with a warning. With a mid tag the width is
    declared, which is how dump_apkg writes a note whose back is empty.
    """
    fallback_deck = get_deck_name(input_path)
    cards = []
    for card in load_cards(input_path):
        if len(card['fields']) == 1 and not is_cloze(card) and card['mid_count'] is None:
            print(f"⚠️ Skipping invalid line: {card['raw']}")
            continue
        card['deck'] = card['deck'] or fallback_deck
        cards.append(card)
    return cards

def generate(input_path, output_dir="generated_decks"):
    """Build one package holding every deck in the file. Returns its path."""
    cards = read_cards(input_path)
    if not cards:
        raise ValueError("No valid cards found.")

    models = build_models(cards, input_path)

    by_deck = {}
    for card in cards:
        by_deck.setdefault(card['deck'], []).append(card)
    decks = [create_deck(name, deck_cards, models) for name, deck_cards in by_deck.items()]
    for deck in decks:
        print(f"  {deck.name}: {len(deck.notes)} cards")

    os.makedirs(output_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    safe_name = re.sub(r'[^\w]', '_', get_deck_name(input_path))
    output_filename = os.path.join(output_dir, f"{safe_name}_{date_str}.apkg")

    # Write beside the final name first so a failure here leaves the previous
    # package where it was. archive_all_decks moves *.apkg only.
    partial = output_filename + ".part"
    genanki.Package(decks).write_to_file(partial)
    archive_all_decks(output_dir)
    os.replace(partial, output_filename)
    total = sum(len(d.notes) for d in decks)
    print(f"✅ Exported {total} cards across {len(decks)} deck(s) → {output_filename}")
    return output_filename

def main():
    input_path = parse_arguments()
    try:
        generate(input_path)
    except ValueError as e:
        print(f"❌ {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
