# ---
# deploy: true
# ---

# Content Scraper API - Stateless scraping with Convex storage

import time

import modal
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from scraper import ScrapeJob, scrape

playwright_image = (
    modal.Image.debian_slim(python_version="3.10")
    .run_commands(
        "apt-get update",
        "apt-get install -y software-properties-common",
        "apt-add-repository non-free",
        "apt-add-repository contrib",
        "pip install playwright==1.42.0",
        "playwright install-deps chromium",
        "playwright install chromium",
    )
    .uv_pip_install("fastapi[standard]", "pydantic", "requests")
    .add_local_python_source("scraper")
)

app = modal.App("content-scraper-api", image=playwright_image)
web_app = FastAPI(title="Content Scraper API")

CONVEX_API = "https://tangentleman--convex-api-fastapi-app-dev.modal.run"
DEFAULT_MAX_AGE = 3600  # 1 hour


class ScrapeRequest(BaseModel):
    url: str
    selector: str
    method: str = "click_copy"


class TaskResponse(BaseModel):
    task_id: str
    site_id: str
    page: str


class DocResponse(BaseModel):
    site_id: str
    page: str
    url: str
    markdown: str
    content_length: int
    updated_at: int
    from_cache: bool


# --- Helper: Check doc freshness ---


def get_cached_doc(site_id: str, page: str, max_age: int) -> dict | None:
    """
    Get doc from Convex if it exists and is fresh enough.
    Returns None if doc doesn't exist or is stale.
    """
    import requests

    resp = requests.get(f"{CONVEX_API}/sites/{site_id}/docs/{page}")
    if resp.status_code != 200:
        return None

    doc = resp.json()
    updated_at = doc.get("updatedAt", 0)
    age_seconds = (time.time() * 1000 - updated_at) / 1000

    if age_seconds > max_age:
        return None

    return doc


# --- Spawnable scrape task ---


@app.function(timeout=300)
async def scrape_and_save(site_id: str, page: str) -> dict:
    """Scrape a page and save to Convex."""
    import requests

    resp = requests.get(f"{CONVEX_API}/sites/{site_id}")
    if resp.status_code != 200:
        return {"success": False, "error": f"Site not found: {site_id}"}

    site = resp.json()
    page_path = site.get("pages", {}).get(page)
    if not page_path:
        return {"success": False, "error": f"Page '{page}' not in site config"}

    url = site["baseUrl"] + page_path
    job = ScrapeJob(
        name=page,
        url=url,
        selector=site["selector"],
        method=site.get("method", "click_copy"),
    )

    result = await scrape(job)
    if not result.success:
        return {"success": False, "error": result.error, "url": url}

    content = "\n".join(str(e) for e in result.entries) if result.entries else ""

    save_resp = requests.post(
        f"{CONVEX_API}/sites/{site_id}/docs/save",
        json={"siteId": site_id, "page": page, "url": url, "markdown": content},
    )

    if save_resp.status_code != 200:
        return {"success": False, "error": f"Failed to save: {save_resp.text}"}

    save_data = save_resp.json()
    return {
        "success": True,
        "site_id": site_id,
        "page": page,
        "url": url,
        "markdown": content,
        "content_length": len(content),
        "content_hash": save_data.get("contentHash"),
        "updated_at": save_data.get("updatedAt"),
    }


# --- API Endpoints ---


@web_app.get("/")
async def root():
    return {
        "name": "Content Scraper API",
        "version": "3.1",
        "convex_api": CONVEX_API,
        "endpoints": {
            "/docs/{site_id}/{page}": "GET - Get doc (cached or fresh scrape)",
            "/docs/{site_id}/{page}/spawn": "POST - Spawn background scrape, return task_id",
            "/scrape": "POST - Scrape any URL (stateless)",
            "/scrape/{site_id}/{page}": "POST - Force scrape & save",
            "/scrape/{site_id}": "POST - Scrape all pages for a site",
            "/task/{task_id}": "GET - Check task status",
        },
    }


@web_app.get("/health")
async def health():
    return {"status": "healthy"}


