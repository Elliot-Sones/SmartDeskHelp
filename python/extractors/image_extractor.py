"""
Image extractor for photos.

Current implementation: Indexes filename and basic metadata only.
Future: Add vision model (ColQwen, LLaVA) for image understanding.
"""

from pathlib import Path
from typing import List, Set

from .base import BaseExtractor, IndexEntry


class ImageExtractor(BaseExtractor):
    """
    Extracts metadata from images.
    
    Current: Filename-based indexing
    Future: Vision model description
    """
    
    @property
    def source_name(self) -> str:
        return "photos"
    
    @property
    def supported_extensions(self) -> Set[str]:
        return {'.jpg', '.jpeg', '.png', '.heic', '.gif', '.webp', '.bmp', '.tiff'}
    
    def can_handle(self, file_path: str) -> bool:
        return Path(file_path).suffix.lower() in self.supported_extensions
    
    def extract(self, file_path: str) -> List[IndexEntry]:
        """Extract index entry from an image file."""
        path = Path(file_path)
        
        # Compute relative folder path
        try:
            folder = str(path.parent.relative_to(Path.home()))
        except ValueError:
            folder = str(path.parent)
        
        # Generate description (expandable for future vision model)
        description = self._generate_description(file_path)
        
        return [IndexEntry(
            text=f"{path.name} - Photo. {description}",
            entry_type="file",
            source="photos",
            file_path=str(path),
            file_name=path.name,
            folder=folder,
            chunk_index=None,
            extra_metadata={
                "extension": path.suffix.lower(),
                # Future: Add EXIF data
                # "width": None,
                # "height": None,
                # "date_taken": None,
            }
        )]
    
    def _generate_description(self, file_path: str) -> str:
        """
        Generate a text description of the image.
        
        Current: Use filename keywords
        Future: Use vision model (ColQwen, LLaVA, etc.)
        """
        path = Path(file_path)
        name = path.stem
        
        # Clean up filename for better searchability
        # Replace underscores/dashes with spaces
        cleaned_name = name.replace('_', ' ').replace('-', ' ')
        
        return f"Image named {cleaned_name}"
        
        # ------------------------------------------------------------------
        # FUTURE IMPLEMENTATION: Vision Model
        # ------------------------------------------------------------------
        # To enable vision-based image understanding, uncomment and modify:
        #
        # from colqwen import describe_image  # or LLaVA, etc.
        # try:
        #     description = describe_image(file_path)
        #     return description
        # except Exception as e:
        #     print(f"[ImageExtractor] Vision model error: {e}")
        #     return f"Image named {cleaned_name}"
        # ------------------------------------------------------------------
