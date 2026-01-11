"""
Orchestrator - Main entry point for the indexing system.

Implements the Cascade Filter architecture for optimized indexing:
- Filter 1: Skip known paths (instant)
- Filter 2: xxHash bytes to detect changes (fast)
- Filter 3: Extract text only for new files (expensive only when needed)
- Filter 4: Embed with ONNX + int8 (optimized)
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import List, Optional, Set

import numpy as np

from .config import get_config, IndexerConfig, set_config
from .models import (
    FileInfo, HashedFile, ExtractedFile, IndexEntry, IndexingStats, 
    DataSource, EntryType
)
from .scanner import Scanner
from .hasher import Hasher
from .extractor import Extractor
from .embedder import Embedder, get_embedder
from .indexer import Indexer, get_indexer
from .watcher import AsyncWatcher, FileChange, ChangeType
from .cloud.icloud import ICloudHandler
from .errors import handle_error, ErrorAction


logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Main orchestrator for the indexing system.
    
    Implements Cascade Filter architecture:
    Scanner → Hasher (xxHash) → Extractor → Embedder (ONNX) → Indexer
    
    Each stage filters out files that don't need further processing,
    minimizing expensive operations.
    """
    
    def __init__(self, config: Optional[IndexerConfig] = None):
        self.config = config or get_config()
        if config:
            set_config(config)
        
        # Initialize components
        self._scanner = Scanner(self.config)
        self._hasher = Hasher(self.config)
        self._extractor = Extractor(self.config)
        self._embedder = get_embedder(self.config)
        self._indexer = get_indexer(self.config)
        self._icloud = ICloudHandler(self.config)
        self._watcher: Optional[AsyncWatcher] = None
    
    async def run_full_scan(
        self, 
        roots: Optional[List[Path]] = None,
        build_leann: bool = True,
    ) -> IndexingStats:
        """
        Run a full scan and index of directories using Cascade Filter.
        
        Cascade Filter stages:
        1. SCAN: Find all files
        2. HASH: xxHash bytes, filter known hashes
        3. EXTRACT: Get text only for new files
        4. EMBED: ONNX + int8 batch embedding
        5. PERSIST: SQLite + LEANN
        
        Args:
            roots: Directories to scan (default: config.roots)
            build_leann: Whether to build LEANN index after DB insert
            
        Returns:
            Statistics about the indexing operation
        """
        roots = roots or self.config.roots
        start_time = time.monotonic()
        stats = IndexingStats()
        
        logger.info(f"Starting Cascade Filter scan of {len(roots)} directories...")
        
        # ═══════════════════════════════════════════════════════════════════
        # PHASE 1: SCAN (Find all files)
        # ═══════════════════════════════════════════════════════════════════
        phase_start = time.monotonic()
        logger.info("Phase 1/5: Scanning files...")
        
        scan_result = await self._scanner.scan(roots)
        stats.files_scanned = len(scan_result.files)
        
        phase_time = time.monotonic() - phase_start
        logger.info(f"Phase 1 complete: {stats.files_scanned} files in {phase_time:.1f}s")
        
        # ═══════════════════════════════════════════════════════════════════
        # PHASE 2: HASH (xxHash bytes, filter known)
        # ═══════════════════════════════════════════════════════════════════
        phase_start = time.monotonic()
        logger.info("Phase 2/5: Hashing files (xxHash)...")
        
        # Get existing hashes for the cascade filter
        existing_hashes = self._indexer.get_existing_hashes()
        
        # Hash all files - this sets is_known flag based on existing_hashes
        hashed_files = await self._hasher.hash_files(
            scan_result.files, 
            existing_hashes
        )
        
        # CASCADE FILTER: Split into new vs known
        new_files = [hf for hf in hashed_files if not hf.is_known]
        known_files = [hf for hf in hashed_files if hf.is_known]
        
        stats.files_deduplicated = len(known_files)
        stats.files_skipped = len(known_files)
        
        phase_time = time.monotonic() - phase_start
        logger.info(
            f"Phase 2 complete: {len(new_files)} new, "
            f"{len(known_files)} known (skipped) in {phase_time:.1f}s"
        )
        
        # ═══════════════════════════════════════════════════════════════════
        # PHASE 3: EXTRACT (Text extraction - only for new files)
        # ═══════════════════════════════════════════════════════════════════
        extracted_files: List[ExtractedFile] = []
        
        if new_files:
            phase_start = time.monotonic()
            logger.info(f"Phase 3/5: Extracting text from {len(new_files)} new files...")
            
            extracted_files = await self._extractor.extract_files(new_files)
            
            phase_time = time.monotonic() - phase_start
            logger.info(f"Phase 3 complete: {len(extracted_files)} files extracted in {phase_time:.1f}s")
        else:
            logger.info("Phase 3/5: Skipped (no new files)")
        
        # ═══════════════════════════════════════════════════════════════════
        # PHASE 4: EMBED (ONNX + int8 batch embedding)
        # ═══════════════════════════════════════════════════════════════════
        if extracted_files:
            phase_start = time.monotonic()
            logger.info("Phase 4/5: Creating entries and embedding...")
            
            all_entries: List[IndexEntry] = []
            
            for ef in extracted_files:
                source = self._get_source(ef.info.path)
                entries = self._embedder.create_entries_from_file(ef, source)
                all_entries.extend(entries)
            
            # Batch embed all texts
            texts = [e.text for e in all_entries]
            logger.info(f"Embedding {len(texts)} texts (ONNX + int8)...")
            embeddings = self._embedder.embed_texts(texts)
            
            phase_time = time.monotonic() - phase_start
            logger.info(f"Phase 4 complete: {len(texts)} embeddings in {phase_time:.1f}s")
            
            # ═══════════════════════════════════════════════════════════════════
            # PHASE 5: PERSIST (SQLite + LEANN)
            # ═══════════════════════════════════════════════════════════════════
            phase_start = time.monotonic()
            logger.info("Phase 5/5: Writing to database...")
            
            db_stats = self._indexer.bulk_insert_entries(all_entries, embeddings)
            stats.files_indexed = db_stats.files_indexed
            stats.chunks_created = db_stats.chunks_created
            
        else:
            logger.info("Phase 4/5: Skipped (no files to embed)")
            logger.info("Phase 5/5: Skipped (nothing to persist)")
        
        # Handle known files - update paths if they've moved
        # (CAS model: content stays, paths can change)
        if known_files:
            logger.info(f"Updating {len(known_files)} known file paths...")
            for hf in known_files:
                # Just ensure the path record exists
                # The bulk_insert handles ON CONFLICT
                source = self._get_source(hf.info.path)
                entry = IndexEntry(
                    text=f"{hf.info.name}",
                    entry_type=EntryType.FILE,
                    source=source,
                    file_path=str(hf.info.path),
                    file_name=hf.info.name,
                    folder=str(hf.info.path.parent),
                    content_hash=hf.binary_hash,
                    extra_metadata={"extension": hf.info.extension}
                )
                # Embed just the filename (fast)
                emb = self._embedder.embed_text(entry.text)
                self._indexer.bulk_insert_entries([entry], np.array([emb]))
        
        # Remove stale paths (files that no longer exist)
        current_paths = {str(hf.info.path) for hf in hashed_files}
        removed = self._indexer.remove_stale_paths(current_paths)
        if removed:
            logger.info(f"Removed {removed} stale paths")
        
        # Build LEANN index
        if build_leann:
            phase_start = time.monotonic()
            logger.info("Building LEANN index...")
            self._indexer.build_leann_index()
            phase_time = time.monotonic() - phase_start
            logger.info(f"LEANN index built in {phase_time:.1f}s")
        
        # Final stats
        stats.duration_seconds = time.monotonic() - start_time
        logger.info(f"Cascade Filter scan complete: {stats}")
        
        return stats
    
    async def run_incremental(
        self,
        changes: List[FileChange],
    ) -> IndexingStats:
        """
        Process incremental file changes using Cascade Filter.
        
        Called by the watcher when files change.
        """
        stats = IndexingStats()
        start_time = time.monotonic()
        
        # Separate by change type
        added_modified = [c for c in changes if c.change_type in {ChangeType.ADDED, ChangeType.MODIFIED}]
        deleted = [c for c in changes if c.change_type == ChangeType.DELETED]
        moved = [c for c in changes if c.change_type == ChangeType.MOVED]
        
        # Handle deletions
        if deleted:
            paths = {str(c.path) for c in deleted}
            all_paths = self._indexer.get_existing_paths()
            self._indexer.remove_stale_paths(all_paths - paths)
        
        # Handle moves (CAS: old path removed, new path added)
        for change in moved:
            if change.old_path:
                # Remove old path
                old_paths = self._indexer.get_existing_paths()
                self._indexer.remove_stale_paths(old_paths - {str(change.old_path)})
        
        # Handle added/modified - use cascade filter
        if added_modified:
            file_infos = []
            for change in added_modified:
                if change.path.exists():
                    stat = change.path.stat()
                    file_infos.append(FileInfo.from_path(
                        change.path, stat.st_mtime, stat.st_size
                    ))
            
            if file_infos:
                # Phase 2: Hash
                existing_hashes = self._indexer.get_existing_hashes()
                hashed = await self._hasher.hash_files(file_infos, existing_hashes)
                
                # Filter to new content
                new_files = [hf for hf in hashed if not hf.is_known]
                
                if new_files:
                    # Phase 3: Extract
                    extracted = await self._extractor.extract_files(new_files)
                    
                    # Phase 4: Embed
                    all_entries = []
                    for ef in extracted:
                        source = self._get_source(ef.info.path)
                        entries = self._embedder.create_entries_from_file(ef, source)
                        all_entries.extend(entries)
                    
                    if all_entries:
                        # Phase 5: Persist
                        texts = [e.text for e in all_entries]
                        embeddings = self._embedder.embed_texts(texts)
                        db_stats = self._indexer.bulk_insert_entries(all_entries, embeddings)
                        stats.files_indexed = db_stats.files_indexed
                        stats.chunks_created = db_stats.chunks_created
        
        stats.duration_seconds = time.monotonic() - start_time
        logger.info(f"Incremental update: {stats}")
        
        return stats
    
    async def start_watching(self, roots: Optional[List[Path]] = None):
        """
        Start the file watcher for real-time updates.
        
        This runs indefinitely until stop_watching() is called.
        """
        roots = roots or self.config.roots
        
        self._watcher = AsyncWatcher(self.config)
        self._watcher.start(roots)
        
        logger.info("Started file watching")
        
        async for batch in self._watcher.changes():
            await self.run_incremental(batch)
    
    def stop_watching(self):
        """Stop the file watcher."""
        if self._watcher:
            self._watcher.stop()
            self._watcher = None
    
    def _get_source(self, path: Path) -> DataSource:
        """Determine the data source for a file path."""
        try:
            path.relative_to(self._icloud.icloud_root)
            return DataSource.ICLOUD
        except ValueError:
            pass
        
        try:
            path.relative_to(Path.home() / "Documents")
            return DataSource.DOCUMENTS
        except ValueError:
            pass
        
        return DataSource.DESKTOP
    
    def close(self):
        """Clean up resources."""
        self.stop_watching()
        self._hasher.close()
        self._extractor.close()
        self._indexer.close()


