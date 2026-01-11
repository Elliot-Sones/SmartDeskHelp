"""
iCloud Tests - Verify iCloud placeholder handling.

Tests:
- Placeholder file detection
- Real filename extraction
- Sync status determination
"""

from pathlib import Path

import pytest

from indexing.cloud.icloud import ICloudHandler, get_icloud_handler
from indexing.models import FileInfo, SyncStatus


class TestICloudHandler:
    """Tests for iCloud placeholder handling."""
    
    @pytest.fixture
    def handler(self, test_config):
        return ICloudHandler(test_config)
    
    def test_detects_placeholder(self, handler, temp_dir):
        """Handler detects iCloud placeholder files."""
        # Placeholder format: .filename.ext.icloud
        placeholder = temp_dir / ".document.pdf.icloud"
        placeholder.touch()
        
        assert handler.is_placeholder(placeholder)
    
    def test_not_placeholder_regular_file(self, handler, temp_dir):
        """Handler correctly identifies regular files."""
        regular = temp_dir / "document.pdf"
        regular.touch()
        
        assert not handler.is_placeholder(regular)
    
    def test_not_placeholder_hidden_file(self, handler, temp_dir):
        """Handler correctly identifies hidden files (not .icloud)."""
        hidden = temp_dir / ".hidden_file"
        hidden.touch()
        
        assert not handler.is_placeholder(hidden)
    
    def test_extracts_real_name(self, handler, temp_dir):
        """Handler extracts real filename from placeholder."""
        placeholder = temp_dir / ".document.pdf.icloud"
        
        real_name = handler.get_real_name(placeholder)
        assert real_name == "document.pdf"
    
    def test_extracts_real_name_complex(self, handler, temp_dir):
        """Handler handles filenames with dots."""
        placeholder = temp_dir / ".my.file.name.txt.icloud"
        
        real_name = handler.get_real_name(placeholder)
        assert real_name == "my.file.name.txt"
    
    def test_get_real_path(self, handler, temp_dir):
        """Handler computes real path from placeholder."""
        placeholder = temp_dir / ".document.pdf.icloud"
        
        real_path = handler.get_real_path(placeholder)
        assert real_path == temp_dir / "document.pdf"
    
    def test_sync_status_placeholder(self, handler, icloud_placeholder):
        """Handler returns PLACEHOLDER status for .icloud files."""
        file_info = FileInfo.from_path(
            icloud_placeholder,
            icloud_placeholder.stat().st_mtime,
            icloud_placeholder.stat().st_size,
        )
        
        status = handler.get_sync_status(file_info)
        assert status == SyncStatus.PLACEHOLDER
    
    def test_sync_status_local(self, handler, sample_files):
        """Handler returns LOCAL status for regular files."""
        file_info = FileInfo.from_path(
            sample_files["txt"],
            sample_files["txt"].stat().st_mtime,
            sample_files["txt"].stat().st_size,
        )
        
        status = handler.get_sync_status(file_info)
        assert status == SyncStatus.LOCAL
    
    def test_is_icloud_path(self, handler):
        """Handler detects paths inside iCloud folder."""
        icloud_path = handler.icloud_root / "Documents" / "file.txt"
        local_path = Path.home() / "Desktop" / "file.txt"
        
        assert handler.is_icloud_path(icloud_path)
        assert not handler.is_icloud_path(local_path)


class TestICloudFileInfo:
    """Tests for FileInfo with iCloud placeholders."""
    
    def test_fileinfo_detects_placeholder(self, icloud_placeholder):
        """FileInfo correctly identifies iCloud placeholders."""
        info = FileInfo.from_path(
            icloud_placeholder,
            icloud_placeholder.stat().st_mtime,
            icloud_placeholder.stat().st_size,
        )
        
        assert info.is_icloud_placeholder is True
    
    def test_fileinfo_extracts_extension(self, icloud_placeholder):
        """FileInfo extracts correct extension from placeholder."""
        info = FileInfo.from_path(
            icloud_placeholder,
            icloud_placeholder.stat().st_mtime,
            icloud_placeholder.stat().st_size,
        )
        
        # .document.pdf.icloud → should extract .pdf
        assert info.extension == ".pdf"
