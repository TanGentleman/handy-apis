# ---
# deploy: true
# ---

# Content Scraper API – lightweight server + PlaywrightWorker dispatch.
#
# server.py owns:
#   - The Modal App and both images (api_image, playwright_image)
#   - All FastAPI endpoints (raw /… for CLI, /api/… for the HTML UI)
#   - Cache read/write, error tracking, job orchestration
#   - HTTP-based link discovery (scrape_links_fetch – runs inline, no browser)
#   - The scheduled refresh_cache heartbeat
#
# Browser work is dispatched to PlaywrightWorker (api/worker.py).

import os
import asyncio
import io
import json
import re
import time
import zipfile
from pathlib import Path
from urllib.parse import urljoin, urlparse

import modal
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, Field

from api.bulk import (
    DEFAULT_DELAY_MS,
    USER_AGENT,
    JobStatus,
    calculate_batches,
    create_job,
    jobs,
    update_job_progress,
)
from api.urls import clean_url, is_asset_url, normalize_page_path, normalize_path, normalize_url

def get_app_name() -> str:
    from dotenv import load_dotenv
    local_env_path = Path(__file__).parent.parent / ".env"
    remote_env_path = Path("/root/.env")
    if not local_env_path.exists() and not remote_env_path.exists():
        raise FileNotFoundError(f"Environment file not found: {local_env_path}")
    if local_env_path.exists():
        load_dotenv(local_env_path)
    else:
        load_dotenv(remote_env_path)
    if not os.environ.get("APP_NAME"):
        print(f"APP_NAME is not set in the environment file: {local_env_path}")
        return "doc"
    app_name = os.environ["APP_NAME"]
    app_name = re.sub(r'[^a-zA-Z0-9]', '', app_name)
    if not app_name:
        raise ValueError("APP_NAME is not a valid Modal app name")
    return app_name

# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------
APP_NAME = get_app_name()
api_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastapi[standard]", "pydantic", "httpx", "markdownify")
    .add_local_dir("api", "/root/api")
    .add_local_file("config/sites.json", "/root/sites.json")
    .add_local_file("ui/ui.html", "/root/ui.html")
    .add_local_file(".env", "/root/.env")
)

minimal_image = modal.Image.debian_slim(python_version="3.11")

# ---------------------------------------------------------------------------
# App + PlaywrightWorker registration
# ---------------------------------------------------------------------------
app = modal.App(APP_NAME, image=api_image)

# Import worker pieces and register the class with our app.
# PlaywrightWorkerBase uses @modal.enter/@modal.exit/@modal.method but has no
# @app.cls decorator – we apply it here to avoid circular imports.
from api.worker import PlaywrightWorkerBase, playwright_image  # noqa: E402

PlaywrightWorker = app.cls(
    image=playwright_image,
    scaledown_window=300,
    timeout=300,
    retries=2,
)(PlaywrightWorkerBase)

# ---------------------------------------------------------------------------
# Modal Dicts
# ---------------------------------------------------------------------------
cache = modal.Dict.from_name("scraper-cache", create_if_missing=True)
error_tracker = modal.Dict.from_name("scraper-errors", create_if_missing=True)
sites_dict = modal.Dict.from_name("scraper-sites", create_if_missing=True)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
IS_PROD = False
DEFAULT_MAX_AGE = 3600 * 24 * 7  # 7 days
ERROR_THRESHOLD = 3
ERROR_EXPIRY = 86400  # 24 hours

# ---------------------------------------------------------------------------
# Site Config Models
# ---------------------------------------------------------------------------


class ClickStep(BaseModel):
    selector: str
    waitAfter: int = 500


class LinksConfig(BaseModel):
    startUrls: list[str] = Field(default_factory=lambda: [""])
    pattern: str = ""
    maxDepth: int = 2
    waitFor: str | None = None
    waitForTimeoutMs: int = 15000
    waitUntil: str = "domcontentloaded"
    gotoTimeoutMs: int = 30000


class ContentConfig(BaseModel):
    mode: str = "browser"
    selector: str | None = None
    method: str = "inner_html"
    clickSequence: list[ClickStep] | None = None
    waitFor: str | None = None
    waitForTimeoutMs: int = 15000
    waitUntil: str = "domcontentloaded"
    gotoTimeoutMs: int = 30000


class SiteConfig(BaseModel):
    name: str
    baseUrl: str
    mode: str = "fetch"
    defaultPath: str = ""
    testPath: str | None = None
    extractor: str | None = None
    links: LinksConfig = Field(default_factory=LinksConfig)
    content: ContentConfig = Field(default_factory=ContentConfig)


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------


def get_cached(cache_key: str, max_age: int) -> dict | None:
    try:
        cached = cache[cache_key]
        if cached and (time.time() - cached.get("timestamp", 0)) < max_age:
            return cached
    except KeyError:
        pass
    return None


