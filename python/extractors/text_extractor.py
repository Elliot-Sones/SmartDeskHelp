"""
Text extractor for documents (PDF, TXT, DOCX, MD, code files).
"""

from pathlib import Path
from typing import List, Set

from .base import BaseExtractor, IndexEntry


class TextExtractor(BaseExtractor):
    """Extracts text from documents and code files."""
    
    # Chunk settings
    CHUNK_SIZE = 512
    CHUNK_OVERLAP = 128
    
    @property
    def source_name(self) -> str:
        return "desktop"
    
    @property
    def supported_extensions(self) -> Set[str]:
        return {
            # Documents
            '.pdf', '.txt', '.md', '.docx', '.doc', '.rtf',
            # Code files
            '.py', '.js', '.ts', '.tsx', '.jsx', '.json',
            '.html', '.css', '.scss', '.yaml', '.yml',
            '.sh', '.bash', '.zsh', '.sql', '.r', '.swift',
            '.java', '.c', '.cpp', '.h', '.hpp', '.go', '.rs'
        }
    
    def can_handle(self, file_path: str) -> bool:
        return Path(file_path).suffix.lower() in self.supported_extensions
    
    def extract(self, file_path: str) -> List[IndexEntry]:
        """Extract file entry + content chunks from a document."""
        path = Path(file_path)
        entries = []
        
        # Compute relative folder path
        try:
            folder = str(path.parent.relative_to(Path.home()))
        except ValueError:
            folder = str(path.parent)
        
        # 1. Always add FILE entry (for "find file" queries)
        entries.append(IndexEntry(
            text=f"{path.name} - {self._get_type_description(path.suffix)} file",
            entry_type="file",
            source=self.source_name,
            file_path=str(path),
            file_name=path.name,
            folder=folder,
            chunk_index=None,
            extra_metadata={"extension": path.suffix.lower()}
        ))
        
        # 2. Extract content and add CHUNK entries
        try:
            content = self._read_content(str(path))
            if content and content.strip():
                chunks = self._chunk_text(content)
                for i, chunk in enumerate(chunks):
                    entries.append(IndexEntry(
                        text=chunk,
                        entry_type="chunk",
                        source=self.source_name,
                        file_path=str(path),
                        file_name=path.name,
                        folder=folder,
                        chunk_index=i,
                        extra_metadata={"total_chunks": len(chunks)}
                    ))
        except Exception as e:
            print(f"[TextExtractor] Warning: Could not extract content from {path.name}: {e}")
        
        return entries
    
    def _get_type_description(self, extension: str) -> str:
        """Get human-readable type description for an extension."""
        descriptions = {
            '.pdf': 'PDF document',
            '.txt': 'text',
            '.md': 'markdown',
            '.docx': 'Word document',
            '.doc': 'Word document',
            '.py': 'Python code',
            '.js': 'JavaScript code',
            '.ts': 'TypeScript code',
            '.json': 'JSON data',
            '.html': 'HTML',
            '.css': 'CSS stylesheet',
        }
        return descriptions.get(extension.lower(), extension.lstrip('.'))
    
    def _read_content(self, file_path: str) -> str:
        """Read text content from various file formats."""
        path = Path(file_path)
        ext = path.suffix.lower()
        
        # PDF files
        if ext == '.pdf':
            return self._read_pdf(file_path)
        
        # Word documents
        if ext in {'.docx', '.doc'}:
            return self._read_docx(file_path)
        
        # Plain text and code files
        try:
            return path.read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return ""
    
    def _read_pdf(self, file_path: str) -> str:
        """Extract text from PDF using pypdf."""
        try:
            from pypdf import PdfReader
            reader = PdfReader(file_path)
            text_parts = []
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
            return "\n".join(text_parts)
        except Exception as e:
            print(f"[TextExtractor] PDF error: {e}")
            return ""
    
    def _read_docx(self, file_path: str) -> str:
        """Extract text from Word documents."""
        try:
            from docx import Document
            doc = Document(file_path)
            return "\n".join(p.text for p in doc.paragraphs if p.text)
        except Exception as e:
            print(f"[TextExtractor] DOCX error: {e}")
            return ""
    
    def _chunk_text(self, text: str) -> List[str]:
        """
        Split text into overlapping chunks for better search.
        
        Uses a sliding window approach:
        - chunk_size: max characters per chunk
        - overlap: characters shared between consecutive chunks
        """
        if len(text) <= self.CHUNK_SIZE:
            return [text.strip()] if text.strip() else []
        
        chunks = []
        pos = 0
        
        while pos < len(text):
            end = pos + self.CHUNK_SIZE
            chunk = text[pos:end].strip()
            
            if chunk:
                chunks.append(chunk)
            
            # Move forward by (chunk_size - overlap)
            pos = end - self.CHUNK_OVERLAP
            
            # Prevent infinite loop
            if pos >= len(text) - self.CHUNK_OVERLAP:
                break
        
        return chunks
