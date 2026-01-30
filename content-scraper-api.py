# ---
# deploy: true
# ---

# Content Scraper API - Modal-native with Dict caching and browser lifecycle

import asyncio
import io
import json
import re
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import modal
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from scraper.bulk import (
    ASSET_EXTENSIONS,
    DEFAULT_DELAY_MS,
    USER_AGENT,
    JobStatus,
    calculate_batches,
    create_job,
    is_asset_url,
    jobs,
    update_job_progress,
)

# Modal image with Playwright
playwright_image = (
    modal.Image.debian_slim(python_version="3.11")
    .run_commands(
        "apt-get update",
        "apt-get install -y software-properties-common",
        "apt-add-repository non-free",
        "apt-add-repository contrib",
        "pip install playwright==1.42.0",
        "playwright install-deps chromium",
        "playwright install chromium",
    )
    .pip_install("fastapi[standard]", "pydantic", "httpx", "markdownify")
    .add_local_dir("scraper", "/root/scraper")
)

app = modal.App("content-scraper-api", image=playwright_image)

# Modal Dict for caching (7-day TTL built-in)
cache = modal.Dict.from_name("scraper-cache", create_if_missing=True)

# Modal Dict for tracking failed links
error_tracker = modal.Dict.from_name("scraper-errors", create_if_missing=True)

DEFAULT_MAX_AGE = 3600 * 48  # 48 hours
ERROR_THRESHOLD = 3  # Skip links that have failed this many times
ERROR_EXPIRY = 86400  # 24 hours - errors auto-expire


# --- Site Config Models ---
class ClickStep(BaseModel):
    """A single step in a click sequence."""
    selector: str
    waitAfter: int = 500


class LinksConfig(BaseModel):
    """Configuration for link discovery."""
    startUrls: list[str] = Field(default_factory=lambda: [""])
    pattern: str = ""
    maxDepth: int = 2
    waitFor: str | None = None
    waitForTimeoutMs: int = 15000
    waitUntil: str = "domcontentloaded"
    gotoTimeoutMs: int = 30000


class ContentConfig(BaseModel):
    """Configuration for content extraction."""
    mode: str = "browser"
    selector: str | None = None
    method: str = "inner_html"
    clickSequence: list[ClickStep] | None = None
    waitFor: str | None = None
    waitForTimeoutMs: int = 15000
    waitUntil: str = "domcontentloaded"
    gotoTimeoutMs: int = 30000


class SiteConfig(BaseModel):
    """Configuration for a documentation site."""
    name: str
    baseUrl: str
    mode: str = "fetch"
    defaultPath: str = ""
    testPath: str | None = None
    extractor: str | None = None
    links: LinksConfig = Field(default_factory=LinksConfig)
    content: ContentConfig = Field(default_factory=ContentConfig)


# --- Cache Helpers ---
def get_cached(cache_key: str, max_age: int) -> dict | None:
    """Get from cache if fresh, else None."""
    try:
        cached = cache[cache_key]
        if cached and (time.time() - cached.get("timestamp", 0)) < max_age:
            return cached
    except KeyError:
        pass
    return None


def set_cached(cache_key: str, data: dict) -> None:
    """Set cache entry with timestamp."""
    cache[cache_key] = {**data, "timestamp": time.time()}


# --- Load sites config ---
def load_sites_config() -> dict[str, SiteConfig]:
    """Load and validate sites configuration from embedded JSON file.

    Returns dict mapping site_id to validated SiteConfig.
    Raises ValidationError if config is invalid.
    """
    config_path = Path("/root/scraper/config/sites.json")
    if not config_path.exists():
        # Fallback to local path during development
        config_path = Path(__file__).parent / "scraper" / "config" / "sites.json"
    with open(config_path) as f:
        raw = json.load(f)["sites"]
    return {site_id: SiteConfig(**cfg) for site_id, cfg in raw.items()}


# --- Response Models ---
class ContentResponse(BaseModel):
    site_id: str
    path: str
    content: str
    content_length: int
    url: str
    from_cache: bool = False


class LinksResponse(BaseModel):
    site_id: str
    links: list[str]
    count: int


class ExportRequest(BaseModel):
    urls: list[str]
    cached_only: bool = True
    max_age: int = DEFAULT_MAX_AGE
    include_manifest: bool = True


# --- Helper functions ---
def html_to_markdown(html: str) -> str:
    """Convert HTML to markdown using markdownify."""
    from markdownify import markdownify as md
    return md(html, heading_style="ATX", strip=["script", "style"]).strip()


def derive_wait_for(content_cfg: ContentConfig) -> str | None:
    """Derive the waitFor selector from content config."""
    if content_cfg.waitFor:
        return content_cfg.waitFor
    if content_cfg.clickSequence:
        return content_cfg.clickSequence[0].selector
    return content_cfg.selector


def extract_page_content(page, content_cfg: ContentConfig) -> str:
    """Extract content from a page using the configured method.

    Assumes page is already loaded and ready. Handles click_copy vs inner_html.
    Returns extracted content as string (markdown for inner_html, raw for click_copy).
    """
    if content_cfg.method == "click_copy":
        if content_cfg.clickSequence:
            for step in content_cfg.clickSequence:
                page.click(step.selector)
                page.wait_for_timeout(step.waitAfter)
        else:
            if not content_cfg.selector:
                raise ValueError("click_copy method requires 'selector' or 'clickSequence'")
            page.click(content_cfg.selector)
            page.wait_for_timeout(1000)
        return page.evaluate("() => navigator.clipboard.readText()")
    else:  # inner_html
        element = page.query_selector(content_cfg.selector)
        raw_html = element.inner_html() if element else ""
        return html_to_markdown(raw_html)


def clean_url(url: str) -> str:
    """Remove query params and fragments from URL."""
    return url.split("?")[0].split("#")[0].rstrip("/")


def normalize_url(url: str) -> str:
    """Normalize URL for consistent matching.

    - Lowercase scheme and host
    - Remove query/fragment
    - Collapse duplicate slashes in path
    - Remove trailing slash (always, for consistent prefix matching)
    """
    url = url.strip()
    p = urlparse(url)

    scheme = (p.scheme or "https").lower()
    netloc = (p.netloc or "").lower()

    # Normalize path - keep empty for root, always strip trailing slash
    path = p.path or ""
    path = re.sub(r"/{2,}", "/", path)  # collapse //
    path = path.rstrip("/")  # always remove trailing slash

    return urlunparse((scheme, netloc, path, "", "", ""))


