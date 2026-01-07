"""HTTP fetcher with conditional GET support and concurrency control."""

import asyncio
import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

# Default user agent for polite scraping
USER_AGENT = "AI-Updates-Monitor/1.0 (https://github.com/ai-updates-monitor; contact@example.com)"


class Fetcher:
    """Async HTTP fetcher with conditional GET and rate limiting."""
    
    def __init__(self, concurrency: int = 10, timeout: int = 20):
        """
        Initialize fetcher.
        
        Args:
            concurrency: Maximum concurrent connections
            timeout: Request timeout in seconds
        """
        self.concurrency = concurrency
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None
        self._semaphore = asyncio.Semaphore(concurrency)
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=self.timeout,
                headers={"User-Agent": USER_AGENT},
            )
        return self._session
    
    async def fetch(
        self,
        url: str,
        etag: str | None = None,
        last_modified: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Fetch URL with conditional GET support.
        
        Args:
            url: URL to fetch
            etag: Previous ETag for conditional GET
            last_modified: Previous Last-Modified for conditional GET
            headers: Additional headers to send
        
        Returns:
            Dict with keys:
                - content: Response body (if 200)
                - etag: New ETag (if present)
                - last_modified: New Last-Modified (if present)
                - not_modified: True if 304 response
                - error: Error message (if failed)
        """
        async with self._semaphore:
            try:
                session = await self._get_session()
                
                # Build request headers
                req_headers = dict(headers or {})
                if etag:
                    req_headers["If-None-Match"] = etag
                if last_modified:
                    req_headers["If-Modified-Since"] = last_modified
                
                async with session.get(url, headers=req_headers, allow_redirects=True) as response:
                    # Handle 304 Not Modified
                    if response.status == 304:
                        return {"not_modified": True}
                    
                    # Handle errors
                    if response.status >= 400:
                        return {"error": f"HTTP {response.status}: {response.reason}"}
                    
                    # Read content
                    content = await response.text()
                    
                    # Extract validators for next request
                    new_etag = response.headers.get("ETag")
                    new_last_modified = response.headers.get("Last-Modified")
                    
                    return {
                        "content": content,
                        "etag": new_etag,
                        "last_modified": new_last_modified,
                        "content_type": response.headers.get("Content-Type", ""),
                    }
                    
            except asyncio.TimeoutError:
                return {"error": "Request timed out"}
            except aiohttp.ClientError as e:
                return {"error": f"Client error: {e}"}
            except Exception as e:
                return {"error": f"Unexpected error: {e}"}
    
    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()