def set_cached(cache_key: str, data: dict) -> None:
    cache[cache_key] = {**data, "timestamp": time.time()}


# ---------------------------------------------------------------------------
# Site loading
# ---------------------------------------------------------------------------


def load_sites_from_file() -> dict[str, dict]:
    config_path = Path("/root/sites.json")
    with open(config_path) as f:
        return json.load(f)["sites"]


def load_sites_config() -> dict[str, SiteConfig]:
    try:
        sites_raw = sites_dict.get("_all_sites", None)
        if sites_raw:
            return {sid: SiteConfig(**cfg) for sid, cfg in sites_raw.items()}
    except KeyError:
        pass

    file_sites = load_sites_from_file()
    try:
        sites_dict["_all_sites"] = file_sites
    except Exception:
        pass
    return {sid: SiteConfig(**cfg) for sid, cfg in file_sites.items()}


# ---------------------------------------------------------------------------
# Response / Request models
# ---------------------------------------------------------------------------


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


class BulkScrapeRequest(BaseModel):
    urls: list[str]
    max_age: int = DEFAULT_MAX_AGE
    batch_size: int = 25


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def html_to_markdown(html: str) -> str:
    from markdownify import markdownify as md

    return md(html, heading_style="ATX", strip=["script", "style"]).strip()


def get_site_resolver() -> dict:
    sites_config = load_sites_config()
    sites = []
    for site_id, config in sites_config.items():
        if config.baseUrl:
            sites.append((normalize_url(config.baseUrl), site_id))
    sites.sort(key=lambda x: len(x[0]), reverse=True)
    return {"sites": sites, "config": sites_config}


def resolve_url_to_site(url: str) -> tuple[str | None, str, str]:
    norm_url = normalize_url(url)
    resolver = get_site_resolver()
    for norm_base, site_id in resolver["sites"]:
        if norm_url == norm_base:
            return (site_id, "", norm_url)
        if norm_url.startswith(norm_base + "/"):
            return (site_id, norm_url[len(norm_base):], norm_url)
    return (None, "", norm_url)


def filter_and_group_urls(urls: list[str]) -> dict:
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
    import posixpath

    path = normalize_path(path)
    if path == "":
        return f"docs/{site_id}/index.md"
    clean = posixpath.normpath(path.lstrip("/"))
    if clean.startswith("..") or "/.." in clean:
        raise ValueError(f"Unsafe path: {path}")
    return f"docs/{site_id}/{clean}.md"


def extract_links_from_html(html: str, base_url: str, pattern: str) -> list[str]:
    links: set[str] = set()
    for match in re.finditer(r'href="([^"]*)"', html):
        link = clean_url(match.group(1))
        if link.startswith("/"):
            parsed = urlparse(base_url)
            link = f"{parsed.scheme}://{parsed.netloc}{link}"
        elif not link.startswith("http"):
            link = urljoin(base_url, link)
        if pattern and pattern not in link:
            if link != base_url and link != f"{base_url}/":
                continue
        if urlparse(link).netloc == urlparse(base_url).netloc:
            links.add(link)
    return sorted(links)


# ---------------------------------------------------------------------------
# HTTP-based link discovery (runs inline – no browser needed)
# ---------------------------------------------------------------------------


async def scrape_links_fetch(site_id: str, config: dict) -> dict:
    """Crawl static site links via HTTP.

    Returns {"content": list[str], "metadata": dict} or {"error": str, "code": str}.
    """
    import httpx

    base_url = config.get("baseUrl", "")
    links_cfg = config.get("links", {})
    start_urls = [
        base_url + p if p else base_url for p in links_cfg.get("startUrls", [""])
    ]
    max_depth = links_cfg.get("maxDepth", 2)
    pattern = links_cfg.get("pattern", "")

    all_links: set[str] = set()
    visited: set[str] = set()
    to_visit = [(url, 0) for url in start_urls]

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        while to_visit:
            batch: list[tuple[str, int]] = []
            while to_visit and len(batch) < 10:
                url, depth = to_visit.pop(0)
                if url not in visited and depth <= max_depth:
                    visited.add(url)
                    batch.append((url, depth))
            if not batch:
                continue

            async def fetch_one(u: str) -> str:
                try:
                    resp = await client.get(u)
                    resp.raise_for_status()
                    return resp.text
                except Exception as e:
                    print(f"[scrape_links_fetch] FAIL {u}: {str(e)[:100]}")
                    return ""

            results = await asyncio.gather(*[fetch_one(u) for u, _ in batch])

            for (url, depth), html in zip(batch, results):
                if not html:
                    continue
                for link in extract_links_from_html(html, base_url, pattern):
                    all_links.add(link)
                    if depth < max_depth and link not in visited:
                        to_visit.append((link, depth + 1))

    print(f"[scrape_links_fetch] OK {len(all_links)} links for {site_id}")
    return {"content": sorted(all_links), "metadata": {"site_id": site_id}}


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
web_app = FastAPI(title="Content Scraper API")