def normalize_path(path: str) -> str:
    """Normalize a URL path for cache keys.

    - Empty string for base page
    - Always starts with / otherwise
    - No trailing slash
    - No duplicate slashes
    """
    if not path:
        return ""
    path = re.sub(r"/{2,}", "/", path)
    if not path.startswith("/"):
        path = "/" + path
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return "" if path == "/" else path


def get_site_resolver() -> dict:
    """Build site resolver mapping normalized baseUrls to site_ids.

    Returns dict with:
    - 'sites': list of (normalized_base, site_id) sorted by length desc (for longest-prefix match)
    - 'config': full sites config

    Not cached - rebuilds each call to pick up sites.json changes.
    This is cheap (parse JSON + sort small list).
    """
    sites_config = load_sites_config()
    sites = []

    for site_id, config in sites_config.items():
        base_url = config.baseUrl
        if base_url:
            norm_base = normalize_url(base_url)
            sites.append((norm_base, site_id))

    # Sort by length descending for longest-prefix match
    sites.sort(key=lambda x: len(x[0]), reverse=True)

    return {
        "sites": sites,
        "config": sites_config,
    }


def resolve_url_to_site(url: str) -> tuple[str | None, str, str]:
    """Resolve a URL to (site_id, path, normalized_url).

    Uses longest-prefix matching on normalized baseUrls.
    Returns (None, "", normalized_url) if no match found.
    """
    norm_url = normalize_url(url)
    resolver = get_site_resolver()

    for norm_base, site_id in resolver["sites"]:
        if norm_url == norm_base:
            return (site_id, "", norm_url)
        if norm_url.startswith(norm_base + "/"):
            path = norm_url[len(norm_base):]
            return (site_id, path, norm_url)

    return (None, "", norm_url)


def filter_and_group_urls(urls: list[str]) -> dict:
    """Filter assets and group URLs by site for bulk processing."""
    by_site: dict[str, list[str]] = {}
    assets, unknown = [], []

    for url in urls:
        site_id, path, _ = resolve_url_to_site(url)
        if not site_id:
            unknown.append(url)
        elif is_asset_url(url):
            assets.append({"url": url, "site_id": site_id, "path": path})
        else:
            by_site.setdefault(site_id, []).append(path)

    return {"by_site": by_site, "assets": assets, "unknown": unknown}


def zip_path_for(site_id: str, path: str) -> str:
    """Generate safe ZIP path: docs/{site_id}/{path}.md

    Handles edge cases:
    - Base page (path="") -> docs/{site}/index.md
    - Prevents zip-slip attacks
    """
    import posixpath

    path = normalize_path(path)
    if path == "":
        return f"docs/{site_id}/index.md"

    # Remove leading slash and normalize
    clean = path.lstrip("/")
    clean = posixpath.normpath(clean)

    # Security: prevent zip-slip
    if clean.startswith("..") or "/.." in clean:
        raise ValueError(f"Unsafe path: {path}")

    return f"docs/{site_id}/{clean}.md"


def extract_links_from_html(html: str, base_url: str, pattern: str) -> list[str]:
    """Extract links from HTML string using regex."""
    links = set()
    for match in re.finditer(r'href="([^"]*)"', html):
        link = match.group(1)
        link = clean_url(link)

        # Resolve relative URLs
        if link.startswith("/"):
            parsed = urlparse(base_url)
            link = f"{parsed.scheme}://{parsed.netloc}{link}"
        elif not link.startswith("http"):
            link = urljoin(base_url, link)

        # Filter by pattern, but always allow the base URL itself.
        if pattern and pattern not in link:
            if link != base_url and link != f"{base_url}/":
                continue

        # Only include links from same domain
        if urlparse(link).netloc == urlparse(base_url).netloc:
            links.add(link)

    return sorted(links)


