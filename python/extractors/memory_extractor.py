"""
Memory extractor for personal facts from the knowledge database.
"""

import sqlite3
from pathlib import Path
from typing import List, Set

from .base import BaseExtractor, IndexEntry


class MemoryExtractor(BaseExtractor):
    """
    Extracts personal memory facts from the SQLite database.
    
    This handles learned facts like:
    - "User's name is Elliot"
    - "User works as a software engineer"
    - "User is interested in AI"
    """
    
    def __init__(self, db_path: str = None):
        """
        Initialize memory extractor.
        
        Args:
            db_path: Path to SQLite database (default: ~/.kel/database.db)
        """
        if db_path is None:
            db_path = str(Path.home() / ".kel" / "database.db")
        self.db_path = db_path
    
    @property
    def source_name(self) -> str:
        return "memory"
    
    @property
    def supported_extensions(self) -> Set[str]:
        # Memory extractor doesn't use file extensions
        return set()
    
    def can_handle(self, file_path: str) -> bool:
        # Memory extractor uses database, not files
        return False
    
    def extract(self, file_path: str = None) -> List[IndexEntry]:
        """
        Extract all memory facts from the database.
        
        Note: file_path is ignored; we read from the database.
        """
        return self.extract_from_db()
    
    def extract_from_db(self) -> List[IndexEntry]:
        """Extract personal memory facts from SQLite database."""
        entries = []
        
        if not Path(self.db_path).exists():
            print(f"[MemoryExtractor] Database not found: {self.db_path}")
            return entries
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Check if personal_memory table exists
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='personal_memory'
            """)
            if not cursor.fetchone():
                print("[MemoryExtractor] personal_memory table not found")
                conn.close()
                return entries
            
            # Extract all memory facts
            cursor.execute("SELECT content, source FROM personal_memory")
            
            for content, source_detail in cursor.fetchall():
                if content and content.strip():
                    entries.append(IndexEntry(
                        text=content,
                        entry_type="chunk",  # Memory facts are searchable content
                        source="memory",
                        file_path=None,
                        file_name=None,
                        folder=None,
                        chunk_index=None,
                        extra_metadata={"memory_source": source_detail or "unknown"}
                    ))
            
            conn.close()
            print(f"[MemoryExtractor] Extracted {len(entries)} memory facts")
            
        except Exception as e:
            print(f"[MemoryExtractor] Error reading database: {e}")
        
        return entries