# --- UI -----------------------------------------------------------
@web_app.get("/", response_class=HTMLResponse)
async def serve_ui():
    html_content = Path("/root/ui.html").read_text()
    return HTMLResponse(content=html_content, media_type="text/html")


@web_app.get("/health")
async def health():
    return {"status": "healthy"}


# --- Sites management ----------------------------------------------


@web_app.get("/sites")
async def get_sites(
    include_test_paths: bool = Query(default=False),
):
    sites_config = load_sites_config()
    if include_test_paths:
        sites = [
            {"id": sid, "testPath": cfg.testPath}
            for sid, cfg in sites_config.items()
            if cfg.testPath
        ]
    else:
        sites = [{"id": sid} for sid in sites_config]
    return {"sites": sites, "count": len(sites)}


@web_app.get("/sites/config")
async def get_sites_config_endpoint():
    sites_config = load_sites_config()
    return {
        "sites": {sid: cfg.model_dump() for sid, cfg in sites_config.items()},
        "count": len(sites_config),
    }


@web_app.post("/sites/{site_id}")
async def add_site(site_id: str, config: SiteConfig):
    try:
        current = sites_dict.get("_all_sites", {})
    except KeyError:
        current = load_sites_from_file()
    current[site_id] = config.model_dump()
    sites_dict["_all_sites"] = current
    return {"success": True, "site_id": site_id, "config": config.model_dump(), "message": f"Site '{site_id}' added successfully"}


@web_app.delete("/sites/{site_id}")
async def delete_site(site_id: str):
    try:
        current = sites_dict.get("_all_sites", {})
    except KeyError:
        current = load_sites_from_file()
    if site_id not in current:
        raise HTTPException(status_code=404, detail=f"Site not found: {site_id}")
    del current[site_id]
    sites_dict["_all_sites"] = current
    return {"success": True, "site_id": site_id, "message": f"Site '{site_id}' deleted successfully"}


@web_app.post("/sites/reset")
async def reset_sites():
    file_sites = load_sites_from_file()
    sites_dict["_all_sites"] = file_sites
    return {"success": True, "count": len(file_sites), "sites": list(file_sites.keys()), "message": f"Reset to {len(file_sites)} sites from sites.json"}


# --- Discover ------------------------------------------------------


@web_app.get("/discover")
async def discover_site(
    url: str = Query(description="Full URL of a documentation page to analyse"),
):
    worker = PlaywrightWorker()
    result = await worker.discover_selectors.remote.aio(url)

    if "error" in result:
        raise HTTPException(status_code=500, detail=f"Failed to analyze page: {result['error']}")

    return {"success": True, **result["content"]}


# --- Links ---------------------------------------------------------


@web_app.get("/sites/{site_id}/links")
async def get_site_links(
    site_id: str,
    max_age: int = Query(default=DEFAULT_MAX_AGE),
) -> LinksResponse:
    sites_config = load_sites_config()
    config = sites_config.get(site_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Unknown site: {site_id}")

    cache_key = f"{site_id}:links"
    cached = get_cached(cache_key, max_age)
    if cached and cached.get("count", 0) > 1:
        return LinksResponse(site_id=site_id, links=cached["links"], count=cached["count"])

    config_dict = config.model_dump()
    if config.mode == "browser":
        worker = PlaywrightWorker()
        result = await worker.scrape_links.remote.aio(site_id, config_dict)
    else:
        result = await scrape_links_fetch(site_id, config_dict)

    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    links = result["content"]
    count = len(links)
    if count > 1:
        set_cached(cache_key, {"links": links, "count": count})

    return LinksResponse(site_id=site_id, links=links, count=count)


# --- Content -------------------------------------------------------


@web_app.get("/sites/{site_id}/content")
async def get_site_content(
    site_id: str,
    path: str = Query(default=""),
    max_age: int = Query(default=DEFAULT_MAX_AGE),
) -> ContentResponse:
    sites_config = load_sites_config()
    config = sites_config.get(site_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Unknown site: {site_id}")

    path = normalize_page_path(path, config.baseUrl) if path else config.defaultPath
    cache_key = f"{site_id}:{path}"
    url = config.baseUrl + path
    force = max_age == 0

    # Cache check (skip when force)
    if not force:
        cached = get_cached(cache_key, max_age)
        if cached:
            return ContentResponse(
                site_id=site_id, path=path, content=cached["content"],
                content_length=len(cached["content"]), url=cached["url"], from_cache=True,
            )

    error_key = f"{site_id}:{path}"

    if force:
        # Clear error history so the scrape proceeds
        try:
            error_tracker.pop(error_key, None)
        except Exception:
            pass
    else:
        # honour error threshold
        try:
            error_info = error_tracker[error_key]
            if error_info and error_info.get("count", 0) >= ERROR_THRESHOLD:
                if time.time() - error_info.get("timestamp", 0) < ERROR_EXPIRY:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Skipped: failed {error_info['count']} times",
                    )
                else:
                    error_tracker.pop(error_key, None)  # expired – retry
        except KeyError:
            pass

    # Dispatch to worker
    worker = PlaywrightWorker()
    result = await worker.scrape_content.remote.aio(site_id, path, config.model_dump())

    if "error" in result:
        # Track error on the server
        try:
            info = error_tracker.get(error_key, {})
            error_tracker[error_key] = {
                "count": info.get("count", 0) + 1,
                "last_error": result["error"],
                "timestamp": time.time(),
            }
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=result["error"])

    content = result["content"]
    result_url = result["metadata"]["url"]

    # Clear error on success
    try:
        error_tracker.pop(error_key, None)
    except Exception:
        pass

    if content:
        set_cached(cache_key, {"content": content, "url": result_url})

    return ContentResponse(
        site_id=site_id, path=path, content=content,
        content_length=len(content), url=result_url, from_cache=False,
    )


