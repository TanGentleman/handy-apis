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
    .pip_install("fastapi[standard]", "pydantic", "httpx")
    .add_local_file("scraper/config/sites.json", "/root/sites.json")
)

app = modal.App("content-scraper-api", image=playwright_image)

# Modal Dict for caching (7-day TTL built-in)
cache = modal.Dict.from_name("scraper-cache", create_if_missing=True)

DEFAULT_MAX_AGE = 3600  # 1 hour


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
    def scrape_content(self, site_id: str, path: str) -> dict:
        """Scrape content from a page using browser."""
        print(f"[scrape_content] site_id={site_id}, path={path}")
        sites_config = load_sites_config()
        config = sites_config.get(site_id)
        if not config:
            print(f"[scrape_content] ERROR: Unknown site: {site_id}")
            return {"success": False, "error": f"Unknown site: {site_id}"}

        url = config["baseUrl"] + path
        content_config = config.get("content", {})
        method = content_config.get("method", "inner_html")
        selector = content_config.get("selector")
        wait_for = content_config.get("waitFor")
        wait_for_timeout = content_config.get("waitForTimeoutMs", 30000)
        wait_until = content_config.get("waitUntil", "networkidle")
        goto_timeout = content_config.get("gotoTimeoutMs", 60000)

        print(
            f"[scrape_content] url={url}, method={method}, selector={selector}, "
            f"wait_until={wait_until}, goto_timeout={goto_timeout}, "
            f"wait_for_timeout={wait_for_timeout}"
        )

        # Determine permissions based on extraction method
        permissions = []
        if method == "click_copy":
            permissions = ["clipboard-read", "clipboard-write"]

        context = self.browser.new_context(permissions=permissions)
        page = context.new_page()

        try:
            print(f"[scrape_content] Navigating to {url}...")
            page.goto(url, wait_until=wait_until, timeout=goto_timeout)
            print(f"[scrape_content] Page loaded")

            # Handle site-specific setup (cookie consent, etc.)
            self._dismiss_cookie_banner(page, config)

            # Wait for content to be ready
            if wait_for:
                print(f"[scrape_content] Waiting for selector: {wait_for}")
                page.wait_for_selector(
                    wait_for, state="visible", timeout=wait_for_timeout
                )
                page.wait_for_timeout(500)

            # Extract content based on method
            if method == "click_copy":
                print(f"[scrape_content] Clicking copy button: {selector}")
                page.click(selector)
                page.wait_for_timeout(1000)
                content = page.evaluate("() => navigator.clipboard.readText()")
            else:  # inner_html
                print(f"[scrape_content] Extracting innerHTML: {selector}")
                element = page.query_selector(selector)
                content = element.inner_html() if element else ""

            print(f"[scrape_content] SUCCESS: extracted {len(content)} chars")
            return {"success": True, "content": content, "url": url}

        except Exception as e:
            print(f"[scrape_content] ERROR: {e}")
            return {"success": False, "error": str(e), "url": url}
        finally:
            context.close()

    @modal.method()
    def scrape_links_browser(self, site_id: str) -> dict:
        """Scrape links from a site using browser (for JS-heavy SPAs)."""
        print(f"[scrape_links_browser] site_id={site_id}")
        sites_config = load_sites_config()
        config = sites_config.get(site_id)
        if not config:
            print(f"[scrape_links_browser] ERROR: Unknown site: {site_id}")
            return {"success": False, "error": f"Unknown site: {site_id}"}

        base_url = config["baseUrl"]
        links_config = config.get("links", {})
        start_urls = links_config.get("startUrls", [""])
        wait_for = links_config.get("waitFor")
        wait_for_timeout = links_config.get("waitForTimeoutMs", 30000)
        wait_until = links_config.get("waitUntil", "networkidle")
        goto_timeout = links_config.get("gotoTimeoutMs", 60000)
        pattern = links_config.get("pattern", "")

        print(
            f"[scrape_links_browser] base_url={base_url}, pattern={pattern}, "
            f"wait_for={wait_for}, wait_until={wait_until}, goto_timeout={goto_timeout}, "
            f"wait_for_timeout={wait_for_timeout}"
        )

        context = self.browser.new_context()
        page = context.new_page()

        try:
            all_links = set()

            for start_path in (start_urls or [""]):
                start_url = base_url + start_path
                print(f"[scrape_links_browser] Navigating to {start_url}...")
                page.goto(start_url, wait_until=wait_until, timeout=goto_timeout)
                print(f"[scrape_links_browser] Page loaded")

                # Handle site-specific setup
                self._dismiss_cookie_banner(page, config)

                # Wait for content
                if wait_for:
                    print(f"[scrape_links_browser] Waiting for selector: {wait_for}")
                    page.wait_for_selector(
                        wait_for, state="visible", timeout=wait_for_timeout
                    )
                    page.wait_for_timeout(2000)

                # Extract all links
                print(f"[scrape_links_browser] Extracting links...")
                raw_links = page.eval_on_selector_all(
                    "a[href]", "elements => elements.map(e => e.href)"
                )
                print(f"[scrape_links_browser] Found {len(raw_links)} raw links")

                for link in raw_links:
                    clean = clean_url(link)
                    if pattern and pattern not in clean:
                        if clean != base_url and clean != f"{base_url}/":
                            continue
                    if clean.startswith(base_url) or urlparse(clean).netloc == urlparse(base_url).netloc:
                        all_links.add(clean)

            print(f"[scrape_links_browser] SUCCESS: {len(all_links)} links after filtering")
            return {"success": True, "links": sorted(all_links)}

        except Exception as e:
            print(f"[scrape_links_browser] ERROR: {e}")
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
        base_url + path if path else base_url for path in links_config.get("startUrls", [""])
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
                    print(f"Error fetching {url}: {e}")
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

    print(f"Found {len(all_links)} links for {site_id}")
    return {"success": True, "links": sorted(all_links)}


