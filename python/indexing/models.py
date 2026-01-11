"""
Data Models - Type definitions for the indexing pipeline.

These dataclasses represent the data flowing through the pipeline stages,
ensuring type safety and clear interfaces between modules.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List
from datetime import datetime
from enum import Enum


class SyncStatus(Enum):
    """Sync status for cloud-synced files."""
    LOCAL = "local"             # File is fully available locally
    PLACEHOLDER = "placeholder" # iCloud placeholder (not downloaded)
    DOWNLOADING = "downloading" # Currently downloading
    NO_ACCESS = "no_access"     # Permission denied


class EntryType(Enum):
    """Type of index entry."""
    FILE = "file"     # Metadata entry for file search
    CHUNK = "chunk"   # Content chunk for deep search


class DataSource(Enum):
    """Source of the indexed data."""
    DESKTOP = "desktop"
    DOCUMENTS = "documents"
    ICLOUD = "icloud"
    PHOTOS = "photos"      # Apple Photos library
    MEMORY = "memory"


@dataclass
class FileInfo:
    """
    Basic file information from the scanner.
    
    This is the lightest-weight representation, containing only
    what we get from stat() without reading file content.
    """
    path: Path
    name: str
    extension: str
    size: int
    mtime: datetime
    is_icloud_placeholder: bool = False
    
    @classmethod
    def from_path(cls, path: Path, mtime: float, size: int) -> "FileInfo":
        """Create FileInfo from a path and stat result."""
        name = path.name
        is_placeholder = name.startswith(".") and name.endswith(".icloud")
        
        # Extract real name from placeholder
        if is_placeholder:
            real_name = name[1:-7]  # Remove leading "." and trailing ".icloud"
            extension = Path(real_name).suffix.lower()
        else:
            extension = path.suffix.lower()
        
        return cls(
            path=path,
            name=name,
            extension=extension,
            size=size,
            mtime=datetime.fromtimestamp(mtime),
            is_icloud_placeholder=is_placeholder,
        )


@dataclass
class HashedFile:
    """
    Stage 2 Output: File with binary identity.
    """
    info: FileInfo
    binary_hash: str           # SHA-256 of raw file binary (not text)
    is_known: bool = False     # True if this binary hash is already in DB
    

@dataclass
class ExtractedFile:
    """
    Stage 3 Output: File with extracted text content.
    """
    info: FileInfo
    binary_hash: str
    text: str                  # Extracted plain text
    first_line: str            # First line for display

    

@dataclass
class IndexEntry:
    """
    A single entry to be added to the index.
    
    Can represent either:
    - A FILE entry (for "find files" queries)
    - A CHUNK entry (for "read content" queries)
    """
    text: str                  # Text to embed
    entry_type: EntryType
    source: DataSource
    file_path: str
    file_name: str
    folder: str
    chunk_index: Optional[int] = None  # Only for CHUNK entries
    content_hash: Optional[str] = None
    extra_metadata: dict = field(default_factory=dict)


@dataclass
class ContentRecord:
    """
    A record in the CAS content table.
    
    This represents unique content, identified by hash.
    Multiple paths can point to the same content.
    """
    id: Optional[int]          # DB primary key (None before insert)
    content_hash: str          # SHA-256 hex digest
    embedding: Optional[bytes] # Serialized 384-dim vector
    first_line: str            # For search result display
    size_bytes: int
    indexed_at: datetime
    
    
@dataclass
class PathRecord:
    """
    A record in the paths table.
    
    This maps a file path to its content record.
    """
    id: Optional[int]          # DB primary key (None before insert)
    content_id: int            # FK to ContentRecord
    path: str
    file_name: str
    extension: str
    source: DataSource
    sync_status: SyncStatus
    last_verified: datetime


@dataclass
class ChunkRecord:
    """
    A content chunk for deep search.
    """
    id: Optional[int]
    content_id: int            # FK to ContentRecord
    chunk_index: int
    text: str
    embedding: Optional[bytes]


@dataclass
class ScanResult:
    """Result of scanning a directory tree."""
    files: List[FileInfo]
    skipped_count: int
    error_count: int
    duration_seconds: float


@dataclass
class IndexingStats:
    """Statistics from an indexing run."""
    files_scanned: int = 0
    files_indexed: int = 0
    files_skipped: int = 0
    files_deduplicated: int = 0  # Same content, new path
    chunks_created: int = 0
    errors: int = 0
    duration_seconds: float = 0.0
    
    def __str__(self) -> str:
        return (
            f"Indexed {self.files_indexed} files "
            f"({self.chunks_created} chunks, "
            f"{self.files_deduplicated} deduplicated, "
            f"{self.files_skipped} skipped, "
            f"{self.errors} errors) "
            f"in {self.duration_seconds:.1f}s"
        )
