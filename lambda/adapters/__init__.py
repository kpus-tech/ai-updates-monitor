"""Adapters package for parsing different source types."""

from .base import BaseAdapter
from .rss import RssAdapter
from .atom import AtomAdapter
from .github_releases import GitHubReleasesAtomAdapter
from .html_articles import HtmlArticlesAdapter
from .html_changelog import HtmlChangelogAdapter

# Adapter registry
_ADAPTERS: dict[str, BaseAdapter] = {
    "rss": RssAdapter(),
    "atom": AtomAdapter(),
    "github_releases_atom": GitHubReleasesAtomAdapter(),
    "html_articles": HtmlArticlesAdapter(),
    "html_changelog": HtmlChangelogAdapter(),
}


def get_adapter(adapter_type: str) -> BaseAdapter:
    """
    Get adapter instance by type.
    
    Args:
        adapter_type: Adapter type string (rss, atom, github_releases_atom, html_articles, html_changelog)
    
    Returns:
        Adapter instance
    
    Raises:
        ValueError: If adapter type is not recognized
    """
    adapter = _ADAPTERS.get(adapter_type)
    if adapter is None:
        raise ValueError(f"Unknown adapter type: {adapter_type}. Available: {list(_ADAPTERS.keys())}")
    return adapter


__all__ = [
    "BaseAdapter",
    "RssAdapter",
    "AtomAdapter",
    "GitHubReleasesAtomAdapter",
    "HtmlArticlesAdapter",
    "HtmlChangelogAdapter",
    "get_adapter",
]
