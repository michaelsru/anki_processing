#!/usr/bin/env python

import os
import sys
import shutil

def cleanup_archive():
    archive_dir = os.path.join("generated_decks", "archive")
    
    if not os.path.exists(archive_dir):
        print(f"ℹ️  Archive directory not found: {archive_dir}")
        return

    files = [f for f in os.listdir(archive_dir) if os.path.isfile(os.path.join(archive_dir, f))]
    
    if not files:
        print(f"ℹ️  Archive is already empty: {archive_dir}")
        return

    print(f"found {len(files)} files in {archive_dir}:")
    for f in files:
        print(f" - {f}")
    
    confirm = input("\n⚠️  Are you sure you want to delete these files? (y/N): ").strip().lower()
    
    if confirm == 'y':
        deleted_count = 0
        for f in files:
            file_path = os.path.join(archive_dir, f)
            try:
                os.remove(file_path)
                deleted_count += 1
            except Exception as e:
                print(f"❌ Failed to delete {f}: {e}")
        
        print(f"\n✅ Successfully deleted {deleted_count} files.")
    else:
        print("\n🚫 Operation cancelled.")

if __name__ == "__main__":
    cleanup_archive()
