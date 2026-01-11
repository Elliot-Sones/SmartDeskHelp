"""
iCloud Handler - macOS iCloud Drive integration.

Handles:
- Detection of iCloud placeholder files (.icloud)
- Triggering downloads via brctl
- Tracking sync status
"""

import asyncio
import logging
import subprocess
from pathlib import Path
from typing import Optional

from ..config import get_config, IndexerConfig
from ..models import FileInfo, SyncStatus


logger = logging.getLogger(__name__)


class ICloudHandler:
    """
    iCloud Drive handler for macOS.
    
    iCloud files that aren't downloaded locally appear as placeholder
    files with names like ".filename.icloud". This handler:
    
    1. Detects these placeholder files
    2. Extracts the real filename
    3. Optionally triggers download via `brctl`
    4. Tracks sync status for the database
    """
    
    def __init__(self, config: IndexerConfig | None = None):
        self.config = config or get_config()
        self._download_timeout_sec = 30
    
    @property
    def icloud_root(self) -> Path:
        """Path to iCloud Drive folder."""
        return self.config.icloud_root
    
    def is_icloud_path(self, path: Path) -> bool:
        """Check if a path is inside iCloud Drive."""
        try:
            path.relative_to(self.icloud_root)
            return True
        except ValueError:
            return False
    
    def is_placeholder(self, path: Path) -> bool:
        """
        Check if a file is an iCloud placeholder (not downloaded).
        
        Placeholder files have names like: .filename.ext.icloud
        """
        name = path.name
        return name.startswith(".") and name.endswith(".icloud")
    
    def get_real_name(self, placeholder_path: Path) -> str:
        """
        Extract the real filename from an iCloud placeholder.
        
        ".document.pdf.icloud" → "document.pdf"
        """
        name = placeholder_path.name
        if not self.is_placeholder(placeholder_path):
            return name
        
        # Remove leading "." and trailing ".icloud"
        return name[1:-7]
    
    def get_real_path(self, placeholder_path: Path) -> Path:
        """
        Get the path the file will have once downloaded.
        
        /path/.document.pdf.icloud → /path/document.pdf
        """
        real_name = self.get_real_name(placeholder_path)
        return placeholder_path.parent / real_name
    
    def get_sync_status(self, file_info: FileInfo) -> SyncStatus:
        """
        Determine the sync status of a file.
        
        Args:
            file_info: File information from scanner
            
        Returns:
            SyncStatus enum value
        """
        if file_info.is_icloud_placeholder:
            return SyncStatus.PLACEHOLDER
        
        if self.is_icloud_path(file_info.path):
            return SyncStatus.LOCAL  # Downloaded iCloud file
        
        return SyncStatus.LOCAL  # Regular local file
    
    async def download_file(
        self, 
        placeholder_path: Path,
        timeout_sec: Optional[int] = None,
    ) -> Optional[Path]:
        """
        Trigger download of an iCloud placeholder file.
        
        Uses `brctl download` to request the file from iCloud.
        
        Args:
            placeholder_path: Path to the .icloud placeholder
            timeout_sec: How long to wait for download (default: 30s)
            
        Returns:
            Path to the downloaded file, or None if download failed/timed out
        """
        if not self.is_placeholder(placeholder_path):
            # Already downloaded
            return placeholder_path
        
        real_path = self.get_real_path(placeholder_path)
        timeout = timeout_sec or self._download_timeout_sec
        
        logger.debug(f"Requesting iCloud download: {real_path.name}")
        
        try:
            # brctl download triggers iCloud to download the file
            process = await asyncio.create_subprocess_exec(
                "brctl", "download", str(real_path),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await process.wait()
            
            # Wait for the file to appear
            downloaded = await self._wait_for_download(real_path, timeout)
            
            if downloaded:
                logger.debug(f"iCloud download complete: {real_path.name}")
                return real_path
            else:
                logger.warning(f"iCloud download timed out: {real_path.name}")
                return None
                
        except FileNotFoundError:
            logger.error("brctl not found - iCloud downloads require macOS")
            return None
        except Exception as e:
            logger.error(f"iCloud download failed: {e}")
            return None
    
    async def _wait_for_download(
        self, 
        real_path: Path, 
        timeout_sec: int,
    ) -> bool:
        """
        Wait for a file to be downloaded from iCloud.
        
        Returns True if the file appeared within the timeout.
        """
        interval = 0.5  # Check every 500ms
        elapsed = 0.0
        
        while elapsed < timeout_sec:
            if real_path.exists():
                return True
            
            await asyncio.sleep(interval)
            elapsed += interval
        
        return False
    
    def should_index_placeholder(self) -> bool:
        """
        Whether to index placeholder files.
        
        If True, placeholders are indexed with just the filename
        (no content chunks). They can be downloaded on-demand later.
        """
        return True


def get_icloud_handler(config: IndexerConfig | None = None) -> ICloudHandler:
    """Get an iCloud handler instance."""
    return ICloudHandler(config)
