"""
Hasher Tests - Verify content hashing and deduplication.

Tests:
- SHA-256 hash computation
- Duplicate detection
- PDF/DOCX extraction (mocked)
- Error handling for unreadable files
"""

import asyncio
from pathlib import Path

import pytest

from indexing.hasher import Hasher, hash_files
from indexing.models import FileInfo
from indexing.config import IndexerConfig


class TestHasher:
    """Tests for the Hasher class."""
    
    @pytest.mark.asyncio
    async def test_hashes_text_file(self, sample_files, test_config):
        """Hasher computes hash for text files."""
        file_info = FileInfo.from_path(
            sample_files["txt"],
            sample_files["txt"].stat().st_mtime,
            sample_files["txt"].stat().st_size,
        )
        
        hasher = Hasher(test_config)
        result = await hasher.hash_file(file_info)
        hasher.close()
        
        assert result is not None
        assert len(result.content_hash) == 64  # SHA-256 hex digest
        assert result.content is not None
        assert "sample text file" in result.content
    
    @pytest.mark.asyncio
    async def test_extracts_first_line(self, sample_files, test_config):
        """Hasher extracts first line for display."""
        file_info = FileInfo.from_path(
            sample_files["txt"],
            sample_files["txt"].stat().st_mtime,
            sample_files["txt"].stat().st_size,
        )
        
        hasher = Hasher(test_config)
        result = await hasher.hash_file(file_info)
        hasher.close()
        
        assert result.first_line == "This is a sample text file."
    
    @pytest.mark.asyncio
    async def test_identical_content_same_hash(self, duplicate_files, test_config):
        """Files with identical content have the same hash."""
        file1, file2 = duplicate_files
        
        info1 = FileInfo.from_path(file1, file1.stat().st_mtime, file1.stat().st_size)
        info2 = FileInfo.from_path(file2, file2.stat().st_mtime, file2.stat().st_size)
        
        hasher = Hasher(test_config)
        results = await hasher.hash_files([info1, info2])
        hasher.close()
        
        assert len(results) == 2
        assert results[0].content_hash == results[1].content_hash
    
    @pytest.mark.asyncio
    async def test_different_content_different_hash(self, sample_files, test_config):
        """Files with different content have different hashes."""
        info_txt = FileInfo.from_path(
            sample_files["txt"],
            sample_files["txt"].stat().st_mtime,
            sample_files["txt"].stat().st_size,
        )
        info_md = FileInfo.from_path(
            sample_files["md"],
            sample_files["md"].stat().st_mtime,
            sample_files["md"].stat().st_size,
        )
        
        hasher = Hasher(test_config)
        results = await hasher.hash_files([info_txt, info_md])
        hasher.close()
        
        assert len(results) == 2
        assert results[0].content_hash != results[1].content_hash
    
    @pytest.mark.asyncio
    async def test_handles_deleted_file(self, temp_dir, test_config):
        """Hasher handles files deleted between scan and hash."""
        # Create file
        file = temp_dir / "temporary.txt"
        file.write_text("Will be deleted")
        
        info = FileInfo.from_path(file, file.stat().st_mtime, file.stat().st_size)
        
        # Delete the file
        file.unlink()
        
        hasher = Hasher(test_config)
        results = await hasher.hash_files([info])
        hasher.close()
        
        # Should return empty list, not crash
        assert len(results) == 0
    
    @pytest.mark.asyncio
    async def test_handles_binary_file(self, temp_dir, test_config):
        """Hasher handles binary files (hashes bytes, no content)."""
        binary = temp_dir / "binary.bin"
        binary.write_bytes(b"\x00\x01\x02\x03\xff\xfe\xfd")
        
        info = FileInfo.from_path(binary, binary.stat().st_mtime, binary.stat().st_size)
        
        hasher = Hasher(test_config)
        result = await hasher.hash_file(info)
        hasher.close()
        
        assert result is not None
        assert len(result.content_hash) == 64
        # Content may be None or a replacement string for binary
    
    @pytest.mark.asyncio
    async def test_parallel_hashing(self, temp_dir, test_config):
        """Hasher processes multiple files in parallel."""
        # Create many files
        files = []
        for i in range(20):
            f = temp_dir / f"parallel_{i}.txt"
            f.write_text(f"Content for file {i}")
            files.append(FileInfo.from_path(f, f.stat().st_mtime, f.stat().st_size))
        
        hasher = Hasher(test_config)
        results = await hasher.hash_files(files)
        hasher.close()
        
        assert len(results) == 20
        # All hashes should be different
        hashes = {r.content_hash for r in results}
        assert len(hashes) == 20


class TestHasherConvenience:
    """Tests for convenience functions."""
    
    @pytest.mark.asyncio
    async def test_hash_files_function(self, sample_files, test_config):
        """hash_files convenience function works."""
        info = FileInfo.from_path(
            sample_files["txt"],
            sample_files["txt"].stat().st_mtime,
            sample_files["txt"].stat().st_size,
        )
        
        results = await hash_files([info], test_config)
        assert len(results) == 1
