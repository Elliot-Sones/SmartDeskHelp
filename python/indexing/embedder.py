"""
Embedder - Optimized batch text-to-vector embedding.

Uses ONNX Runtime for 1.5-2x faster inference and optional int8
quantization for an additional 2-3x speedup (with ~2% quality loss).
"""

import logging
from typing import List, Optional
import numpy as np

from .config import get_config, IndexerConfig
from .models import ExtractedFile, IndexEntry, EntryType, DataSource


logger = logging.getLogger(__name__)


class Embedder:
    """
    Optimized batch embedding generator.
    
    Features:
    - ONNX Runtime backend (1.5-2x faster than PyTorch)
    - Optional int8 quantization (2-3x faster, ~2% quality loss)
    - Lazy model loading
    - Batch processing for GPU efficiency
    """
    
    def __init__(self, config: IndexerConfig | None = None):
        self.config = config or get_config()
        self._model = None
        self._dimension: int = 384  # Default for all-MiniLM-L6-v2
        self._onnx_loaded = False
    
    def _get_model(self):
        """Lazy-load the embedding model with ONNX support if available."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                import torch
                
                # Determine device
                device = "cpu"
                if torch.backends.mps.is_available():
                    device = "mps"
                elif torch.cuda.is_available():
                    device = "cuda"
                
                # Try ONNX backend if enabled
                backend = None
                if self.config.use_onnx:
                    try:
                        import onnxruntime
                        backend = "onnx"
                        logger.info(f"Loading ONNX embedding model on {device}...")
                    except ImportError:
                        logger.warning(
                            "onnxruntime not installed. Using PyTorch. "
                            "Install with: pip install onnxruntime-gpu"
                        )
                
                # Load model
                if backend == "onnx":
                    self._model = SentenceTransformer(
                        "all-MiniLM-L6-v2",
                        device=device,
                        backend="onnx",
                    )
                    self._onnx_loaded = True
                else:
                    self._model = SentenceTransformer(
                        "all-MiniLM-L6-v2",
                        device=device,
                    )
                    # Apply half precision for speedup if not ONNX
                    if device in ("cuda", "mps"):
                        self._model.half()
                
                self._dimension = self._model.get_sentence_embedding_dimension()
                backend_name = "ONNX" if self._onnx_loaded else "PyTorch"
                logger.info(f"Loaded {backend_name} model (dim={self._dimension}) on {device}")
                
            except ImportError:
                logger.error("sentence-transformers not installed. Run: pip install sentence-transformers")
                raise
        return self._model
    
    @property
    def dimension(self) -> int:
        """Get embedding dimension (loads model if needed)."""
        self._get_model()
        return self._dimension
    
    def embed_texts(self, texts: List[str]) -> np.ndarray:
        """
        Embed multiple texts in batches.
        
        Args:
            texts: List of strings to embed
            
        Returns:
            NumPy array of shape (len(texts), dimension)
        """
        if not texts:
            return np.array([]).reshape(0, self._dimension)
        
        model = self._get_model()
        batch_size = self.config.embedder_batch_size
        all_embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            embeddings = model.encode(
                batch, 
                convert_to_numpy=True,
                normalize_embeddings=True,  # Better for cosine similarity
            )
            all_embeddings.append(embeddings)
        
        result = np.vstack(all_embeddings)
        
        # Apply int8 quantization if enabled
        if self.config.use_int8:
            result = self._quantize_int8(result)
        
        return result
    
    def _quantize_int8(self, embeddings: np.ndarray) -> np.ndarray:
        """
        Apply int8 quantization to embeddings.
        
        This reduces storage by 4x and can speed up distance calculations.
        Quality loss is typically ~2%.
        """
        try:
            from sentence_transformers.quantization import quantize_embeddings
            return quantize_embeddings(embeddings, precision="int8")
        except ImportError:
            # Fallback: manual quantization
            # Scale to int8 range [-128, 127]
            scale = 127.0 / np.abs(embeddings).max(axis=1, keepdims=True)
            quantized = (embeddings * scale).astype(np.int8)
            return quantized
    
    def embed_text(self, text: str) -> np.ndarray:
        """Embed a single text."""
        return self.embed_texts([text])[0]
    
    def serialize_embedding(self, embedding: np.ndarray) -> bytes:
        """Convert embedding to bytes for storage."""
        return embedding.tobytes()
    
    def deserialize_embedding(self, data: bytes, dtype=np.float32) -> np.ndarray:
        """Convert bytes back to embedding."""
        return np.frombuffer(data, dtype=dtype)
    
    def create_entries_from_file(
        self, 
        extracted_file: ExtractedFile,
        source: DataSource = DataSource.DESKTOP,
    ) -> List[IndexEntry]:
        """
        Create index entries from an extracted file.
        
        Returns:
            - 1 FILE entry (for "find file" queries)
            - N CHUNK entries (for "read content" queries)
        """
        path = extracted_file.info.path
        entries: List[IndexEntry] = []
        
        # Compute relative folder
        try:
            from pathlib import Path as PathLib
            folder = str(path.parent.relative_to(PathLib.home()))
        except ValueError:
            folder = str(path.parent)
        
        # 1. FILE entry (always)
        file_description = f"{path.name} - {self._get_type_description(extracted_file.info.extension)} file"
        entries.append(IndexEntry(
            text=file_description,
            entry_type=EntryType.FILE,
            source=source,
            file_path=str(path),
            file_name=path.name,
            folder=folder,
            chunk_index=None,
            content_hash=extracted_file.binary_hash,
            extra_metadata={"extension": extracted_file.info.extension},
        ))
        
        # 2. CHUNK entries (if we have content)
        if extracted_file.text:
            chunks = self._chunk_text(extracted_file.text)
            for i, chunk in enumerate(chunks):
                entries.append(IndexEntry(
                    text=chunk,
                    entry_type=EntryType.CHUNK,
                    source=source,
                    file_path=str(path),
                    file_name=path.name,
                    folder=folder,
                    chunk_index=i,
                    content_hash=extracted_file.binary_hash,
                    extra_metadata={"total_chunks": len(chunks)},
                ))
        
        return entries
    
    def _chunk_text(self, text: str) -> List[str]:
        """
        Split text into overlapping chunks.
        
        Uses sliding window with overlap for context preservation.
        """
        chunk_size = self.config.chunk_size
        overlap = self.config.chunk_overlap
        
        if len(text) <= chunk_size:
            return [text.strip()] if text.strip() else []
        
        chunks = []
        pos = 0
        
        while pos < len(text):
            end = pos + chunk_size
            chunk = text[pos:end].strip()
            
            if chunk:
                chunks.append(chunk)
            
            # Move forward by (chunk_size - overlap)
            pos = end - overlap
            
            # Prevent infinite loop
            if pos >= len(text) - overlap:
                break
        
        return chunks
    
    def _get_type_description(self, extension: str) -> str:
        """Get human-readable file type description."""
        descriptions = {
            ".pdf": "PDF document",
            ".txt": "text",
            ".md": "markdown",
            ".docx": "Word document",
            ".doc": "Word document",
            ".py": "Python code",
            ".js": "JavaScript code",
            ".ts": "TypeScript code",
            ".json": "JSON data",
            ".html": "HTML",
            ".css": "CSS stylesheet",
        }
        return descriptions.get(extension.lower(), extension.lstrip("."))


# Singleton instance
_embedder: Optional[Embedder] = None


def get_embedder(config: IndexerConfig | None = None) -> Embedder:
    """Get the singleton embedder instance."""
    global _embedder
    if _embedder is None:
        _embedder = Embedder(config)
    return _embedder
