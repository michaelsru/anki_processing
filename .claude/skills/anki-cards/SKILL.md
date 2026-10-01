---
name: anki-cards
description: Turn raw notes, prose, datasheet excerpts, or a list of topics into Anki cards that don't duplicate the existing collection. Use whenever the user has source material to convert into cards, wants to add cards on a topic, or asks to check new cards against what they already have.
---

# Authoring Anki cards from raw material

The source material is usually **not** distilled into discrete points. Distilling
it is your job. Deduplicating it against thousands of existing cards is
`check_overlap.py`'s job — don't try to eyeball the corpus yourself.

## Step 1 — Confirm the corpus is complete

Overlap checking is only as good as the corpus at `anki_review_output/cards.txt`.
Two traps:

- `dump_apkg.py` runs `shutil.rmtree()` on its output directory, so that file
  holds **only the notes from the last `.apkg` dumped**.
- If that was a single topic deck, dedup silently checks against a fraction of
  the collection and will look like it is working.

Before distilling, check the corpus size and ask the user to confirm it covers
their whole collection. If it doesn't, tell them:

> In Anki: **File → Export → All Decks**, include scheduling, save as `.apkg`.
> Then run `python dump_apkg.py <export>.apkg`.

Ignore the `--- Verifying GUIDs ---` section of that output. `verify_guids.py`
reads the first bracket as the GUID, so on deck-prefixed files it compares deck
names against real GUIDs and reports everything as mismatched. It's a known bug,
not a problem with the deck.

## Step 2 — Read the format

`template_cards.txt` at the repo root is the format contract and a runnable
example. Read it before writing any card. The rules that actually break
generation:

- **Every line gets a `[DeckName]` prefix.** A bare `[GUID] Front :: Back` line
  creates a *deck* named after the GUID.
- **`{{c` anywhere in a line makes it a cloze card.** No other switch exists.
- **A spaced ` :: ` is a field separator, always** — including inside a cloze
  deletion. Write `{{c1::answer}}` with no spaces around the inner `::`.
- Copy GUIDs from a dump byte-for-byte. Never invent one for an existing card.

## Step 3 — Distill into candidates

Write to `candidates/<topic>.txt`. Do not append to the main cards file yet.

**Assign an explicit GUID to every new card**, `[topic-NNNN]` style
(`[i2c-0001]`, `[rtos-0014]`). This is not optional. Without one, the GUID is
derived from `guid_for(front_text, model_id)`, and the untagged-basic model id
is `1607392319 + max_fields` for the whole group — so adding a single
three-field card later shifts `max_fields`, shifts the model id, and re-derives
the GUID of **every GUID-less card in that group**, orphaning cards that never
changed. Explicit GUIDs are the only protection.

Allocate the counter by scanning existing GUIDs with that prefix in the corpus
so you don't collide.

### Atomize first — one recallable idea per card

This rule governs the two that follow. Everything below tells you to *add*
qualifiers, hedges and scope tags; this tells you what to do instead when adding
them would put two ideas on one card. Precision is never bought with length.

**The recite test.** Count the distinct things you must produce from memory to
score the card correct. More than one and it is not a card, it is a paragraph
with a question mark. Real example from a Wi-Fi deck — this back field requires
five separate recollections and should have been three cards:

> *What is `hostapd` responsible for?* :: It is the userspace daemon that manages
> and configures access-point operation — it owns the AP configuration, admits
> associations, and runs the authenticator side of the key handshake.
> Timing-sensitive beacon transmission is normally performed lower down, by the
> driver, firmware or hardware.

**Applying a caveat without inflating the answer.** When review shows a card is
imprecise, there are exactly three legal fixes, in order of preference:

1. **Narrow the question** so the caveat becomes unnecessary. "What does a scan
   result report per network?" → "…per entry?" fixes the error and adds nothing.
2. **Split the caveat into its own card.** "Why is MAC work pushed below the host
   driver?" and "How do FullMAC and SoftMAC divide the MAC?" are two cards.
3. **Drop the claim** if it does not deserve a card of its own.

Appending a clause to the back field is not on that list. It is the default
failure mode: correcting eleven cards for precision once grew their answers 68%
and split none of them.

**One legitimate long answer: ordered sequences.** A layer trace or a boot order
is a single idea that unavoidably costs many words. Do not truncate or split it
— make it a cloze with one deletion per step, so each review recalls one item.

**The tripwire.** You cannot eyeball this; that 68% happened while following
"keep answers short." Before the overlap check, run:

```bash
grep -v '^#' candidates/<topic>.txt | grep ' :: ' | \
  awk -F' :: ' '{ n=split($2,w," "); if (n>25) print n"w  "$0 }'
```

Every line it prints is guilty until argued innocent. An ordered-sequence cloze
is the usual acquittal; a back field with a `;` or an `—` joining two clauses
almost never is.

