"""
Base class for all content extractors.
Each extractor handles a specific content type (text, images, memory, etc.)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional, Set


@dataclass
class IndexEntry:
    """A single entry to add to the LEANN index."""
    
    text: str                           # Searchable text content
    entry_type: str                     # "file" or "chunk"
    source: str                         # "desktop", "photos", "memory", etc.
    file_path: Optional[str] = None     # Full path to file
    file_name: Optional[str] = None     # Just the filename
    folder: Optional[str] = None        # Folder path relative to home
    chunk_index: Optional[int] = None   # Chunk number (for multi-chunk files)
    extra_metadata: dict = field(default_factory=dict)


class BaseExtractor(ABC):
    """
    Base class for all content extractors.
    
    To add a new content type:
    1. Create a new class extending BaseExtractor
    2. Implement source_name, supported_extensions, can_handle, and extract
    3. Add the extractor to EXTRACTORS list in leann_indexer.py
    """
    
    @property
    @abstractmethod
    def source_name(self) -> str:
        """
        Name of this source (e.g., 'desktop', 'photos', 'memory').
        Used for filtering searches by source.
        """
        pass
    
    @property
    @abstractmethod
    def supported_extensions(self) -> Set[str]:
        """
        File extensions this extractor handles (e.g., {'.pdf', '.txt'}).
        Include the dot.
        """
        pass
    
    @abstractmethod
    def can_handle(self, file_path: str) -> bool:
        """
        Check if this extractor can process the given file.
        
        Args:
            file_path: Full path to the file
            
        Returns:
            True if this extractor should handle the file
        """
        pass
    
    @abstractmethod
    def extract(self, file_path: str) -> List[IndexEntry]:
        """
        Extract index entries from a file.
        
        Should return:
        - One "file" entry for the file itself (for find/open queries)
        - Zero or more "chunk" entries for the content (for read queries)
        
        Args:
            file_path: Full path to the file
            
        Returns:
            List of IndexEntry objects to add to the index
        """
        pass
