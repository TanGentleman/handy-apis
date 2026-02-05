"""PlaywrightWorker – browser automation in a dedicated Modal image.

Workers receive full site config dicts and return standardised results.
Single-page methods (scrape_content, scrape_links, discover_selectors) never
touch the cache; the server handles all caching.

process_batch writes to cache directly because bulk jobs are spawned
fire-and-forget (.spawn) and the server cannot await their results.

Return format
-------------
  Success: {"content": ..., "metadata": {...}}
  Error  : {"error": "message", "code": "ERROR_CODE"}
"""

import time
from urllib.parse import urlparse

import modal

from api.urls import clean_url

# ---------------------------------------------------------------------------
# Image
# ---------------------------------------------------------------------------
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
    .pip_install("markdownify", "httpx")
    .add_local_dir("api", "/root/api")
)

# ---------------------------------------------------------------------------
# Modal Dicts – only touched by process_batch (fire-and-forget bulk jobs)
# ---------------------------------------------------------------------------
_cache = modal.Dict.from_name("scraper-cache", create_if_missing=True)
_error_tracker = modal.Dict.from_name("scraper-errors", create_if_missing=True)

ERROR_THRESHOLD = 3
ERROR_EXPIRY = 86400  # 24 h
DEFAULT_MAX_AGE = 604800  # 7 days

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _html_to_markdown(html: str) -> str:
    from markdownify import markdownify as md

    return md(html, heading_style="ATX", strip=["script", "style"]).strip()


def _derive_wait_for(content_cfg: dict) -> str | None:
    if content_cfg.get("waitFor"):
        return content_cfg["waitFor"]
    click_seq = content_cfg.get("clickSequence")
    if click_seq:
        return click_seq[0]["selector"]
    return content_cfg.get("selector")


def _extract_page_content(page, content_cfg: dict) -> str:
    if content_cfg.get("method") == "click_copy":
        click_seq = content_cfg.get("clickSequence")
        if click_seq:
            for step in click_seq:
                page.click(step["selector"])
                page.wait_for_timeout(step.get("waitAfter", 500))
        else:
            selector = content_cfg.get("selector")
            if not selector:
                raise ValueError("click_copy requires 'selector' or 'clickSequence'")
            page.click(selector)
            page.wait_for_timeout(1000)
        return page.evaluate("() => navigator.clipboard.readText()")
    else:  # inner_html
        element = page.query_selector(content_cfg.get("selector"))
        raw_html = element.inner_html() if element else ""
        return _html_to_markdown(raw_html)


def _dismiss_cookie_banner(page, config: dict):
    extractor = config.get("extractor") or "default"
    if extractor == "terraform":
        try:
            page.get_by_role("button", name="Accept All").click(timeout=3000)
            page.wait_for_timeout(1000)
        except Exception:
            pass


def _set_cached(key: str, data: dict) -> None:
    _cache[key] = {**data, "timestamp": time.time()}


def _get_cached(key: str) -> dict | None:
    try:
        entry = _cache[key]
        if entry and (time.time() - entry.get("timestamp", 0)) < DEFAULT_MAX_AGE:
            return entry
    except KeyError:
        pass
    return None


# ---------------------------------------------------------------------------
# Worker class   (registered with app.cls() in server.py – no decorator here)
# ---------------------------------------------------------------------------


