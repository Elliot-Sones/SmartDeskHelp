"""
Indexing Package - Cascade Filter architecture for fast file indexing.

Modules:
    - config: Centralized configuration
    - scanner: Fast parallel file system traversal
    - hasher: xxHash content hashing (fast deduplication)
    - extractor: Text extraction (pdftotext CLI, docx, etc.)
    - embedder: ONNX + int8 batch embedding
    - indexer: SQLite + LEANN writer
    - watcher: Real-time file change detection
    - orchestrator: Main entry point (Cascade Filter)

Cascade Filter Flow:
    Scan → Hash (xxHash) → Extract (lazy) → Embed (ONNX) → Persist

Usage:
    from indexing import Orchestrator
    
    orchestrator = Orchestrator()
    await orchestrator.run_full_scan()
"""

from .orchestrator import Orchestrator

__all__ = ["Orchestrator"]
