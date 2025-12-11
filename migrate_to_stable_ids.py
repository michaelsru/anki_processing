#!/usr/bin/env python3

import sqlite3
import zipfile
import os
import shutil
import genanki
import zstandard
import io
import json
import sys

def get_guids_from_apkg(apkg_path):
    """Extracts a dictionary of {Front: GUID} from an .apkg file."""
    temp_dir = "temp_migration_extraction"
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    print(f"Extracting GUIDs from {apkg_path}...")
    with zipfile.ZipFile(apkg_path, 'r') as z:
        z.extractall(temp_dir)
        
    db_path = os.path.join(temp_dir, "collection.anki21b")
    if not os.path.exists(db_path):
        db_path = os.path.join(temp_dir, "collection.anki2")
        
    # Handle Zstd compression if needed (for 21b)
    final_db_path = os.path.join(temp_dir, "collection.db")
    
    if db_path.endswith(".anki21b"):
        with open(db_path, 'rb') as f:
            data = f.read()
            dctx = zstandard.ZstdDecompressor()
            with dctx.stream_reader(io.BytesIO(data)) as reader:
                with open(final_db_path, 'wb') as out_f:
                    shutil.copyfileobj(reader, out_f)
    else:
        shutil.copy(db_path, final_db_path)
        
    conn = sqlite3.connect(final_db_path)
    cursor = conn.cursor()
    
    # Notes table: id, guid, mid, mod, usn, tags, flds, sfld, csum, flags, data
    # flds are separated by 0x1f
    cursor.execute("SELECT guid, flds FROM notes")
    rows = cursor.fetchall()
    
    guid_map = {}
    for guid, flds in rows:
        fields = flds.split('\x1f')
        if fields:
            front = fields[0].strip()
            guid_map[front] = guid
            
    conn.close()
    shutil.rmtree(temp_dir)
    return guid_map

def migrate_file(txt_path, apkg_path):
    guid_map = get_guids_from_apkg(apkg_path)
    print(f"Recovered {len(guid_map)} GUIDs.")
    
    new_lines = []
    with open(txt_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                new_lines.append(line)
                continue
                
            if "::" in line:
                parts = line.split("::", 1)
                front = parts[0].strip()
                
                # Check if already has ID
                if front.startswith('[') and '] ' in front:
                    new_lines.append(line)
                    continue
                    
                if front in guid_map:
                    guid = guid_map[front]
                    new_lines.append(f"[{guid}] {line}")
                else:
                    # Generate a stable GUID based on content if not found
                    # (This happens for new cards added after the apkg was generated)
                    guid = genanki.guid_for(front)
                    new_lines.append(f"[{guid}] {line}")
            else:
                new_lines.append(line)
                
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(new_lines))
    print(f"Migrated {txt_path} with stable GUIDs.")

import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Migrate text file to use stable GUIDs from an existing .apkg')
    parser.add_argument('txt_path', help='Path to the source text file (e.g., cards.txt)')
    parser.add_argument('apkg_path', help='Path to the existing .apkg file to recover GUIDs from')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.txt_path):
        print(f"Error: Text file not found: {args.txt_path}")
        sys.exit(1)
        
    if not os.path.exists(args.apkg_path):
        print(f"Error: APKG file not found: {args.apkg_path}")
        sys.exit(1)
        
    migrate_file(args.txt_path, args.apkg_path)