# --- Cache management ----------------------------------------------


@web_app.get("/cache/keys")
async def cache_keys(
    site_id: str = Query(default=None),
    content_only: bool = Query(default=True),
):
    sites_config = load_sites_config()
    results = []
    for key in cache.keys():
        if content_only and key.endswith(":links"):
            continue
        parts = key.split(":", 1)
        if len(parts) != 2:
            continue
        key_site_id, key_path = parts
        if site_id and key_site_id != site_id:
            continue
        cfg = sites_config.get(key_site_id)
        if cfg:
            results.append({"site_id": key_site_id, "path": key_path, "url": cfg.baseUrl + key_path})
    return {"count": len(results), "keys": results}


@web_app.get("/cache/stats")
async def cache_stats():
    keys = list(cache.keys())
    by_site: dict[str, int] = {}
    by_type = {"content": 0, "links": 0}
    for key in keys:
        site = key.split(":")[0]
        by_site[site] = by_site.get(site, 0) + 1
        if key.endswith(":links"):
            by_type["links"] += 1
        else:
            by_type["content"] += 1
    return {"total_entries": len(keys), "by_site": by_site, "by_type": by_type}


@web_app.delete("/cache/{site_id}")
async def clear_cache(site_id: str):
    to_delete = [k for k in cache.keys() if k.startswith(f"{site_id}:")]
    for k in to_delete:
        cache.pop(k, None)
    return {"site_id": site_id, "deleted": len(to_delete)}


# --- Errors --------------------------------------------------------


@web_app.get("/errors")
async def get_errors():
    errors = []
    for key in error_tracker.keys():
        info = error_tracker[key]
        parts = key.split(":", 1)
        errors.append({
            "site_id": parts[0],
            "path": parts[1] if len(parts) > 1 else "",
            "count": info.get("count", 0),
            "last_error": info.get("last_error", ""),
            "timestamp": info.get("timestamp", 0),
        })
    errors.sort(key=lambda x: x["count"], reverse=True)
    return {"total_failed_links": len(errors), "errors": errors}


@web_app.delete("/errors")
async def clear_all_errors():
    count = len(list(error_tracker.keys()))
    error_tracker.clear()
    return {"cleared": count}


@web_app.delete("/errors/{site_id}")
async def clear_site_errors(site_id: str):
    to_delete = [k for k in error_tracker.keys() if k.startswith(f"{site_id}:")]
    for k in to_delete:
        error_tracker.pop(k, None)
    return {"site_id": site_id, "cleared": len(to_delete)}


# --- Index (parallel scrape of entire site) ------------------------


