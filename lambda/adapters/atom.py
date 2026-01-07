"""Atom feed adapter for extracting items from Atom feeds."""

import logging
from typing import Any

import feedparser

from .base import BaseAdapter

logger = logging.getLogger(__name__)


class AtomAdapter(BaseAdapter):
    """Adapter for parsing Atom feeds."""
    
    def extract(self, content: str, source: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Extract items from Atom feed content.
        
        Atom feeds are similar to RSS but have some differences in field names.
        feedparser normalizes most of these, but we handle Atom-specific fields here.
        
        Args:
            content: Atom XML content
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
            logger.error(f"Error parsing Atom feed {source.get('id')}: {e}")
            return []
    
    def _parse_entry(self, entry: Any, source: dict[str, Any]) -> dict[str, Any] | None:
        """Parse a single Atom entry into a normalized item."""
        try:
            # Atom uses 'id' as the unique identifier
            item_id = entry.get("id", "")
            
            # Extract title
            title = entry.get("title", "").strip()
            if not title:
                return None
            
            # Extract link - Atom often has multiple links with different rel attributes
            link = ""
            if entry.get("links"):
                for link_obj in entry.links:
                    rel = link_obj.get("rel", "alternate")
                    if rel == "alternate":
                        link = link_obj.get("href", "")
                        break
                if not link and entry.links:
                    link = entry.links[0].get("href", "")
            elif entry.get("link"):
                link = entry.link
            
            # Use id as link fallback if it's a URL
            if not link and item_id.startswith("http"):
                link = item_id
            
            # Extract date - Atom prefers 'updated' over 'published'
            date = ""
            if entry.get("updated"):
                date = entry.updated
            elif entry.get("published"):
                date = entry.published
            
            # Extract summary/content
            summary = ""
            if entry.get("summary"):
                summary = self._clean_html(entry.summary)[:500]
            elif entry.get("content"):
                # Atom content can be a list
                content_list = entry.content if isinstance(entry.content, list) else [entry.content]
                for content_item in content_list:
                    if isinstance(content_item, dict):
                        summary = self._clean_html(content_item.get("value", ""))[:500]
                    else:
                        summary = self._clean_html(str(content_item))[:500]
                    if summary:
                        break
            
            return {
                "id": item_id,
                "title": title,
                "link": link,
                "date": date,
                "summary": summary,
            }
            
        except Exception as e:
            logger.warning(f"Error parsing Atom entry: {e}")
            return None
    
    def _clean_html(self, html: str) -> str:
        """Remove HTML tags from text."""
        if not html:
            return ""
        
        import re
        clean = re.sub(r'<[^>]+>', '', html)
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()