### Author everything as cloze

Write every new card as a cloze note, including ones that hold a single fact and
have no obvious deletion. The note *kind* is the one property you cannot change
later: Anki matches an imported note to an existing one by GUID, and if the kinds
differ the import aborts with

> Cloze note types cannot be merged with regular note types.

So a card that ships as Basic is frozen as Basic for as long as you want to keep
its review history. Starting it as cloze costs nothing — a lone `{{c1::...}}`
produces exactly one card, the same as a Basic front/back — and leaves you free
to add `{{c2::}}`, `{{c3::}}` later, when the atomize rule says it should have
been three cards all along.

Two shapes, both already present in the collection:

```
An SSID is {{c1::the human-readable name of a Wi-Fi network}}.
How do you add a cloze deletion in Anki?<br>{{c1::⌘⇧C}}
```

Prefer the declarative first form; fall back to `Question?<br>{{c1::answer}}`
when the fact only reads as a question. Field 2 is still the Extra, and every
rule above still applies to it.

**Converting an already-imported Basic card to cloze requires a NEW GUID.**
Reusing the GUID does not reset that card, it fails the entire import. Allocate
the next free `[topic-NNNN]` and expect the old note to survive in the collection
as a duplicate you must delete by hand — which is the whole reason to start as
cloze.

### Generalize — no company-specific cards

**Every card must teach a transferable concept.** No employer name, no internal
project names, no internal paths, no "our module" / "our setup" framing — in the
question or the answer.

Ask what general principle the specific detail is an instance of, and make that
the card:

| Don't | Do |
|---|---|
| How does Tesla establish cellular connectivity through QCMAP? | What is the role of a connectivity manager such as QCMAP in a cellular Linux system? |
| Which file configures QCMAP on our module? | What kinds of networking configuration might a mobile-AP manager control? |

Note the second pattern: when the specific answer is an internal path or
filename, generalize to the *category* of thing rather than swapping in a
different specific.

Naming a widely-documented third-party technology (QCMAP, udev, fastboot, UBI)
is fine and usually necessary for the card to mean anything. What goes is the
employer, the internal project, and the "ours" framing. Source material will be
full of employer-specific detail; that is expected, and extracting the concept
it demonstrates is your job during distillation. A card tied to one employer's
setup stops being useful the moment that context changes.

### Label scope — mark platform-specific claims

Generalizing is not the same as knowing how far a claim reaches. Vendor and
training material describes how *one* platform behaves, and those descriptions
become cards that read as general architecture — an implementation detail stated
as a universal fact teaches a wrong mental model, which is harder to unlearn than
a gap.

Mark the scope by the cheapest means that fits, and obey the atomize rule above:
if the hedge will not fit in the front or in a short clause, the fix is a second
card, not a longer answer. For every technical claim, decide where it comes from — the standard, the
vendor's architecture, or the particular build in front of you — and say so on
the card:

| Scope | How to mark it |
|---|---|
| Universal / standardised | State it plainly. |
| Vendor architecture, varies by platform | Hedge in-sentence: "on many Qualcomm Linux platforms…", "commonly", "normally" |
| One firmware, toolchain, or filesystem | Explicit tag: `<i>[platform-specific]</i>`, `<i>[this MCFG implementation]</i>`, `<i>[vendor-specific]</i>` |

Put the tag on the **front**, so the scope is known while answering.

Two failure modes that keep recurring:

- **Absolutes the standard doesn't guarantee.** "Each APN requires its own
  datacall" is wrong — write "two different APNs normally require separate
  sessions." The same trap covers partial lists framed as complete ("the two
  roles"), "every"/"all" quantifiers, and approximations written as identities
  ("a BSSID is effectively one AP").
- **Build time collapsed into runtime.** "Once a carrier matches, the XML tree is
  expanded and built into the MBN" implies compilation happens on the device. Keep
  build-time (source → compiled artifact) and runtime (identifiers → select an
  already-built artifact) on separate cards.

A fact about the employer's project rather than the platform is not a
scope-labelling problem — it fails the generalization rule and is not a card.

### Card quality

- The front must be answerable without the surrounding source paragraph.
  "What is its maximum speed?" is useless; "What is I2C fast-mode's maximum
  clock speed?" is a card.
- List answers (3+ items) make bad recall cards. Split them, or use cloze with
  one deletion per item.
- A cloze's Extra field is part of the card. Do not use it to smuggle back the
  detail you split out — if it restates other cards, delete it.
- Prefer two plain cards to one card that contrasts two things, unless the
  contrast *is* the idea. "What is X?" plus "What is Y?" beats "What is the
  difference between X and Y?" whenever X and Y are independently useful.
