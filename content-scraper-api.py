# ---
# deploy: true
# ---

# Content Scraper API - Stateless scraping with Convex storage

import modal
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from scraper import ScrapeJob, ScrapeResult, scrape

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


class ScrapeRequest(BaseModel):
    url: str
    selector: str
    method: str = "click_copy"


class TaskResponse(BaseModel):
    task_id: str
    site_id: str
    page: str


# --- Spawnable scrape task ---


@app.function(timeout=300)
async def scrape_and_save(site_id: str, page: str) -> dict:
    """
    Scrape a page using Convex site config and save result to Convex.
    
    This is the main workhorse - can be called directly or spawned for background processing.
    
    Usage:
        # Direct call (blocking)
        result = scrape_and_save.remote(site_id="modal", page="volumes")
        
        # Spawn (non-blocking)
        call = scrape_and_save.spawn(site_id="modal", page="volumes")
        result = call.get()  # Get result later
    """
    import requests

    # 1. Get site config from Convex
    resp = requests.get(f"{CONVEX_API}/sites/{site_id}")
    if resp.status_code != 200:
        return {"success": False, "error": f"Site not found: {site_id}"}
    
    site = resp.json()
    
    # 2. Build URL and scrape
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
    
    # 3. Save to Convex
    content = "\n".join(str(e) for e in result.entries) if result.entries else ""
    
    save_resp = requests.post(
        f"{CONVEX_API}/sites/{site_id}/docs/save",
        json={"siteId": site_id, "page": page, "url": url, "markdown": content},
    )
    
    if save_resp.status_code != 200:
        return {"success": False, "error": f"Failed to save: {save_resp.text}", "url": url}
    
    return {
        "success": True,
        "site_id": site_id,
        "page": page,
        "url": url,
        "content_length": len(content),
        "content_hash": save_resp.json().get("contentHash"),
    }


# --- API Endpoints ---


@web_app.get("/")
async def root():
    return {
        "name": "Content Scraper API",
        "version": "3.0",
        "convex_api": CONVEX_API,
        "endpoints": {
            "/scrape": "POST - Scrape any URL (stateless)",
            "/scrape/{site_id}/{page}": "POST - Scrape page & save to Convex",
            "/scrape/{site_id}/{page}/spawn": "POST - Spawn background scrape task",
            "/scrape/{site_id}": "POST - Scrape all pages for a site",
            "/task/{task_id}": "GET - Check task status",
            "/health": "GET - Health check",
        },
    }


@web_app.get("/health")
async def health():
    return {"status": "healthy"}


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
    """Scrape a page and save to Convex (blocking)."""
    result = await scrape_and_save.local(site_id, page)
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result.get("error"))
    return result


@web_app.post("/scrape/{site_id}/{page}/spawn", response_model=TaskResponse)
async def spawn_scrape(site_id: str, page: str):
    """Spawn a background scrape task. Returns task_id for polling."""
    call = scrape_and_save.spawn(site_id, page)
    return TaskResponse(task_id=call.object_id, site_id=site_id, page=page)


@web_app.post("/scrape/{site_id}")
async def scrape_site(site_id: str, pages: list[str] = Query(default=None)):
    """Scrape all (or specified) pages for a site."""
    import requests
    
    # Get site config
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
        result = call.get(timeout=0)  # Non-blocking check
        return {"status": "completed", "result": result}
    except TimeoutError:
        return {"status": "running", "task_id": task_id}
    except Exception as e:
        return {"status": "failed", "error": str(e)}


@app.function()
@modal.asgi_app(requires_proxy_auth=True)
def fastapi_app():
    return web_app
