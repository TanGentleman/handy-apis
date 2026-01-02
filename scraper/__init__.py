"""Scraper module - unified scraping with pluggable extraction and parsing."""

from .types import ScrapeJob, ScrapeResult, BatchConfig, ExtractFn, ParseFn, SiteConfig, CachedDoc
from .extract import click_copy, text_content, inner_html, EXTRACTORS
from .cache import ScrapeCache
from .docs_cache import DocsCache
from .collections import CollectionManager
from .core import scrape, scrape_batch, get_all_links as get_links

__all__ = [
    # Types
    "ScrapeJob",
    "ScrapeResult",
    "BatchConfig",
    "ExtractFn",
    "ParseFn",
    "SiteConfig",
    "CachedDoc",
    # Extractors
    "click_copy",
    "text_content",
    "inner_html",
    "EXTRACTORS",
    # Cache
    "ScrapeCache",
    "DocsCache",
    # Collections
    "CollectionManager",
    # Core
    "scrape",
    "scrape_batch",
    "get_links",
]
