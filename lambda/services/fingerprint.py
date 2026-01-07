"""Fingerprint computation for content deduplication."""

import hashlib
import json
from typing import Any


def compute_fingerprint(items: list[dict[str, Any]], max_items: int = 10) -> str:
    """
    Compute a fingerprint hash from extracted items.
    
    The fingerprint is computed from a normalized representation of the items,
    ensuring that the same content always produces the same hash.
    
    Args:
        items: List of extracted items (each with id, title, link, date, etc.)
        max_items: Maximum number of items to include in fingerprint
    
    Returns:
        SHA256 hex digest of the normalized items
    """
    if not items:
        return hashlib.sha256(b"empty").hexdigest()
    
    # Take only the top N items for fingerprinting
    items_to_hash = items[:max_items]
    
    # Normalize items to stable representation
    normalized = []
    for item in items_to_hash:
        # Use only stable fields for fingerprinting
        normalized_item = {
            "id": item.get("id", ""),
            "title": _normalize_text(item.get("title", "")),
            "link": item.get("link", ""),
        }
        normalized.append(normalized_item)
    
    # Sort by id or link for stability
    normalized.sort(key=lambda x: x.get("id") or x.get("link") or "")
    
    # Serialize to JSON with sorted keys for determinism
    content = json.dumps(normalized, sort_keys=True, ensure_ascii=True)
    
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _normalize_text(text: str) -> str:
    """
    Normalize text for stable fingerprinting.
    
    - Strips leading/trailing whitespace
    - Collapses multiple whitespace to single space
    - Converts to lowercase
    """
    if not text:
        return ""
    
    # Strip and collapse whitespace
    normalized = " ".join(text.split())
    
    # Lowercase for case-insensitive comparison
    return normalized.lower()


def compute_content_hash(content: str) -> str:
    """
    Compute a simple hash of raw content.
    
    Used as a fallback when item extraction isn't possible.
    
    Args:
        content: Raw content string
    
    Returns:
        SHA256 hex digest
    """
    if not content:
        return hashlib.sha256(b"empty").hexdigest()
    
    # Normalize whitespace
    normalized = " ".join(content.split())
    
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
