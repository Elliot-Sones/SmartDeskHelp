"""
Watcher Tests - Verify file change detection and debouncing.

Tests:
- Change detection (add, modify, delete)
- Skip pattern filtering
- Debounce behavior (batching rapid changes)
"""

import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from indexing.watcher import Watcher, AsyncWatcher, ChangeType, FileChange
from indexing.config import IndexerConfig


class TestWatcher:
    """Tests for the Watcher class."""
    
    @pytest.fixture
    def watcher(self, test_config):
        w = Watcher(test_config)
        yield w
        w.stop()
    
    def test_watcher_creates(self, watcher):
        """Watcher initializes correctly."""
        assert watcher is not None
        assert watcher._running is False
    
    def test_should_skip_ds_store(self, watcher):
        """Watcher skips .DS_Store files."""
        assert watcher._should_skip(Path("/tmp/.DS_Store"))
    
    def test_should_skip_hidden(self, watcher):
        """Watcher skips hidden files."""
        assert watcher._should_skip(Path("/tmp/.hidden"))
    
    def test_should_not_skip_icloud_placeholder(self, watcher):
        """Watcher does not skip .icloud placeholder files."""
        assert not watcher._should_skip(Path("/tmp/.file.txt.icloud"))
    
    def test_should_skip_node_modules(self, watcher):
        """Watcher skips files in node_modules."""
        assert watcher._should_skip(Path("/project/node_modules/package/index.js"))
    
    def test_should_skip_git(self, watcher):
        """Watcher skips files in .git directories."""
        assert watcher._should_skip(Path("/project/.git/objects/abc"))
    
    def test_should_not_skip_normal_file(self, watcher):
        """Watcher does not skip normal files."""
        assert not watcher._should_skip(Path("/tmp/document.pdf"))
        assert not watcher._should_skip(Path("/Users/me/Desktop/script.py"))


class TestFileChange:
    """Tests for the FileChange dataclass."""
    
    def test_creates_added_change(self):
        """FileChange creates an ADDED change."""
        change = FileChange(
            path=Path("/tmp/new.txt"),
            change_type=ChangeType.ADDED,
            timestamp=time.monotonic(),
        )
        
        assert change.change_type == ChangeType.ADDED
        assert change.old_path is None
    
    def test_creates_moved_change(self):
        """FileChange creates a MOVED change with old path."""
        change = FileChange(
            path=Path("/tmp/new_location/file.txt"),
            change_type=ChangeType.MOVED,
            timestamp=time.monotonic(),
            old_path=Path("/tmp/old_location/file.txt"),
        )
        
        assert change.change_type == ChangeType.MOVED
        assert change.old_path == Path("/tmp/old_location/file.txt")


class TestWatcherDebounce:
    """Tests for watcher debounce behavior."""
    
    def test_queues_changes(self, test_config):
        """Watcher queues changes for debouncing."""
        watcher = Watcher(test_config)
        
        # Manually queue changes (normally done by watchdog events)
        watcher._queue_change(Path("/tmp/file1.txt"), ChangeType.ADDED)
        watcher._queue_change(Path("/tmp/file2.txt"), ChangeType.MODIFIED)
        
        assert watcher.get_pending_count() == 2
        watcher.stop()
    
    def test_later_change_overrides(self, test_config):
        """Later change to same file overrides earlier change."""
        watcher = Watcher(test_config)
        
        watcher._queue_change(Path("/tmp/file.txt"), ChangeType.ADDED)
        watcher._queue_change(Path("/tmp/file.txt"), ChangeType.MODIFIED)
        
        # Should only have 1 pending (the MODIFIED)
        assert watcher.get_pending_count() == 1
        
        pending = watcher._pending_changes
        assert pending["/tmp/file.txt"].change_type == ChangeType.MODIFIED
        watcher.stop()


class TestAsyncWatcher:
    """Tests for the async watcher interface."""
    
    def test_creates_async_watcher(self, test_config):
        """AsyncWatcher initializes correctly."""
        watcher = AsyncWatcher(test_config)
        assert watcher is not None
        assert hasattr(watcher, "_change_queue")