@web_app.post("/sites/{site_id}/index")
async def index_site(
    site_id: str,
    max_age: int = Query(default=DEFAULT_MAX_AGE),
    batch_size: int = Query(default=25),
):
    sites_config = load_sites_config()
    config = sites_config.get(site_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Unknown site: {site_id}")

    # Get links
    links_response = await get_site_links(site_id, max_age=max_age)
    base_url = config.baseUrl

    # Extract paths, filter assets
    paths: list[str] = []
    skipped_assets = 0
    for link in links_response.links:
        if is_asset_url(link):
            skipped_assets += 1
            continue
        if link.startswith(base_url):
            paths.append(link[len(base_url):])
        else:
            lp = urlparse(link)
            if lp.netloc == urlparse(base_url).netloc:
                paths.append(lp.path)

    # Separate cached vs stale
    paths_to_scrape: list[str] = []
    cached_count = 0
    for p in paths:
        if get_cached(f"{site_id}:{p}", max_age):
            cached_count += 1
        else:
            paths_to_scrape.append(p)

    # Scrape in batches of batch_size
    worker = PlaywrightWorker()
    config_dict = config.model_dump()
    successful, failed, errors = 0, 0, []

    for i in range(0, len(paths_to_scrape), batch_size):
        chunk = paths_to_scrape[i : i + batch_size]
        tasks = [worker.scrape_content.remote.aio(site_id, p, config_dict) for p in chunk]
        chunk_results = await asyncio.gather(*tasks, return_exceptions=True)

        for j, result in enumerate(chunk_results):
            p = chunk[j]
            if isinstance(result, Exception):
                failed += 1
                errors.append({"path": p, "error": str(result)})
            elif "error" in result:
                failed += 1
                errors.append({"path": p, "error": result["error"]})
            else:
                content = result["content"]
                if content:
                    successful += 1
                    set_cached(f"{site_id}:{p}", {"content": content, "url": result["metadata"]["url"]})
                else:
                    failed += 1
                    errors.append({"path": p, "error": "Empty content"})

    return {
        "site_id": site_id,
        "total": len(paths),
        "skipped_assets": skipped_assets,
        "cached": cached_count,
        "scraped": len(paths_to_scrape),
        "successful": successful,
        "failed": failed,
        "errors": errors[:10],
    }


# --- Download (ZIP) ------------------------------------------------


@web_app.get("/sites/{site_id}/download")
async def download_site(
    site_id: str,
    max_age: int = Query(default=DEFAULT_MAX_AGE),
    batch_size: int = Query(default=25),
):
    sites_config = load_sites_config()
    config = sites_config.get(site_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Unknown site: {site_id}")

    print(f"[download_site] Starting download for {site_id}")

    links_response = await get_site_links(site_id, max_age=max_age)
    base_url = config.baseUrl

    paths: list[str] = []
    for link in links_response.links:
        if link.startswith(base_url):
            paths.append(link[len(base_url):])
        else:
            lp = urlparse(link)
            if lp.netloc == urlparse(base_url).netloc:
                paths.append(lp.path)

    print(f"[download_site] {len(paths)} pages")

    worker = PlaywrightWorker()
    config_dict = config.model_dump()

    # Collect content: cache-hit inline, scrape in batches
    page_results: list[dict] = []
    uncached_paths: list[str] = []

    for p in paths:
        cached = get_cached(f"{site_id}:{p}", max_age)
        if cached:
            page_results.append({"path": p, "content": cached["content"], "success": True, "from_cache": True})
        else:
            uncached_paths.append(p)

    for i in range(0, len(uncached_paths), batch_size):
        chunk = uncached_paths[i : i + batch_size]
        tasks = [worker.scrape_content.remote.aio(site_id, p, config_dict) for p in chunk]
        chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
        for j, result in enumerate(chunk_results):
            p = chunk[j]
            if isinstance(result, Exception) or "error" in result:
                page_results.append({"path": p, "success": False, "error": str(result.get("error", result) if isinstance(result, dict) else result)})
            else:
                content = result["content"]
                if content:
                    set_cached(f"{site_id}:{p}", {"content": content, "url": result["metadata"]["url"]})
                page_results.append({"path": p, "content": content, "success": bool(content), "from_cache": False})

    # Build ZIP
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        ok, cached_n, scraped_n, fail_n = 0, 0, 0, 0
        for r in page_results:
            if not r.get("success") or not r.get("content"):
                fail_n += 1
                continue
            content = r["content"]
            if content.lstrip().startswith("<"):
                content = html_to_markdown(content)
            safe = r["path"].strip("/").replace("//", "/") or "index"
            zf.writestr(f"{site_id}/{safe}.md", content)
            ok += 1
            if r.get("from_cache"):
                cached_n += 1
            else:
                scraped_n += 1

        zf.writestr(
            f"{site_id}/README.md",
            f"# {config.name} Documentation\n\n"
            f"Downloaded from: {base_url}\n"
            f"Total pages: {len(paths)}\n"
            f"Successfully downloaded: {ok} (cached: {cached_n}, scraped: {scraped_n})\n"
            f"Failed: {fail_n}\n"
            f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}\n",
        )

    print(f"[download_site] ZIP – ok={ok} cached={cached_n} scraped={scraped_n} fail={fail_n}")
    zip_buffer.seek(0)
    return StreamingResponse(
        io.BytesIO(zip_buffer.read()),
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename={site_id}_docs.zip",
            "X-Download-Total": str(len(paths)),
            "X-Download-Cached": str(cached_n),
            "X-Download-Scraped": str(scraped_n),
            "X-Download-Failed": str(fail_n),
        },
    )


# --- Export (URL list → ZIP) ---------------------------------------


