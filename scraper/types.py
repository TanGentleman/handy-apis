"""Type definitions for scrape jobs."""

from datetime import datetime
from typing import Callable, Awaitable, Literal
from pydantic import BaseModel
from playwright.async_api import Page

# Type aliases
ExtractFn = Callable[[Page, str], Awaitable[list[str]]]
ParseFn = Callable[[str], dict]
ExtractMethod = Literal["click_copy", "text_content", "inner_html", "custom"]


class ScrapeJob(BaseModel):
    """Configuration for a scrape job."""
    name: str
    url: str
    selector: str
    method: ExtractMethod = "text_content"
    timeout: int = 30000
    wait_until: Literal["load", "domcontentloaded", "networkidle"] = "networkidle"
    use_cache: bool = True

    class Config:
        extra = "allow"  # Allow extra fields for custom data


class ScrapeResult(BaseModel):
    """Result from a scrape job."""
    job_name: str
    url: str
    success: bool
    entries: list[dict | str]
    cached: bool = False
    error: str | None = None


class BatchConfig(BaseModel):
    """Batch of scrape jobs."""
    jobs: list[ScrapeJob]


class SiteConfig(BaseModel):
    """Configuration for a documentation site."""
    name: str
    base_url: str
    sections: dict[str, str] = {}  # name -> path suffix (e.g., "guide": "/guide")
    pages: dict[str, str] = {}     # name -> path (e.g., "volumes": "/guide/volumes")
    selector: str
    method: ExtractMethod = "click_copy"

    def get_page_url(self, page: str) -> str:
        """Get full URL for a page."""
        if page not in self.pages:
            raise ValueError(f"Page '{page}' not found in site '{self.name}'")
        return self.base_url + self.pages[page]


class CachedDoc(BaseModel):
    """Metadata for a cached documentation page."""
    site: str
    page: str
    url: str
    path: str  # relative path to .md file
    scraped_at: datetime
    content_hash: str
    size_bytes: int
