"""
Indexer Tests - Verify database operations and CAS behavior.

Tests:
- Bulk insert operations
- Content deduplication by hash
- Path updates when files move
- Stale path cleanup
"""

import asyncio
from datetime import datetime
from pathlib import Path

import pytest
import numpy as np

from indexing.indexer import Indexer, get_indexer
from indexing.models import IndexEntry, EntryType, DataSource
from indexing.config import IndexerConfig


class TestIndexer:
    """Tests for the Indexer class."""
    
    @pytest.fixture
    def indexer(self, test_config):
        """Create an indexer instance."""
        idx = Indexer(test_config)
        yield idx
        idx.close()
    
    def test_creates_tables(self, indexer):
        """Indexer creates required tables on init."""
        conn = indexer._get_connection()
        
        # Check tables exist
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        tables = {row[0] for row in cursor.fetchall()}
        
        assert "content" in tables
        assert "paths" in tables
        assert "chunks" in tables
    
    def test_bulk_insert_single_file(self, indexer):
        """Indexer inserts a single file entry."""
        entry = IndexEntry(
            text="test.txt - text file",
            entry_type=EntryType.FILE,
            source=DataSource.DESKTOP,
            file_path="/tmp/test.txt",
            file_name="test.txt",
            folder="tmp",
            content_hash="abc123",
            extra_metadata={"extension": ".txt"},
        )
        
        embedding = np.random.randn(384).astype(np.float32)
        
        stats = indexer.bulk_insert_entries([entry], np.array([embedding]))
        
        assert stats.files_indexed == 1
    
    def test_bulk_insert_with_chunks(self, indexer):
        """Indexer inserts file and chunk entries together."""
        entries = [
            IndexEntry(
                text="document.pdf - PDF document file",
                entry_type=EntryType.FILE,
                source=DataSource.DESKTOP,
                file_path="/tmp/document.pdf",
                file_name="document.pdf",
                folder="tmp",
                content_hash="hash123",
            ),
            IndexEntry(
                text="This is the first chunk of content.",
                entry_type=EntryType.CHUNK,
                source=DataSource.DESKTOP,
                file_path="/tmp/document.pdf",
                file_name="document.pdf",
                folder="tmp",
                chunk_index=0,
                content_hash="hash123",
            ),
            IndexEntry(
                text="This is the second chunk of content.",
                entry_type=EntryType.CHUNK,
                source=DataSource.DESKTOP,
                file_path="/tmp/document.pdf",
                file_name="document.pdf",
                folder="tmp",
                chunk_index=1,
                content_hash="hash123",
            ),
        ]
        
        embeddings = np.random.randn(3, 384).astype(np.float32)
        
        stats = indexer.bulk_insert_entries(entries, embeddings)
        
        assert stats.files_indexed == 1
        assert stats.chunks_created == 2
    
    def test_deduplicates_by_hash(self, indexer):
        """Indexer deduplicates content with same hash."""
        # Insert first file
        entry1 = IndexEntry(
            text="original.txt - text file",
            entry_type=EntryType.FILE,
            source=DataSource.DESKTOP,
            file_path="/tmp/original.txt",
            file_name="original.txt",
            folder="tmp",
            content_hash="same_hash_123",
        )
        embeddings1 = np.random.randn(1, 384).astype(np.float32)
        indexer.bulk_insert_entries([entry1], embeddings1)
        
        # Insert second file with same hash (different path)
        entry2 = IndexEntry(
            text="copy.txt - text file",
            entry_type=EntryType.FILE,
            source=DataSource.DESKTOP,
            file_path="/tmp/copy.txt",
            file_name="copy.txt",
            folder="tmp",
            content_hash="same_hash_123",  # Same hash!
        )
        embeddings2 = np.random.randn(1, 384).astype(np.float32)
        stats = indexer.bulk_insert_entries([entry2], embeddings2)
        
        assert stats.files_deduplicated == 1
        
        # Both paths should exist
        paths = indexer.get_existing_paths()
        assert "/tmp/original.txt" in paths
        assert "/tmp/copy.txt" in paths
        
        # But only one content record
        hashes = indexer.get_existing_hashes()
        assert len(hashes) == 1
    
    def test_updates_path_when_moved(self, indexer):
        """Indexer updates path when file moves (same hash, new path)."""
        # Insert original
        entry1 = IndexEntry(
            text="file.txt - text file",
            entry_type=EntryType.FILE,
            source=DataSource.DESKTOP,
            file_path="/tmp/old/file.txt",
            file_name="file.txt",
            folder="tmp/old",
            content_hash="file_hash",
        )
        embeddings = np.random.randn(1, 384).astype(np.float32)
        indexer.bulk_insert_entries([entry1], embeddings)
        
        # Insert at new location with same hash
        # (simulates what orchestrator does after removing old path)
        entry2 = IndexEntry(
            text="file.txt - text file",
            entry_type=EntryType.FILE,
            source=DataSource.DESKTOP,
            file_path="/tmp/new/file.txt",
            file_name="file.txt",
            folder="tmp/new",
            content_hash="file_hash",  # Same hash
        )
        stats = indexer.bulk_insert_entries([entry2], embeddings)
        
        # Should be deduplicated (content exists)
        assert stats.files_deduplicated == 1
        
        # Both paths exist until stale removal
        paths = indexer.get_existing_paths()
        assert "/tmp/new/file.txt" in paths
    
    def test_removes_stale_paths(self, indexer):
        """Indexer removes paths that no longer exist."""
        # Insert two files
        entries = [
            IndexEntry(
                text="keep.txt",
                entry_type=EntryType.FILE,
                source=DataSource.DESKTOP,
                file_path="/tmp/keep.txt",
                file_name="keep.txt",
                folder="tmp",
                content_hash="hash1",
            ),
            IndexEntry(
                text="delete.txt",
                entry_type=EntryType.FILE,
                source=DataSource.DESKTOP,
                file_path="/tmp/delete.txt",
                file_name="delete.txt",
                folder="tmp",
                content_hash="hash2",
            ),
        ]
        embeddings = np.random.randn(2, 384).astype(np.float32)
        indexer.bulk_insert_entries(entries, embeddings)
        
        # Remove one
        removed = indexer.remove_stale_paths({"/tmp/keep.txt"})
        
        assert removed == 1
        
        paths = indexer.get_existing_paths()
        assert "/tmp/keep.txt" in paths
        assert "/tmp/delete.txt" not in paths
    
    def test_find_content_by_hash(self, indexer):
        """Indexer finds content by hash."""
        entry = IndexEntry(
            text="findme.txt",
            entry_type=EntryType.FILE,
            source=DataSource.DESKTOP,
            file_path="/tmp/findme.txt",
            file_name="findme.txt",
            folder="tmp",
            content_hash="searchable_hash",
        )
        embeddings = np.random.randn(1, 384).astype(np.float32)
        indexer.bulk_insert_entries([entry], embeddings)
        
        # Find it
        content_id = indexer.find_content_by_hash("searchable_hash")
        assert content_id is not None
        
        # Non-existent hash returns None
        assert indexer.find_content_by_hash("nonexistent") is None


class TestIndexerBulkOperations:
    """Tests for bulk operation performance."""
    
    @pytest.fixture
    def indexer(self, test_config):
        idx = Indexer(test_config)
        yield idx
        idx.close()
    
    def test_bulk_insert_many(self, indexer):
        """Indexer handles bulk inserts efficiently."""
        entries = []
        for i in range(100):
            entries.append(IndexEntry(
                text=f"file_{i}.txt - text file",
                entry_type=EntryType.FILE,
                source=DataSource.DESKTOP,
                file_path=f"/tmp/file_{i}.txt",
                file_name=f"file_{i}.txt",
                folder="tmp",
                content_hash=f"hash_{i}",
            ))
        
        embeddings = np.random.randn(100, 384).astype(np.float32)
        
        stats = indexer.bulk_insert_entries(entries, embeddings)
        
        assert stats.files_indexed == 100
        assert len(indexer.get_existing_paths()) == 100