async def _build_export_zip(request: ExportRequest) -> tuple[bytes, dict]:
    """Shared logic: resolve URLs → fetch content → build ZIP.

    Returns (zip_bytes, stats_dict).
    """
    urls = request.urls
    cached_only = request.cached_only
    max_age = request.max_age

    if not urls:
        raise HTTPException(status_code=400, detail="No URLs provided")

    print(f"[export_zip] Processing {len(urls)} URLs (cached_only={cached_only})")

    # Resolve & dedupe
    resolved: list[dict] = []
    seen: set[tuple[str, str]] = set()
    unknown_urls: list[dict] = []

    for url in urls:
        sid, path, norm = resolve_url_to_site(url)
        entry = {"original_url": url, "normalized_url": norm, "site_id": sid, "path": path}
        if not sid:
            unknown_urls.append(entry)
            continue
        key = (sid, normalize_path(path))
        if key not in seen:
            seen.add(key)
            resolved.append(entry)

    dupe_count = len(urls) - len(resolved) - len(unknown_urls)
    print(f"[export_zip] {len(resolved)} unique, {len(unknown_urls)} unknown, {dupe_count} dupes")

    # Fetch content
    worker = PlaywrightWorker()
    sites_config = load_sites_config()
    semaphore = asyncio.Semaphore(50)

    async def fetch_one(r: dict) -> dict:
        sid = r["site_id"]
        path = r["path"]
        cache_key = f"{sid}:{path}"
        base = {"original_url": r["original_url"], "normalized_url": r["normalized_url"],
                "site_id": sid, "path": path, "success": False, "from_cache": False,
                "content": None, "content_length": 0, "error": None, "zip_path": None}

        cached = get_cached(cache_key, max_age)
        if cached:
            base.update(success=True, from_cache=True, content=cached["content"],
                        content_length=len(cached["content"]))
            return base
        if cached_only:
            base["error"] = "Not in cache"
            return base

        async with semaphore:
            cfg = sites_config.get(sid)
            if not cfg:
                base["error"] = "Unknown site"
                return base
            result = await worker.scrape_content.remote.aio(sid, path, cfg.model_dump())

        if "error" in result:
            base["error"] = result["error"]
        else:
            content = result["content"]
            base.update(success=True, content=content, content_length=len(content) if content else 0)
            if content:
                set_cached(cache_key, {"content": content, "url": result["metadata"]["url"]})
        return base

    fetch_results = await asyncio.gather(*[fetch_one(r) for r in resolved], return_exceptions=True)

    # Build ZIP
    ok, cached_n, scraped_n, miss_n, error_n = 0, 0, 0, 0, 0
    manifest_entries: list[dict] = []

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for result in fetch_results:
            if isinstance(result, Exception):
                error_n += 1
                continue

            entry = {k: result[k] for k in ("original_url", "normalized_url", "site_id", "path",
                                             "success", "from_cache", "content_length", "error")}
            entry["zip_path"] = None

            if result["success"] and result["content"]:
                content = result["content"]
                if content.lstrip().startswith("<"):
                    content = html_to_markdown(content)
                try:
                    zpath = zip_path_for(result["site_id"], result["path"])
                    zf.writestr(zpath, content)
                    entry["zip_path"] = zpath
                    ok += 1
                    if result["from_cache"]:
                        cached_n += 1
                    else:
                        scraped_n += 1
                except ValueError as e:
                    entry["error"] = str(e)
                    error_n += 1
            else:
                if result.get("error") == "Not in cache":
                    miss_n += 1
                else:
                    error_n += 1

            manifest_entries.append(entry)

        # Unknown URLs
        for r in unknown_urls:
            manifest_entries.append({
                "url": r["original_url"], "normalized_url": r["normalized_url"],
                "site_id": None, "path": None, "success": False, "from_cache": False,
                "content_length": 0, "error": "No matching site configuration", "zip_path": None,
            })
            error_n += 1

        if request.include_manifest:
            manifest = {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "total_urls": len(urls), "ok": ok, "cached": cached_n, "scraped": scraped_n,
                "miss": miss_n, "error": error_n + len(unknown_urls),
                "unknown_sites": len(unknown_urls), "entries": manifest_entries,
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    print(f"[export_zip] ok={ok} cached={cached_n} scraped={scraped_n} miss={miss_n} error={error_n}")

    stats = {
        "total": len(urls), "ok": ok, "cached": cached_n, "scraped": scraped_n,
        "miss": miss_n, "error": error_n + len(unknown_urls), "unknown_sites": len(unknown_urls),
    }
    zip_buffer.seek(0)
    return zip_buffer.read(), stats


@web_app.post("/export/zip")
async def export_urls_as_zip(request: ExportRequest):
    zip_bytes, stats = await _build_export_zip(request)
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers={
            "Content-Disposition": "attachment; filename=docs_export.zip",
            "X-Export-Total": str(stats["total"]),
            "X-Export-Ok": str(stats["ok"]),
            "X-Export-Cached": str(stats["cached"]),
            "X-Export-Scraped": str(stats["scraped"]),
            "X-Export-Miss": str(stats["miss"]),
            "X-Export-Error": str(stats["error"]),
        },
    )


# --- Bulk jobs -----------------------------------------------------


