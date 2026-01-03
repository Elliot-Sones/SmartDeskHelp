#!/usr/bin/env python3
"""
LEANN Indexer - Builds unified index from all sources.

Usage:
    python leann_indexer.py              # Index ~/Desktop
    python leann_indexer.py --force      # Force rebuild
    python leann_indexer.py --no-memory  # Skip personal memory
"""

import os
import sys
from pathlib import Path
from typing import List

from leann import LeannBuilder

# Import extractors
from extractors.text_extractor import TextExtractor
from extractors.image_extractor import ImageExtractor
from extractors.memory_extractor import MemoryExtractor


# Configuration
INDEX_PATH = os.path.expanduser("~/.kel/leann.index")
DB_PATH = os.path.expanduser("~/.kel/database.db")
DEFAULT_DIRECTORIES = ["~/Desktop"]

# Register extractors (add new ones here)
EXTRACTORS = [
    TextExtractor(),
    ImageExtractor(),
]

# Directories to always skip
SKIP_DIRS = {
    'node_modules', '__pycache__', '.git', '.svn', '.hg',
    'venv', '.venv', 'env', '.env', 'build', 'dist',
    'target', '.idea', '.vscode', 'Pods', 'DerivedData'
}


def should_skip_path(path: Path) -> bool:
    """Check if a path should be skipped."""
    # Skip hidden files/folders
    if any(part.startswith('.') for part in path.parts):
        return True
    
    # Skip known directories
    if any(skip_dir in path.parts for skip_dir in SKIP_DIRS):
        return True
    
    return False


def build_index(
    directories: List[str] = None,
    include_memory: bool = True,
    force: bool = False
) -> dict:
    """
    Build unified LEANN index from all sources.
    
    Args:
        directories: Directories to index (default: ~/Desktop)
        include_memory: Include personal memory facts
        force: Force rebuild even if index exists
    
    Returns:
        dict with stats (file_count, chunk_count, etc.)
    """
    if directories is None:
        directories = DEFAULT_DIRECTORIES
    
    # Check if index exists
    if os.path.exists(INDEX_PATH) and not force:
        print(f"[Indexer] Index already exists at {INDEX_PATH}")
        print("[Indexer] Use --force to rebuild")
        return {"status": "exists", "path": INDEX_PATH}
    
    print("[Indexer] Starting LEANN index build...")
    
    builder = LeannBuilder(backend_name="hnsw")
    stats = {
        "files_processed": 0,
        "files_skipped": 0,
        "entries_added": 0,
        "sources": {}
    }
    
    # 1. Index files from directories
    for dir_path in directories:
        root = Path(dir_path).expanduser().resolve()
        print(f"[Indexer] Scanning {root}...")
        
        if not root.exists():
            print(f"[Indexer] Warning: Directory not found: {root}")
            continue
        
        for file_path in root.rglob("*"):
            # Skip directories and problematic paths
            if not file_path.is_file():
                continue
            if should_skip_path(file_path):
                stats["files_skipped"] += 1
                continue
            
            # Find matching extractor
            for extractor in EXTRACTORS:
                if extractor.can_handle(str(file_path)):
                    try:
                        entries = extractor.extract(str(file_path))
                        
                        for entry in entries:
                            builder.add_text(entry.text, metadata={
                                "type": entry.entry_type,
                                "source": entry.source,
                                "file_path": entry.file_path,
                                "file_name": entry.file_name,
                                "folder": entry.folder,
                                "chunk_index": entry.chunk_index,
                                **entry.extra_metadata
                            })
                            stats["entries_added"] += 1
                            
                            # Track by source
                            source = entry.source
                            if source not in stats["sources"]:
                                stats["sources"][source] = 0
                            stats["sources"][source] += 1
                        
                        stats["files_processed"] += 1
                        
                    except Exception as e:
                        print(f"[Indexer] Error processing {file_path.name}: {e}")
                        stats["files_skipped"] += 1
                    
                    break  # Only use first matching extractor
            
            # Progress indicator
            if stats["files_processed"] % 100 == 0 and stats["files_processed"] > 0:
                print(f"[Indexer] Processed {stats['files_processed']} files, {stats['entries_added']} entries...")
    
    # 2. Index personal memory
    if include_memory and os.path.exists(DB_PATH):
        print("[Indexer] Adding personal memory facts...")
        memory_extractor = MemoryExtractor(DB_PATH)
        
        for entry in memory_extractor.extract_from_db():
            builder.add_text(entry.text, metadata={
                "type": entry.entry_type,
                "source": entry.source,
                **entry.extra_metadata
            })
            stats["entries_added"] += 1
            
            if "memory" not in stats["sources"]:
                stats["sources"]["memory"] = 0
            stats["sources"]["memory"] += 1
    
    # 3. Build and save index
    if stats["entries_added"] == 0:
        print("[Indexer] No entries to index!")
        return {"status": "empty", "stats": stats}
    
    print(f"[Indexer] Building index with {stats['entries_added']} entries...")
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    
    builder.build_index(INDEX_PATH)
    
    print(f"[Indexer] ✓ Index saved to {INDEX_PATH}")
    print(f"[Indexer] Stats: {stats['files_processed']} files, {stats['entries_added']} entries")
    print(f"[Indexer] Sources: {stats['sources']}")
    
    return {"status": "success", "path": INDEX_PATH, "stats": stats}


if __name__ == "__main__":
    # Parse simple command line args
    force = "--force" in sys.argv
    include_memory = "--no-memory" not in sys.argv
    
    # Custom directories (any arg not starting with --)
    custom_dirs = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
    directories = custom_dirs if custom_dirs else None
    
    result = build_index(
        directories=directories,
        include_memory=include_memory,
        force=force
    )
    
    print(f"\n[Indexer] Result: {result['status']}")
