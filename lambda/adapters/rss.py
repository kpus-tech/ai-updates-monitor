"""RSS feed adapter for extracting items from RSS feeds."""

import logging
from typing import Any

import feedparser

from .base import BaseAdapter

logger = logging.getLogger(__name__)


class RssAdapter(BaseAdapter):
    """Adapter for parsing RSS feeds."""
    
    def extract(self, content: str, source: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Extract items from RSS feed content.
        
        Args:
            content: RSS XML content
            source: Source configuration
        
        Returns:
            List of extracted feed items
        """
        max_items = self._get_max_items(source)
        
        try:
            feed = feedparser.parse(content)
            
            if feed.bozo and not feed.entries:
                logger.warning(f"Feed parse error for {source.get('id')}: {feed.bozo_exception}")
                return []
            
            items = []
            for entry in feed.entries[:max_items]:
                item = self._parse_entry(entry, source)
                if item:
                    items.append(item)
            
            return items
            
        except Exception as e:
            logger.error(f"Error parsing RSS feed {source.get('id')}: {e}")
            return []
    
    def _parse_entry(self, entry: Any, source: dict[str, Any]) -> dict[str, Any] | None:
        """Parse a single feed entry into a normalized item."""
        try:
            # Extract unique ID (prefer guid, fallback to link)
            item_id = entry.get("id") or entry.get("guid") or entry.get("link", "")
            
            # Extract title
            title = entry.get("title", "").strip()
            if not title:
                return None
            
            # Extract link
            link = entry.get("link", "")
            if not link and entry.get("links"):
                for link_obj in entry.links:
                    if link_obj.get("rel") == "alternate" or link_obj.get("type", "").startswith("text/html"):
                        link = link_obj.get("href", "")
                        break
                if not link and entry.links:
                    link = entry.links[0].get("href", "")
            
            # Extract date
            date = ""
            if entry.get("published"):
                date = entry.published
            elif entry.get("updated"):
                date = entry.updated
            elif entry.get("created"):
                date = entry.created
            
            # Extract summary
            summary = ""
            if entry.get("summary"):
                summary = self._clean_html(entry.summary)[:500]
            elif entry.get("description"):
                summary = self._clean_html(entry.description)[:500]
            
            return {
                "id": item_id,
                "title": title,
                "link": link,
                "date": date,
                "summary": summary,
            }
            
        except Exception as e:
            logger.warning(f"Error parsing entry: {e}")
            return None
    
    def _clean_html(self, html: str) -> str:
        """Remove HTML tags from text."""
        if not html:
            return ""
        
        # Simple HTML stripping - BeautifulSoup is available but this is faster for simple cases
        import re
        clean = re.sub(r'<[^>]+>', '', html)
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()