class PlaywrightWorkerBase:
    """Browser-based scraper with lifecycle management."""

    @modal.enter()
    def setup(self):
        from playwright.sync_api import sync_playwright

        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch()
        print("PlaywrightWorker browser started")

    @modal.exit()
    def cleanup(self):
        self.browser.close()
        self.playwright.stop()
        print("PlaywrightWorker browser closed")

    # ------------------------------------------------------------------
    # Single-page methods – return data, never touch cache
    # ------------------------------------------------------------------

    @modal.method()
    def scrape_content(self, site_id: str, path: str, config: dict) -> dict:
        """Scrape content from a single page.

        Returns {"content": str, "metadata": dict} or {"error": str, "code": str}.
        """
        content_cfg = config.get("content", {})
        url = config.get("baseUrl", "") + path
        wait_for = _derive_wait_for(content_cfg)
        permissions = (
            ["clipboard-read", "clipboard-write"]
            if content_cfg.get("method") == "click_copy"
            else []
        )

        print(f"[scrape_content] {url} (method={content_cfg.get('method', 'inner_html')})")
        context = self.browser.new_context(permissions=permissions)
        page = context.new_page()
        try:
            page.goto(
                url,
                wait_until=content_cfg.get("waitUntil", "domcontentloaded"),
                timeout=content_cfg.get("gotoTimeoutMs", 30000),
            )
            _dismiss_cookie_banner(page, config)
            if wait_for:
                page.wait_for_selector(
                    wait_for,
                    state="visible",
                    timeout=content_cfg.get("waitForTimeoutMs", 15000),
                )
                page.wait_for_timeout(500)

            content = _extract_page_content(page, content_cfg)
            print(f"[scrape_content] OK {len(content):,} chars")
            return {
                "content": content,
                "metadata": {"url": url, "site_id": site_id, "path": path},
            }
        except Exception as e:
            print(f"[scrape_content] FAIL {str(e)[:200]}")
            return {"error": str(e)[:200], "code": "SCRAPE_FAILED"}
        finally:
            context.close()

    @modal.method()
    def scrape_links(self, site_id: str, config: dict) -> dict:
        """Browser-based link discovery for JS-rendered pages.

        Returns {"content": list[str], "metadata": dict} or {"error": str, "code": str}.
        """
        base_url = config.get("baseUrl", "")
        links_cfg = config.get("links", {})
        start_urls = links_cfg.get("startUrls", [""])
        wait_for = links_cfg.get("waitFor")
        pattern = links_cfg.get("pattern", "")

        print(f"[scrape_links] {base_url} ({len(start_urls)} start URLs)")
        context = self.browser.new_context()
        page = context.new_page()
        try:
            all_links: set[str] = set()
            for start_path in start_urls or [""]:
                page.goto(
                    base_url + start_path,
                    wait_until=links_cfg.get("waitUntil", "domcontentloaded"),
                    timeout=links_cfg.get("gotoTimeoutMs", 30000),
                )
                _dismiss_cookie_banner(page, config)
                if wait_for:
                    page.wait_for_selector(
                        wait_for,
                        state="visible",
                        timeout=links_cfg.get("waitForTimeoutMs", 15000),
                    )
                    page.wait_for_timeout(2000)

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

            links = sorted(all_links)
            print(f"[scrape_links] OK {len(links)} links")
            return {"content": links, "metadata": {"site_id": site_id, "base_url": base_url}}
        except Exception as e:
            print(f"[scrape_links] FAIL {str(e)[:200]}")
            return {"error": str(e)[:200], "code": "LINKS_FAILED"}
        finally:
            context.close()

    @modal.method()
    def discover_selectors(self, url: str) -> dict:
        """Analyse a docs page and suggest scraping configuration.

        Returns {"content": dict, "metadata": dict} or {"error": str, "code": str}.
        """
        print(f"[discover_selectors] Analyzing {url}")
        context = self.browser.new_context()
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(2000)

            framework = self._detect_framework(page)
            copy_buttons = self._find_copy_buttons(page, url)
            content_selectors = self._find_content_selectors(page)
            link_analysis = self._analyze_links(page, url)
            base_url = self._suggest_base_url(url)

            print(
                f"[discover_selectors] OK framework={framework}, "
                f"{len(copy_buttons)} copy btns, {len(content_selectors)} selectors"
            )
            return {
                "content": {
                    "url": url,
                    "framework": framework,
                    "base_url_suggestion": base_url,
                    "copy_buttons": copy_buttons[:5],
                    "content_selectors": content_selectors[:10],
                    "link_analysis": link_analysis,
                },
                "metadata": {"url": url},
            }
        except Exception as e:
            print(f"[discover_selectors] FAIL {str(e)[:200]}")
            return {"error": str(e)[:200], "code": "DISCOVER_FAILED"}
        finally:
            context.close()

    # ------------------------------------------------------------------
    # Batch method – writes to cache for fire-and-forget bulk jobs
    # ------------------------------------------------------------------

    @modal.method()
    def process_batch(
        self,
        job_id: str,
        site_id: str,
        paths: list[str],
        config: dict,
        batch_size: int = 25,
    ) -> dict:
        """Process a batch of pages for a bulk job.

        Writes successful results to cache and updates job progress directly
        because bulk jobs are spawned fire-and-forget (.spawn).

        Returns {"content": list[dict], "metadata": dict} or {"error": str, "code": str}.
        """
        from api.bulk import DEFAULT_DELAY_MS, update_job_progress

        content_cfg = config.get("content", {})
        base_url = config.get("baseUrl", "")
        permissions = (
            ["clipboard-read", "clipboard-write"]
            if content_cfg.get("method") == "click_copy"
            else []
        )

        context = self.browser.new_context(permissions=permissions)
        page = context.new_page()
        summary = {"success": 0, "skipped": 0, "failed": 0, "errors": []}
        items: list[dict] = []

        try:
            for i, path in enumerate(paths):
                cache_key = f"{site_id}:{path}"
                url = base_url + path

                # Skip if fresh cache hit
                if _get_cached(cache_key):
                    summary["skipped"] += 1
                    continue

                # Skip if error threshold exceeded and not expired
                try:
                    err = _error_tracker.get(cache_key, {})
                    if (
                        err.get("count", 0) >= ERROR_THRESHOLD
                        and time.time() - err.get("timestamp", 0) < ERROR_EXPIRY
                    ):
                        summary["skipped"] += 1
                        continue
                except KeyError:
                    pass

                try:
                    page.goto(
                        url,
                        wait_until=content_cfg.get("waitUntil", "domcontentloaded"),
                        timeout=content_cfg.get("gotoTimeoutMs", 30000),
                    )
                    wait_for = _derive_wait_for(content_cfg)
                    if wait_for:
                        page.wait_for_selector(
                            wait_for,
                            state="visible",
                            timeout=content_cfg.get("waitForTimeoutMs", 15000),
                        )
                    content = _extract_page_content(page, content_cfg)

                    if content:
                        _set_cached(cache_key, {"content": content, "url": url})
                        summary["success"] += 1
                        items.append({"content": content, "metadata": {"url": url, "path": path}})
                        try:
                            _error_tracker.pop(cache_key, None)
                        except Exception:
                            pass
                    else:
                        summary["failed"] += 1
                        summary["errors"].append({"path": path, "error": "Empty content"})

                except Exception as e:
                    summary["failed"] += 1
                    summary["errors"].append({"path": path, "error": str(e)[:200]})
                    try:
                        err = _error_tracker.get(cache_key, {})
                        _error_tracker[cache_key] = {
                            "count": err.get("count", 0) + 1,
                            "last_error": str(e)[:200],
                            "timestamp": time.time(),
                        }
                    except Exception:
                        pass

                if i < len(paths) - 1:
                    time.sleep(DEFAULT_DELAY_MS / 1000)
        finally:
            context.close()

        update_job_progress(job_id, summary)
        return {"content": items, "metadata": {"job_id": job_id, "site_id": site_id, **summary}}

    # ------------------------------------------------------------------
    # Discovery helpers (private)
    # ------------------------------------------------------------------

    def _detect_framework(self, page) -> str:
        framework_indicators = {
            "docusaurus": [
                'meta[name="generator"][content*="Docusaurus"]',
                'div[class*="docusaurus"]',
                ".theme-doc-markdown",
            ],
            "mintlify": [
                'meta[name="generator"][content*="Mintlify"]',
                'div[id="__next"]',
                'button[aria-label="Copy page"]',
            ],
            "gitbook": [
                'meta[name="generator"][content*="GitBook"]',
                ".gitbook-markdown",
                'div[class*="gitbook"]',
            ],
            "readme": [
                'meta[name="generator"][content*="readme"]',
                ".markdown-body",
            ],
            "vitepress": [
                'meta[name="generator"][content*="VitePress"]',
                ".vp-doc",
            ],
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
        try:
            ctx = self.browser.new_context(
                permissions=["clipboard-read", "clipboard-write"]
            )
            p = ctx.new_page()
            p.goto(url, wait_until="domcontentloaded", timeout=30000)
            p.wait_for_timeout(1000)
            p.click(selector, timeout=5000)
            p.wait_for_timeout(1000)
            content = p.evaluate("() => navigator.clipboard.readText()")
            ctx.close()
            if content and len(content) > 500:
                return {"selector": selector, "chars": len(content), "works": True}
        except Exception as e:
            return {"selector": selector, "error": str(e)[:100], "works": False}
        return {"selector": selector, "works": False}

    def _find_copy_buttons(self, page, url: str) -> list[dict]:
        patterns = [
            # Flexible title/aria-label matches (catches "Copy page", "Copy page markdown for use with LLMs", etc.)
            "//button[contains(@title, 'Copy page')]",
            "//button[contains(@aria-label, 'Copy page')]",
            # Text content matches
            "//button[.//span[contains(text(), 'Copy page')]]",
            "//button[contains(., 'Copy page')]",
            "button[type='button']:has(div:has-text('Copy as Markdown'))",
            "#page-context-menu-button",
            "//button[.//span[normalize-space(text())='Copy page']]",
        ]
        results = []
        for pat in patterns:
            try:
                if page.locator(pat).all():
                    r = self._test_copy_button(url, pat)
                    if r:
                        results.append(r)
            except Exception:
                continue
        return results

    def _find_content_selectors(self, page) -> list[dict]:
        candidates = [
            "main article .theme-doc-markdown",
            "main article",
            ".markdown-body",
            ".gitbook-markdown",
            ".vp-doc",
            "#mainContent",
            "#provider-docs-content",
            "[role='main'] article",
            "[role='main']",
            "main",
            "article",
            ".content",
            "#content",
        ]
        found = []
        for sel in candidates:
            try:
                el = page.query_selector(sel)
                if el:
                    html = el.inner_html()
                    text = el.inner_text()
                    if len(text) > 500:
                        found.append({
                            "selector": sel,
                            "chars": len(html),
                            "text_chars": len(text),
                            "recommended": 1000 < len(text) < 50000,
                        })
            except Exception:
                continue
        found.sort(key=lambda x: (x["recommended"], x["text_chars"]), reverse=True)
        return found

    def _analyze_links(self, page, url: str) -> dict:
        try:
            all_links = page.eval_on_selector_all(
                "a[href]", "elements => elements.map(e => e.href)"
            )
        except Exception:
            all_links = []

        parsed_url = urlparse(url)
        internal: list[str] = []
        for link in all_links:
            try:
                clean = clean_url(link)
                if urlparse(clean).netloc == parsed_url.netloc:
                    internal.append(clean)
            except Exception:
                continue
        internal = sorted(set(internal))

        path_patterns: dict[str, int] = {}
        for link in internal:
            try:
                parts = [p for p in urlparse(link).path.split("/") if p]
                if parts:
                    path_patterns[f"/{parts[0]}/"] = path_patterns.get(f"/{parts[0]}/", 0) + 1
            except Exception:
                continue

        return {
            "total_internal_links": len(internal),
            "sample_links": internal[:20],
            "path_patterns": sorted(path_patterns.items(), key=lambda x: x[1], reverse=True)[:10],
        }

    def _suggest_base_url(self, url: str) -> str:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if parsed.path and parsed.path != "/":
            parts = [p for p in parsed.path.split("/") if p]
            if parts:
                return f"{base}/{parts[0]}"
        return base
