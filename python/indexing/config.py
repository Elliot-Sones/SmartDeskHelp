"""
Indexing Configuration - Centralized settings for the indexing system.

Uses environment variables with sensible defaults. All paths are resolved 
to absolute paths for reliability.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Set, List


@dataclass
class IndexerConfig:
    """
    Configuration for the indexing system.
    
    All paths default to ~/.kel directory.
    Concurrency limits are tuned for typical desktop hardware.
    """
    
    # --- Paths ---
    roots: List[Path] = field(default_factory=lambda: [
        Path.home() / "Desktop",
        Path.home() / "Documents",
        Path.home() / "Pictures",
        Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs",
    ])
    index_path: Path = field(default_factory=lambda: Path.home() / ".kel" / "leann.index")
    db_path: Path = field(default_factory=lambda: Path.home() / ".kel" / "database.db")
    
    # --- Concurrency Limits ---
    scanner_concurrency: int = 60   # Increased for faster scanning
    hasher_concurrency: int = 32    # Parallel xxHash operations
    extractor_concurrency: int = 32 # Parallel text extraction (pdftotext, etc.)
    embedder_batch_size: int = 512  # Higher batch size for GPU efficiency
    db_batch_size: int = 500        # Larger transaction batches (reduces commit overhead)
    
    # --- Optimization Flags ---
    use_onnx: bool = True           # Use ONNX Runtime for faster inference
    use_int8: bool = True           # Use int8 quantization (2-3x faster, ~2% quality loss)
    
    # --- Skip Patterns ---
    skip_dirs: Set[str] = field(default_factory=lambda: {
        # Version control
        ".git", ".svn", ".hg",
        # Dependencies
        "node_modules", "__pycache__", ".venv", "venv", "env",
        # Build outputs
        "build", "dist", "target", "out", ".next",
        # IDE/Editor
        ".idea", ".vscode",
        # macOS/iOS
        "Pods", "DerivedData", ".Trash",
        # Cache
        ".cache", ".npm", ".yarn",
    })
    
    skip_extensions: Set[str] = field(default_factory=lambda: {
        # Large binaries
        ".zip", ".tar", ".gz", ".rar", ".7z",
        ".dmg", ".iso", ".pkg",
        # Executables
        ".exe", ".dll", ".so", ".dylib",
        # Media (handled by ImageExtractor separately)
        ".mp4", ".mov", ".avi", ".mkv",
        ".mp3", ".wav", ".flac",
        # Lock files
        ".lock", ".lockb",
    })
    
    # --- Supported File Types ---
    text_extensions: Set[str] = field(default_factory=lambda: {
        # Documents
        ".pdf", ".txt", ".md", ".docx", ".doc", ".rtf",
        # Code
        ".py", ".js", ".ts", ".tsx", ".jsx", ".json",
        ".html", ".css", ".scss", ".yaml", ".yml",
        ".sh", ".bash", ".zsh", ".sql", ".r", ".swift",
        ".java", ".c", ".cpp", ".h", ".hpp", ".go", ".rs",
    })
    
    image_extensions: Set[str] = field(default_factory=lambda: {
        ".jpg", ".jpeg", ".png", ".gif", ".webp",
        ".heic", ".heif", ".bmp", ".tiff",
    })
    
    # --- Chunking ---
    chunk_size: int = 1000       # Approx 250 tokens (model max is 256)
    chunk_overlap: int = 200     # Overlap between chunks
    
    # --- Watcher ---
    debounce_ms: int = 2000      # Batch rapid changes within this window
    
    # --- iCloud ---
    icloud_root: Path = field(
        default_factory=lambda: Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    )
    
    def __post_init__(self):
        """Ensure all paths are absolute and parent directories exist."""
        self.index_path = self.index_path.expanduser().resolve()
        self.db_path = self.db_path.expanduser().resolve()
        self.icloud_root = self.icloud_root.expanduser().resolve()
        self.roots = [p.expanduser().resolve() for p in self.roots]
        
        # Create directories if they don't exist
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
    
    @classmethod
    def from_env(cls) -> "IndexerConfig":
        """
        Create config from environment variables.
        
        Supported env vars:
            INDEXER_ROOTS: Comma-separated list of paths
            INDEXER_INDEX_PATH: Path to LEANN index
            INDEXER_DB_PATH: Path to SQLite database
            INDEXER_SCANNER_CONCURRENCY: Parallel stat operations
            INDEXER_HASHER_CONCURRENCY: Parallel file reads
        """
        config = cls()
        
        if roots := os.environ.get("INDEXER_ROOTS"):
            config.roots = [Path(p.strip()) for p in roots.split(",")]
        
        if index_path := os.environ.get("INDEXER_INDEX_PATH"):
            config.index_path = Path(index_path)
        
        if db_path := os.environ.get("INDEXER_DB_PATH"):
            config.db_path = Path(db_path)
        
        if scanner := os.environ.get("INDEXER_SCANNER_CONCURRENCY"):
            config.scanner_concurrency = int(scanner)
        
        if hasher := os.environ.get("INDEXER_HASHER_CONCURRENCY"):
            config.hasher_concurrency = int(hasher)
        
        config.__post_init__()
        return config


# Singleton default config
_default_config: IndexerConfig | None = None


def get_config() -> IndexerConfig:
    """Get the default configuration (singleton)."""
    global _default_config
    if _default_config is None:
        _default_config = IndexerConfig.from_env()
    return _default_config


def set_config(config: IndexerConfig) -> None:
    """Override the default configuration (for testing)."""
    global _default_config
    _default_config = config
