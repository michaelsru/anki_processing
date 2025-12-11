import zipfile
import sqlite3
import zstandard
import json
import os
import shutil
import io
import tempfile

class AnkiDeckUnpacker:
    def __init__(self, apkg_path):
        self.apkg_path = apkg_path
        self.temp_dir = tempfile.mkdtemp()
        self.conn = None
        self.cursor = None
        self.db_path = None

    def unpack(self):
        """Unpacks the .apkg file to a temporary directory and processes media."""
        print(f"Extracting {self.apkg_path} to temporary storage...")
        
        # 1. Unzip the contents
        with zipfile.ZipFile(self.apkg_path, 'r') as z:
            z.extractall(self.temp_dir)
            
        # 2. Rename Media Files
        self._process_media()
        
        # 3. Prepare Database
        self._prepare_database()

    def export_media(self, target_dir):
        """Copies processed media files to the target directory."""
        if not os.path.exists(target_dir):
            os.makedirs(target_dir)
            
        count = 0
        for filename in os.listdir(self.temp_dir):
            # Skip database files and the media map itself (if it still exists)
            if filename.startswith("collection.anki") or filename == "media":
                continue
            
            src = os.path.join(self.temp_dir, filename)
            dst = os.path.join(target_dir, filename)
            
            if os.path.isfile(src):
                shutil.copy2(src, dst)
                count += 1
        
        if count > 0:
            print(f"Exported {count} media files to {target_dir}")

    def _process_media(self):
        media_map_path = os.path.join(self.temp_dir, "media")
        
        if os.path.exists(media_map_path):
            with open(media_map_path, 'rb') as f:
                data = f.read()
                
            # Check for Zstandard magic bytes (0x28 B5 2F FD)
            if data.startswith(b'\x28\xb5\x2f\xfd'):
                print("Detected Zstandard compressed media file. Decompressing...")
                dctx = zstandard.ZstdDecompressor()
                with dctx.stream_reader(io.BytesIO(data)) as reader:
                    data = reader.read()
                
            if not data:
                print("Media file is empty.")
                media_map = {}
            else:
                media_map = json.loads(data)
            
            # Rename the numbered files to their original extensions
            for numeric_name, original_name in media_map.items():
                old_path = os.path.join(self.temp_dir, numeric_name)
                new_path = os.path.join(self.temp_dir, original_name)
                if os.path.exists(old_path):
                    os.rename(old_path, new_path)
            
            os.remove(media_map_path) # cleanup

    def _prepare_database(self):
        # Check for newer Anki format (collection.anki21b)
        db_path_v2 = os.path.join(self.temp_dir, "collection.anki21b")
        db_path_legacy = os.path.join(self.temp_dir, "collection.anki2")
        
        if os.path.exists(db_path_v2):
            print("Detected V2/V3 scheduler database (collection.anki21b). Decompressing...")
            with open(db_path_v2, 'rb') as f:
                data = f.read()
                dctx = zstandard.ZstdDecompressor()
                with dctx.stream_reader(io.BytesIO(data)) as reader:
                    decompressed_db = reader.read()
                    
            # Write to a temp file to open with sqlite
            self.db_path = os.path.join(self.temp_dir, "collection.anki2_decompressed")
            with open(self.db_path, 'wb') as f:
                f.write(decompressed_db)
        else:
            self.db_path = db_path_legacy

    def get_notes(self):
        """Yields notes from the database."""
        if not self.db_path or not os.path.exists(self.db_path):
            raise FileNotFoundError("Database not found. Did you call unpack()?")
            
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        
        # Get the raw field data and GUID
        self.cursor.execute("SELECT flds, guid FROM notes")
        notes = self.cursor.fetchall()
        
        return notes

    def close(self):
        if self.conn:
            self.conn.close()
        
        if self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
