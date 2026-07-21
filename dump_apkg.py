#!/usr/bin/env python

import os
import json
import sqlite3
import shutil
import argparse
from anki_unpacker import AnkiDeckUnpacker
from verify_guids import verify

def _get_notes_with_decks(db_path):
    """Query notes joined with their deck names directly from the SQLite DB.
    Returns list of (fields_str, guid, deck_name, mid) sorted by deck.
    Fields are padded to the model's declared field count so the round-trip
    always produces notes with the right number of fields.
    """
    conn = sqlite3.connect(db_path)
    try:
        # --- Deck ID → name ---
        row = conn.execute("SELECT decks FROM col LIMIT 1").fetchone()
        col_decks = row[0] if row else None

        if col_decks:
            decks_json = json.loads(col_decks)
            deck_id_to_name = {int(k): v["name"].replace('\x1f', '::') for k, v in decks_json.items()}
        else:
            deck_rows = conn.execute("SELECT id, name FROM decks").fetchall()
            deck_id_to_name = {r[0]: r[1].replace('\x1f', '::') for r in deck_rows}

        # --- Model ID → declared field count ---
        try:
            # Newer Anki: separate `fields` table keyed by ntid
            fc_rows = conn.execute("SELECT ntid, COUNT(*) FROM fields GROUP BY ntid").fetchall()
            mid_to_field_count = {r[0]: r[1] for r in fc_rows}
            print(f"[debug] fields table: {len(fc_rows)} models → {dict(list(mid_to_field_count.items())[:5])}")
        except Exception as e:
            print(f"[debug] fields table query failed: {e}")
            mid_to_field_count = {}

        if not mid_to_field_count:
            # Legacy: col.models JSON, each model has a 'flds' array
            try:
                models_row = conn.execute("SELECT models FROM col LIMIT 1").fetchone()
                if models_row and models_row[0]:
                    models_json = json.loads(models_row[0])
                    mid_to_field_count = {int(k): len(v["flds"]) for k, v in models_json.items()}
                    print(f"[debug] col.models fallback: {len(mid_to_field_count)} models")
                else:
                    print("[debug] col.models is empty — no field count available")
            except Exception as e:
                print(f"[debug] col.models fallback failed: {e}")

        # --- Notes + cards join ---
        rows = conn.execute("""
            SELECT n.flds, n.guid, MIN(c.did), n.mid
            FROM notes n
            JOIN cards c ON c.nid = n.id
            GROUP BY n.id
            ORDER BY MIN(c.did), n.id
        """).fetchall()
    finally:
        conn.close()

    result = []
    for flds, guid, did, mid in rows:
        deck_name = deck_id_to_name.get(did, f"Unknown({did})")
        fields = flds.split('\x1f')
        expected = mid_to_field_count.get(mid)
        if expected and len(fields) < expected:
            fields += [''] * (expected - len(fields))
        model_field_count = expected or len(fields)
        result.append(('\x1f'.join(fields), guid, deck_name, mid, model_field_count))

    return result


def unpack_and_review(apkg_path, output_dir="anki_review_output"):
    # 1. Prepare Output Directory
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    unpacker = AnkiDeckUnpacker(apkg_path)
    unpacker.unpack()

    # Export media to nested 'media' folder
    media_dir = os.path.join(output_dir, "media")
    unpacker.export_media(media_dir)

    try:
        notes_with_decks = _get_notes_with_decks(unpacker.db_path)
        apkg_name = os.path.basename(apkg_path)

        # HTML still uses legacy get_notes() — deck info not needed there
        notes = unpacker.get_notes()
        _generate_html(notes, output_dir, apkg_name)
        _generate_text(notes_with_decks, output_dir)

    finally:
        unpacker.close()

def _generate_html(notes, output_dir, deck_name):
    """Generates a Review HTML Page."""
    html_path = os.path.join(output_dir, "index.html")
    
    html_content = [
        "<html><head><style>",
        "body { font-family: sans-serif; max_width: 800px; margin: 20px auto; background: #f4f4f9; }",
        ".card { background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }",
        "img { max-width: 100%; height: auto; }",
        ".field-sep { border-top: 1px dashed #ccc; margin: 10px 0; }",
        "</style></head><body>",
        f"<h1>Deck Preview: {deck_name}</h1>"
    ]
    
    for note in notes:
        # Anki fields are separated by the hex character 0x1f
        fields = note[0].split('\x1f')
        guid = note[1]
        
        card_html = f'<div class="card" data-guid="{guid}">'
        for i, field in enumerate(fields):
            # Update image paths to point to media folder
            field = field.replace('src="', 'src="media/')
            
            if i > 0:
                card_html += '<div class="field-sep"></div>'
            card_html += f'<div>{field}</div>'
        card_html += '</div>'
        
        html_content.append(card_html)
    
    html_content.append("</body></html>")
    
    with open(html_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html_content))
        
    print(f"Done! Open this file to review: {html_path}")

def _generate_text(notes_with_decks, output_dir):
    """Generates a Raw Text File.
    Format: [DeckName] [GUID] [mid:ID:FIELDCOUNT] Field1 :: Field2
    Trailing empty fields are stripped from display; FIELDCOUNT carries the padding info.
    """
    txt_path = os.path.join(output_dir, "cards.txt")
    lines = []

    for flds, guid, deck_name, mid, model_field_count in notes_with_decks:
        fields = [f.strip().replace('\n', ' ') for f in flds.split('\x1f')]
        # Strip trailing empty fields — count is encoded in the mid tag instead
        while fields and not fields[-1]:
            fields.pop()
        line_content = " :: ".join(fields)
        lines.append(f"[{deck_name}] [{guid}] [mid:{mid}:{model_field_count}] {line_content}")

    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Generated raw text file: {txt_path}")


def main():
    parser = argparse.ArgumentParser(description='Unpack Anki APKG file to HTML/Text for review')
    parser.add_argument('apkg_path', help='Path to the .apkg file')
    parser.add_argument('--output_dir', default='anki_review_output', help='Directory to output files')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.apkg_path):
        print(f"Error: File not found: {args.apkg_path}")
        return

    unpack_and_review(args.apkg_path, args.output_dir)

    # Verify GUIDs
    print("\n--- Verifying GUIDs ---")
    try:
        verify(os.path.join(args.output_dir, "cards.txt"), args.apkg_path)
    except ImportError:
        print("Warning: verify_guids module not found. Skipping verification.")
    except Exception as e:
        print(f"Warning: Verification failed: {e}")

if __name__ == "__main__":
    main()