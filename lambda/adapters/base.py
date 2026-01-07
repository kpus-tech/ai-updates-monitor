"""Base adapter class for content extraction."""

from abc import ABC, abstractmethod
from typing import Any


class BaseAdapter(ABC):
    """Abstract base class for content adapters."""
    
    @abstractmethod
    def extract(self, content: str, source: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Extract items from content.
        
        Args:
            content: Raw content (HTML, XML, etc.)
            source: Source configuration dict with keys like:
                - id: Source identifier
                - url: Source URL
                - selector: CSS selector (for HTML adapters)
                - max_items: Maximum items to extract
                - ignore_patterns: Regex patterns to filter out
        
        Returns:
            List of extracted items, each containing:
                - id: Unique identifier (GUID, link, etc.)
                - title: Item title
                - link: Item URL
                - date: Publication date (optional)
                - summary: Brief description (optional)
        """
        pass
    
    def _get_max_items(self, source: dict[str, Any], default: int = 10) -> int:
        """Get max_items from source config or use default."""
        return source.get("max_items", default)
