#!/usr/bin/env python3

import sqlite3
import zipfile
import os
import shutil
import zstandard
import io

import tempfile

def get_guids_from_apkg(apkg_path):
    with tempfile.TemporaryDirectory() as temp_dir:
        with zipfile.ZipFile(apkg_path, 'r') as z:
            z.extractall(temp_dir)
            
        db_path = os.path.join(temp_dir, "collection.anki21b")
        if not os.path.exists(db_path):
            db_path = os.path.join(temp_dir, "collection.anki2")
            
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
        cursor.execute("SELECT guid, flds FROM notes")
        
        # Return a dict of {guid: front_field}
        guids = {}
        for row in cursor.fetchall():
            guid = row[0]
            flds = row[1]
            front = flds.split('\x1f')[0]
            guids[guid] = front
            
        conn.close()
        return guids

def verify(txt_path, apkg_path, verbose=False):
    expected_cards = {} # {guid: front}
    
    with open(txt_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            # Use partition to find the first occurrence of '] '
            if line.startswith('[') and '] ' in line:
                part1, sep, part2 = line.partition('] ')
                guid = part1[1:]
                
                # Extract Front content (everything before ' :: ')
                if ' :: ' in part2:
                    front = part2.split(' :: ')[0]
                else:
                    front = part2 # Fallback if no back field
                    
                expected_cards[guid] = front
    
    actual_cards = get_guids_from_apkg(apkg_path)
    
    expected_guids = set(expected_cards.keys())
    actual_guids = set(actual_cards.keys())
    
    missing = expected_guids - actual_guids
    unexpected = actual_guids - expected_guids
    
    # print matches
    matches = expected_guids & actual_guids
    print(f"✅ MATCHES: {len(matches)}")
    
    if not missing and not unexpected:
        print("✅ SUCCESS: All GUIDs match!")
    else:
        if missing:
            print(f"{len(missing)} New cards found in {txt_path}")
            if verbose:
                for guid in missing:
                    print(f"✅ [NEW] {expected_cards.get(guid, 'Unknown')}")
            # else:
            #     for guid in missing:
            #         print(f"✅ {guid}")
                    
        if unexpected:
            print(f"{len(unexpected)} Deleted cards found in {apkg_path}")
            if verbose:
                for guid in unexpected:
                    print(f"❌ [DELETED] {actual_cards.get(guid, 'Unknown')}")
            # else:
            #     for guid in unexpected:
            #         print(f"❌ {guid}")

import argparse
import sys

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Verify that GUIDs in an .apkg match the source text file')
    parser.add_argument('txt_path', help='Path to the source text file (e.g., cards.txt)')
    parser.add_argument('apkg_path', help='Path to the generated .apkg file')
    parser.add_argument('-v', '--verbose', action='store_true', help='Print detailed card content for mismatches')
    
    args = parser.parse_args()
    
    if not os.path.exists(args.txt_path):
        print(f"Error: Text file not found: {args.txt_path}")
        sys.exit(1)
        
    if not os.path.exists(args.apkg_path):
        print(f"Error: APKG file not found: {args.apkg_path}")
        sys.exit(1)
        
    verify(args.txt_path, args.apkg_path, args.verbose)
