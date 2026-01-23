# ---
# deploy: true
# ---

# Content Scraper API - Modal-native with Dict caching and browser lifecycle

import asyncio
import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import modal
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

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
    .add_local_file("scraper/config/sites.json", "/root/sites.json")
)

app = modal.App("content-scraper-api", image=playwright_image)

# Modal Dict for caching (7-day TTL built-in)
cache = modal.Dict.from_name("scraper-cache", create_if_missing=True)

# Modal Dict for tracking failed links
error_tracker = modal.Dict.from_name("scraper-errors", create_if_missing=True)

DEFAULT_MAX_AGE = 3600 * 48  # 48 hours
ERROR_THRESHOLD = 3  # Skip links that have failed this many times
ERROR_EXPIRY = 86400  # 24 hours - errors auto-expire


# --- Load sites config ---
def load_sites_config() -> dict:
    """Load sites configuration from embedded JSON file."""
    config_path = Path("/root/sites.json")
    if not config_path.exists():
        # Fallback to local path during development
        config_path = Path(__file__).parent / "scraper" / "config" / "sites.json"
    with open(config_path) as f:
        return json.load(f)["sites"]


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


# --- Helper functions ---
def html_to_markdown(html: str) -> str:
    """Convert HTML to markdown using markdownify."""
    from markdownify import markdownify as md
    return md(html, heading_style="ATX", strip=["script", "style"]).strip()


def clean_url(url: str) -> str:
    """Remove query params and fragments from URL."""
    return url.split("?")[0].split("#")[0].rstrip("/")


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

    def _dismiss_cookie_banner(self, page, site_config: dict):
        """Handle cookie consent banners for specific sites."""
        extractor = site_config.get("extractor", "default")
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

        url = config["baseUrl"] + path
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

        content_config = config.get("content", {})
        method = content_config.get("method", "inner_html")
        selector = content_config.get("selector")
        click_sequence = content_config.get("clickSequence")
        # Auto-derive waitFor if not explicitly set (falls back to first click target or selector)
        wait_for = content_config.get("waitFor")
        if not wait_for:
            if click_sequence:
                wait_for = click_sequence[0].get("selector")
            elif selector:
                wait_for = selector
        wait_for_timeout = content_config.get("waitForTimeoutMs", 15000)
        wait_until = content_config.get("waitUntil", "domcontentloaded")
        goto_timeout = content_config.get("gotoTimeoutMs", 30000)

        print(f"[scrape_content] {url} (method={method})")

        # Determine permissions based on extraction method
        permissions = []
        if method == "click_copy":
            permissions = ["clipboard-read", "clipboard-write"]

        context = self.browser.new_context(permissions=permissions)
        page = context.new_page()

        try:
            page.goto(url, wait_until=wait_until, timeout=goto_timeout)

            # Handle site-specific setup (cookie consent, etc.)
            self._dismiss_cookie_banner(page, config)

            # Wait for content to be ready
            if wait_for:
                page.wait_for_selector(
                    wait_for, state="visible", timeout=wait_for_timeout
                )
                page.wait_for_timeout(500)

            # Extract content based on method
            if method == "click_copy":
                if click_sequence:
                    # Validate clickSequence config
                    for i, step in enumerate(click_sequence):
                        if not step.get("selector"):
                            raise ValueError(
                                f"clickSequence[{i}] missing required 'selector' field"
                            )
                    # Multi-step click sequence (e.g., open dropdown, then click option)
                    for i, step in enumerate(click_sequence):
                        step_selector = step["selector"]
                        wait_after = step.get("waitAfter", 500)
                        print(f"[scrape_content] Click step {i+1}: {step_selector}")
                        page.click(step_selector)
                        page.wait_for_timeout(wait_after)
                else:
                    # Single click (backward compatible)
                    if not selector:
                        raise ValueError(
                            "click_copy method requires 'selector' or 'clickSequence'"
                        )
                    page.click(selector)
                    page.wait_for_timeout(1000)
                content = page.evaluate("() => navigator.clipboard.readText()")
            else:  # inner_html
                element = page.query_selector(selector)
                raw_html = element.inner_html() if element else ""
                content = html_to_markdown(raw_html)

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

        base_url = config["baseUrl"]
        links_config = config.get("links", {})
        start_urls = links_config.get("startUrls", [""])
        wait_for = links_config.get("waitFor")
        wait_for_timeout = links_config.get("waitForTimeoutMs", 15000)
        wait_until = links_config.get("waitUntil", "domcontentloaded")
        goto_timeout = links_config.get("gotoTimeoutMs", 30000)
        pattern = links_config.get("pattern", "")

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


