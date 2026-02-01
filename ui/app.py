"""
Docpull UI - Lightweight Modal app for managing documentation scraping.

Separate from the main scraper API (no Playwright needed).
Calls the scraper API via HTTP.
"""

import os
from pathlib import Path

import modal
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# Check .env exists before attempting deployment
_local_env = Path(__file__).parent.parent / ".env"
if not _local_env.exists():
    raise RuntimeError(
        "\n" + "=" * 70 + "\n"
        "ERROR: .env file not found!\n\n"
        "Run 'python setup.py' to deploy the API and generate .env,\n"
        "then deploy the UI.\n"
        + "=" * 70
    )

# Lightweight image - FastAPI + httpx + dotenv (loads .env in Modal)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install("fastapi[standard]", "httpx", "python-dotenv")
    .add_local_file("ui/ui.html", "/root/ui.html")
    .add_local_file(".env", "/root/.env")
)

# Load .env inside Modal container
from dotenv import load_dotenv
load_dotenv("/root/.env")

# Get config from environment
SCRAPER_API_URL = os.environ.get("SCRAPER_API_URL")
IS_PROD = os.environ.get("IS_PROD", "false").lower() in ("true", "1", "yes")

app = modal.App("docpull", image=image)


def get_scraper_api_url():
    """Get scraper API URL from environment."""
    return SCRAPER_API_URL

web_app = FastAPI(title="Docpull UI")


# --- Request Models ---
class DiscoverRequest(BaseModel):
    url: str


class BulkRequest(BaseModel):
    urls: list[str]


class ExportRequest(BaseModel):
    urls: list[str]
    cached_only: bool = True


class AddSiteRequest(BaseModel):
    site_id: str
    config: dict


class LinksRequest(BaseModel):
    site_id: str
    save: bool = False
    force: bool = False


class ContentRequest(BaseModel):
    site_id: str
    path: str


# --- API Proxy Helpers ---
async def call_scraper_api(
    method: str,
    path: str,
    request: Request,
    json_body: dict | None = None,
    params: dict | None = None,
) -> dict:
    """Proxy request to scraper API, forwarding auth headers."""
    import httpx

    # Forward Modal auth headers from the incoming request
    headers = {}
    if "modal-key" in request.headers:
        headers["Modal-Key"] = request.headers["modal-key"]
    if "modal-secret" in request.headers:
        headers["Modal-Secret"] = request.headers["modal-secret"]

    url = f"{get_scraper_api_url()}{path}"

    async with httpx.AsyncClient(timeout=120.0) as client:
        if method == "GET":
            resp = await client.get(url, headers=headers, params=params)
        elif method == "POST":
            resp = await client.post(url, headers=headers, json=json_body, params=params)
        elif method == "DELETE":
            resp = await client.delete(url, headers=headers, params=params)
        else:
            raise ValueError(f"Unsupported method: {method}")

        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)

        return resp.json()


# --- UI HTML ---
# Read HTML from file (copied into image at build time)
_HTML_FILE = Path("/root/ui.html")
if _HTML_FILE.exists():
    HTML_CONTENT = _HTML_FILE.read_text()
else:
    # Fallback for local development
    HTML_CONTENT = (Path(__file__).parent / "ui.html").read_text()


# --- Routes ---
@web_app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """Serve the UI."""
    return HTML_CONTENT


@web_app.get("/api/sites")
async def list_sites(request: Request):
    """List configured sites."""
    return await call_scraper_api("GET", "/sites", request)


@web_app.get("/api/sites/{site_id}/links")
async def get_links(site_id: str, request: Request):
    """Get links for a site."""
    return await call_scraper_api("GET", f"/sites/{site_id}/links", request)


@web_app.get("/api/sites/{site_id}/content")
async def get_content(site_id: str, path: str, request: Request):
    """Get content for a page."""
    return await call_scraper_api("GET", f"/sites/{site_id}/content", request, params={"path": path})


@web_app.get("/api/discover")
async def discover_get(url: str, request: Request):
    """Discover selectors for a URL (GET method)."""
    return await call_scraper_api("GET", "/discover", request, params={"url": url})


@web_app.post("/api/discover")
async def discover_post(req: DiscoverRequest, request: Request):
    """Discover selectors for a URL (POST method for ui.html compatibility).

    Returns CLI-style output format for compatibility with ui.html.
    """
    try:
        data = await call_scraper_api("GET", "/discover", request, params={"url": req.url})
    except HTTPException as e:
        return {"success": False, "stdout": "", "stderr": str(e.detail)}

    # Format as CLI-style output that ui.html expects
    framework = data.get("framework", "unknown")
    base_url = data.get("base_url_suggestion", req.url)
    copy_buttons = data.get("copy_buttons", [])
    content_selectors = data.get("content_selectors", [])
    link_analysis = data.get("link_analysis", {})

    output_lines = [
        "=" * 70,
        f"DISCOVERY RESULTS FOR: {req.url}",
        "=" * 70,
        f"\nFramework Detected: {framework.upper()}",
        f"Suggested Base URL: {base_url}",
    ]

    # Copy buttons
    output_lines.append("\n" + "-" * 70)
    output_lines.append("COPY BUTTONS:")
    working = [b for b in copy_buttons if b.get("works")]
    if working:
        for btn in working:
            output_lines.append(f"  {btn['selector']} - {btn.get('chars', 0)} chars")
    else:
        output_lines.append("  No working copy buttons found")

    # Content selectors
    output_lines.append("\n" + "-" * 70)
    output_lines.append("CONTENT SELECTORS:")
    for sel in content_selectors[:5]:
        marker = "[RECOMMENDED]" if sel.get("recommended") else ""
        output_lines.append(f"  {sel['selector']} {marker}")
        output_lines.append(f"     {sel.get('text_chars', 0)} text chars")

    # Links
    output_lines.append("\n" + "-" * 70)
    output_lines.append("LINK ANALYSIS:")
    output_lines.append(f"  Total internal links: {link_analysis.get('total_internal_links', 0)}")

    # Generate suggested config
    output_lines.append("\n" + "=" * 70)
    output_lines.append("SUGGESTED CONFIGURATION:")
    output_lines.append("=" * 70)

    # Determine site_id from URL
    from urllib.parse import urlparse
    parsed = urlparse(req.url)
    site_id = parsed.hostname.replace(".", "-").replace("docs-", "").replace("www-", "")

    # Build config
    content_method = "inner_html"
    content_selector = "main"
    if working:
        content_method = "click_copy"
        content_selector = working[0]["selector"]
    elif content_selectors:
        content_selector = content_selectors[0]["selector"]

    config = {
        "name": site_id,
        "baseUrl": base_url,
        "mode": "browser",
        "links": {"startUrls": [""], "pattern": ""},
        "content": {
            "mode": "browser",
            "selector": content_selector,
            "method": content_method
        }
    }

    import json
    output_lines.append(f'\n"{site_id}": {json.dumps(config, indent=2)}')
    output_lines.append("\n" + "=" * 70)

    return {
        "success": True,
        "stdout": "\n".join(output_lines),
        "stderr": ""
    }