@web_app.post("/jobs/bulk")
async def submit_bulk_job(request: BulkScrapeRequest):
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

    # Spawn workers fire-and-forget – pass full config dict
    sites_config = load_sites_config()
    worker = PlaywrightWorker()
    for batch in batches:
        cfg = sites_config.get(batch["site_id"])
        if cfg:
            worker.process_batch.spawn(
                job_id, batch["site_id"], batch["paths"],
                cfg.model_dump(), request.batch_size,
            )

    print(f"[submit_bulk_job] job_id={job_id} batches={len(batches)} sites={list(grouped['by_site'].keys())}")
    return {"job_id": job_id, "status": "in_progress", "batches": len(batches), "input": job["input"]}


@web_app.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    try:
        job = jobs[job_id]
    except KeyError:
        raise HTTPException(404, f"Job not found: {job_id}")

    total = job["input"]["to_scrape"]
    pct = round((job["progress"]["completed"] / total) * 100, 1) if total else 100
    return {
        "job_id": job_id, "status": job["status"],
        "progress_pct": pct,
        "elapsed_seconds": round(time.time() - job["created_at"], 1),
        "input": job["input"], "progress": job["progress"],
        "workers": job["workers"], "errors": job["errors"][:10],
    }


@web_app.get("/jobs")
async def list_jobs(limit: int = Query(default=20, le=100)):
    try:
        all_keys = list(jobs.keys())
    except Exception:
        return {"jobs": []}

    result = []
    for job_id in all_keys[-limit:]:
        try:
            job = jobs[job_id]
            result.append({
                "job_id": job_id, "status": job["status"],
                "created_at": job["created_at"], "sites": job["input"]["sites"],
                "progress": f"{job['progress']['completed']}/{job['input']['to_scrape']}",
            })
        except KeyError:
            continue
    return {"jobs": sorted(result, key=lambda x: x["created_at"], reverse=True)}


# ===========================================================================
# /api/* routes – served to the HTML UI (ui.html)
# These mirror the contract that ui/app.py previously provided.
# ===========================================================================

# --- Simple pass-throughs ------------------------------------------


@web_app.get("/api/sites")
async def api_list_sites():
    return await get_sites()


@web_app.get("/api/sites/config")
async def api_get_sites_config():
    return await get_sites_config_endpoint()


@web_app.get("/api/sites/{site_id}/links")
async def api_get_links(site_id: str):
    return await get_site_links(site_id)


@web_app.get("/api/sites/{site_id}/content")
async def api_get_content(site_id: str, path: str = Query(default="")):
    return await get_site_content(site_id, path=path)


@web_app.get("/api/discover")
async def api_discover_get(url: str):
    return await discover_site(url=url)


@web_app.post("/api/jobs/bulk")
async def api_submit_bulk(request: BulkScrapeRequest):
    return await submit_bulk_job(request)


@web_app.get("/api/jobs/{job_id}")
async def api_get_job(job_id: str):
    return await get_job_status(job_id)


@web_app.get("/api/jobs")
async def api_list_jobs():
    return await list_jobs()


@web_app.get("/api/cache/keys")
async def api_cache_keys(site_id: str = Query(default=None)):
    return await cache_keys(site_id=site_id, content_only=True)


# --- Wrapped endpoints (ui.html expects {success, stdout, stderr}) --------


class _DiscoverPostBody(BaseModel):
    url: str


@web_app.post("/api/discover")
async def api_discover_post(req: _DiscoverPostBody):
    worker = PlaywrightWorker()
    result = await worker.discover_selectors.remote.aio(req.url)

    if "error" in result:
        return {"success": False, "stdout": "", "stderr": result["error"]}

    data = result["content"]
    framework = data.get("framework", "unknown")
    base_url = data.get("base_url_suggestion", req.url)
    copy_buttons = data.get("copy_buttons", [])
    content_selectors = data.get("content_selectors", [])
    link_analysis = data.get("link_analysis", {})

    lines = [
        "=" * 70,
        f"DISCOVERY RESULTS FOR: {req.url}",
        "=" * 70,
        f"\nFramework Detected: {framework.upper()}",
        f"Suggested Base URL: {base_url}",
        "\n" + "-" * 70,
        "COPY BUTTONS:",
    ]

    working = [b for b in copy_buttons if b.get("works")]
    if working:
        for btn in working:
            lines.append(f"  {btn['selector']} - {btn.get('chars', 0)} chars")
    else:
        lines.append("  No working copy buttons found")

    lines += ["\n" + "-" * 70, "CONTENT SELECTORS:"]
    for sel in content_selectors[:5]:
        marker = "[RECOMMENDED]" if sel.get("recommended") else ""
        lines.append(f"  {sel['selector']} {marker}")
        lines.append(f"     {sel.get('text_chars', 0)} text chars")

    lines += [
        "\n" + "-" * 70, "LINK ANALYSIS:",
        f"  Total internal links: {link_analysis.get('total_internal_links', 0)}",
        "\n" + "=" * 70, "SUGGESTED CONFIGURATION:", "=" * 70,
    ]

    # Build suggested config
    parsed = urlparse(req.url)
    site_id = parsed.hostname.replace(".", "-").replace("docs-", "").replace("www-", "")
    content_method = "inner_html"
    content_selector = "main"
    if working:
        content_method = "click_copy"
        content_selector = working[0]["selector"]
    elif content_selectors:
        content_selector = content_selectors[0]["selector"]

    suggested = {
        "name": site_id, "baseUrl": base_url, "mode": "browser",
        "links": {"startUrls": [""], "pattern": ""},
        "content": {"mode": "browser", "selector": content_selector, "method": content_method},
    }
    lines.append(f'\n"{site_id}": {json.dumps(suggested, indent=2)}')
    lines.append("\n" + "=" * 70)

    return {"success": True, "stdout": "\n".join(lines), "stderr": ""}