# --- HTTP-based Link Discovery ---
@app.function(timeout=300)
async def scrape_links_fetch(site_id: str) -> dict:
    """Scrape links using HTTP fetch (for static sites)."""
    import httpx

    sites_config = load_sites_config()
    config = sites_config.get(site_id)
    if not config:
        return {"success": False, "error": f"Unknown site: {site_id}"}

    base_url = config["baseUrl"]
    links_config = config.get("links", {})
    start_urls = [
        base_url + path if path else base_url
        for path in links_config.get("startUrls", [""])
    ]
    max_depth = links_config.get("maxDepth", 2)
    pattern = links_config.get("pattern", "")

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
        "version": "6.0",
        "storage": "Modal Dict (7-day TTL)",
        "endpoints": {
            "/sites": "GET - List available site IDs",
            "/discover": "GET - Analyze a page and suggest selectors (url param)",
            "/sites/{site_id}/links": "GET - Get all doc links for a site (cached)",
            "/sites/{site_id}/content": "GET - Get content from a page (cached, max_age=0 to force)",
            "/sites/{site_id}/index": "POST - Fetch all pages in parallel",
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
            {"id": site_id, "testPath": config["testPath"]}
            for site_id, config in sites_config.items()
            if config.get("testPath")
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
    try:
        cached = cache[cache_key]
        if cached and cached.get("count", 0) > 1:
            age = time.time() - cached["timestamp"]
            if age < max_age:
                return LinksResponse(
                    site_id=site_id,
                    links=cached["links"],
                    count=cached["count"],
                )
    except KeyError:
        pass  # Not in cache

    # Use browser mode for JS-heavy sites, fetch mode for static sites
    if config.get("mode") == "browser":
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
        cache[cache_key] = {
            "links": links,
            "count": count,
            "timestamp": time.time(),
        }

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
        path = config.get("defaultPath", "")
    cache_key = f"{site_id}:{path}"
    url = config["baseUrl"] + path

    # Check cache first
    try:
        cached = cache[cache_key]
        if cached:
            age = time.time() - cached["timestamp"]
            if age < max_age:
                return ContentResponse(
                    site_id=site_id,
                    path=path,
                    content=cached["content"],
                    content_length=len(cached["content"]),
                    url=cached["url"],
                    from_cache=True,
                )
    except KeyError:
        pass  # Not in cache

    # Scrape fresh content (force=True if max_age=0 to also clear error tracking)
    scraper = Scraper()
    result = await scraper.scrape_content.remote.aio(site_id, path, force=(max_age == 0))

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error"))

    # Save to cache only if content is non-empty
    if result["content"]:
        cache[cache_key] = {
            "content": result["content"],
            "url": result["url"],
            "timestamp": time.time(),
        }

    return ContentResponse(
        site_id=site_id,
        path=path,
        content=result["content"],
        content_length=len(result["content"]),
        url=result["url"],
        from_cache=False,
    )


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
    base_url = config["baseUrl"]

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
    now = time.time()

    for path in paths:
        cache_key = f"{site_id}:{path}"
        try:
            cached = cache[cache_key]
            if cached and (now - cached["timestamp"]) < max_age:
                cached_count += 1
                continue  # Skip, cache is fresh
        except KeyError:
            pass
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
                    cache[cache_key] = {
                        "content": result["content"],
                        "url": result["url"],
                        "timestamp": time.time(),
                    }
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


@app.function()
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def fastapi_app():
    """FastAPI app with concurrent request handling."""
    return web_app
