"""GitHub Releases Atom adapter for extracting release information."""

import logging
import re
from typing import Any

import feedparser

from .base import BaseAdapter

logger = logging.getLogger(__name__)


class GitHubReleasesAtomAdapter(BaseAdapter):
    """Adapter for parsing GitHub releases Atom feeds."""
    
    def extract(self, content: str, source: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Extract items from GitHub releases Atom feed.
        
        GitHub releases.atom feeds have a specific structure:
        - Entry IDs are tag URIs like "tag:github.com,2008:Repository/123456/v1.0.0"
        - Links point to the release page
        - Content contains release notes (often markdown/HTML)
        
        Args:
            content: GitHub releases Atom XML content
            source: Source configuration
        
        Returns:
            List of extracted release items
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
            logger.error(f"Error parsing GitHub releases feed {source.get('id')}: {e}")
            return []
    
    def _parse_entry(self, entry: Any, source: dict[str, Any]) -> dict[str, Any] | None:
        """Parse a single GitHub release entry into a normalized item."""
        try:
            # GitHub uses tag URIs as IDs
            item_id = entry.get("id", "")
            
            # Extract version tag from ID or title
            # ID format: tag:github.com,2008:Repository/123456/v1.0.0
            tag_version = self._extract_tag_version(item_id, entry.get("title", ""))
            
            # Extract title - GitHub release titles are usually the tag name
            title = entry.get("title", "").strip()
            if not title:
                title = tag_version or "Unknown Release"
            
            # Extract link to release page
            link = ""
            if entry.get("links"):
                for link_obj in entry.links:
                    if link_obj.get("rel") == "alternate":
                        link = link_obj.get("href", "")
                        break
                if not link and entry.links:
                    link = entry.links[0].get("href", "")
            elif entry.get("link"):
                link = entry.link
            
            # Extract date
            date = ""
            if entry.get("updated"):
                date = entry.updated
            elif entry.get("published"):
                date = entry.published
            
            # Extract release notes summary
            summary = ""
            if entry.get("content"):
                content_list = entry.content if isinstance(entry.content, list) else [entry.content]
                for content_item in content_list:
                    if isinstance(content_item, dict):
                        summary = self._clean_html(content_item.get("value", ""))[:500]
                    else:
                        summary = self._clean_html(str(content_item))[:500]
                    if summary:
                        break
            elif entry.get("summary"):
                summary = self._clean_html(entry.summary)[:500]
            
            # Add tag version to the item for better fingerprinting
            return {
                "id": item_id,
                "title": title,
                "link": link,
                "date": date,
                "summary": summary,
                "tag": tag_version,
            }
            
        except Exception as e:
            logger.warning(f"Error parsing GitHub release entry: {e}")
            return None
    
    def _extract_tag_version(self, item_id: str, title: str) -> str:
        """Extract version tag from GitHub release ID or title."""
        # Try to extract from tag URI
        # Format: tag:github.com,2008:Repository/123456/v1.0.0
        if item_id:
            match = re.search(r'/([^/]+)$', item_id)
            if match:
                return match.group(1)
        
        # Fall back to title (often the tag name)
        if title:
            # Look for version patterns
            version_match = re.search(r'v?\d+\.\d+(?:\.\d+)?(?:-[a-zA-Z0-9.]+)?', title)
            if version_match:
                return version_match.group(0)
            return title.strip()
        
        return ""
    
    def _clean_html(self, html: str) -> str:
        """Remove HTML tags and clean text."""
        if not html:
            return ""
        
        # Remove HTML tags
        clean = re.sub(r'<[^>]+>', '', html)
        # Collapse whitespace
        clean = re.sub(r'\s+', ' ', clean)
        return clean.strip()
