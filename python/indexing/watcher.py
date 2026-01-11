"""
Watcher - Real-time file change detection.

Uses watchdog for cross-platform file system monitoring with
debouncing to batch rapid changes.
"""

import asyncio
import logging
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum

from .config import get_config, IndexerConfig


logger = logging.getLogger(__name__)


class ChangeType(Enum):
    """Type of file system change."""
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    MOVED = "moved"


@dataclass
class FileChange:
    """A pending file change event."""
    path: Path
    change_type: ChangeType
    timestamp: float
    old_path: Optional[Path] = None  # For MOVED events


class Watcher:
    """
    Real-time file system watcher with debouncing.
    
    Uses watchdog for cross-platform monitoring. Changes are debounced
    (batched over a time window) to handle rapid saves efficiently.
    """
    
    def __init__(
        self, 
        config: IndexerConfig | None = None,
        on_changes: Optional[Callable[[List[FileChange]], None]] = None,
    ):
        self.config = config or get_config()
        self.on_changes = on_changes
        
        self._observer = None
        self._pending_changes: Dict[str, FileChange] = {}
        self._debounce_task: Optional[asyncio.Task] = None
        self._running = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
    
    def start(self, roots: List[Path] | None = None):
        """
        Start watching directories.
        
        Args:
            roots: Directories to watch (default: config.roots)
        """
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler, FileSystemEvent
        except ImportError:
            logger.error("watchdog not installed. Run: pip install watchdog")
            raise
        
        roots = roots or self.config.roots
        self._loop = asyncio.get_event_loop()
        
        class EventHandler(FileSystemEventHandler):
            def __init__(handler_self):
                handler_self.watcher = self
            
            def on_created(handler_self, event: FileSystemEvent):
                if not event.is_directory:
                    handler_self.watcher._queue_change(
                        Path(event.src_path), ChangeType.ADDED
                    )
            
            def on_modified(handler_self, event: FileSystemEvent):
                if not event.is_directory:
                    handler_self.watcher._queue_change(
                        Path(event.src_path), ChangeType.MODIFIED
                    )
            
            def on_deleted(handler_self, event: FileSystemEvent):
                if not event.is_directory:
                    handler_self.watcher._queue_change(
                        Path(event.src_path), ChangeType.DELETED
                    )
            
            def on_moved(handler_self, event: FileSystemEvent):
                if not event.is_directory:
                    handler_self.watcher._queue_change(
                        Path(event.dest_path), 
                        ChangeType.MOVED,
                        old_path=Path(event.src_path)
                    )
        
        self._observer = Observer()
        handler = EventHandler()
        
        for root in roots:
            if root.exists():
                self._observer.schedule(handler, str(root), recursive=True)
                logger.info(f"Watching: {root}")
            else:
                logger.warning(f"Watch root not found: {root}")
        
        self._running = True
        self._observer.start()
        logger.info("File watcher started")
    
    def stop(self):
        """Stop watching."""
        self._running = False
        
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=2)
            self._observer = None
        
        if self._debounce_task:
            self._debounce_task.cancel()
            self._debounce_task = None
        
        logger.info("File watcher stopped")
    
    def _queue_change(
        self, 
        path: Path, 
        change_type: ChangeType,
        old_path: Optional[Path] = None,
    ):
        """Queue a change for debounced processing."""
        # Skip files that match skip patterns
        if self._should_skip(path):
            return
        
        change = FileChange(
            path=path,
            change_type=change_type,
            timestamp=time.monotonic(),
            old_path=old_path,
        )
        
        # Use path as key - later events override earlier ones
        self._pending_changes[str(path)] = change
        
        # Schedule flush
        self._schedule_flush()
    
    def _schedule_flush(self):
        """Schedule a debounced flush of pending changes."""
        if self._debounce_task and not self._debounce_task.done():
            # Already scheduled
            return
        
        if self._loop:
            self._debounce_task = self._loop.create_task(self._flush_after_delay())
    
    async def _flush_after_delay(self):
        """Wait for debounce period then flush changes."""
        await asyncio.sleep(self.config.debounce_ms / 1000.0)
        await self._flush_changes()
    
    async def _flush_changes(self):
        """Process all pending changes."""
        if not self._pending_changes:
            return
        
        # Grab pending changes
        changes = list(self._pending_changes.values())
        self._pending_changes.clear()
        
        logger.info(f"Processing {len(changes)} file changes")
        
        # Call handler
        if self.on_changes:
            try:
                self.on_changes(changes)
            except Exception as e:
                logger.error(f"Change handler error: {e}")
    
    def _should_skip(self, path: Path) -> bool:
        """Check if a path should be skipped."""
        name = path.name
        
        # Skip system files
        if name in {".DS_Store", "Thumbs.db", "desktop.ini"}:
            return True
        
        # Skip hidden files (except iCloud placeholders)
        if name.startswith(".") and not name.endswith(".icloud"):
            return True
        
        # Check if any parent is in skip list
        for part in path.parts:
            if part in self.config.skip_dirs:
                return True
        
        # Check extension
        ext = path.suffix.lower()
        if ext in self.config.skip_extensions:
            return True
        
        return False
    
    def get_pending_count(self) -> int:
        """Get number of pending changes."""
        return len(self._pending_changes)


class AsyncWatcher(Watcher):
    """
    Async-friendly version of the watcher.
    
    Provides an async generator interface for processing changes.
    """
    
    def __init__(self, config: IndexerConfig | None = None):
        super().__init__(config)
        self._change_queue: asyncio.Queue[List[FileChange]] = asyncio.Queue()
        self.on_changes = self._enqueue_changes
    
    def _enqueue_changes(self, changes: List[FileChange]):
        """Put changes in the async queue."""
        if self._loop:
            self._loop.call_soon_threadsafe(
                self._change_queue.put_nowait, changes
            )
    
    async def changes(self):
        """
        Async generator that yields batches of changes.
        
        Usage:
            watcher = AsyncWatcher()
            watcher.start()
            
            async for batch in watcher.changes():
                for change in batch:
                    print(f"{change.change_type}: {change.path}")
        """
        while self._running:
            try:
                batch = await asyncio.wait_for(
                    self._change_queue.get(), 
                    timeout=1.0
                )
                yield batch
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break


def create_watcher(
    config: IndexerConfig | None = None,
    async_mode: bool = True,
) -> Watcher:
    """
    Create a file watcher.
    
    Args:
        config: Configuration (default: global config)
        async_mode: If True, return AsyncWatcher for async iteration
        
    Returns:
        Watcher or AsyncWatcher instance
    """
    if async_mode:
        return AsyncWatcher(config)
    return Watcher(config)
