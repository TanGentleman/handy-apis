"""Scraper module - stateless scraping with pluggable extraction."""

from .models import ScrapeJob, ScrapeResult, ExtractFn, ParseFn
from .extract import click_copy, text_content, inner_html, terraform_links, EXTRACTORS
from .core import scrape, scrape_batch

__all__ = [
    # Types
    "ScrapeJob",
    "ScrapeResult",
    "ExtractFn",
    "ParseFn",
    # Extractors
    "click_copy",
    "text_content",
    "inner_html",
    "terraform_links",
    "EXTRACTORS",
    # Core
    "scrape",
    "scrape_batch",
]
