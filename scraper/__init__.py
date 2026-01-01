"""Scraper module - unified scraping with pluggable extraction and parsing."""

from .types import ScrapeJob, ScrapeResult, BatchConfig, ExtractFn, ParseFn
from .extract import click_copy, text_content, inner_html, EXTRACTORS
from .cache import ScrapeCache
from .core import scrape, scrape_batch

__all__ = [
    # Types
    "ScrapeJob",
    "ScrapeResult",
    "BatchConfig",
    "ExtractFn",
    "ParseFn",
    # Extractors
    "click_copy",
    "text_content",
    "inner_html",
    "EXTRACTORS",
    # Cache
    "ScrapeCache",
    # Core
    "scrape",
    "scrape_batch",
]