- HTML is fine and encouraged: `<code>`, `<b>`, `<ul><li>`, `<br>`.
- Media does not round-trip — `generate_anki_from_text.py` packages no media
  files. Don't emit `<img>` tags and expect images to appear.

## Step 4 — Run the overlap check

```bash
python check_overlap.py candidates/<topic>.txt
```

Add `--json` when you want to consume the result structurally. It checks three
things: candidates vs. corpus, candidates vs. each other, and GUID collisions
(which exit non-zero, because generating over a colliding GUID silently
overwrites the existing card).

The threshold defaults to 0.5 and is deliberately loose. **The script is the
recall stage; you are the precision stage.** Expect false positives — that is
the design, not a bug.

**Include pending candidate files in the corpus.** `--corpus` defaults to the
dump of what is already in Anki, which does not include topics distilled earlier
in the same session and not yet imported. Concatenate them first, or you will
happily generate the same APN card twice:

```bash
cat anki_review_output/cards.txt candidates/*.txt > /tmp/corpus.txt
python check_overlap.py candidates/<topic>.txt --corpus /tmp/corpus.txt
```

**Each card is scored as one bag of words.** Front and back are pooled, with
cloze deletions unwrapped, so a cloze candidate is compared against the whole of
a basic card and not just its question. `score` is the share of the candidate's
words that appear in the other card. `shared` is how many words the two have in
common. A pair is flagged only when `score` clears the threshold and the cards
share at least three words (or every word, for a candidate shorter than that).
The floor keeps two-word fronts like "What does EPS stand for?" from matching
every other "stand for" card.

## Step 5 — Adjudicate every flagged card

The scores rank matches. They don't decide them, so read both cards:

- **High `score`, many `shared` words** → usually a true duplicate. Drop the
  candidate.
- **High `score`, but the differing words are the fact** → a real distinction
  the lexical check can't see (`100 kHz` vs `400 kHz` share every word but the
  number). Usually keep.
- **`(same words, swapped sides)`** → the candidate asks the reverse of an
  existing basic card. Treat it as a duplicate unless the user wants both
  directions.
- **Flagged against another candidate** → you distilled the same fact twice from
  one document. Merge them.
- **Existing card is nearly right but incomplete** → merge into the existing
  card: edit that line in place, **keeping its GUID**, and drop the candidate.
  This preserves the review history. Pass `--allow-existing-guids` when the file
  then contains those merged-in existing cards.

Present the decisions to the user before acting on them. Don't silently drop
cards — that's why the tool annotates rather than deletes.

Known limitation: the check is lexical, so it can't catch a paraphrase with no
shared vocabulary, such as a cloze that rewords every term of an existing card.

## Step 6 — Generate

Run the generator directly on the adjudicated candidates file — it already skips
`#` comments, so there is no need to strip them first:

```bash
./venv/bin/python generate_anki_from_text.py candidates/<topic>.txt
```

The output lands in `generated_decks/<name>_<date>.apkg`; the source file's name
is also the fallback deck for lines without a `[DeckName]` prefix. Importing a
per-topic package is additive by GUID — it updates the notes it contains and
touches nothing else.

**Generating several topics in a row does not leave several packages.** Every run
first moves everything in `generated_decks/` into `generated_decks/archive/`, so
runs 2 and 3 sweep away runs 1 and 2. Worse, restoring by name is unreliable: if
the archive already holds a file of that name, the newer one is saved as
`..._1.apkg`, so a naive `mv` back recovers the *stale* one. Copy each package
somewhere safe immediately after generating it:

```bash
mkdir -p /tmp/hold
for f in topic_a topic_b topic_c; do
  ./venv/bin/python generate_anki_from_text.py candidates/$f.txt
  cp generated_decks/${f}_*.apkg /tmp/hold/
done
cp /tmp/hold/*.apkg generated_decks/
```

Verify note counts by reading the SQLite inside each `.apkg` rather than trusting
the generator's console output, which reports what it *intended* to write.

If any line changes an already-imported card from Basic to cloze, the import
fails wholesale with "Cloze note types cannot be merged with regular note types."
Give those cards new GUIDs (see *Author everything as cloze*) and tell the user
the superseded notes must be deleted by hand.

Tell the user to import into a **scratch Anki profile first** if the file
contains round-tripped cards. Preserving a `[mid:...]` tag preserves the model
*id*, not the model: field names and templates are regenerated as generic
`Field 1..N`, so a deck built on a real Anki notetype gets flattened.

## Useful commands

```bash
python check_overlap.py cand.txt --threshold 0.3    # widen the net
python check_overlap.py cand.txt --annotate         # write notes above flagged cards
python check_overlap.py cand.txt --clean            # strip those notes again
python check_overlap.py cand.txt --strict           # comment out flagged cards
python -m unittest tests.test_check_overlap -v      # no genanki needed
```
