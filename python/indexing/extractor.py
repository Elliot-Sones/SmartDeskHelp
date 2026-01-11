"""
Extractor - Fast text extraction from various file formats.

Uses pdftotext CLI for PDFs (5-10x faster than pypdf) with fallback
to pure Python libraries when CLI tools are unavailable.
"""

import asyncio
import logging
import subprocess
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

from .config import get_config, IndexerConfig
from .models import HashedFile, ExtractedFile, FileInfo
from .errors import handle_error, ErrorAction


logger = logging.getLogger(__name__)


# Check for pdftotext availability at module load
_PDFTOTEXT_AVAILABLE = shutil.which("pdftotext") is not None
if not _PDFTOTEXT_AVAILABLE:
    logger.warning(
        "pdftotext not found. PDF extraction will be slower. "
        "Install with: brew install poppler"
    )


class Extractor:
    """
    Fast parallel text extractor.
    
    Uses CLI tools where available (pdftotext) for maximum speed,
    with fallback to pure Python libraries.
    """
    
    def __init__(self, config: IndexerConfig | None = None):
        self.config = config or get_config()
        self._executor: ThreadPoolExecutor | None = None
    
    def _get_executor(self) -> ThreadPoolExecutor:
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self.config.extractor_concurrency,
                thread_name_prefix="extractor"
            )
        return self._executor
    
    async def extract_files(self, files: List[HashedFile]) -> List[ExtractedFile]:
        """
        Extract text from multiple files in parallel.
        
        Args:
            files: List of HashedFile to extract text from
            
        Returns:
            List of ExtractedFile with text content
        """
        if not files:
            return []
        
        loop = asyncio.get_event_loop()
        executor = self._get_executor()
        
        BATCH_SIZE = 500  # Process in batches to limit memory
        all_extracted: List[ExtractedFile] = []
        
        for i in range(0, len(files), BATCH_SIZE):
            batch = files[i:i + BATCH_SIZE]
            
            tasks = [
                loop.run_in_executor(executor, self._extract_file_sync, hf)
                for hf in batch
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, ExtractedFile):
                    all_extracted.append(result)
                elif isinstance(result, Exception):
                    # Already logged in _extract_file_sync
                    pass
        
        logger.info(f"Extracted text from {len(all_extracted)} files")
        return all_extracted
    
    def _extract_file_sync(self, hashed_file: HashedFile) -> ExtractedFile:
        """
        Synchronous text extraction (runs in thread pool).
        
        Raises exceptions for error handling by the caller.
        """
        path = hashed_file.info.path
        ext = hashed_file.info.extension.lower()
        
        try:
            # Route to appropriate extractor
            if ext == ".pdf":
                text = self._extract_pdf(path)
            elif ext in {".docx", ".doc"}:
                text = self._extract_docx(path)
            else:
                text = self._extract_text(path)
            
            # Get first line for display
            first_line = ""
            if text:
                lines = text.strip().split("\n")
                if lines:
                    first_line = lines[0][:200]
            
            return ExtractedFile(
                info=hashed_file.info,
                binary_hash=hashed_file.binary_hash,
                text=text or "",
                first_line=first_line,
            )
            
        except Exception as e:
            handle_error(e, path, "extract_text")
            raise
    
    def _extract_pdf(self, path: Path) -> Optional[str]:
        """
        Extract text from PDF using pdftotext CLI (fast) or pypdf (fallback).
        """
        if _PDFTOTEXT_AVAILABLE:
            return self._extract_pdf_cli(path)
        else:
            return self._extract_pdf_pypdf(path)
    
    def _extract_pdf_cli(self, path: Path) -> Optional[str]:
        """Extract PDF text using pdftotext CLI (5-10x faster than pypdf)."""
        try:
            result = subprocess.run(
                ["pdftotext", "-layout", "-nopgbrk", str(path), "-"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                logger.debug(f"pdftotext failed for {path.name}: {result.stderr}")
                return self._extract_pdf_pypdf(path)
        except subprocess.TimeoutExpired:
            logger.warning(f"pdftotext timeout for {path.name}")
            return None
        except Exception as e:
            logger.debug(f"pdftotext error for {path.name}: {e}")
            return self._extract_pdf_pypdf(path)
    
    def _extract_pdf_pypdf(self, path: Path) -> Optional[str]:
        """Extract PDF text using pypdf (pure Python fallback)."""
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(path))
            text_parts = []
            for page in reader.pages:
                if text := page.extract_text():
                    text_parts.append(text)
            return "\n".join(text_parts)
        except Exception as e:
            logger.debug(f"pypdf extraction failed for {path.name}: {e}")
            return None
    
    def _extract_docx(self, path: Path) -> Optional[str]:
        """Extract text from Word document."""
        try:
            from docx import Document
            doc = Document(str(path))
            return "\n".join(p.text for p in doc.paragraphs if p.text)
        except Exception as e:
            logger.debug(f"DOCX extraction failed for {path.name}: {e}")
            return None
    
    def _extract_text(self, path: Path) -> Optional[str]:
        """Read plain text file."""
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None
    
    def close(self):
        """Shutdown the thread pool."""
        if self._executor:
            self._executor.shutdown(wait=False)
            self._executor = None


async def extract_files(
    files: List[HashedFile],
    config: IndexerConfig | None = None,
) -> List[ExtractedFile]:
    """
    Convenience function to extract text from files.
    
    Usage:
        extracted = await extract_files(hashed_files)
        for ef in extracted:
            print(f"{ef.info.name}: {len(ef.text)} chars")
    """
    extractor = Extractor(config)
    try:
        return await extractor.extract_files(files)
    finally:
        extractor.close()
