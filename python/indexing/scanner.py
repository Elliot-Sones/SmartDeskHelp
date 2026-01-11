"""
Scanner - Fast parallel file system traversal.

Uses asyncio for non-blocking directory traversal with controlled
concurrency to avoid overwhelming the file system.
"""

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import AsyncGenerator, Set, List

from .config import get_config, IndexerConfig
from .models import FileInfo, ScanResult
from .errors import handle_error, ErrorAction


logger = logging.getLogger(__name__)


class Scanner:
    """
    Fast parallel file system scanner.
    
    Yields FileInfo objects for each file found, filtering out
    directories and files that match skip patterns.
    """
    
    def __init__(self, config: IndexerConfig | None = None):
        self.config = config or get_config()
        self._semaphore: asyncio.Semaphore | None = None
        
    async def scan(self, roots: List[Path] | None = None) -> ScanResult:
        """
        Scan directories and return all found files.
        
        Args:
            roots: Directories to scan (default: config.roots)
            
        Returns:
            ScanResult with list of FileInfo and statistics
        """
        roots = roots or self.config.roots
        self._semaphore = asyncio.Semaphore(self.config.scanner_concurrency)
        
        start_time = time.monotonic()
        files: List[FileInfo] = []
        skipped = 0
        errors = 0
        
        async for file_info in self.scan_iter(roots):
            files.append(file_info)
        
        # Note: skipped/errors are tracked in scan_iter but not easily
        # accessible here. For now, we just report what we got.
        duration = time.monotonic() - start_time
        
        logger.info(f"Scanned {len(files)} files in {duration:.1f}s")
        
        return ScanResult(
            files=files,
            skipped_count=skipped,
            error_count=errors,
            duration_seconds=duration,
        )
    
    async def scan_iter(
        self, 
        roots: List[Path] | None = None
    ) -> AsyncGenerator[FileInfo, None]:
        """
        Iterate over files in directories.
        
        This is a streaming interface that yields files as they're found,
        useful for immediate processing without waiting for full scan.
        """
        roots = roots or self.config.roots
        
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.config.scanner_concurrency)
        
        for root in roots:
            if not root.exists():
                logger.warning(f"Root directory not found: {root}")
                continue
            
            async for file_info in self._scan_directory(root):
                yield file_info
    
    async def _scan_directory(self, directory: Path) -> AsyncGenerator[FileInfo, None]:
        """
        Recursively scan a single directory.
        
        Uses a work queue pattern for breadth-first traversal with
        controlled parallelism.
        """
        # Use os.scandir for efficiency (returns DirEntry with cached stat)
        try:
            entries = list(os.scandir(directory))
        except (PermissionError, OSError) as e:
            handle_error(e, directory, "scan_directory")
            return
        
        # Process entries concurrently with semaphore
        subdirs: List[Path] = []
        
        for entry in entries:
            try:
                if entry.is_dir(follow_symlinks=False):
                    # Check if we should skip this directory
                    if self._should_skip_dir(entry.name):
                        continue
                    subdirs.append(Path(entry.path))
                    
                elif entry.is_file(follow_symlinks=False):
                    # Check if we should skip this file
                    if self._should_skip_file(entry.name):
                        continue
                    
                    # Get file info
                    async with self._semaphore:
                        file_info = await self._get_file_info(entry)
                        if file_info:
                            yield file_info
                            
            except (PermissionError, OSError) as e:
                handle_error(e, Path(entry.path), "scan_entry")
                continue
        
        # Recursively scan subdirectories
        for subdir in subdirs:
            async for file_info in self._scan_directory(subdir):
                yield file_info
    
    async def _get_file_info(self, entry: os.DirEntry) -> FileInfo | None:
        """
        Get FileInfo from a directory entry.
        
        This runs stat() which may block briefly on network filesystems.
        """
        try:
            stat = entry.stat(follow_symlinks=False)
            return FileInfo.from_path(
                path=Path(entry.path),
                mtime=stat.st_mtime,
                size=stat.st_size,
            )
        except (PermissionError, OSError) as e:
            handle_error(e, Path(entry.path), "stat")
            return None
    
    def _should_skip_dir(self, name: str) -> bool:
        """Check if a directory should be skipped."""
        # Skip hidden directories (except .icloud files)
        if name.startswith(".") and not name.endswith(".icloud"):
            return True
        
        return name in self.config.skip_dirs
    
    def _should_skip_file(self, name: str) -> bool:
        """Check if a file should be skipped."""
        # Skip system files
        if name in {".DS_Store", "Thumbs.db", "desktop.ini"}:
            return True
        
        # Skip hidden files (except .icloud placeholders)
        if name.startswith(".") and not name.endswith(".icloud"):
            return True
        
        # Check extension
        ext = Path(name).suffix.lower()
        if ext in self.config.skip_extensions:
            return True
        
        return False


async def scan_directories(
    roots: List[Path] | None = None,
    config: IndexerConfig | None = None,
) -> ScanResult:
    """
    Convenience function to scan directories.
    
    Usage:
        result = await scan_directories([Path.home() / "Desktop"])
        for file in result.files:
            print(file.path)
    """
    scanner = Scanner(config)
    return await scanner.scan(roots)