# --- FastAPI Web App ---
web_app = FastAPI(title="Content Scraper API")


@web_app.get("/")
async def root():
    """API root with endpoint documentation."""
    return {
        "name": "Content Scraper API",
        "version": "5.0",
        "storage": "Modal Dict (7-day TTL)",
        "endpoints": {
            "/sites": "GET - List available site IDs",
            "/sites/{site_id}/links": "GET - Get all doc links for a site",
            "/sites/{site_id}/content": "GET - Get content from a page (cached or fresh)",
        },
    }


@web_app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@web_app.get("/sites")
async def get_sites():
    """List all available site IDs."""
    sites_config = load_sites_config()
    return {"sites": list(sites_config.keys()), "count": len(sites_config)}


@web_app.get("/sites/{site_id}/links")
async def get_site_links(site_id: str) -> LinksResponse:
    """Get all documentation links for a site."""
    sites_config = load_sites_config()
    config = sites_config.get(site_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Unknown site: {site_id}")

    # Use browser mode for JS-heavy sites, fetch mode for static sites
    if config.get("mode") == "browser":
        scraper = Scraper()
        result = scraper.scrape_links_browser.remote(site_id)
    else:
        result = await scrape_links_fetch.remote.aio(site_id)

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error"))

    return LinksResponse(
        site_id=site_id,
        links=result["links"],
        count=len(result["links"]),
    )


@web_app.get("/sites/{site_id}/content")
async def get_site_content(
    site_id: str,
    path: str = Query(default="", description="Page path relative to baseUrl"),
    max_age: int = Query(default=DEFAULT_MAX_AGE, description="Max cache age in seconds"),
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

    # Scrape fresh content
    scraper = Scraper()
    result = scraper.scrape_content.remote(site_id, path)

    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error"))

    # Save to cache
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


@app.function()
@modal.concurrent(max_inputs=100)
@modal.asgi_app()
def fastapi_app():
    """FastAPI app with concurrent request handling."""
    return web_app