class _LinksPostBody(BaseModel):
    site_id: str
    save: bool = False
    force: bool = False


@web_app.post("/api/links")
async def api_links_post(req: _LinksPostBody):
    params_max_age = 0 if req.force else DEFAULT_MAX_AGE
    result = await get_site_links(req.site_id, max_age=params_max_age)
    return {
        "success": True,
        "stdout": "\n".join(result.links) + f"\n\nTotal: {result.count} links",
        "stderr": "",
    }


class _ContentPostBody(BaseModel):
    site_id: str
    path: str


@web_app.post("/api/content")
async def api_content_post(req: _ContentPostBody):
    result = await get_site_content(req.site_id, path=req.path)
    content = result.content
    return {
        "success": True,
        "stdout": f"Content ({len(content)} chars):\n\n{content[:2000]}{'...' if len(content) > 2000 else ''}",
        "stderr": "",
    }


class _AddSiteBody(BaseModel):
    site_id: str
    name: str
    baseUrl: str
    mode: str = "fetch"
    defaultPath: str = ""
    testPath: str | None = None
    extractor: str | None = None
    links: dict = {}
    content: dict = {}


@web_app.post("/api/add-site")
async def api_add_site(req: _AddSiteBody):
    cfg = SiteConfig(
        name=req.name, baseUrl=req.baseUrl, mode=req.mode,
        defaultPath=req.defaultPath, testPath=req.testPath,
        extractor=req.extractor, links=req.links, content=req.content,
    )
    try:
        result = await add_site(req.site_id, cfg)
        return {"success": True, "stdout": f"Site '{req.site_id}' added successfully!\n\nConfig: {result.get('config', {})}", "stderr": ""}
    except HTTPException as e:
        return {"success": False, "stdout": "", "stderr": f"Failed to add site: {e.detail}"}


@web_app.delete("/api/sites/{site_id}")
async def api_delete_site(site_id: str):
    try:
        await delete_site(site_id)
        return {"success": True, "stdout": f"Site '{site_id}' deleted successfully!", "stderr": ""}
    except HTTPException as e:
        return {"success": False, "stdout": "", "stderr": f"Failed to delete site: {e.detail}"}


@web_app.post("/api/sites/reset")
async def api_reset_sites():
    try:
        result = await reset_sites()
        return {"success": True, "stdout": f"Sites config reset! Loaded {result.get('count', '?')} sites from sites.json", "stderr": ""}
    except HTTPException as e:
        return {"success": False, "stdout": "", "stderr": f"Failed to reset sites: {e.detail}"}


class _ExportPostBody(BaseModel):
    urls: list[str]
    cached_only: bool = True


@web_app.post("/api/export")
async def api_export(req: _ExportPostBody):
    import base64

    export_req = ExportRequest(urls=req.urls, cached_only=req.cached_only, include_manifest=True)
    zip_bytes, stats = await _build_export_zip(export_req)
    return {
        "success": True,
        "zip_base64": base64.b64encode(zip_bytes).decode("utf-8"),
        "filename": "docs_export.zip",
        "size": len(zip_bytes),
        "stats": stats,
    }


# ===========================================================================
# Scheduled cache refresh (minimal image – no Playwright, no FastAPI)
# ===========================================================================


@app.function(schedule=modal.Period(days=6), image=minimal_image)
def refresh_cache():
    """Touch all cache entries to prevent Modal Dict 7-day expiration."""
    _c = modal.Dict.from_name("scraper-cache", create_if_missing=True)
    keys = list(_c.keys())
    refreshed = 0
    for key in keys:
        try:
            _ = _c[key]
            refreshed += 1
        except KeyError:
            pass
    print(f"[refresh_cache] Refreshed {refreshed}/{len(keys)} entries")
    return {"refreshed": refreshed, "total_keys": len(keys)}


# ===========================================================================
# Modal entrypoint
# ===========================================================================


@app.function()
@modal.concurrent(max_inputs=100)
@modal.asgi_app(requires_proxy_auth=IS_PROD)
def pull():
    return web_app