# --- Browser-based Scraper with Lifecycle ---
@app.cls(timeout=300, retries=2)
class Scraper:
    """Browser-based scraper with lifecycle management.

    Uses @modal.enter() to launch browser once per container,
    reusing it across all requests for performance.
    """

    @modal.enter()
    def start_browser(self):
        """Launch browser once when container starts."""
        from playwright.sync_api import sync_playwright

        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch()
        print("Browser started")

    @modal.exit()
    def close_browser(self):
        """Clean up browser when container exits."""
        self.browser.close()
        self.pw.stop()
        print("Browser closed")

    def _dismiss_cookie_banner(self, page, site_config: SiteConfig):
        """Handle cookie consent banners for specific sites."""
        extractor = site_config.extractor or "default"
        if extractor == "terraform":
            try:
                btn = page.get_by_role("button", name="Accept All")
                btn.click(timeout=3000)
                page.wait_for_timeout(1000)
            except Exception:
                pass  # Banner may not exist

    @modal.method()
    def scrape_content(self, site_id: str, path: str, force: bool = False) -> dict:
        """Scrape content from a page using browser."""
        print(f"[scrape_content] site_id={site_id}, path={path}, force={force}")
        sites_config = load_sites_config()
        config = sites_config.get(site_id)
        if not config:
            print(f"[scrape_content] ERROR: Unknown site: {site_id}")
            return {"success": False, "error": f"Unknown site: {site_id}"}

        url = config.baseUrl + path
        error_key = f"{site_id}:{path}"

        # Force flag clears error tracking for this path
        if force:
            try:
                error_tracker.pop(error_key, None)
            except Exception:
                pass
        else:
            # Check error tracker - skip if failed too many times (unless expired)
            try:
                error_info = error_tracker[error_key]
                if error_info and error_info.get("count", 0) >= ERROR_THRESHOLD:
                    # Check if error has expired (auto-recovery)
                    age = time.time() - error_info.get("timestamp", 0)
                    if age < ERROR_EXPIRY:
                        print(f"[scrape_content] SKIP {url} (failed {error_info['count']}x)")
                        return {
                            "success": False,
                            "error": f"Skipped: failed {error_info['count']} times",
                            "url": url,
                            "error_count": error_info["count"],
                        }
                    else:
                        # Error expired, clear it and retry
                        print(f"[scrape_content] Error expired for {url}, retrying...")
                        error_tracker.pop(error_key, None)
            except KeyError:
                pass  # No error history

        content_cfg = config.content
        wait_for = derive_wait_for(content_cfg)

        print(f"[scrape_content] {url} (method={content_cfg.method})")

        # Determine permissions based on extraction method
        permissions = ["clipboard-read", "clipboard-write"] if content_cfg.method == "click_copy" else []

        context = self.browser.new_context(permissions=permissions)
        page = context.new_page()

        try:
            page.goto(url, wait_until=content_cfg.waitUntil, timeout=content_cfg.gotoTimeoutMs)

            # Handle site-specific setup (cookie consent, etc.)
            self._dismiss_cookie_banner(page, config)

            # Wait for content to be ready
            if wait_for:
                page.wait_for_selector(wait_for, state="visible", timeout=content_cfg.waitForTimeoutMs)
                page.wait_for_timeout(500)

            content = extract_page_content(page, content_cfg)

            print(f"[scrape_content] OK {len(content):,} chars")

            # Clear error on success
            try:
                error_tracker.pop(error_key, None)
            except Exception:
                pass

            return {"success": True, "content": content, "url": url}

        except Exception as e:
            error_msg = str(e)[:200]  # Truncate long errors
            print(f"[scrape_content] FAIL {error_msg}")

            # Track error
            try:
                error_info = error_tracker.get(error_key, {})
                error_tracker[error_key] = {
                    "count": error_info.get("count", 0) + 1,
                    "last_error": error_msg,
                    "timestamp": time.time(),
                }
            except Exception:
                pass

            return {"success": False, "error": error_msg, "url": url}
        finally:
            context.close()

    def _detect_framework(self, page) -> str:
        """Detect docs framework (docusaurus, mintlify, gitbook, readme, vitepress)."""
        framework_indicators = {
            "docusaurus": [
                'meta[name="generator"][content*="Docusaurus"]',
                'div[class*="docusaurus"]',
                '.theme-doc-markdown'
            ],
            "mintlify": [
                'meta[name="generator"][content*="Mintlify"]',
                'div[id="__next"]',
                'button[aria-label="Copy page"]'
            ],
            "gitbook": [
                'meta[name="generator"][content*="GitBook"]',
                '.gitbook-markdown',
                'div[class*="gitbook"]'
            ],
            "readme": [
                'meta[name="generator"][content*="readme"]',
                '.markdown-body'
            ],
            "vitepress": [
                'meta[name="generator"][content*="VitePress"]',
                '.vp-doc'
            ]
        }

        for fw_name, selectors in framework_indicators.items():
            for selector in selectors:
                try:
                    if page.query_selector(selector):
                        return fw_name
                except Exception:
                    continue
        return "unknown"

    def _test_copy_button(self, url: str, selector: str) -> dict:
        """Test a copy button by clicking and reading clipboard."""
        try:
            test_context = self.browser.new_context(
                permissions=["clipboard-read", "clipboard-write"]
            )
            test_page = test_context.new_page()
            test_page.goto(url, wait_until="domcontentloaded", timeout=30000)
            test_page.wait_for_timeout(1000)
            test_page.click(selector, timeout=5000)
            test_page.wait_for_timeout(1000)
            content = test_page.evaluate("() => navigator.clipboard.readText()")
            test_context.close()

            if content and len(content) > 500:
                return {
                    "selector": selector,
                    "chars": len(content),
                    "works": True
                }
        except Exception as e:
            return {
                "selector": selector,
                "error": str(e)[:100],
                "works": False
            }
        return {"selector": selector, "works": False}

    def _find_copy_buttons(self, page, url: str) -> list[dict]:
        """Find and test copy button selectors on the page."""
        copy_button_patterns = [
            "//button[@aria-label='Copy page']",
            "//button[@title='Copy page']",
            "//button[.//span[contains(text(), 'Copy page')]]",
            "//button[contains(., 'Copy page')]",
            "button[type='button']:has(div:has-text('Copy as Markdown'))",
            "#page-context-menu-button",
            "//button[.//span[normalize-space(text())='Copy page']]"
        ]

        copy_buttons = []
        for pattern in copy_button_patterns:
            try:
                elements = page.locator(pattern).all()
                if elements:
                    result = self._test_copy_button(url, pattern)
                    if result:
                        copy_buttons.append(result)
            except Exception:
                continue

        return copy_buttons

    def _find_content_selectors(self, page) -> list[dict]:
        """Find and rank content selectors by quality."""
        candidate_selectors = [
            "main article .theme-doc-markdown",  # Docusaurus
            "main article",                      # Mintlify/common
            ".markdown-body",                    # GitHub-style
            ".gitbook-markdown",                 # GitBook
            ".vp-doc",                           # VitePress
            "#mainContent",                      # Datadog
            "#provider-docs-content",            # Terraform
            "[role='main'] article",             # Semantic HTML
            "[role='main']",
            "main",
            "article",
            ".content",
            "#content"
        ]

        content_selectors = []
        for selector in candidate_selectors:
            try:
                element = page.query_selector(selector)
                if element:
                    html = element.inner_html()
                    text = element.inner_text()

                    # Only consider if has substantial content
                    if len(text) > 500:
                        content_selectors.append({
                            "selector": selector,
                            "chars": len(html),
                            "text_chars": len(text),
                            "recommended": 1000 < len(text) < 50000
                        })
            except Exception:
                continue

        # Sort by likelihood (recommended first, then by text length)
        content_selectors.sort(
            key=lambda x: (x["recommended"], x["text_chars"]),
            reverse=True
        )

        return content_selectors

    def _analyze_links(self, page, url: str) -> dict:
        """Analyze internal links and detect common path patterns."""
        try:
            all_links = page.eval_on_selector_all(
                "a[href]", "elements => elements.map(e => e.href)"
            )
        except Exception:
            all_links = []

        parsed_url = urlparse(url)

        # Clean and filter internal links
        internal_links = []
        for link in all_links:
            try:
                clean = clean_url(link)
                link_parsed = urlparse(clean)

                # Only internal links from same domain
                if link_parsed.netloc == parsed_url.netloc:
                    internal_links.append(clean)
            except Exception:
                continue

        internal_links = sorted(set(internal_links))

        # Detect common path patterns
        path_patterns = {}
        for link in internal_links:
            try:
                path = urlparse(link).path
                parts = [p for p in path.split('/') if p]
                if parts:
                    # Use first path segment as pattern
                    pattern = f"/{parts[0]}/"
                    path_patterns[pattern] = path_patterns.get(pattern, 0) + 1
            except Exception:
                continue

        # Sort patterns by frequency
        sorted_patterns = sorted(
            path_patterns.items(),
            key=lambda x: x[1],
            reverse=True
        )

        return {
            "total_internal_links": len(internal_links),
            "sample_links": internal_links[:20],
            "path_patterns": sorted_patterns[:10]
        }

    def _suggest_base_url(self, url: str) -> str:
        """Extract base URL from full page URL."""
        parsed_url = urlparse(url)
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}"

        if parsed_url.path and parsed_url.path != '/':
            # Extract first path segment as likely base (e.g., /docs, /api)
            path_parts = [p for p in parsed_url.path.split('/') if p]
            if path_parts:
                return f"{base_url}/{path_parts[0]}"

        return base_url

    @modal.method()
    def discover_selectors(self, url: str) -> dict:
        """Analyze a docs page and suggest scraping config.

        Returns framework, copy_buttons, content_selectors, link_analysis, base_url_suggestion.
        """
        print(f"[discover_selectors] Analyzing {url}")

        context = self.browser.new_context()
        page = context.new_page()

        try:
            # Load page and wait for JS rendering
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            # Perform analysis
            framework = self._detect_framework(page)
            copy_buttons = self._find_copy_buttons(page, url)
            content_selectors = self._find_content_selectors(page)
            link_analysis = self._analyze_links(page, url)
            base_url = self._suggest_base_url(url)

            result = {
                "success": True,
                "url": url,
                "framework": framework,
                "base_url_suggestion": base_url,
                "copy_buttons": copy_buttons[:5],  # Top 5
                "content_selectors": content_selectors[:10],  # Top 10
                "link_analysis": link_analysis
            }

            print(f"[discover_selectors] OK - framework={framework}, "
                  f"{len(copy_buttons)} copy buttons, "
                  f"{len(content_selectors)} content selectors, "
                  f"{link_analysis['total_internal_links']} links")

            return result

        except Exception as e:
            error_msg = str(e)[:200]
            print(f"[discover_selectors] FAIL {error_msg}")
            return {"success": False, "error": error_msg}
        finally:
            context.close()

    @modal.method()
    def scrape_links_browser(self, site_id: str) -> dict:
        """Scrape links from a site using browser (for JS-heavy SPAs)."""
        sites_config = load_sites_config()
        config = sites_config.get(site_id)
        if not config:
            print(f"[scrape_links_browser] ERROR: Unknown site: {site_id}")
            return {"success": False, "error": f"Unknown site: {site_id}"}

        base_url = config.baseUrl
        links_cfg = config.links
        start_urls = links_cfg.startUrls
        wait_for = links_cfg.waitFor
        wait_for_timeout = links_cfg.waitForTimeoutMs
        wait_until = links_cfg.waitUntil
        goto_timeout = links_cfg.gotoTimeoutMs
        pattern = links_cfg.pattern

        print(f"[scrape_links_browser] {base_url} ({len(start_urls)} start URLs)")

        context = self.browser.new_context()
        page = context.new_page()

        try:
            all_links = set()

            for start_path in start_urls or [""]:
                start_url = base_url + start_path
                page.goto(start_url, wait_until=wait_until, timeout=goto_timeout)

                # Handle site-specific setup
                self._dismiss_cookie_banner(page, config)

                # Wait for content
                if wait_for:
                    page.wait_for_selector(
                        wait_for, state="visible", timeout=wait_for_timeout
                    )
                    page.wait_for_timeout(2000)

                # Extract all links
                raw_links = page.eval_on_selector_all(
                    "a[href]", "elements => elements.map(e => e.href)"
                )

                for link in raw_links:
                    clean = clean_url(link)
                    if pattern and pattern not in clean:
                        if clean != base_url and clean != f"{base_url}/":
                            continue
                    if (
                        clean.startswith(base_url)
                        or urlparse(clean).netloc == urlparse(base_url).netloc
                    ):
                        all_links.add(clean)

            print(f"[scrape_links_browser] OK {len(all_links)} links")
            return {"success": True, "links": sorted(all_links)}

        except Exception as e:
            print(f"[scrape_links_browser] FAIL {str(e)[:200]}")
            return {"success": False, "error": str(e)}
        finally:
            context.close()


