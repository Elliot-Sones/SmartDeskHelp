"""
LEANN Search - Unified search with source and intent filtering.
"""

import os
from typing import Dict, List, Optional

from leann import LeannSearcher


INDEX_PATH = os.path.expanduser("~/.kel/leann.index")

# Global searcher (lazy loaded)
_searcher: Optional[LeannSearcher] = None


def get_searcher() -> Optional[LeannSearcher]:
    """Get or create LEANN searcher (lazy loaded)."""
    global _searcher
    
    if _searcher is None:
        if not os.path.exists(INDEX_PATH):
            return None
        _searcher = LeannSearcher(INDEX_PATH)
    
    return _searcher


def index_exists() -> bool:
    """Check if LEANN index exists."""
    return os.path.exists(INDEX_PATH)


def search(
    query: str,
    intent: str = "read",
    source: Optional[str] = None,
    folder: Optional[str] = None,
    top_k: int = 10
) -> Dict:
    """
    Search the LEANN index with filters.
    
    Args:
        query: Search terms (e.g., "resume school elliot")
        intent: "read" returns chunks, "find"/"open" returns files
        source: Filter by source ("desktop", "photos", "memory", or None for all)
        folder: Filter by folder path (e.g., "Desktop/Home")
        top_k: Number of results to return
    
    Returns:
        dict with "results" list or "error" message
    """
    searcher = get_searcher()
    
    if not searcher:
        return {
            "error": "Index not built. Run: python leann_indexer.py",
            "results": []
        }
    
    # Build metadata filters
    filters = {}
    
    # Filter by entry type based on intent
    if intent == "read":
        filters["type"] = {"==": "chunk"}
    else:
        filters["type"] = {"==": "file"}
    
    # Filter by source (desktop, photos, memory)
    if source:
        filters["source"] = {"==": source}
    
    # Filter by folder path
    if folder:
        filters["folder"] = {"starts_with": folder}
    
    try:
        # Perform search
        results = searcher.search(query, top_k=top_k, metadata_filters=filters)
        
        return {
            "results": [
                {
                    "text": r.text,
                    "source": r.metadata.get("source"),
                    "type": r.metadata.get("type"),
                    "file_path": r.metadata.get("file_path"),
                    "file_name": r.metadata.get("file_name"),
                    "folder": r.metadata.get("folder"),
                    "chunk_index": r.metadata.get("chunk_index"),
                    "score": round(r.score, 4)
                }
                for r in results
            ]
        }
        
    except Exception as e:
        return {
            "error": f"Search failed: {str(e)}",
            "results": []
        }


def search_files(query: str, folder: Optional[str] = None, top_k: int = 10) -> Dict:
    """Convenience function: Search for files only."""
    return search(query, intent="find", folder=folder, top_k=top_k)


def search_content(query: str, source: Optional[str] = None, top_k: int = 10) -> Dict:
    """Convenience function: Search content chunks only."""
    return search(query, intent="read", source=source, top_k=top_k)


def search_memory(query: str, top_k: int = 10) -> Dict:
    """Convenience function: Search personal memory only."""
    return search(query, intent="read", source="memory", top_k=top_k)


def search_photos(query: str, top_k: int = 10) -> Dict:
    """Convenience function: Search photos only."""
    return search(query, intent="find", source="photos", top_k=top_k)
