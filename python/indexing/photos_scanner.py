"""
Photos Scanner - Apple Photos Library Metadata Extraction.

Reads metadata from Apple Photos (Photos.app) using the osxphotos library.
Extracts keywords, persons (faces), locations, and dates that Apple's ML
has already computed for each photo.

This enables semantic photo search without running our own vision models.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Generator
import json

logger = logging.getLogger(__name__)


@dataclass
class PhotoEntry:
    """Metadata for a single photo from Apple Photos."""
    file_path: str                    # Full path to original file
    file_name: str                    # Display name
    keywords: List[str] = field(default_factory=list)   # Apple's ML labels
    persons: List[str] = field(default_factory=list)    # Face names
    location: str = ""                # Place name or coordinates
    date: Optional[datetime] = None   # Photo date
    apple_uuid: str = ""              # Apple's unique ID
    is_favorite: bool = False
    is_hidden: bool = False
    album_names: List[str] = field(default_factory=list)
    
    def to_search_text(self) -> str:
        """
        Create a text representation for embedding fallback search.
        Only used when keyword search finds no results.
        """
        parts = []
        
        if self.persons:
            parts.append(f"Photo of {' and '.join(self.persons)}")
        else:
            parts.append("Photo")
        
        if self.keywords:
            parts.append(' '.join(self.keywords))
        
        if self.location:
            parts.append(f"at {self.location}")
        
        if self.date:
            parts.append(f"on {self.date.strftime('%B %Y')}")
        
        return ' '.join(parts)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "file_path": self.file_path,
            "file_name": self.file_name,
            "keywords": self.keywords,
            "persons": self.persons,
            "location": self.location,
            "date": self.date.isoformat() if self.date else None,
            "apple_uuid": self.apple_uuid,
            "is_favorite": self.is_favorite,
            "album_names": self.album_names,
        }


class PhotosScanner:
    """
    Scanner for Apple Photos Library.
    
    Uses osxphotos to read the Photos.sqlite database
    and extract all metadata that Apple has computed.
    """
    
    def __init__(self):
        self._photosdb = None
        self._available = None
    
    def is_available(self) -> bool:
        """Check if osxphotos is installed and Photos library is accessible."""
        if self._available is not None:
            return self._available
        
        try:
            import osxphotos
            # Try to access the default library
            self._photosdb = osxphotos.PhotosDB()
            self._available = True
            logger.info(f"Apple Photos library found: {self._photosdb.library_path}")
            logger.info(f"Total photos: {len(self._photosdb.photos())}")
        except ImportError:
            logger.warning(
                "osxphotos not installed. Apple Photos integration disabled. "
                "Install with: pip install osxphotos"
            )
            self._available = False
        except Exception as e:
            logger.warning(f"Could not access Apple Photos library: {e}")
            self._available = False
        
        return self._available
    
    def scan(self) -> List[PhotoEntry]:
        """
        Scan Apple Photos and return all photo entries.
        
        Returns:
            List of PhotoEntry with metadata from Apple Photos.
        """
        if not self.is_available():
            return []
        
        entries = list(self.scan_iter())
        logger.info(f"Scanned {len(entries)} photos from Apple Photos")
        return entries
    
    def scan_iter(self) -> Generator[PhotoEntry, None, None]:
        """
        Iterate over photos in Apple Photos library.
        
        Yields:
            PhotoEntry for each photo with accessible metadata.
        """
        if not self.is_available():
            return
        
        import osxphotos
        
        # Get all photos (including hidden, excluding deleted)
        photos = self._photosdb.photos(intrash=False)
        
        for photo in photos:
            try:
                # Skip if no valid path (e.g., iCloud placeholder not downloaded)
                if not photo.path or not Path(photo.path).exists():
                    continue
                
                # Extract metadata
                entry = PhotoEntry(
                    file_path=photo.path,
                    file_name=photo.filename or photo.original_filename or "Unknown",
                    keywords=list(photo.keywords) if photo.keywords else [],
                    persons=[p.name for p in photo.person_info if p.name] if photo.person_info else [],
                    location=self._format_location(photo),
                    date=photo.date,
                    apple_uuid=photo.uuid,
                    is_favorite=photo.favorite,
                    is_hidden=photo.hidden,
                    album_names=[a.title for a in photo.album_info if a.title] if photo.album_info else [],
                )
                
                yield entry
                
            except Exception as e:
                logger.debug(f"Error processing photo {photo.uuid}: {e}")
                continue
    
    def _format_location(self, photo) -> str:
        """Format photo location as a readable string."""
        try:
            if photo.place:
                # Apple provides structured place info
                place = photo.place
                parts = []
                if place.name:
                    parts.append(place.name)
                if place.city:
                    parts.append(place.city)
                if place.country:
                    parts.append(place.country)
                return ', '.join(parts) if parts else ""
            elif photo.location:
                # Fallback to coordinates
                lat, lon = photo.location
                return f"{lat:.2f}, {lon:.2f}"
        except Exception:
            pass
        return ""
    
    def get_photo_by_uuid(self, uuid: str) -> Optional[PhotoEntry]:
        """Get a single photo by its Apple UUID."""
        if not self.is_available():
            return None
        
        photos = self._photosdb.photos(uuid=[uuid])
        if photos:
            for entry in self.scan_iter():
                if entry.apple_uuid == uuid:
                    return entry
        return None
    
    def search_by_keywords(
        self, 
        keywords: List[str],
        include_persons: bool = True,
        include_locations: bool = True,
        limit: int = 20,
    ) -> List[PhotoEntry]:
        """
        Search photos by keyword matching.
        
        This is the FAST PATH - direct string matching, no ML needed.
        
        Args:
            keywords: List of terms to search for (e.g., ["Elliot", "snow"])
            include_persons: Match against person/face names
            include_locations: Match against location strings
            limit: Maximum results to return
            
        Returns:
            List of matching PhotoEntry, sorted by relevance.
        """
        if not self.is_available():
            return []
        
        # Normalize keywords for matching
        keywords_lower = [k.lower() for k in keywords]
        
        results = []
        
        for entry in self.scan_iter():
            score = 0
            
            # Match keywords
            for kw in entry.keywords:
                if kw.lower() in keywords_lower:
                    score += 2  # Strong match
                elif any(k in kw.lower() for k in keywords_lower):
                    score += 1  # Partial match
            
            # Match persons
            if include_persons:
                for person in entry.persons:
                    person_lower = person.lower()
                    if person_lower in keywords_lower:
                        score += 3  # Very strong match (named person)
                    elif any(k in person_lower for k in keywords_lower):
                        score += 2
            
            # Match location
            if include_locations and entry.location:
                location_lower = entry.location.lower()
                for kw in keywords_lower:
                    if kw in location_lower:
                        score += 1
            
            # Match album names
            for album in entry.album_names:
                if album.lower() in keywords_lower:
                    score += 1
            
            if score > 0:
                results.append((score, entry))
        
        # Sort by score descending, then by date descending
        results.sort(key=lambda x: (x[0], x[1].date or datetime.min), reverse=True)
        
        return [entry for _, entry in results[:limit]]


# Singleton instance
_scanner: Optional[PhotosScanner] = None


def get_photos_scanner() -> PhotosScanner:
    """Get the singleton PhotosScanner instance."""
    global _scanner
    if _scanner is None:
        _scanner = PhotosScanner()
    return _scanner


def search_photos(keywords: List[str], limit: int = 10) -> List[dict]:
    """
    Convenience function to search photos by keywords.
    
    Args:
        keywords: Search terms (e.g., ["Elliot", "snow", "winter"])
        limit: Max results
        
    Returns:
        List of photo metadata dicts
    """
    scanner = get_photos_scanner()
    results = scanner.search_by_keywords(keywords, limit=limit)
    return [r.to_dict() for r in results]


# Quick test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    scanner = get_photos_scanner()
    if scanner.is_available():
        print("\n=== First 5 Photos ===")
        for i, entry in enumerate(scanner.scan_iter()):
            if i >= 5:
                break
            print(f"\n{entry.file_name}")
            print(f"  Keywords: {entry.keywords}")
            print(f"  Persons: {entry.persons}")
            print(f"  Location: {entry.location}")
            print(f"  Date: {entry.date}")
        
        print("\n=== Search Test ===")
        results = scanner.search_by_keywords(["outdoor", "nature"], limit=3)
        for r in results:
            print(f"  {r.file_name}: {r.keywords}")
    else:
        print("Apple Photos not available")