# --- SiteWorker for Bulk Jobs ---
@app.cls(timeout=600, retries=1, image=playwright_image)
class SiteWorker:
    """Worker for bulk batch processing with browser lifecycle."""

    @modal.enter()
    def start_browser(self):
        """Launch browser once when container starts."""
        from playwright.sync_api import sync_playwright

        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch()
        print("SiteWorker browser started")

    @modal.exit()
    def close_browser(self):
        """Clean up browser when container exits."""
        self.browser.close()
        self.pw.stop()
        print("SiteWorker browser closed")

    @modal.method()
    def process_batch(
        self,
        job_id: str,
        site_id: str,
        paths: list[str],
        delay_ms: int = DEFAULT_DELAY_MS,
        max_age: int = DEFAULT_MAX_AGE,
    ) -> dict:
        """Process a batch of paths for a single site."""
        config = load_sites_config().get(site_id)
        if not config:
            result = {"success": 0, "failed": len(paths), "skipped": 0, "errors": [{"path": "*", "error": f"Unknown site: {site_id}"}]}
            update_job_progress(job_id, result)
            return result

        content_cfg = config.content
        permissions = ["clipboard-read", "clipboard-write"] if content_cfg.method == "click_copy" else []

        context = self.browser.new_context(user_agent=USER_AGENT, permissions=permissions)
        page = context.new_page()
        results = {"success": 0, "skipped": 0, "failed": 0, "errors": []}

        try:
            for i, path in enumerate(paths):
                cache_key = f"{site_id}:{path}"
                url = config.baseUrl + path

                # Skip if cached
                if get_cached(cache_key, max_age):
                    results["skipped"] += 1
                    continue

                # Skip if error threshold exceeded
                try:
                    err = error_tracker.get(cache_key, {})
                    if err.get("count", 0) >= ERROR_THRESHOLD and time.time() - err.get("timestamp", 0) < ERROR_EXPIRY:
                        results["skipped"] += 1
                        continue
                except KeyError:
                    pass

                try:
                    page.goto(url, wait_until=content_cfg.waitUntil, timeout=content_cfg.gotoTimeoutMs)

                    wait_for = derive_wait_for(content_cfg)
                    if wait_for:
                        page.wait_for_selector(wait_for, state="visible", timeout=content_cfg.waitForTimeoutMs)

                    content = extract_page_content(page, content_cfg)

                    if content:
                        set_cached(cache_key, {"content": content, "url": url})
                        results["success"] += 1
                        try:
                            error_tracker.pop(cache_key, None)
                        except Exception:
                            pass
                    else:
                        results["failed"] += 1
                        results["errors"].append({"path": path, "error": "Empty content"})

                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append({"path": path, "error": str(e)[:200]})
                    try:
                        err = error_tracker.get(cache_key, {})
                        error_tracker[cache_key] = {"count": err.get("count", 0) + 1, "last_error": str(e)[:200], "timestamp": time.time()}
                    except Exception:
                        pass

                if i < len(paths) - 1:
                    time.sleep(delay_ms / 1000)
        finally:
            context.close()

        update_job_progress(job_id, results)
        return results


