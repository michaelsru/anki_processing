"""The one place that reads and writes the card-line text format.

    [DeckName] [GUID] [mid:ID:COUNT] Field1 :: Field2

Every bracket group is optional. dump_apkg.py writes this format,
generate_anki_from_text.py, check_overlap.py and verify_guids.py read it.
template_cards.txt documents it for humans. No genanki dependency.
"""

import re

FIELD_SEP = ' :: '

_GROUP_CLOSE_RE = re.compile(r'\](?=\s|$)')
_MID_RE = re.compile(r'^mid:(\d+)(?::(\d+))?$')


def split_bracket_groups(line, max_groups=3):
    """Consume up to `max_groups` leading [...] groups. Returns (groups, remainder).

    A group opens at a leading '[' and closes at the first ']' followed by
    whitespace or end of line. Bracket depth can't be used: base91 GUIDs may
    contain unbalanced '[' or ']' (e.g. [Pr0gsJ]<qW], [ab]]), but never
    whitespace.
    """
    groups = []
    rest = line.lstrip()

    while len(groups) < max_groups and rest.startswith('['):
        close = _GROUP_CLOSE_RE.search(rest, 1)
        if not close:
            break
        groups.append(rest[1:close.start()])
        rest = rest[close.start() + 1:].lstrip()

    return groups, rest


def _looks_like_deck(value):
    """A lone bracket is a deck name, not a GUID, when it reads like one.

    Deck names contain '::', spaces, or plain alphanumerics. genanki GUIDs are
    base91 and nearly always contain punctuation, so the ambiguity only bites
    on hand-written GUIDs like [15938472], which template_cards.txt rule 1
    tells authors to avoid by always writing the deck prefix.
    """
    return ('::' in value or ' ' in value
            or value.replace('_', '').replace('-', '').isalnum())


def parse_card_line(line):
    """Parse one card line into a dict, or return None for comments/blanks.

    Keys: raw, deck, guid, mid (the whole tag text), mid_id, mid_count,
    fields, front, back. Absent parts are None. A malformed mid tag keeps
    its text in `mid` but leaves mid_id and mid_count None, so the card is
    handled as untagged.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith('#'):
        return None

    groups, content = split_bracket_groups(stripped)

    deck = guid = mid = None
    for g in groups:
        if g.startswith('mid:'):
            mid = g
        elif deck is None and _looks_like_deck(g):
            deck = g
        elif guid is None:
            guid = g

    if not content:
        return None

    fields = [f.strip() for f in content.split(FIELD_SEP)]
    # A cloze deletion is {{c1::text}}, so the bare-'::' fallback is for basic cards only.
    if len(fields) == 1 and '{{c' not in content and '::' in content:
        fields = [f.strip() for f in content.split('::')]

    mid_id = mid_count = None
    m = _MID_RE.match(mid) if mid else None
    if m:
        mid_id = int(m.group(1))
        mid_count = int(m.group(2)) if m.group(2) else None

    return {
        'raw': stripped,
        'deck': deck,
        'guid': guid,
        'mid': mid,
        'mid_id': mid_id,
        'mid_count': mid_count,
        'fields': fields,
        'front': fields[0],
        'back': ' '.join(fields[1:]),
    }


def load_cards(path):
    """Parse a file into card dicts, each carrying its 1-based `lineno`."""
    cards = []
    with open(path, 'r', encoding='utf-8') as f:
        for lineno, line in enumerate(f, 1):
            card = parse_card_line(line)
            if card:
                card['lineno'] = lineno
                cards.append(card)
    return cards


def format_card_line(deck, guid, mid_id, field_count, fields):
    """Write one card line. The inverse of parse_card_line.

    Trailing empty fields are dropped; COUNT in the mid tag carries the
    model's width, and the generator pads back up to it. Newlines inside a
    field are flattened because the format is one card per line.
    """
    fields = [f.strip().replace('\n', ' ') for f in fields]
    while fields and not fields[-1]:
        fields.pop()
    return f"[{deck}] [{guid}] [mid:{mid_id}:{field_count}] {FIELD_SEP.join(fields)}"