@web_app.post("/api/add-site")
async def add_site(req: AddSiteRequest):
    """Add site to config - not supported in deployed Modal UI."""
    raise HTTPException(
        status_code=501,
        detail="Adding sites is not supported in deployed UI. Use local ui-server.py instead."
    )


@web_app.post("/api/links")
async def get_links_post(req: LinksRequest, request: Request):
    """Get links for a site (POST method for ui.html compatibility)."""
    params = {}
    if req.force:
        params["max_age"] = 0
    result = await call_scraper_api("GET", f"/sites/{req.site_id}/links", request, params=params)
    # Wrap in format expected by ui.html
    return {
        "success": True,
        "stdout": "\n".join(result.get("links", [])) + f"\n\nTotal: {result.get('count', 0)} links",
        "stderr": ""
    }


@web_app.post("/api/content")
async def get_content_post(req: ContentRequest, request: Request):
    """Get content for a page (POST method for ui.html compatibility)."""
    result = await call_scraper_api(
        "GET", f"/sites/{req.site_id}/content", request, params={"path": req.path}
    )
    # Wrap in format expected by ui.html
    content = result.get("content", "")
    return {
        "success": True,
        "stdout": f"Content ({len(content)} chars):\n\n{content[:2000]}{'...' if len(content) > 2000 else ''}",
        "stderr": ""
    }


@web_app.post("/api/jobs/bulk")
async def submit_bulk(req: BulkRequest, request: Request):
    """Submit a bulk scrape job."""
    return await call_scraper_api("POST", "/jobs/bulk", request, json_body={"urls": req.urls})


@web_app.get("/api/jobs/{job_id}")
async def get_job(job_id: str, request: Request):
    """Get job status."""
    return await call_scraper_api("GET", f"/jobs/{job_id}", request)


@web_app.get("/api/jobs")
async def list_jobs(request: Request):
    """List recent jobs."""
    return await call_scraper_api("GET", "/jobs", request)


@web_app.get("/api/cache/keys")
async def cache_keys(request: Request, site_id: str | None = None):
    """Get cached URLs."""
    params = {"content_only": "true"}
    if site_id:
        params["site_id"] = site_id
    return await call_scraper_api("GET", "/cache/keys", request, params=params)


@web_app.post("/api/export")
async def export_urls(req: ExportRequest, request: Request):
    """Export URLs as ZIP file."""
    import base64
    import httpx

    # Forward Modal auth headers from the incoming request
    headers = {}
    if "modal-key" in request.headers:
        headers["Modal-Key"] = request.headers["modal-key"]
    if "modal-secret" in request.headers:
        headers["Modal-Secret"] = request.headers["modal-secret"]

    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            resp = await client.post(
                f"{get_scraper_api_url()}/export/zip",
                json={
                    "urls": req.urls,
                    "cached_only": req.cached_only,
                    "include_manifest": True,
                },
                headers=headers,
            )
            resp.raise_for_status()

            # Extract stats from headers
            stats = {
                "total": resp.headers.get("X-Export-Total", "?"),
                "ok": resp.headers.get("X-Export-Ok", "?"),
                "cached": resp.headers.get("X-Export-Cached", "?"),
                "scraped": resp.headers.get("X-Export-Scraped", "?"),
                "miss": resp.headers.get("X-Export-Miss", "?"),
                "error": resp.headers.get("X-Export-Error", "?"),
            }

            # Return ZIP as base64 for frontend download
            zip_b64 = base64.b64encode(resp.content).decode("utf-8")

            return {
                "success": True,
                "zip_base64": zip_b64,
                "filename": "docs_export.zip",
                "size": len(resp.content),
                "stats": stats,
            }

    except httpx.HTTPStatusError as e:
        error_detail = str(e)
        try:
            error_detail = e.response.json().get("detail", str(e))
        except Exception:
            pass
        raise HTTPException(status_code=e.response.status_code, detail=f"API error: {error_detail}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Export timed out")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Failed to connect to API: {e}")


# --- Modal Entrypoint ---
@app.function()
@modal.asgi_app(requires_proxy_auth=IS_PROD)
def ui():
    """Serve the UI app."""
    return web_app
