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
                try:
                    media_map = json.loads(data)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    print("⚠️  JSON decode failed. Trying Protobuf parser...")
                    try:
                        media_map = self._parse_protobuf_media(data)
                    except Exception as e:
                        print(f"❌ Protobuf parse failed: {e}")
                        media_map = {}
            
            # Rename the numbered files to their original extensions
            for numeric_name, original_name in media_map.items():
                old_path = os.path.join(self.temp_dir, numeric_name)
                new_path = os.path.join(self.temp_dir, original_name)
                if os.path.exists(old_path):
                    os.rename(old_path, new_path)
            
            os.remove(media_map_path) # cleanup

    def _parse_protobuf_media(self, data):
        """Parses Anki's protobuf media format."""
        media_map = {}
        pos = 0
        length = len(data)
        
        def read_varint(pos):
            result = 0
            shift = 0
            while True:
                if pos >= length:
                    raise IndexError("Varint read out of bounds")
                b = data[pos]
                pos += 1
                result |= (b & 0x7f) << shift
                if not (b & 0x80):
                    return result, pos
                shift += 7
        
        while pos < length:
            # Read tag
            tag, pos = read_varint(pos)
            field_number = tag >> 3
            wire_type = tag & 7
            
            if field_number == 1 and wire_type == 2: # MediaEntry message
                msg_len, pos = read_varint(pos)
                end_pos = pos + msg_len
                
                filename = None
                idx = None
                
                while pos < end_pos:
                    inner_tag, pos = read_varint(pos)
                    inner_field = inner_tag >> 3
                    inner_type = inner_tag & 7
                    
                    if inner_field == 1 and inner_type == 2: # Filename
                        str_len, pos = read_varint(pos)
                        filename = data[pos:pos+str_len].decode('utf-8', errors='replace')
                        pos += str_len
                    elif inner_field == 2 and inner_type == 0: # Index
                        idx, pos = read_varint(pos)
                    elif inner_type == 2: # Skip length delimited (e.g. checksum)
                        skip_len, pos = read_varint(pos)
                        pos += skip_len
                    elif inner_type == 0: # Skip varint
                        _, pos = read_varint(pos)
                    elif inner_type == 5: # Skip 32-bit
                        pos += 4
                    elif inner_type == 1: # Skip 64-bit
                        pos += 8
                    else:
                        # Should not happen in this specific format, but good to be safe
                        # If we don't know the type, we can't skip it easily without a schema
                        # But we assume valid Anki protobuf
                        pass
                
                if filename is not None and idx is not None:
                    media_map[str(idx)] = filename
            else:
                # Skip top-level unknown fields
                if wire_type == 2:
                    skip_len, pos = read_varint(pos)
                    pos += skip_len
                elif wire_type == 0:
                    _, pos = read_varint(pos)
                elif wire_type == 5:
                    pos += 4
                elif wire_type == 1:
                    pos += 8
                    
        return media_map

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