# --- HTTP-based Link Discovery ---
@app.function(timeout=300)
async def scrape_links_fetch(site_id: str) -> dict:
    """Scrape links using HTTP fetch (for static sites)."""
    import httpx

    sites_config = load_sites_config()
    config = sites_config.get(site_id)
    if not config:
        return {"success": False, "error": f"Unknown site: {site_id}"}

    base_url = config.baseUrl
    links_cfg = config.links
    start_urls = [
        base_url + path if path else base_url
        for path in links_cfg.startUrls
    ]
    max_depth = links_cfg.maxDepth
    pattern = links_cfg.pattern

    all_links: set[str] = set()
    visited: set[str] = set()
    to_visit = [(url, 0) for url in start_urls]

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        while to_visit:
            # Process in batches of 10
            batch = []
            while to_visit and len(batch) < 10:
                url, depth = to_visit.pop(0)
                if url not in visited and depth <= max_depth:
                    visited.add(url)
                    batch.append((url, depth))

            if not batch:
                continue

            # Fetch all URLs in batch concurrently
            async def fetch_one(url: str) -> str:
                try:
                    resp = await client.get(url)
                    resp.raise_for_status()
                    return resp.text
                except Exception as e:
                    print(f"[scrape_links_fetch] FAIL {url}: {str(e)[:100]}")
                    return ""

            tasks = [fetch_one(url) for url, _ in batch]
            results = await asyncio.gather(*tasks)

            for (url, depth), html in zip(batch, results):
                if not html:
                    continue

                # Extract links from HTML
                links = extract_links_from_html(html, base_url, pattern)

                for link in links:
                    all_links.add(link)
                    if depth < max_depth and link not in visited:
                        to_visit.append((link, depth + 1))

    print(f"[scrape_links_fetch] OK {len(all_links)} links for {site_id}")
    return {"success": True, "links": sorted(all_links)}


# --- FastAPI Web App ---
web_app = FastAPI(title="Content Scraper API")


@web_app.get("/")
async def root():
    """API root with endpoint documentation."""
    return {
        "name": "Content Scraper API",
        "version": "8.0",
        "storage": "Modal Dict (7-day TTL)",
        "endpoints": {
            "/sites": "GET - List available site IDs",
            "/discover": "GET - Analyze a page and suggest selectors (url param)",
            "/sites/{site_id}/links": "GET - Get all doc links for a site (cached)",
            "/sites/{site_id}/content": "GET - Get content from a page (cached, max_age=0 to force)",
            "/sites/{site_id}/index": "POST - Fetch all pages in parallel",
            "/sites/{site_id}/download": "GET - Download all docs as ZIP file",
            "/export/zip": "POST - Export list of URLs as ZIP (auto-resolves sites)",
            "/jobs/bulk": "POST - Submit bulk scrape job (fire-and-forget)",
            "/jobs/{job_id}": "GET - Get job status",
            "/jobs": "GET - List recent jobs",
            "/cache/keys": "GET - List cached URLs (content_only=true, site_id=optional)",
            "/cache/stats": "GET - Get cache statistics",
            "/cache/{site_id}": "DELETE - Clear cache for a site",
            "/errors": "GET/DELETE - List or clear all error tracking",
            "/errors/{site_id}": "DELETE - Clear errors for a site",
        },
        "features": [
            "Links caching (when >1 link)",
            "Content caching (48 hour default)",
            "Error tracking (skip after 3 failures, auto-expire 24h, force clears)",
            "Parallel bulk indexing (50 concurrent)",
            "ZIP download with folder structure",
            "URL-based export with auto site resolution (longest-prefix match)",
            "Bulk job queue with fire-and-forget workers (up to 100 containers)",
        ],
    }


@web_app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@web_app.get("/sites")
async def get_sites(
    include_test_paths: bool = Query(default=False, description="Include testPath for each site (filters to sites with testPath)")
):
    """List all available sites, optionally filtered to those with test paths."""
    sites_config = load_sites_config()
    if include_test_paths:
        # Only include sites that have a testPath configured
        sites = [
            {"id": site_id, "testPath": config.testPath}
            for site_id, config in sites_config.items()
            if config.testPath
        ]
    else:
        sites = [{"id": site_id} for site_id, config in sites_config.items()]
    return {"sites": sites, "count": len(sites)}


@web_app.get("/discover")
async def discover_site(
    url: str = Query(
        description="Full URL of a documentation page to analyze",
        examples=["https://developers.example.com/docs/getting-started"],
    )
):
    """Analyze a documentation page and suggest scraping configuration.

    Detects framework, tests copy buttons, ranks content selectors, and analyzes link patterns.
    See CLAUDE.md for usage workflow.
    """
    scraper = Scraper()
    result = await scraper.discover_selectors.remote.aio(url)

    if not result["success"]:
        error_detail = result.get("error", "Unknown error during analysis")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to analyze page: {error_detail}"
        )

    return result


