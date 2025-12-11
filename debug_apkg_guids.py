import zipfile
import sqlite3
import zstandard
import io
import os
import shutil
import sys

def inspect_apkg(apkg_path):
    temp_dir = "temp_debug_extraction"
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    
    try:
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
        cursor.execute("SELECT guid FROM notes LIMIT 10")
        print(f"First 10 GUIDs in {apkg_path}:")
        for row in cursor.fetchall():
            print(row[0])
            
        conn.close()
    finally:
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python debug_apkg_guids.py <apkg_path>")
        sys.exit(1)
    inspect_apkg(sys.argv[1])
