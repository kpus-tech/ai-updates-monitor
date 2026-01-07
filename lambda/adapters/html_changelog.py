"""HTML Changelog adapter for extracting changelog entries from web pages."""

import logging
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseAdapter

logger = logging.getLogger(__name__)


class HtmlChangelogAdapter(BaseAdapter):
    """Adapter for parsing HTML changelog pages."""
    
    def extract(self, content: str, source: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Extract changelog entries from HTML page.
        
        Changelogs typically have:
        - Version headings (h1, h2, h3)
        - Date stamps
        - Lists of changes (ul, ol)
        
        The source config can include selectors for:
        - container_selector: Main changelog container
        - entry_selector: Individual changelog entries/sections
        - version_selector: Version heading
        - date_selector: Date element
        - content_selector: Change list content
        
        Args:
            content: HTML content
            source: Source configuration with selectors
        
        Returns:
            List of extracted changelog entries
        """
        max_items = self._get_max_items(source)
        base_url = source.get("url", "")
        
        try:
            soup = BeautifulSoup(content, "lxml")
            
            # Remove script and style elements
            for element in soup(["script", "style", "noscript"]):
                element.decompose()
            
            # Get selectors from source config
            selectors = source.get("selectors", {})
            container_selector = selectors.get("container")
            entry_selector = selectors.get("entry")
            version_selector = selectors.get("version")
            date_selector = selectors.get("date")
            content_selector = selectors.get("content")
            
            # Find container
            if container_selector:
                container = soup.select_one(container_selector)
                if not container:
                    logger.warning(f"Container not found for {source.get('id')}: {container_selector}")
                    container = soup
            else:
                container = soup
            
            # Find entries
            if entry_selector:
                entries = container.select(entry_selector)
            else:
                # Fallback: find entries by version headings
                entries = self._find_entries_by_headings(container)
            
            if not entries:
                logger.warning(f"No changelog entries found for {source.get('id')}")
                return []
            
            items = []
            for entry in entries[:max_items]:
                item = self._parse_entry(
                    entry,
                    base_url,
                    version_selector,
                    date_selector,
                    content_selector,
                )
                if item and item.get("title"):
                    items.append(item)
            
            return items
            
        except Exception as e:
            logger.error(f"Error parsing HTML changelog {source.get('id')}: {e}")
            return []
    
    def _parse_entry(
        self,
        element: Any,
        base_url: str,
        version_selector: str | None,
        date_selector: str | None,
        content_selector: str | None,
    ) -> dict[str, Any] | None:
        """Parse a single changelog entry."""
        try:
            # Extract version/title
            title = ""
            if version_selector:
                version_element = element.select_one(version_selector)
                if version_element:
                    title = version_element.get_text(strip=True)
            
            if not title:
                # Try common version heading patterns
                version_element = (
                    element.select_one("h1, h2, h3, h4") or
                    element.select_one("[class*='version']") or
                    element.select_one("[class*='release']")
                )
                if version_element:
                    title = version_element.get_text(strip=True)
            
            if not title:
                # If element itself is a heading
                if element.name in ["h1", "h2", "h3", "h4"]:
                    title = element.get_text(strip=True)
            
            if not title:
                return None
            
            # Extract date
            date = ""
            if date_selector:
                date_element = element.select_one(date_selector)
                if date_element:
                    date = date_element.get("datetime") or date_element.get_text(strip=True)
            
            if not date:
                # Try to find date in common patterns
                date_element = (
                    element.select_one("time") or
                    element.select_one("[class*='date']")
                )
                if date_element:
                    date = date_element.get("datetime") or date_element.get_text(strip=True)
                else:
                    # Try to extract date from title
                    date = self._extract_date_from_text(title)
            
            # Extract content summary
            summary = ""
            if content_selector:
                content_element = element.select_one(content_selector)
                if content_element:
                    summary = self._summarize_content(content_element)
            
            if not summary:
                # Try to find change list
                list_element = element.select_one("ul, ol")
                if list_element:
                    summary = self._summarize_content(list_element)
                else:
                    # Get text content excluding the heading
                    for heading in element.select("h1, h2, h3, h4"):
                        heading.decompose()
                    summary = element.get_text(strip=True)[:300]
            
            # Extract link (anchor ID)
            link = ""
            entry_id = element.get("id", "")
            if entry_id:
                link = f"{base_url}#{entry_id}"
            elif version_element := element.select_one("[id]"):
                link = f"{base_url}#{version_element.get('id')}"
            
            # Generate ID from version/title
            item_id = entry_id or self._generate_id(title)
            
            return {
                "id": item_id,
                "title": self._clean_title(title),
                "link": link,
                "date": self._clean_date(date),
                "summary": summary,
            }
            
        except Exception as e:
            logger.warning(f"Error parsing changelog entry: {e}")
            return None
    
    def _find_entries_by_headings(self, container: Any) -> list:
        """Find changelog entries by looking for version headings."""
        # Look for headings that match version patterns
        version_pattern = re.compile(
            r'v?\d+\.\d+(?:\.\d+)?|'  # Semantic versions
            r'\d{4}[-/]\d{2}[-/]\d{2}|'  # Dates
            r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+',
            re.IGNORECASE
        )
        
        entries = []
        for heading in container.select("h1, h2, h3, h4"):
            text = heading.get_text(strip=True)
            if version_pattern.search(text):
                # Include the heading and following siblings until next heading
                entries.append(heading)
        
        return entries
    
    def _summarize_content(self, element: Any) -> str:
        """Summarize changelog content."""
        # Extract list items
        items = element.select("li")
        if items:
            summaries = []
            for item in items[:5]:  # First 5 items
                text = item.get_text(strip=True)
                if text:
                    summaries.append(f"• {text[:100]}")
            return "\n".join(summaries)
        
        # Fall back to plain text
        return element.get_text(strip=True)[:300]
    
    def _extract_date_from_text(self, text: str) -> str:
        """Try to extract date from text."""
        # Common date patterns in changelogs
        patterns = [
            r'\((\d{4}[-/]\d{2}[-/]\d{2})\)',  # (2024-01-15)
            r'[-–]\s*(\d{4}[-/]\d{2}[-/]\d{2})',  # - 2024-01-15
            r'(\d{4}[-/]\d{2}[-/]\d{2})',  # 2024-01-15
            r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4})',  # Jan 15, 2024
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1)
        
        return ""
    
    def _generate_id(self, title: str) -> str:
        """Generate a stable ID from title."""
        normalized = re.sub(r'\s+', ' ', title.lower().strip())
        return f"version:{normalized[:100]}"
    
    def _clean_title(self, title: str) -> str:
        """Clean up changelog title."""
        # Remove excessive whitespace
        title = ' '.join(title.split())
        return title.strip()
    
    def _clean_date(self, date: str) -> str:
        """Clean up date string."""
        if not date:
            return ""
        date = ' '.join(date.split())
        return date.strip()
