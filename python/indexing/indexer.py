"""
Indexer - Database and LEANN index writer.

Handles bulk inserts into SQLite (CAS tables) and building/updating
the LEANN vector index.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple, Set
import numpy as np

from .config import get_config, IndexerConfig
from .models import (
    ContentRecord, PathRecord, ChunkRecord, 
    IndexEntry, EntryType, DataSource, SyncStatus, IndexingStats
)
from .embedder import get_embedder


logger = logging.getLogger(__name__)


class Indexer:
    """
    Database and vector index writer.
    
    Uses Content-Addressable Storage (CAS) pattern:
    - Content table: unique content by hash
    - Paths table: file paths pointing to content
    """
    
    def __init__(self, config: IndexerConfig | None = None):
        self.config = config or get_config()
        self._conn: Optional[sqlite3.Connection] = None
        self._embedder = get_embedder(config)
        self._leann_builder = None
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get or create database connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.config.db_path))
            self._conn.row_factory = sqlite3.Row
            # Performance optimizations
            self._conn.execute("PRAGMA journal_mode = WAL")
            self._conn.execute("PRAGMA synchronous = NORMAL")
            self._conn.execute("PRAGMA cache_size = -64000")  # 64MB cache
            self._init_tables()
        return self._conn
    
    def _init_tables(self):
        """Create CAS tables if they don't exist."""
        conn = self._conn
        conn.executescript("""
            -- Content-Addressable Storage
            CREATE TABLE IF NOT EXISTS content (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_hash TEXT NOT NULL UNIQUE,
                embedding BLOB,
                first_line TEXT,
                size_bytes INTEGER NOT NULL,
                indexed_at INTEGER NOT NULL
            );
            
            CREATE INDEX IF NOT EXISTS idx_content_hash ON content(content_hash);
            
            -- Path pointers
            CREATE TABLE IF NOT EXISTS paths (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_id INTEGER NOT NULL,
                path TEXT NOT NULL UNIQUE,
                file_name TEXT NOT NULL,
                extension TEXT,
                source TEXT NOT NULL,
                sync_status TEXT DEFAULT 'local',
                last_verified INTEGER NOT NULL,
                FOREIGN KEY (content_id) REFERENCES content(id) ON DELETE CASCADE
            );
            
            CREATE INDEX IF NOT EXISTS idx_paths_content ON paths(content_id);
            CREATE INDEX IF NOT EXISTS idx_paths_source ON paths(source);
            
            -- Content chunks for deep search
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                embedding BLOB,
                FOREIGN KEY (content_id) REFERENCES content(id) ON DELETE CASCADE
            );
            
            CREATE INDEX IF NOT EXISTS idx_chunks_content ON chunks(content_id);
        """)
        conn.commit()
    
    def get_existing_hashes(self) -> Set[str]:
        """Get all content hashes currently in the database."""
        conn = self._get_connection()
        cursor = conn.execute("SELECT content_hash FROM content")
        return {row[0] for row in cursor.fetchall()}
    
    def get_existing_paths(self) -> Set[str]:
        """Get all file paths currently in the database."""
        conn = self._get_connection()
        cursor = conn.execute("SELECT path FROM paths")
        return {row[0] for row in cursor.fetchall()}
    
    def find_content_by_hash(self, content_hash: str) -> Optional[int]:
        """Find content ID by hash. Returns None if not found."""
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT id FROM content WHERE content_hash = ?",
            (content_hash,)
        )
        row = cursor.fetchone()
        return row[0] if row else None
    
    def bulk_insert_entries(
        self, 
        entries: List[IndexEntry],
        embeddings: np.ndarray,
    ) -> IndexingStats:
        """
        Insert multiple entries in a single transaction.
        
        Args:
            entries: Index entries to insert
            embeddings: Corresponding embeddings (same order)
            
        Returns:
            Statistics about the operation
        """
        stats = IndexingStats()
        conn = self._get_connection()
        
        # Group entries by file (content_hash)
        file_entries: dict[str, List[Tuple[IndexEntry, np.ndarray]]] = {}
        for entry, emb in zip(entries, embeddings):
            key = entry.content_hash or entry.file_path
            if key not in file_entries:
                file_entries[key] = []
            file_entries[key].append((entry, emb))
        
        now = int(datetime.now().timestamp())
        
        try:
            with conn:
                for hash_key, group in file_entries.items():
                    # Find the FILE entry in this group
                    file_entry = next(
                        (e for e, _ in group if e.entry_type == EntryType.FILE),
                        None
                    )
                    if not file_entry:
                        continue
                    
                    file_embedding = next(
                        (emb for e, emb in group if e.entry_type == EntryType.FILE),
                        None
                    )
                    
                    # Check if content already exists
                    existing_id = self.find_content_by_hash(file_entry.content_hash)
                    
                    if existing_id:
                        content_id = existing_id
                        stats.files_deduplicated += 1
                    else:
                        # Insert new content
                        cursor = conn.execute(
                            """
                            INSERT INTO content (content_hash, embedding, first_line, size_bytes, indexed_at)
                            VALUES (?, ?, ?, ?, ?)
                            """,
                            (
                                file_entry.content_hash,
                                self._embedder.serialize_embedding(file_embedding) if file_embedding is not None else None,
                                file_entry.extra_metadata.get("first_line", ""),
                                file_entry.extra_metadata.get("size", 0),
                                now,
                            )
                        )
                        content_id = cursor.lastrowid
                        stats.files_indexed += 1
                    
                    # Insert or update path
                    conn.execute(
                        """
                        INSERT INTO paths (content_id, path, file_name, extension, source, sync_status, last_verified)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(path) DO UPDATE SET
                            content_id = excluded.content_id,
                            last_verified = excluded.last_verified
                        """,
                        (
                            content_id,
                            file_entry.file_path,
                            file_entry.file_name,
                            file_entry.extra_metadata.get("extension", ""),
                            file_entry.source.value,
                            SyncStatus.LOCAL.value,
                            now,
                        )
                    )
                    
                    # Insert chunks
                    chunk_entries = [
                        (e, emb) for e, emb in group if e.entry_type == EntryType.CHUNK
                    ]
                    if chunk_entries:
                        # Delete old chunks for this content
                        conn.execute("DELETE FROM chunks WHERE content_id = ?", (content_id,))
                        
                        # Insert new chunks
                        for entry, emb in chunk_entries:
                            conn.execute(
                                """
                                INSERT INTO chunks (content_id, chunk_index, text, embedding)
                                VALUES (?, ?, ?, ?)
                                """,
                                (
                                    content_id,
                                    entry.chunk_index,
                                    entry.text,
                                    self._embedder.serialize_embedding(emb),
                                )
                            )
                            stats.chunks_created += 1
            
        except Exception as e:
            logger.error(f"Bulk insert failed: {e}")
            stats.errors += 1
            raise
        
        return stats
    
    def remove_stale_paths(self, valid_paths: Set[str]) -> int:
        """
        Remove paths that no longer exist on disk.
        
        Args:
            valid_paths: Set of paths that still exist
            
        Returns:
            Number of paths removed
        """
        conn = self._get_connection()
        existing = self.get_existing_paths()
        stale = existing - valid_paths
        
        if not stale:
            return 0
        
        with conn:
            conn.executemany(
                "DELETE FROM paths WHERE path = ?",
                [(p,) for p in stale]
            )
        
        # Clean up orphaned content (content with no paths)
        conn.execute("""
            DELETE FROM content 
            WHERE id NOT IN (SELECT content_id FROM paths)
        """)
        conn.commit()
        
        logger.info(f"Removed {len(stale)} stale paths")
        return len(stale)
    
    def build_leann_index(self, include_chunks: bool = True) -> str:
        """
        Build LEANN index from database content.
        
        Returns:
            Path to the created index
        """
        try:
            from leann import LeannBuilder
        except ImportError:
            logger.error("leann not installed. Run: pip install leann")
            raise
        
        conn = self._get_connection()
        builder = LeannBuilder(backend_name="hnsw")
        
        # Add file entries
        cursor = conn.execute("""
            SELECT c.id, c.embedding, c.first_line, p.path, p.file_name, p.source
            FROM content c
            JOIN paths p ON p.content_id = c.id
            WHERE c.embedding IS NOT NULL
        """)
        
        file_count = 0
        for row in cursor:
            if row["embedding"]:
                embedding = self._embedder.deserialize_embedding(row["embedding"])
                builder.add_vector(
                    embedding,
                    metadata={
                        "type": "file",
                        "file_path": row["path"],
                        "file_name": row["file_name"],
                        "source": row["source"],
                        "text": row["first_line"],
                    }
                )
                file_count += 1
        
        # Add chunks
        chunk_count = 0
        if include_chunks:
            cursor = conn.execute("""
                SELECT ch.id, ch.embedding, ch.text, ch.chunk_index,
                       p.path, p.file_name, p.source
                FROM chunks ch
                JOIN content c ON c.id = ch.content_id
                JOIN paths p ON p.content_id = c.id
                WHERE ch.embedding IS NOT NULL
            """)
            
            for row in cursor:
                embedding = self._embedder.deserialize_embedding(row["embedding"])
                builder.add_vector(
                    embedding,
                    metadata={
                        "type": "chunk",
                        "file_path": row["path"],
                        "file_name": row["file_name"],
                        "source": row["source"],
                        "chunk_index": row["chunk_index"],
                        "text": row["text"],  # Store full text for RAG
                    }
                )
                chunk_count += 1
        
        # Build and save
        index_path = str(self.config.index_path)
        builder.build_index(index_path)
        
        logger.info(f"Built LEANN index: {file_count} files, {chunk_count} chunks → {index_path}")
        return index_path
    
    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None


def get_indexer(config: IndexerConfig | None = None) -> Indexer:
    """Create a new indexer instance."""
    return Indexer(config)
