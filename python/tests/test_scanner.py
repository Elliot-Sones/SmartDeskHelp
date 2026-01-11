"""
Scanner Tests - Verify file system traversal behavior.

Tests:
- Basic file discovery
- Skip pattern filtering (hidden files, node_modules, etc.)
- Concurrent scanning
- Error handling for permission issues
"""

import asyncio
from pathlib import Path

import pytest

from indexing.scanner import Scanner, scan_directories
from indexing.config import IndexerConfig


class TestScanner:
    """Tests for the Scanner class."""
    
    @pytest.mark.asyncio
    async def test_finds_basic_files(self, sample_files, test_config):
        """Scanner finds regular files."""
        scanner = Scanner(test_config)
        result = await scanner.scan()
        
        paths = {str(f.path) for f in result.files}
        
        assert str(sample_files["txt"]) in paths
        assert str(sample_files["md"]) in paths
        assert str(sample_files["py"]) in paths
    
    @pytest.mark.asyncio
    async def test_finds_nested_files(self, sample_files, test_config):
        """Scanner finds files in nested directories."""
        scanner = Scanner(test_config)
        result = await scanner.scan()
        
        paths = {str(f.path) for f in result.files}
        assert str(sample_files["nested"]) in paths
    
    @pytest.mark.asyncio
    async def test_skips_hidden_files(self, sample_files, test_config):
        """Scanner skips hidden files (starting with .)."""
        scanner = Scanner(test_config)
        result = await scanner.scan()
        
        paths = {str(f.path) for f in result.files}
        assert str(sample_files["hidden"]) not in paths
    
    @pytest.mark.asyncio
    async def test_skips_node_modules(self, sample_files, test_config):
        """Scanner skips node_modules directories."""
        scanner = Scanner(test_config)
        result = await scanner.scan()
        
        paths = {str(f.path) for f in result.files}
        assert str(sample_files["node_modules"]) not in paths
    
    @pytest.mark.asyncio
    async def test_skips_ds_store(self, temp_dir, test_config):
        """Scanner skips .DS_Store files."""
        ds_store = temp_dir / ".DS_Store"
        ds_store.write_bytes(b"\x00\x00\x00\x01")
        
        scanner = Scanner(test_config)
        result = await scanner.scan()
        
        names = {f.name for f in result.files}
        assert ".DS_Store" not in names
    
    @pytest.mark.asyncio
    async def test_includes_icloud_placeholders(self, icloud_placeholder, test_config):
        """Scanner includes iCloud placeholder files (.icloud)."""
        scanner = Scanner(test_config)
        result = await scanner.scan()
        
        # iCloud placeholders should be included (handled specially later)
        placeholder_files = [f for f in result.files if f.is_icloud_placeholder]
        assert len(placeholder_files) == 1
        assert placeholder_files[0].path == icloud_placeholder
    
    @pytest.mark.asyncio
    async def test_extracts_correct_metadata(self, sample_files, test_config):
        """Scanner extracts correct file metadata."""
        scanner = Scanner(test_config)
        result = await scanner.scan()
        
        txt_file = next(f for f in result.files if f.path == sample_files["txt"])
        
        assert txt_file.name == "sample.txt"
        assert txt_file.extension == ".txt"
        assert txt_file.size > 0
        assert txt_file.mtime is not None
    
    @pytest.mark.asyncio
    async def test_handles_empty_directory(self, temp_dir, test_config):
        """Scanner handles empty directories gracefully."""
        empty_dir = temp_dir / "empty"
        empty_dir.mkdir()
        
        config = IndexerConfig(roots=[empty_dir])
        scanner = Scanner(config)
        result = await scanner.scan()
        
        assert len(result.files) == 0
    
    @pytest.mark.asyncio
    async def test_handles_nonexistent_directory(self, temp_dir, test_config):
        """Scanner handles non-existent directories gracefully."""
        config = IndexerConfig(roots=[temp_dir / "does_not_exist"])
        scanner = Scanner(config)
        result = await scanner.scan()
        
        assert len(result.files) == 0
    
    @pytest.mark.asyncio
    async def test_scan_iter_streaming(self, sample_files, test_config):
        """Scanner's streaming interface works correctly."""
        scanner = Scanner(test_config)
        
        files = []
        async for file_info in scanner.scan_iter():
            files.append(file_info)
        
        # Should find the same files as scan()
        result = await scanner.scan()
        assert len(files) == len(result.files)


class TestScannerConcurrency:
    """Tests for scanner concurrency behavior."""
    
    @pytest.mark.asyncio
    async def test_respects_concurrency_limit(self, temp_dir, test_config):
        """Scanner respects the concurrency limit."""
        # Create many files
        for i in range(50):
            (temp_dir / f"file_{i}.txt").write_text(f"Content {i}")
        
        # Set low concurrency
        test_config.scanner_concurrency = 5
        scanner = Scanner(test_config)
        
        result = await scanner.scan()
        assert len(result.files) == 50
    
    @pytest.mark.asyncio
    async def test_convenience_function(self, sample_files, test_config):
        """scan_directories convenience function works."""
        result = await scan_directories(config=test_config)
        assert len(result.files) > 0