@web_app.get("/docs/{site_id}/{page}")
async def get_doc(
    site_id: str,
    page: str,
    max_age: int = Query(default=DEFAULT_MAX_AGE, description="Max cache age in seconds"),
):
    """
    Get documentation. Returns cached version if fresh, otherwise scrapes.
    
    - max_age=0: Always scrape fresh
    - max_age=3600: Use cache if updated within 1 hour (default)
    - max_age=86400: Use cache if updated within 24 hours
    """
    cached = get_cached_doc(site_id, page, max_age)
    if cached:
        return DocResponse(
            site_id=site_id,
            page=page,
            url=cached["url"],
            markdown=cached["markdown"],
            content_length=len(cached["markdown"]),
            updated_at=cached["updatedAt"],
            from_cache=True,
        )

    result = await scrape_and_save.local(site_id, page)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error"))

    return DocResponse(
        site_id=site_id,
        page=page,
        url=result["url"],
        markdown=result["markdown"],
        content_length=result["content_length"],
        updated_at=result["updated_at"],
        from_cache=False,
    )


@web_app.post("/docs/{site_id}/{page}/spawn")
async def spawn_doc_refresh(
    site_id: str,
    page: str,
    max_age: int = Query(default=DEFAULT_MAX_AGE, description="Max cache age in seconds"),
):
    """
    Get doc if cached, otherwise spawn background scrape and return task_id.
    
    Returns either:
    - {"cached": true, "doc": DocResponse} if fresh cache exists
    - {"cached": false, "task": TaskResponse} if scrape was spawned
    """
    cached = get_cached_doc(site_id, page, max_age)
    if cached:
        return {
            "cached": True,
            "doc": DocResponse(
                site_id=site_id,
                page=page,
                url=cached["url"],
                markdown=cached["markdown"],
                content_length=len(cached["markdown"]),
                updated_at=cached["updatedAt"],
                from_cache=True,
            ),
        }

    call = scrape_and_save.spawn(site_id, page)
    return {
        "cached": False,
        "task": TaskResponse(task_id=call.object_id, site_id=site_id, page=page),
    }


@web_app.post("/scrape")
async def scrape_url(req: ScrapeRequest):
    """Scrape any URL (stateless, no storage)."""
    job = ScrapeJob(name="adhoc", url=req.url, selector=req.selector, method=req.method)
    result = await scrape(job)
    content = "\n".join(str(e) for e in result.entries) if result.entries else ""
    return {
        "success": result.success,
        "content": content,
        "content_length": len(content),
        "url": result.url,
        "error": result.error,
    }


@web_app.post("/scrape/{site_id}/{page}")
async def scrape_page(site_id: str, page: str):
    """Force scrape a page and save to Convex (ignores cache)."""
    result = await scrape_and_save.local(site_id, page)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result


@web_app.post("/scrape/{site_id}")
async def scrape_site(site_id: str, pages: list[str] = Query(default=None)):
    """Scrape all (or specified) pages for a site."""
    import requests

    resp = requests.get(f"{CONVEX_API}/sites/{site_id}")
    if resp.status_code != 200:
        raise HTTPException(status_code=404, detail=f"Site not found: {site_id}")

    site = resp.json()
    target_pages = pages or list(site.get("pages", {}).keys())

    results = []
    for page in target_pages:
        result = await scrape_and_save.local(site_id, page)
        results.append(result)

    return {
        "site_id": site_id,
        "results": results,
        "total": len(results),
        "successful": sum(1 for r in results if r.get("success")),
        "failed": sum(1 for r in results if not r.get("success")),
    }


@web_app.get("/task/{task_id}")
async def get_task_status(task_id: str):
    """Check status of a spawned task."""
    from modal.functions import FunctionCall

    call = FunctionCall.from_id(task_id)
    try:
        result = call.get(timeout=0)
        return {"status": "completed", "result": result}
    except TimeoutError:
        return {"status": "running", "task_id": task_id}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


@app.function()
@modal.asgi_app(requires_proxy_auth=True)
def fastapi_app():
    return web_app