@web_app.get("/sites/{site_id}/links")
async def get_site_links(
    site_id: str,
    max_age: int = Query(
        default=DEFAULT_MAX_AGE, description="Max cache age in seconds"
    ),
) -> LinksResponse:
    """Get all documentation links for a site."""
    sites_config = load_sites_config()
    config = sites_config.get(site_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Unknown site: {site_id}")

    cache_key = f"{site_id}:links"

    # Check cache first
    cached = get_cached(cache_key, max_age)
    if cached and cached.get("count", 0) > 1:
        return LinksResponse(
            site_id=site_id,
            links=cached["links"],
            count=cached["count"],
        )

    # Use browser mode for JS-heavy sites, fetch mode for static sites
    if config.mode == "browser":
        scraper = Scraper()
        result = await scraper.scrape_links_browser.remote.aio(site_id)
    else:
        result = await scrape_links_fetch.remote.aio(site_id)

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error"))

    links = result["links"]
    count = len(links)

    # Cache if more than 1 link
    if count > 1:
        set_cached(cache_key, {"links": links, "count": count})

    return LinksResponse(
        site_id=site_id,
        links=links,
        count=count,
    )


@web_app.get("/sites/{site_id}/content")
async def get_site_content(
    site_id: str,
    path: str = Query(default="", description="Page path relative to baseUrl"),
    max_age: int = Query(
        default=DEFAULT_MAX_AGE, description="Max cache age in seconds"
    ),
) -> ContentResponse:
    """Get content from a specific page.

    Returns cached version if fresh, otherwise scrapes fresh content.
    """
    sites_config = load_sites_config()
    config = sites_config.get(site_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Unknown site: {site_id}")

    if not path:
        path = config.defaultPath
    cache_key = f"{site_id}:{path}"
    url = config.baseUrl + path

    # Check cache first
    cached = get_cached(cache_key, max_age)
    if cached:
        return ContentResponse(
            site_id=site_id,
            path=path,
            content=cached["content"],
            content_length=len(cached["content"]),
            url=cached["url"],
            from_cache=True,
        )

    # Scrape fresh content (force=True if max_age=0 to also clear error tracking)
    scraper = Scraper()
    result = await scraper.scrape_content.remote.aio(site_id, path, force=(max_age == 0))

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error"))

    # Save to cache only if content is non-empty
    if result["content"]:
        set_cached(cache_key, {"content": result["content"], "url": result["url"]})

    return ContentResponse(
        site_id=site_id,
        path=path,
        content=result["content"],
        content_length=len(result["content"]),
        url=result["url"],
        from_cache=False,
    )


@web_app.get("/cache/keys")
async def cache_keys(
    site_id: str = Query(default=None, description="Filter by site ID"),
    content_only: bool = Query(default=True, description="Only content keys, not links"),
):
    """List all cached keys, optionally filtered by site.

    Returns URLs reconstructed from cache keys.
    """
    sites_config = load_sites_config()
    results = []

    for key in cache.keys():
        # Skip links keys if content_only
        if content_only and key.endswith(":links"):
            continue

        parts = key.split(":", 1)
        if len(parts) != 2:
            continue

        key_site_id, path = parts

        # Filter by site if specified
        if site_id and key_site_id != site_id:
            continue

        # Reconstruct URL
        config = sites_config.get(key_site_id)
        if config:
            url = config.baseUrl + path
            results.append({
                "site_id": key_site_id,
                "path": path,
                "url": url,
            })

    return {
        "count": len(results),
        "keys": results,
    }


@web_app.get("/cache/stats")
async def cache_stats():
    """Get cache statistics."""
    keys = list(cache.keys())
    by_site = {}
    by_type = {"content": 0, "links": 0}

    for key in keys:
        parts = key.split(":")
        site = parts[0]

        # Track by site
        by_site[site] = by_site.get(site, 0) + 1

        # Track by type (links keys end with ":links")
        if key.endswith(":links"):
            by_type["links"] += 1
        else:
            by_type["content"] += 1

    return {
        "total_entries": len(keys),
        "by_site": by_site,
        "by_type": by_type,
    }


@web_app.delete("/cache/{site_id}")
async def clear_cache(site_id: str):
    """Clear cache for a site."""
    deleted = 0
    keys_to_delete = []

    for key in cache.keys():
        if key.startswith(f"{site_id}:"):
            keys_to_delete.append(key)

    for key in keys_to_delete:
        cache.pop(key, None)
        deleted += 1

    return {"site_id": site_id, "deleted": deleted}


@web_app.get("/errors")
async def get_errors():
    """Get all failed links with error counts."""
    errors = []
    for key in error_tracker.keys():
        error_info = error_tracker[key]
        parts = key.split(":", 1)
        errors.append(
            {
                "site_id": parts[0],
                "path": parts[1] if len(parts) > 1 else "",
                "count": error_info.get("count", 0),
                "last_error": error_info.get("last_error", ""),
                "timestamp": error_info.get("timestamp", 0),
            }
        )

    # Sort by error count descending
    errors.sort(key=lambda x: x["count"], reverse=True)

    return {
        "total_failed_links": len(errors),
        "errors": errors,
    }


@web_app.delete("/errors")
async def clear_all_errors():
    """Clear all error tracking data."""
    count = len(list(error_tracker.keys()))
    error_tracker.clear()
    return {"cleared": count}


@web_app.delete("/errors/{site_id}")
async def clear_site_errors(site_id: str):
    """Clear error tracking for a specific site."""
    deleted = 0
    keys_to_delete = []

    for key in error_tracker.keys():
        if key.startswith(f"{site_id}:"):
            keys_to_delete.append(key)

    for key in keys_to_delete:
        error_tracker.pop(key, None)
        deleted += 1

    return {"site_id": site_id, "cleared": deleted}


@web_app.post("/sites/{site_id}/index")
async def index_site(
    site_id: str,
    max_age: int = Query(
        default=DEFAULT_MAX_AGE, description="Max cache age in seconds"
    ),
    max_concurrent: int = Query(default=50, description="Max concurrent requests"),
):
    """Fetch all pages for a site in parallel, respecting cache."""
    sites_config = load_sites_config()
    config = sites_config.get(site_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Unknown site: {site_id}")

    # Get all links first
    links_response = await get_site_links(site_id, max_age=max_age)
    links = links_response.links
    base_url = config.baseUrl

    # Extract paths from links
    paths = []
    for link in links:
        if link.startswith(base_url):
            path = link[len(base_url) :]
            paths.append(path)
        else:
            # Handle links with different scheme or www
            from urllib.parse import urlparse

            link_parsed = urlparse(link)
            base_parsed = urlparse(base_url)
            if link_parsed.netloc == base_parsed.netloc:
                paths.append(link_parsed.path)

    # Check cache for each path, separate into fresh vs stale
    paths_to_scrape = []
    cached_count = 0

    for path in paths:
        cache_key = f"{site_id}:{path}"
        if get_cached(cache_key, max_age):
            cached_count += 1
        else:
            paths_to_scrape.append(path)

    # Scrape stale/missing paths in parallel with concurrency limit
    scraper = Scraper()
    semaphore = asyncio.Semaphore(max_concurrent)

    async def scrape_with_limit(path):
        async with semaphore:
            return await scraper.scrape_content.remote.aio(site_id, path)

    tasks = [scrape_with_limit(path) for path in paths_to_scrape]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results and update cache
    successful = 0
    failed = 0
    errors = []

    for i, result in enumerate(results):
        path = paths_to_scrape[i]
        if isinstance(result, Exception):
            failed += 1
            errors.append({"path": path, "error": str(result)})
        elif isinstance(result, dict):
            if result.get("success"):
                successful += 1
                # Write to cache only if content is non-empty
                if result["content"]:
                    cache_key = f"{site_id}:{path}"
                    set_cached(cache_key, {"content": result["content"], "url": result["url"]})
            else:
                failed += 1
                errors.append({"path": path, "error": result.get("error", "unknown")})

    return {
        "site_id": site_id,
        "total": len(paths),
        "cached": cached_count,
        "scraped": len(paths_to_scrape),
        "successful": successful,
        "failed": failed,
        "errors": errors[:10],
    }


@web_app.get("/sites/{site_id}/download")
async def download_site(
    site_id: str,
    max_age: int = Query(
        default=DEFAULT_MAX_AGE, description="Max cache age in seconds"
    ),
    max_concurrent: int = Query(default=50, description="Max concurrent requests"),
):
    """Download all documentation for a site as a ZIP file.

    Creates a ZIP archive with all pages organized in folders matching the URL structure,
    just like the --save option in docpull.py. Each page is saved as markdown.
    """
    sites_config = load_sites_config()
    config = sites_config.get(site_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Unknown site: {site_id}")

    print(f"[download_site] Starting download for {site_id}")

    # Get all links first
    links_response = await get_site_links(site_id, max_age=max_age)
    links = links_response.links
    base_url = config.baseUrl

    # Extract paths from links
    paths = []
    for link in links:
        if link.startswith(base_url):
            path = link[len(base_url):]
            paths.append(path)
        else:
            # Handle links with different scheme or www
            link_parsed = urlparse(link)
            base_parsed = urlparse(base_url)
            if link_parsed.netloc == base_parsed.netloc:
                paths.append(link_parsed.path)

    print(f"[download_site] Found {len(paths)} pages to download")

    # Fetch all content (similar to index endpoint)
    scraper = Scraper()
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_content_for_path(path):
        async with semaphore:
            cache_key = f"{site_id}:{path}"
            # Try cache first
            cached = get_cached(cache_key, max_age)
            if cached:
                return {
                    "path": path,
                    "content": cached["content"],
                    "success": True,
                    "from_cache": True
                }

            # Scrape if not cached
            result = await scraper.scrape_content.remote.aio(site_id, path)
            if result.get("success"):
                content = result["content"]
                # Write to cache for future requests
                if content:
                    set_cached(cache_key, {"content": content, "url": result["url"]})
                return {
                    "path": path,
                    "content": content,
                    "success": True,
                    "from_cache": False
                }
            else:
                return {
                    "path": path,
                    "error": result.get("error", "Unknown error"),
                    "success": False
                }

    tasks = [fetch_content_for_path(path) for path in paths]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    print(f"[download_site] Fetched {len(paths)} pages, creating ZIP")

    # Create ZIP file in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        successful_count = 0
        cached_count = 0
        scraped_count = 0
        failed_count = 0

        for result in results:
            if isinstance(result, Exception):
                failed_count += 1
                continue

            if not isinstance(result, dict) or not result.get("success"):
                failed_count += 1
                continue

            path = result["path"]
            content = result["content"]

            # Track cache stats
            if result.get("from_cache"):
                cached_count += 1
            else:
                scraped_count += 1

            # Convert HTML to markdown if needed
            if content.lstrip().startswith("<"):
                content = html_to_markdown(content)

            # Sanitize path for filename - create proper folder structure
            safe_path = path.strip("/").replace("//", "/") or "index"

            # Create the file path within the ZIP: site_id/path.md
            zip_path = f"{site_id}/{safe_path}.md"

            # Add to ZIP
            zip_file.writestr(zip_path, content)
            successful_count += 1

        # Add a README with metadata
        readme_content = f"""# {config.name} Documentation

Downloaded from: {base_url}
Total pages: {len(paths)}
Successfully downloaded: {successful_count} (cached: {cached_count}, scraped: {scraped_count})
Failed: {failed_count}
Generated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}
"""
        zip_file.writestr(f"{site_id}/README.md", readme_content)

    print(f"[download_site] ZIP created - {successful_count} pages (cached: {cached_count}, scraped: {scraped_count}), {failed_count} failed")

    # Return ZIP file
    zip_buffer.seek(0)
    return StreamingResponse(
        io.BytesIO(zip_buffer.read()),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={site_id}_docs.zip",
            "X-Download-Total": str(len(paths)),
            "X-Download-Cached": str(cached_count),
            "X-Download-Scraped": str(scraped_count),
            "X-Download-Failed": str(failed_count),
        }
    )


@web_app.post("/export/zip")
async def export_urls_as_zip(request: ExportRequest):
    """Export a list of URLs as a ZIP file with docs/{site}/{path}.md structure.

    Takes arbitrary URLs, resolves them to configured sites using longest-prefix
    matching on baseUrls, fetches content (from cache or fresh), and returns
    a ZIP file organized by site.

    Request body:
    - urls: List of documentation URLs to export
    - cached_only: If true (default), only return cached content (no scraping)
    - max_age: Max cache age in seconds (default 48h)
    - include_manifest: If true (default), include manifest.json with metadata
    """
    urls = request.urls
    cached_only = request.cached_only
    max_age = request.max_age
    include_manifest = request.include_manifest

    if not urls:
        raise HTTPException(status_code=400, detail="No URLs provided")

    print(f"[export_zip] Processing {len(urls)} URLs (cached_only={cached_only})")

    # Resolve all URLs to (site_id, path)
    resolved: list[dict] = []
    for url in urls:
        site_id, path, norm_url = resolve_url_to_site(url)
        resolved.append({
            "original_url": url,
            "normalized_url": norm_url,
            "site_id": site_id,
            "path": path,
        })

    # Group by site and dedupe by (site_id, normalized_path) to avoid duplicate zip entries
    by_site: dict[str, list[dict]] = {}
    unknown_urls: list[dict] = []
    seen_paths: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    dupe_count = 0

    for r in resolved:
        if r["site_id"]:
            by_site.setdefault(r["site_id"], []).append(r)
            key = (r["site_id"], normalize_path(r["path"]))
            if key not in seen_paths:
                seen_paths.add(key)
                deduped.append(r)
            else:
                dupe_count += 1
        else:
            unknown_urls.append(r)

    print(f"[export_zip] Resolved to {len(by_site)} sites, {len(unknown_urls)} unknown, {dupe_count} dupes removed")

    # Fetch content for each resolved URL
    scraper = Scraper()
    semaphore = asyncio.Semaphore(50)

    async def fetch_content(r: dict) -> dict:
        """Fetch content for a resolved URL."""
        site_id = r["site_id"]
        path = r["path"]
        cache_key = f"{site_id}:{path}"

        result = {
            **r,
            "success": False,
            "from_cache": False,
            "content": None,
            "content_length": 0,
            "error": None,
        }

        # Try cache first
        cached = get_cached(cache_key, max_age)
        if cached:
            result["success"] = True
            result["from_cache"] = True
            result["content"] = cached["content"]
            result["content_length"] = len(cached["content"])
            return result

        # If cached_only, mark as miss
        if cached_only:
            result["error"] = "Not in cache"
            return result

        # Scrape fresh content
        async with semaphore:
            scrape_result = await scraper.scrape_content.remote.aio(site_id, path)

        if scrape_result.get("success"):
            content = scrape_result["content"]
            result["success"] = True
            result["from_cache"] = False
            result["content"] = content
            result["content_length"] = len(content) if content else 0

            # Cache the result
            if content:
                set_cached(cache_key, {"content": content, "url": scrape_result["url"]})
        else:
            result["error"] = scrape_result.get("error", "Unknown error")

        return result

    # Fetch all content in parallel (using deduped list)
    tasks = [fetch_content(r) for r in deduped]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Process results
    manifest_entries: list[dict] = []
    ok_count = 0
    miss_count = 0
    error_count = 0
    cached_count = 0
    scraped_count = 0

    # Create ZIP in memory
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for result in results:
            if isinstance(result, Exception):
                error_count += 1
                continue

            entry = {
                "url": result["original_url"],
                "normalized_url": result["normalized_url"],
                "site_id": result["site_id"],
                "path": result["path"],
                "success": result["success"],
                "from_cache": result.get("from_cache", False),
                "content_length": result.get("content_length", 0),
                "error": result.get("error"),
                "zip_path": None,
            }

            if result["success"] and result["content"]:
                content = result["content"]

                # Convert HTML to markdown if needed
                if content.lstrip().startswith("<"):
                    content = html_to_markdown(content)

                # Generate safe ZIP path
                try:
                    zpath = zip_path_for(result["site_id"], result["path"])
                    zf.writestr(zpath, content)
                    entry["zip_path"] = zpath
                    ok_count += 1

                    if result.get("from_cache"):
                        cached_count += 1
                    else:
                        scraped_count += 1
                except ValueError as e:
                    entry["error"] = str(e)
                    error_count += 1
            else:
                if result.get("error") == "Not in cache":
                    miss_count += 1
                else:
                    error_count += 1

            manifest_entries.append(entry)

        # Add unknown URLs to manifest
        for r in unknown_urls:
            manifest_entries.append({
                "url": r["original_url"],
                "normalized_url": r["normalized_url"],
                "site_id": None,
                "path": None,
                "success": False,
                "from_cache": False,
                "content_length": 0,
                "error": "No matching site configuration",
                "zip_path": None,
            })
            error_count += 1

        # Add manifest.json if requested
        if include_manifest:
            manifest = {
                "generated_at": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                "total_urls": len(urls),
                "ok": ok_count,
                "cached": cached_count,
                "scraped": scraped_count,
                "miss": miss_count,
                "error": error_count + len(unknown_urls),
                "unknown_sites": len(unknown_urls),
                "entries": manifest_entries,
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    print(f"[export_zip] ZIP created - ok={ok_count} (cached={cached_count}, scraped={scraped_count}), miss={miss_count}, error={error_count}")

    # Return ZIP
    zip_buffer.seek(0)
    return StreamingResponse(
        io.BytesIO(zip_buffer.read()),
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=docs_export.zip",
            "X-Export-Total": str(len(urls)),
            "X-Export-Ok": str(ok_count),
            "X-Export-Cached": str(cached_count),
            "X-Export-Scraped": str(scraped_count),
            "X-Export-Miss": str(miss_count),
            "X-Export-Error": str(error_count + len(unknown_urls)),
        }
    )


# --- Bulk Job Endpoints ---
class BulkScrapeRequest(BaseModel):
    """Request body for bulk scrape jobs."""
    urls: list[str]
    max_age: int = DEFAULT_MAX_AGE


@web_app.post("/jobs/bulk")
async def submit_bulk_job(request: BulkScrapeRequest):
    """Submit a bulk scrape job (fire-and-forget).

    Groups URLs by site, distributes across workers, and returns immediately.
    Use GET /jobs/{job_id} to check progress.
    """
    if not request.urls:
        raise HTTPException(400, "No URLs provided")

    grouped = filter_and_group_urls(request.urls)

    if not grouped["by_site"]:
        return {"job_id": "", "status": "completed", "message": "No scrapeable URLs"}

    job_id = create_job(request.urls, grouped["by_site"], grouped["assets"], grouped["unknown"])
    batches = calculate_batches(grouped["by_site"])

    job = jobs[job_id]
    job["status"] = JobStatus.IN_PROGRESS
    job["workers"]["total"] = len(batches)
    jobs[job_id] = job

    # Spawn workers (fire-and-forget)
    worker = SiteWorker()
    for batch in batches:
        worker.process_batch.spawn(job_id, batch["site_id"], batch["paths"], max_age=request.max_age)

    print(f"[submit_bulk_job] job_id={job_id}, batches={len(batches)}, sites={list(grouped['by_site'].keys())}")

    return {
        "job_id": job_id,
        "status": "in_progress",
        "batches": len(batches),
        "input": job["input"],
    }


@web_app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get the status of a bulk scrape job."""
    try:
        job = jobs[job_id]
    except KeyError:
        raise HTTPException(404, f"Job not found: {job_id}")

    total = job["input"]["to_scrape"]
    pct = round((job["progress"]["completed"] / total) * 100, 1) if total else 100

    return {
        "job_id": job_id,
        "status": job["status"],
        "progress_pct": pct,
        "elapsed_seconds": round(time.time() - job["created_at"], 1),
        "input": job["input"],
        "progress": job["progress"],
        "workers": job["workers"],
        "errors": job["errors"][:10],
    }


@web_app.get("/jobs")
async def list_jobs(limit: int = Query(default=20, le=100)):
    """List recent bulk scrape jobs."""
    result = []
    for job_id in list(jobs.keys())[-limit:]:
        try:
            job = jobs[job_id]
            result.append({
                "job_id": job_id,
                "status": job["status"],
                "created_at": job["created_at"],
                "sites": job["input"]["sites"],
                "progress": f"{job['progress']['completed']}/{job['input']['to_scrape']}",
            })
        except KeyError:
            # Job was deleted between keys() and get()
            continue
    return {"jobs": sorted(result, key=lambda x: x["created_at"], reverse=True)}


@app.function()
@modal.concurrent(max_inputs=100)
@modal.asgi_app(requires_proxy_auth=True)
def fastapi_app():
    """FastAPI app with concurrent request handling."""
    return web_app
