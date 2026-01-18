"""Type definitions for scrape jobs."""

from typing import Callable, Awaitable, Literal
from pydantic import BaseModel
from playwright.async_api import Page

# Type aliases
ExtractFn = Callable[[Page, str], Awaitable[list[str]]]
ParseFn = Callable[[str], dict]
ExtractMethod = Literal["click_copy", "text_content", "inner_html", "terraform_registry", "terraform_links", "custom"]


class ScrapeJob(BaseModel):
    """Configuration for a scrape job."""
    name: str
    url: str
    selector: str
    method: ExtractMethod = "text_content"
    timeout: int = 30000
    wait_until: Literal["load", "domcontentloaded", "networkidle"] = "networkidle"
    debug_html_path: str | None = None
    debug_screenshot_path: str | None = None

    class Config:
        extra = "allow"


class ScrapeResult(BaseModel):
    """Result from a scrape job."""
    job_name: str
    url: str
    success: bool
    entries: list[dict | str]
    error: str | None = None
