#!/usr/bin/env python

import os
import shutil
import argparse
from anki_unpacker import AnkiDeckUnpacker

def unpack_and_review(apkg_path, output_dir="anki_review_output"):
    # 1. Prepare Output Directory
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)
    
    unpacker = AnkiDeckUnpacker(apkg_path)
    unpacker.unpack()
    unpacker.export_media(output_dir)
    
    try:
        notes = unpacker.get_notes()
        deck_name = os.path.basename(apkg_path)
        
        _generate_html(notes, output_dir, deck_name)
        _generate_text(notes, output_dir)
        
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
            if i > 0:
                card_html += '<div class="field-sep"></div>'
            card_html += f'<div>{field}</div>'
        card_html += '</div>'
        
        html_content.append(card_html)
    
    html_content.append("</body></html>")
    
    with open(html_path, "w", encoding="utf-8") as f:
        f.write("\n".join(html_content))
        
    print(f"Done! Open this file to review: {html_path}")

def _generate_text(notes, output_dir):
    """Generates a Raw Text File ([GUID] Front :: Back)."""
    txt_path = os.path.join(output_dir, "cards.txt")
    text_content = []
    
    for note in notes:
        fields = note[0].split('\x1f')
        guid = note[1]
        
        # Assume first two fields are Front and Back
        if len(fields) >= 2:
            front = fields[0].strip()
            back = fields[1].strip()
            # We don't need to strip HTML tags because the user wants to preserve them for the text format
            # (so they can be re-imported with formatting)
            text_content.append(f"[{guid}] {front} :: {back}")
    
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(text_content))
        
    print(f"Generated raw text file: {txt_path}")


def main():
    parser = argparse.ArgumentParser(description='Extract and review Anki deck content.')
    parser.add_argument('apkg_path', type=str, help='Path to the Anki .apkg file')
    parser.add_argument('--output_dir', type=str, default='anki_review_output', help='Output directory for extracted files')
    
    args = parser.parse_args()
    unpack_and_review(args.apkg_path, args.output_dir)

if __name__ == "__main__":
    main()