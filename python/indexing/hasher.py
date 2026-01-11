"""
Hasher - Fast content hashing using xxHash.

Uses xxHash (2.5GB/s) instead of SHA256 (500MB/s) for 5x faster hashing.
Hashes raw file bytes only - text extraction is handled separately
by the Extractor module (cascade filter design).
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Set

try:
    import xxhash
    _USE_XXHASH = True
except ImportError:
    import hashlib
    _USE_XXHASH = False
    logging.getLogger(__name__).warning(
        "xxhash not installed. Using SHA256 (slower). "
        "Install with: pip install xxhash"
    )

from .config import get_config, IndexerConfig
from .models import FileInfo, HashedFile
from .errors import handle_error, ErrorAction


logger = logging.getLogger(__name__)


class Hasher:
    """
    Fast content hasher using xxHash.
    
    This is part of the Cascade Filter architecture - it only hashes
    raw file bytes without extracting text. Text extraction happens
    later in the Extractor module, only for files that pass the hash filter.
    """
    
    def __init__(self, config: IndexerConfig | None = None):
        self.config = config or get_config()
        self._executor: ThreadPoolExecutor | None = None
    
    def _get_executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self.config.hasher_concurrency,
                thread_name_prefix="hasher"
            )
        return self._executor
    
    async def hash_files(
        self, 
        files: List[FileInfo],
        existing_hashes: Optional[Set[str]] = None,
    ) -> List[HashedFile]:
        """
        Hash multiple files in parallel using xxHash.
        
        This is a fast operation - only reads file bytes and computes hash.
        No text extraction is performed here (cascade filter design).
        
        Args:
            files: List of FileInfo to hash
            existing_hashes: Set of hashes already in the database
                            (used to set is_known flag for filtering)
            
        Returns:
            List of HashedFile with binary_hash and is_known flag
        """
        if not files:
            return []
        
        existing_hashes = existing_hashes or set()
        loop = asyncio.get_event_loop()
        executor = self._get_executor()
        
        BATCH_SIZE = 2000  # Large batch since hashing is fast
        all_hashed: List[HashedFile] = []
        
        for i in range(0, len(files), BATCH_SIZE):
            batch = files[i:i + BATCH_SIZE]
            
            tasks = [
                loop.run_in_executor(
                    executor, 
                    self._hash_file_sync, 
                    file_info,
                    existing_hashes,
                )
                for file_info in batch
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, HashedFile):
                    all_hashed.append(result)
                elif isinstance(result, Exception):
                    # Already logged in _hash_file_sync
                    pass
        
        known_count = sum(1 for h in all_hashed if h.is_known)
        new_count = len(all_hashed) - known_count
        logger.info(f"Hashed {len(all_hashed)} files: {known_count} known, {new_count} new")
        
        return all_hashed
    
    def _hash_file_sync(
        self, 
        file_info: FileInfo,
        existing_hashes: Set[str],
    ) -> HashedFile:
        """
        Synchronous file hashing (runs in thread pool).
        
        Uses xxHash for 5x faster hashing than SHA256.
        """
        path = file_info.path
        
        try:
            binary_hash = self._compute_hash(path)
            is_known = binary_hash in existing_hashes
            
            return HashedFile(
                info=file_info,
                binary_hash=binary_hash,
                is_known=is_known,
            )
            
        except Exception as e:
            handle_error(e, path, "hash_file")
            raise
    
    def _compute_hash(self, path: Path) -> str:
        """
        Compute hash of file bytes.
        
        Uses xxHash (2.5GB/s) when available, SHA256 (500MB/s) as fallback.
        """
        if _USE_XXHASH:
            hasher = xxhash.xxh64()
        else:
            import hashlib
            hasher = hashlib.sha256()
        
        # Read in 64KB chunks for memory efficiency
        with open(path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        
        return hasher.hexdigest()
    
    async def hash_file(self, file_info: FileInfo) -> Optional[HashedFile]:
        """
        Hash a single file.
        
        Args:
            file_info: File to hash
            
        Returns:
            HashedFile or None if hashing failed
        """
        results = await self.hash_files([file_info])
        return results[0] if results else None
    
    def close(self):
        """Shutdown the thread pool."""
        if self._executor:
            self._executor.shutdown(wait=False)
            self._executor = None


async def hash_files(
    files: List[FileInfo],
    existing_hashes: Optional[Set[str]] = None,
    config: IndexerConfig | None = None,
) -> List[HashedFile]:
    """
    Convenience function to hash files.
    
    Usage:
        hashed = await hash_files(file_infos, existing_hashes)
        new_files = [h for h in hashed if not h.is_known]
        print(f"{len(new_files)} new files to process")
    """
    hasher = Hasher(config)
    try:
        return await hasher.hash_files(files, existing_hashes)
    finally:
        hasher.close()
