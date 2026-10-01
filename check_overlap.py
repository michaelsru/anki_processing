#!/usr/bin/env python3
"""Flag candidate Anki cards that duplicate cards already in your collection.

This is the *recall* stage of the card-authoring workflow: it uses cheap lexical
similarity with a deliberately loose threshold to surface near-misses, and leaves
the keep/drop/merge decision to a human (or to Claude via the anki-cards skill).

    python check_overlap.py candidates/i2c.txt
    python check_overlap.py candidates/i2c.txt --corpus anki_review_output/cards.txt
    python check_overlap.py candidates/i2c.txt --annotate
    python check_overlap.py candidates/i2c.txt --json

Card format is the one documented in template_cards.txt:

    [DeckName] [GUID] [mid:ID:COUNT] Field1 :: Field2

No genanki dependency — this runs without the venv.
"""

import argparse
import html
import json
import os
import re
import sys

DEFAULT_CORPUS = os.path.join("anki_review_output", "cards.txt")
DEFAULT_THRESHOLD = 0.45

# Question fronts are mostly interrogative boilerplate. Without this, every
# "What is the ...?" card looks like every other "What is the ...?" card.
STOPWORDS = {
    'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
    'what', 'which', 'who', 'whom', 'whose', 'when', 'where', 'why', 'how',
    'do', 'does', 'did', 'done', 'doing', 'can', 'could', 'will', 'would',
    'shall', 'should', 'may', 'might', 'must', 'of', 'in', 'on', 'at', 'to',
    'for', 'with', 'by', 'from', 'as', 'and', 'or', 'but', 'if', 'then',
    'than', 'that', 'this', 'these', 'those', 'it', 'its', 'you', 'your',
    'i', 'we', 'they', 'them', 'their', 'there', 'here', 'not', 'no',
    'has', 'have', 'had', 's', 't',
}

_CLOZE_RE = re.compile(r'\{\{c\d+::(.*?)\}\}', re.DOTALL)
_TAG_RE = re.compile(r'<[^>]+>')
_WORD_RE = re.compile(r'\w+')
_ANNOTATION_RE = re.compile(r'^#\s*OVERLAP\b')
_GROUP_CLOSE_RE = re.compile(r'\](?=\s|$)')


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

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


