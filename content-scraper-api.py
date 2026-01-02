# ---
# deploy: true
# ---

# Content Scraper API - Unified scraping with pluggable extraction

import asyncio
import time
from pathlib import Path

import modal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from scraper import ScrapeJob, ScrapeResult, ScrapeCache, DocsCache, CollectionManager, scrape, get_links

playwright_image = modal.Image.debian_slim(python_version="3.10").run_commands(
    "apt-get update",
    "apt-get install -y software-properties-common",
    "apt-add-repository non-free",
    "apt-add-repository contrib",
    "pip install playwright==1.42.0",
    "playwright install-deps chromium",
    "playwright install chromium",
).uv_pip_install("fastapi[standard]", "pydantic").add_local_python_source("scraper").add_local_file("selectors.json", "/app/selectors.json")

app = modal.App("content-scraper-api", image=playwright_image)
web_app = FastAPI(title="Content Scraper API")

volume = modal.Volume.from_name("scraping-volume", create_if_missing=True)
CACHE_PATH = Path("/cache")
CONFIG_PATH = Path("/app/selectors.json")

class ScrapeRequest(BaseModel):
    url: str
    selector: str
    method: str = "click_copy"
    use_cache: bool = True


class BatchScrapeRequest(BaseModel):
    requests: list[ScrapeRequest]
    use_cache: bool = True


class ScrapeResponse(BaseModel):
    success: bool
    content: str
    content_length: int
    url: str
    cached: bool = False
    processing_time_seconds: float
    error: str | None = None


class BatchScrapeResponse(BaseModel):
    results: list[ScrapeResponse]
    total: int
    successful: int
    failed: int
    cached: int
    total_processing_time_seconds: float


def result_to_response(result: ScrapeResult, processing_time: float) -> ScrapeResponse:
    """Convert ScrapeResult to API response format."""
    content = "\n".join(str(e) for e in result.entries) if result.entries else ""
    return ScrapeResponse(
        success=result.success,
        content=content,
        content_length=len(content),
        url=result.url,
        cached=result.cached,
        processing_time_seconds=processing_time,
        error=result.error,
    )


@web_app.get("/")
async def root():
    return {
        "name": "Content Scraper API",
        "version": "2.2",
        "endpoints": {
            "/scrape": "POST - Scrape content from any URL",
            "/scrape/batch": "POST - Scrape multiple URLs in parallel",
            "/cache": "GET - View cache stats",
            "/health": "GET - Health check",
            "/sites": "GET - List configured documentation sites",
            "/docs/{site}": "GET - List cached pages for a site",
            "/docs/{site}/{page}": "GET - Get cached documentation page",
            "/docs/{site}/{page}/refresh": "POST - Scrape/refresh a documentation page",
        },
        "methods": ["click_copy", "text_content", "inner_html"],
    }


@web_app.get("/health")
async def health():
    return {"status": "healthy"}


@web_app.get("/cache")
async def cache_stats():
    """Get cache statistics."""
    cache = ScrapeCache(CACHE_PATH)
    return cache.stats()


@web_app.post("/scrape", response_model=ScrapeResponse)
async def scrape_content(request: ScrapeRequest):
    """Scrape a single URL."""
    start_time = time.time()

    cache = ScrapeCache(CACHE_PATH) if request.use_cache else None

    job = ScrapeJob(
        name="single",
        url=request.url,
        selector=request.selector,
        method=request.method,
        use_cache=request.use_cache,
    )
    result = await scrape(job, cache=cache)

    if cache and not result.cached:
        volume.commit()

    return result_to_response(result, time.time() - start_time)


