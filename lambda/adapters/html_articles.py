"""HTML Articles adapter for extracting articles from web pages."""

import logging
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseAdapter

logger = logging.getLogger(__name__)


class HtmlArticlesAdapter(BaseAdapter):
    """Adapter for parsing HTML pages with article lists."""
    
    def extract(self, content: str, source: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Extract articles from HTML page using CSS selectors.
        
        The source config should include selectors for:
        - container_selector: Main container holding the article list
        - item_selector: Individual article items
        - title_selector: Title element within each item
        - link_selector: Link element (or use title if it's a link)
        - date_selector: Date element (optional)
        
        Args:
            content: HTML content
            source: Source configuration with selectors
        
        Returns:
            List of extracted article items
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
            item_selector = selectors.get("item")
            title_selector = selectors.get("title")
            link_selector = selectors.get("link")
            date_selector = selectors.get("date")
            
            # Find container if specified
            if container_selector:
                container = soup.select_one(container_selector)
                if not container:
                    logger.warning(f"Container not found for {source.get('id')}: {container_selector}")
                    container = soup
            else:
                container = soup
            
            # Find items
            if item_selector:
                items_elements = container.select(item_selector)
            else:
                # Fallback: try common article patterns
                items_elements = self._find_items_fallback(container)
            
            if not items_elements:
                logger.warning(f"No items found for {source.get('id')}")
                return []
            
            items = []
            for element in items_elements[:max_items]:
                item = self._parse_item(
                    element,
                    base_url,
                    title_selector,
                    link_selector,
                    date_selector,
                )
                if item and item.get("title"):
                    items.append(item)
            
            return items
            
        except Exception as e:
            logger.error(f"Error parsing HTML articles {source.get('id')}: {e}")
            return []
    
    def _parse_item(
        self,
        element: Any,
        base_url: str,
        title_selector: str | None,
        link_selector: str | None,
        date_selector: str | None,
    ) -> dict[str, Any] | None:
        """Parse a single article item."""
        try:
            # Extract title
            title = ""
            title_element = None
            if title_selector:
                title_element = element.select_one(title_selector)
            if not title_element:
                # Try common title patterns
                title_element = (
                    element.select_one("h1, h2, h3, h4") or
                    element.select_one("[class*='title']") or
                    element.select_one("a")
                )
            
            if title_element:
                title = title_element.get_text(strip=True)
            
            if not title:
                return None
            
            # Extract link
            link = ""
            if link_selector:
                link_element = element.select_one(link_selector)
                if link_element:
                    link = link_element.get("href", "")
            
            if not link:
                # Try to find link from title element or first anchor
                if title_element and title_element.name == "a":
                    link = title_element.get("href", "")
                elif title_element:
                    parent_link = title_element.find_parent("a")
                    if parent_link:
                        link = parent_link.get("href", "")
                
                if not link:
                    # Try first anchor in element
                    first_link = element.select_one("a[href]")
                    if first_link:
                        link = first_link.get("href", "")
            
            # Make link absolute
            if link and not link.startswith(("http://", "https://")):
                link = urljoin(base_url, link)
            
            # Extract date
            date = ""
            if date_selector:
                date_element = element.select_one(date_selector)
                if date_element:
                    date = date_element.get_text(strip=True)
                    # Also check datetime attribute
                    if not date:
                        date = date_element.get("datetime", "")
            
            if not date:
                # Try common date patterns
                date_element = (
                    element.select_one("time") or
                    element.select_one("[class*='date']") or
                    element.select_one("[class*='time']")
                )
                if date_element:
                    date = date_element.get("datetime") or date_element.get_text(strip=True)
            
            # Generate ID from link or title
            item_id = link or self._generate_id(title)
            
            return {
                "id": item_id,
                "title": title,
                "link": link,
                "date": self._clean_date(date),
            }
            
        except Exception as e:
            logger.warning(f"Error parsing article item: {e}")
            return None
    
    def _find_items_fallback(self, container: Any) -> list:
        """Find article items using common patterns."""
        # Try common article list patterns
        patterns = [
            "article",
            "[class*='article']",
            "[class*='post']",
            "[class*='card']",
            "[class*='item']",
            "li[class*='blog']",
            ".blog-post",
            ".news-item",
        ]
        
        for pattern in patterns:
            items = container.select(pattern)
            if len(items) >= 2:  # At least 2 items suggests a list
                return items
        
        return []
    
    def _generate_id(self, title: str) -> str:
        """Generate a stable ID from title."""
        # Normalize and hash the title
        normalized = re.sub(r'\s+', ' ', title.lower().strip())
        return f"title:{normalized[:100]}"
    
    def _clean_date(self, date: str) -> str:
        """Clean up date string."""
        if not date:
            return ""
        
        # Remove common prefixes
        date = re.sub(r'^(Published|Posted|Updated|Date)[:|\s]*', '', date, flags=re.IGNORECASE)
        
        # Collapse whitespace
        date = ' '.join(date.split())
        
        return date.strip()
