# ---
# deploy: true
# ---

# Content Scraper API - Unified scraping with pluggable extraction

import asyncio
import time
from pathlib import Path

import modal
from fastapi import FastAPI
from pydantic import BaseModel

from scraper import ScrapeJob, ScrapeResult, ScrapeCache, scrape

playwright_image = modal.Image.debian_slim(python_version="3.10").run_commands(
    "apt-get update",
    "apt-get install -y software-properties-common",
    "apt-add-repository non-free",
    "apt-add-repository contrib",
    "pip install playwright==1.42.0",
    "playwright install-deps chromium",
    "playwright install chromium",
).uv_pip_install("fastapi[standard]", "pydantic").add_local_python_source("scraper")

app = modal.App("content-scraper-api", image=playwright_image)
web_app = FastAPI(title="Content Scraper API")

volume = modal.Volume.from_name("scraping-volume", create_if_missing=True)
CACHE_PATH = Path("/cache")


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
        "version": "2.1",
        "endpoints": {
            "/scrape": "POST - Scrape content from any URL",
            "/scrape/batch": "POST - Scrape multiple URLs in parallel",
            "/cache": "GET - View cache stats",
            "/health": "GET - Health check",
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


@app.function(volumes={"/cache": volume})
@modal.asgi_app(requires_proxy_auth=True)
def fastapi_app():
    return web_app