async def run_full_scan(
    roots: Optional[List[Path]] = None,
    config: Optional[IndexerConfig] = None,
) -> IndexingStats:
    """
    Convenience function to run a full scan.
    
    Usage:
        stats = await run_full_scan()
        print(stats)
    """
    orchestrator = Orchestrator(config)
    try:
        return await orchestrator.run_full_scan(roots)
    finally:
        orchestrator.close()


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Cascade Filter file indexer")
    parser.add_argument("--roots", nargs="+", help="Directories to index")
    parser.add_argument("--force", action="store_true", help="Force rebuild")
    parser.add_argument("--watch", action="store_true", help="Watch for changes")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="[%(levelname)s] %(name)s: %(message)s"
    )
    
    # Parse roots
    roots = None
    if args.roots:
        roots = [Path(r).expanduser().resolve() for r in args.roots]
    
    # Run
    async def _main():
        orchestrator = Orchestrator()
        
        try:
            # Full scan
            stats = await orchestrator.run_full_scan(roots)
            print(f"\n{stats}")
            
            # Watch mode
            if args.watch:
                print("\nWatching for changes (Ctrl+C to stop)...")
                await orchestrator.start_watching(roots)
                
        except KeyboardInterrupt:
            print("\nStopped.")
        finally:
            orchestrator.close()
    
    asyncio.run(_main())


if __name__ == "__main__":
    main()