def parse_card_line(line):
    """Parse one card line into a dict, or return None for comments/blanks.

    Mirrors the tolerance of generate_anki_from_text.parse_deck_prefix: the
    deck prefix is optional, the GUID is optional, the mid tag is optional.
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

    fields = [f.strip() for f in content.split(' :: ')]
    if len(fields) == 1 and '{{c' not in content and '::' in content:
        fields = [f.strip() for f in content.split('::')]

    return {
        'raw': stripped,
        'deck': deck,
        'guid': guid,
        'mid': mid,
        'front': fields[0],
        'back': ' '.join(fields[1:]),
    }


def _looks_like_deck(value):
    """Same heuristic generate_anki_from_text.parse_deck_prefix uses."""
    return ('::' in value or ' ' in value
            or value.replace('_', '').replace('-', '').isalnum())


def load_cards(path):
    cards = []
    with open(path, 'r', encoding='utf-8') as f:
        for lineno, line in enumerate(f, 1):
            card = parse_card_line(line)
            if card:
                card['lineno'] = lineno
                cards.append(card)
    return cards


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def unwrap_cloze(text):
    """{{c1::answer::hint}} -> answer.

    The hint is scaffolding, not content — keeping it inflates similarity
    between unrelated cards that happen to share a hint. Applied repeatedly so
    nested deletions collapse rather than crash.
    """
    for _ in range(5):
        new = _CLOZE_RE.sub(lambda m: m.group(1).split('::')[0], text)
        if new == text:
            break
        text = new
    return text


def tokenize(text):
    """Normalize card text to a set of content words."""
    text = unwrap_cloze(text)
    text = _TAG_RE.sub(' ', text)      # <code>, <br>, <ul><li> match everything
    text = html.unescape(text)         # &mdash; &nbsp; &gt;
    words = _WORD_RE.findall(text.lower())
    # Digits are kept on purpose: "100 kHz" vs "400 kHz" is the whole difference
    # between two otherwise identical protocol cards.
    content = {w for w in words if w not in STOPWORDS}
    return content or set(words)


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def containment(a, b):
    """|a & b| / |a| — how much of `a` is already covered by `b`.

    Asymmetric on purpose: a short new card fully contained in a long existing
    one is a duplicate worth surfacing.
    """
    if not a:
        return 0.0
    return len(a & b) / len(a)


def jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def score_pair(cand_tokens, other_tokens):
    """Score a candidate against another card on front and back separately."""
    fs = containment(cand_tokens['front'], other_tokens['front'])
    bs = containment(cand_tokens['back'], other_tokens['back'])
    return {
        'front': round(fs, 3),
        'back': round(bs, 3),
        'front_jaccard': round(jaccard(cand_tokens['front'], other_tokens['front']), 3),
        'back_jaccard': round(jaccard(cand_tokens['back'], other_tokens['back']), 3),
    }


def is_flagged(scores, threshold):
    """A similar FRONT is the duplicate signal.

    A shared back with a different front is usually an intentional reverse card
    (see create_reverse_cards.py), so back similarity alone never flags.
    """
    if scores['front'] >= threshold:
        return True
    return scores['front'] >= threshold * 0.7 and scores['back'] >= threshold


def tokens_for(card):
    return {'front': tokenize(card['front']), 'back': tokenize(card['back'])}


def find_overlaps(candidates, corpus, threshold, top_n=3):
    """Compare each candidate against the corpus and against earlier candidates."""
    corpus_tokens = [tokens_for(c) for c in corpus]
    cand_tokens = [tokens_for(c) for c in candidates]

    results = []
    for i, cand in enumerate(candidates):
        matches = []

        for j, other in enumerate(corpus):
            scores = score_pair(cand_tokens[i], corpus_tokens[j])
            if is_flagged(scores, threshold):
                matches.append({'source': 'corpus', 'card': other, 'scores': scores})

        for j, other in enumerate(candidates):
            if i == j:
                continue
            scores = score_pair(cand_tokens[i], cand_tokens[j])
            if is_flagged(scores, threshold):
                matches.append({'source': 'candidate', 'card': other, 'scores': scores})

        matches.sort(key=lambda m: (m['scores']['front'], m['scores']['back']),
                     reverse=True)
        if matches:
            results.append({'candidate': cand, 'matches': matches[:top_n]})

    return results


def find_guid_collisions(candidates, corpus):
    corpus_guids = {c['guid'] for c in corpus if c['guid']}
    return [c for c in candidates if c['guid'] and c['guid'] in corpus_guids]


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def format_report(results, candidates, corpus, threshold):
    out = []
    out.append(f"Corpus: {len(corpus)} cards   Candidates: {len(candidates)} cards"
               f"   Threshold: {threshold}")
    out.append("")

    if not results:
        out.append("✅ No overlaps found. All candidates look new.")
        return "\n".join(out)

    for r in results:
        cand = r['candidate']
        out.append(f"── line {cand['lineno']}: {cand['front'][:100]}")
        for m in r['matches']:
            s = m['scores']
            tag = "existing" if m['source'] == 'corpus' else "candidate"
            loc = m['card'].get('guid') or f"line {m['card']['lineno']}"
            out.append(f"     front={s['front']:<5} back={s['back']:<5} "
                       f"[{tag}] [{m['card'].get('deck') or '?'}] [{loc}]")
            out.append(f"       {m['card']['front'][:100]}")
        out.append("")

    out.append(f"⚠️  {len(results)} of {len(candidates)} candidates flagged "
               f"— adjudicate before generating.")
    return "\n".join(out)


def annotate_file(path, results):
    """Rewrite the candidate file with '# OVERLAP ...' notes above flagged cards.

    Cards are left LIVE — the script surfaces, it does not decide. Prior
    annotations are stripped first so repeated runs don't accumulate.
    """
    by_lineno = {r['candidate']['lineno']: r for r in results}

    with open(path, 'r', encoding='utf-8') as f:
        original = f.readlines()

    out = []
    for lineno, line in enumerate(original, 1):
        if _ANNOTATION_RE.match(line.strip()):
            continue  # drop stale annotations
        r = by_lineno.get(lineno)
        if r:
            for m in r['matches']:
                s = m['scores']
                loc = m['card'].get('guid') or f"line {m['card']['lineno']}"
                out.append(f"# OVERLAP front={s['front']} back={s['back']} "
                           f"[{m['card'].get('deck') or '?'}] [{loc}] "
                           f"{m['card']['front'][:120]}\n")
        out.append(line)

    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(out)


def strip_annotations(path):
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    kept = [l for l in lines if not _ANNOTATION_RE.match(l.strip())]
    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(kept)
    return len(lines) - len(kept)


def comment_out_flagged(path, results):
    """--strict: comment the flagged cards themselves out."""
    by_lineno = {r['candidate']['lineno'] for r in results}
    with open(path, 'r', encoding='utf-8') as f:
        original = f.readlines()

    out = []
    for lineno, line in enumerate(original, 1):
        if _ANNOTATION_RE.match(line.strip()):
            continue
        if lineno in by_lineno:
            out.append(f"# OVERLAP-DROPPED {line.rstrip()}\n")
        else:
            out.append(line)

    with open(path, 'w', encoding='utf-8') as f:
        f.writelines(out)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Flag candidate Anki cards that overlap with your existing collection.')
    parser.add_argument('candidates', help='Candidate cards file (template_cards.txt format)')
    parser.add_argument('--corpus', default=DEFAULT_CORPUS,
                        help=f'Existing cards to compare against (default: {DEFAULT_CORPUS}). '
                             'Should be a dump of your FULL collection, not one deck.')
    parser.add_argument('--threshold', type=float, default=DEFAULT_THRESHOLD,
                        help=f'Similarity threshold, lower = more flagged (default: {DEFAULT_THRESHOLD})')
    parser.add_argument('--top', type=int, default=3, help='Max matches shown per candidate')
    parser.add_argument('--json', action='store_true', help='Emit JSON instead of a text report')
    parser.add_argument('--annotate', action='store_true',
                        help='Insert "# OVERLAP ..." notes above flagged cards, leaving them live')
    parser.add_argument('--strict', action='store_true',
                        help='Comment out flagged cards instead of just annotating them')
    parser.add_argument('--clean', action='store_true',
                        help='Remove all "# OVERLAP" annotations from the candidate file and exit')
    parser.add_argument('--allow-existing-guids', action='store_true',
                        help='Permit candidate GUIDs that already exist in the corpus. '
                             'Use when the file contains merged-in existing cards.')

    args = parser.parse_args()

    if not os.path.exists(args.candidates):
        print(f"❌ Candidate file not found: {args.candidates}")
        sys.exit(1)

    if args.clean:
        removed = strip_annotations(args.candidates)
        print(f"Removed {removed} annotation line(s) from {args.candidates}")
        return

    if not os.path.exists(args.corpus):
        print(f"❌ Corpus not found: {args.corpus}")
        print("   Export your FULL collection from Anki (File → Export → All Decks),")
        print("   then run: python dump_apkg.py <export>.apkg")
        sys.exit(1)

    candidates = load_cards(args.candidates)
    corpus = load_cards(args.corpus)

    if not candidates:
        print(f"❌ No cards found in {args.candidates}")
        sys.exit(1)

    collisions = find_guid_collisions(candidates, corpus)
    if collisions and not args.allow_existing_guids:
        print(f"❌ {len(collisions)} candidate GUID(s) already exist in the corpus.")
        print("   Generating would OVERWRITE those existing cards:")
        for c in collisions[:10]:
            print(f"     line {c['lineno']}: [{c['guid']}] {c['front'][:70]}")
        print("   Give the new cards fresh GUIDs, or pass --allow-existing-guids")
        print("   if these are existing cards you are deliberately editing.")
        sys.exit(2)

    results = find_overlaps(candidates, corpus, args.threshold, args.top)

    if args.json:
        payload = {
            'corpus_size': len(corpus),
            'candidate_size': len(candidates),
            'threshold': args.threshold,
            'flagged': [{
                'lineno': r['candidate']['lineno'],
                'front': r['candidate']['front'],
                'deck': r['candidate']['deck'],
                'guid': r['candidate']['guid'],
                'matches': [{
                    'source': m['source'],
                    'deck': m['card'].get('deck'),
                    'guid': m['card'].get('guid'),
                    'front': m['card']['front'],
                    'back': m['card']['back'],
                    'scores': m['scores'],
                } for m in r['matches']],
            } for r in results],
        }
        print(json.dumps(payload, indent=2))
    else:
        print(format_report(results, candidates, corpus, args.threshold))

    if args.strict:
        comment_out_flagged(args.candidates, results)
        print(f"\n📝 Commented out {len(results)} flagged card(s) in {args.candidates}")
    elif args.annotate:
        annotate_file(args.candidates, results)
        print(f"\n📝 Annotated {args.candidates} ({len(results)} flagged, cards left live)")


if __name__ == '__main__':
    main()
