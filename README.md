# Anki Deck Generation Tools

This project contains a suite of tools for generating, managing, and inspecting Anki decks from text files. It is designed to support a "text-first" workflow where you maintain your cards in a version-controllable text file and generate `.apkg` files for import into Anki.

## Key Features
- **Text-to-Anki Generation**: Convert simple text files into Anki packages.
- **Stable GUIDs**: A card with an explicit `[GUID]` keeps it across regenerations, so Anki updates the note and keeps its review history. A card without one gets a GUID derived from its front text, which changes whenever that text does.
- **Deck Inspection**: Extract and view the contents of any `.apkg` file (supports modern Anki V2/V3 formats and Zstd compression).

## File Format
The source text file (e.g., `cards.txt`) uses a line-per-card format:
```text
[DeckName] [GUID] [mid:MODEL_ID:FIELDCOUNT] Field1 :: Field2
```
- **DeckName**: The target deck. `::` nests decks (`Embedded::Protocols::I2C`).
- **GUID**: A unique identifier that ensures Anki recognizes the card as the same
  note even if you edit the text. Optional, but see the warning below.
- **mid tag**: Optional. Emitted by `dump_apkg.py` to remember the source notetype.
- **Separator**: ` :: ` (spaced) separates fields.

**Example:**
```text
[Algorithms] [12345678] What is the time complexity of Binary Search? :: O(log n)
[Algorithms] [87654321] What data structure uses LIFO? :: Stack
```

⚠️ **Always write the `[DeckName]` prefix.** A bare `[12345678] Question :: Answer`
line is parsed as a *deck named 12345678* — the GUID is discarded. (Earlier
versions of this README documented that GUID-only form; deck-prefix support
superseded it.)

**`template_cards.txt` in the repo root is the full format reference** and a
runnable example — every rule, every trap, with live cards you can generate as-is.

## Scripts

### 1. `generate_anki_from_text.py`
The main script to generate `.apkg` files.
```bash
./venv/bin/python generate_anki_from_text.py candidates/i2c.txt
```
**Output**: `generated_decks/<name>_<date>.apkg`, where `<name>` is the input
file's name with non-word characters replaced by `_`. Existing packages in
`generated_decks/` are moved to `generated_decks/archive/` first. A file whose
`[mid:ID:COUNT]` tags contradict each other (a line with more fields than its
COUNT, or one mid used by both cloze and basic lines) is refused with the file
and line number of every offending line, and nothing is written or archived.

### 2. `dump_apkg.py`
Extracts and visualizes the contents of an `.apkg` file. Useful for verifying deck content without opening Anki.
```bash
./venv/bin/python dump_apkg.py generated_decks/i2c_2025-12-10.apkg
```
**Output**:
- `anki_review_output/index.html`: HTML preview of the deck.
- `anki_review_output/cards.txt`: Raw text format (for re-importing/editing).
- `anki_review_output/media/`: any media files in the package.

### 3. `verify_guids.py`
Verifies that the GUIDs in a generated `.apkg` match the source text file.
```bash
./venv/bin/python verify_guids.py anki_review_output/cards.txt generated_decks/i2c_2025-12-10.apkg
```

**Options**:
- `--verbose` or `-v`: Print the content of missing or unexpected cards to help identify discrepancies.

Lines without a GUID are skipped, because their GUID is derived from the front
text and the model id at generation time. `dump_apkg.py` runs this check on its
own output automatically.

### 4. `check_overlap.py`
Flags candidate cards that duplicate cards already in your collection, so you
don't study the same fact twice.
```bash
./venv/bin/python check_overlap.py candidates/i2c.txt --corpus anki_review_output/cards.txt
```
Each card's front and back are pooled into one bag of content words, because a
cloze card keeps everything in its first field. A candidate is flagged when at
least half of its words appear in another card and the two share at least 3
words (or every word, for a candidate shorter than that). The floor keeps a
two-word front like "What does APN stand for?" from matching every other
"stand for" card. Reverse cards are flagged too, labelled "same words, swapped
sides", so you can keep them on purpose. It also dedups candidates against each
other, and hard-errors on GUID collisions that would silently overwrite existing
cards.

**Options**: `--threshold` (default 0.5, lower = more flagged), `--json`,
`--annotate` (notes above flagged cards, cards left live), `--strict` (comment
flagged cards out), `--clean` (strip annotations), `--allow-existing-guids`.

Deliberately loose: it's the recall stage, you're the precision stage.

### Supporting modules
- `card_format.py`: parses and writes the card line format. Every script above
  reads lines through it, so there is one answer to which bracket is the deck.
- `anki_unpacker.py`: extracts an `.apkg` (zip, Zstandard, media map) for
  `dump_apkg.py`.
- `cleanup_archive.py`: deletes everything in `generated_decks/archive/` after
  asking.
- `run_tests.py`: runs the test suite, same as
  `./venv/bin/python -m unittest discover tests`.

## Workflow
1.  **Export the FULL collection** from Anki (File → Export → All Decks) and run
    `dump_apkg.py` on it. `dump_apkg.py` wipes its output directory each run, so
    `anki_review_output/cards.txt` only ever holds the last deck you dumped —
    dedup against a partial corpus looks like it's working when it isn't.
2.  **Distill** new material into `candidates/<topic>.txt` (see `template_cards.txt`).
3.  **Check**: Run `check_overlap.py` and adjudicate anything flagged.
4.  **Generate**: Run `generate_anki_from_text.py candidates/<topic>.txt`.
5.  **Import**: Double-click the generated `.apkg` to import into Anki.
6.  **Study**: Anki will update existing cards (preserving scheduling) and add new ones.

Steps 2–3 are automated by the `anki-cards` skill in `.claude/skills/`.

## Known limitations
- **Media does not round-trip.** `dump_apkg.py` extracts images to
  `anki_review_output/media/`, but `generate_anki_from_text.py` packages no media
  files. `<img>` tags survive as text; the images do not.
- **Anki tags are not carried.** Nothing in the pipeline reads or writes
  `notes.tags`, so tags are absent from dumps and never set on generated notes.
- **Notetypes are flattened.** Preserving a `[mid:...]` tag preserves the model
  *id*, not the model — field names and templates are regenerated as generic
  `Field 1..N`. Test round-trips on a scratch Anki profile first.
