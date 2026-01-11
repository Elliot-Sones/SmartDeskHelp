#!/usr/bin/env python3
"""
LEANN Indexer Wrapper (Compatibility Layer)

This script replaces the legacy indexer. It transparently routes 
commands to the new, high-performance 'indexing' package.

Usage:
    python leann_indexer.py [dirs...]    # Index specific directories
    python leann_indexer.py --force      # Force rebuild (delete DB)
    python leann_indexer.py --no-memory  # (Ignored, for compatibility)
"""

import sys
import asyncio
import argparse
import logging
import shutil
import os
from pathlib import Path
from typing import List, Optional

# Add current directory to path so we can import 'indexing'
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from indexing.orchestrator import Orchestrator
from indexing.config import get_config

# Configure logging to match legacy format roughly
logging.basicConfig(
    level=logging.INFO,
    format="[Indexer] %(message)s"
)
logger = logging.getLogger("Indexer")

def main():
    parser = argparse.ArgumentParser(description="LEANN Indexer (New Engine)")
    parser.add_argument("roots", nargs="*", help="Directories to index")
    parser.add_argument("--force", action="store_true", help="Force rebuild (delete existing index)")
    parser.add_argument("--no-memory", action="store_true", help="Skip memory indexing (legacy flag)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
    
    config = get_config()
    db_path = config.db_path
    index_path = config.index_path
    
    # Handle --force (Rebuild)
    if args.force:
        logger.info("Forcing rebuild: removing existing database and index...")
        if db_path.exists():
            try:
                os.remove(db_path)
                logger.info(f"Removed {db_path}")
            except OSError as e:
                logger.warning(f"Could not remove {db_path}: {e}")
                
        if index_path.exists():
            try:
                os.remove(index_path)
                logger.info(f"Removed {index_path}")
            except OSError as e:
                logger.warning(f"Could not remove {index_path}: {e}")
                
        # Also clean up WAL/SHM files if they exist
        for ext in ["-wal", "-shm"]:
            wal_path = db_path.with_name(db_path.name + ext)
            if wal_path.exists():
                try:
                    os.remove(wal_path)
                except OSError:
                    pass

    # Resolve roots
    roots: Optional[List[Path]] = None
    if args.roots:
        roots = [Path(r).expanduser().resolve() for r in args.roots]
    else:
        # If no args provided, config.py defaults will be used (Desktop, Docs, Cloud, etc.)
        pass

    logger.info("Starting new indexing engine...")
    if roots:
        logger.info(f"Scanning roots: {[str(r) for r in roots]}")
    else:
        logger.info(f"Scanning default roots: {[str(r) for r in config.roots]}")

    # Run the orchestrator
    async def run():
        orchestrator = Orchestrator(config)
        try:
            stats = await orchestrator.run_full_scan(roots)
            logger.info(f"Scan complete!")
            logger.info(f"Files Indexed: {stats.files_indexed}")
            logger.info(f"Files Deduplicated: {stats.files_deduplicated}")
            logger.info(f"Files Skipped: {stats.files_skipped}")
            logger.info(f"Total Time: {stats.duration_seconds:.2f}s")
            
            # Print legacy status line for app compatibility
            print(f"[Indexer] Result: success")
            
        except Exception as e:
            logger.error(f"Indexing failed: {e}")
            print(f"[Indexer] Result: error")
            sys.exit(1)
        finally:
            orchestrator.close()

    asyncio.run(run())

if __name__ == "__main__":
    main()