@web_app.post("/scrape/batch", response_model=BatchScrapeResponse)
async def scrape_batch_endpoint(batch: BatchScrapeRequest):
    """Scrape multiple URLs in parallel."""
    start_time = time.time()

    cache = ScrapeCache(CACHE_PATH) if batch.use_cache else None

    jobs = [
        ScrapeJob(
            name=f"batch_{i}",
            url=req.url,
            selector=req.selector,
            method=req.method,
            use_cache=batch.use_cache,
        )
        for i, req in enumerate(batch.requests)
    ]

    job_times = {}

    async def timed_scrape(job: ScrapeJob) -> ScrapeResult:
        job_start = time.time()
        result = await scrape(job, cache=cache)
        job_times[job.name] = time.time() - job_start
        return result

    results = await asyncio.gather(*[timed_scrape(job) for job in jobs])

    if cache and any(not r.cached for r in results):
        volume.commit()

    responses = [
        result_to_response(result, job_times.get(result.job_name, 0))
        for result in results
    ]

    return BatchScrapeResponse(
        results=responses,
        total=len(responses),
        successful=sum(1 for r in responses if r.success),
        failed=sum(1 for r in responses if not r.success),
        cached=sum(1 for r in responses if r.cached),
        total_processing_time_seconds=time.time() - start_time,
    )

@web_app.post("/get_docs_links", response_model=dict)
async def get_docs_links(request_dict: dict):
    url = request_dict.get("url")
    if not url:
        raise HTTPException(status_code=400, detail="URL is required")
    links = get_links(url)
    docs_links = [link for link in links if "docs" in link]
    return {"links": docs_links}


# --- Documentation Collection Endpoints ---

@web_app.get("/sites")
async def list_sites():
    """List all configured documentation sites."""
    manager = CollectionManager(CONFIG_PATH)
    sites = {}
    for site_id in manager.list_sites():
        site = manager.get_site(site_id)
        sites[site_id] = {
            "name": site.name,
            "base_url": site.base_url,
            "sections": site.sections,
            "pages": list(site.pages.keys()),
        }
    return {"sites": sites}


@web_app.get("/docs/{site}")
async def list_site_docs(site: str):
    """List cached pages for a site and available pages from config."""
    manager = CollectionManager(CONFIG_PATH)
    docs_cache = DocsCache(CACHE_PATH)

    try:
        site_config = manager.get_site(site)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    cached_pages = docs_cache.list_pages(site)
    configured_pages = list(site_config.pages.keys())

    return {
        "site": site,
        "name": site_config.name,
        "cached_pages": cached_pages,
        "configured_pages": configured_pages,
        "cache_stats": docs_cache.stats(),
    }


@web_app.get("/docs/{site}/{page}")
async def get_doc(site: str, page: str):
    """Get cached documentation content for a site/page."""
    docs_cache = DocsCache(CACHE_PATH)

    content = docs_cache.get_content(site, page)
    if content is None:
        raise HTTPException(
            status_code=404,
            detail=f"Page '{page}' not cached for site '{site}'. Use POST /docs/{site}/{page}/refresh to scrape it.",
        )

    metadata = docs_cache.get(site, page)
    return {
        "site": site,
        "page": page,
        "content": content,
        "content_length": len(content),
        "scraped_at": metadata.scraped_at.isoformat() if metadata else None,
    }


@web_app.post("/docs/{site}/{page}/refresh")
async def refresh_doc(site: str, page: str):
    """Scrape/refresh documentation for a site/page using selectors.json config."""
    manager = CollectionManager(CONFIG_PATH)
    docs_cache = DocsCache(CACHE_PATH)

    try:
        job = manager.create_job(site, page, use_cache=False)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    start_time = time.time()
    result = await scrape(job)

    if not result.success:
        raise HTTPException(status_code=500, detail=result.error or "Scraping failed")

    content = "\n".join(str(e) for e in result.entries) if result.entries else ""
    docs_cache.save(site, page, job.url, content)
    volume.commit()

    return {
        "site": site,
        "page": page,
        "url": job.url,
        "content_length": len(content),
        "processing_time_seconds": time.time() - start_time,
    }


@app.function(volumes={"/cache": volume})
@modal.asgi_app(requires_proxy_auth=True)
def fastapi_app():
    return web_app
