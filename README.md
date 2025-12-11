# Anki Deck Generation Tools

This project contains a suite of tools for generating, managing, and inspecting Anki decks from text files. It is designed to support a "text-first" workflow where you maintain your cards in a version-controllable text file and generate `.apkg` files for import into Anki.

## Key Features
- **Text-to-Anki Generation**: Convert simple text files into Anki packages.
- **Stable GUIDs**: Preserves learning progress by assigning persistent IDs to cards.
- **Deck Inspection**: Extract and view the contents of any `.apkg` file (supports modern Anki V2/V3 formats and Zstd compression).
- **Migration Tools**: Helpers to convert existing decks or HTML dumps into the supported text format.

## File Format
The source text file (e.g., `cards.txt`) uses a simple format:
```text
[<GUID>] Question :: Answer
```
- **GUID**: A unique identifier (e.g., `[15938472]`) that ensures Anki recognizes the card as the same note even if you edit the text.
- **Separator**: `::` separates the Front (Question) and Back (Answer).

**Example:**
```text
[12345678] What is the time complexity of Binary Search? :: O(log n)
[87654321] What data structure uses LIFO? :: Stack
```

## Scripts

### 1. `generate_anki_from_text.py`
The main script to generate `.apkg` files.
```bash
./venv/bin/python generate_anki_from_text.py cards.txt
```
**Output**: `cards_basic_[DATE].apkg`

### 2. `dump_apkg.py`
Extracts and visualizes the contents of an `.apkg` file. Useful for verifying deck content without opening Anki.
```bash
./venv/bin/python dump_apkg.py cards_basic_2025-12-10.apkg
```
**Output**:
- `anki_review_output/index.html`: HTML preview of the deck.
- `anki_review_output/deck_raw.txt`: Raw text format (for re-importing/editing).

### 3. `verify_guids.py`
Verifies that the GUIDs in a generated `.apkg` match the source text file.
```bash
./venv/bin/python verify_guids.py cards.txt cards_basic_2025-12-10.apkg
```

**Options**:
- `--verbose` or `-v`: Print the content of missing or unexpected cards to help identify discrepancies.

## Workflow
1.  **Edit**: Add or modify cards in `cards.txt`.
2.  **Generate**: Run `generate_anki_from_text.py`.
3.  **Import**: Double-click the generated `.apkg` to import into Anki.
4.  **Study**: Anki will update existing cards (preserving scheduling) and add new ones.
