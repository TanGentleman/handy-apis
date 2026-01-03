# ---
# deploy: true
# ---

# Convex Data Store API - Simple API for interacting with Convex backend

import hashlib
import os
from typing import Any

import modal
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx

# Modal setup
image = modal.Image.debian_slim(python_version="3.12").uv_pip_install(
    "fastapi[standard]", "pydantic", "httpx"
)

app = modal.App("convex-api", image=image)
web_app = FastAPI(title="Convex Data Store API")

# Convex configuration
def get_convex_url() -> str:
    if not os.environ.get("CONVEX_URL"):
        raise ValueError("CONVEX_URL environment variable is required")
    return os.environ["CONVEX_URL"]

# Request/Response Models

class SiteConfig(BaseModel):
    """Site configuration."""
    siteId: str
    name: str
    baseUrl: str
    selector: str
    method: str = "click_copy"
    pages: dict[str, str]
    sections: dict[str, str] | None = None


class DocContent(BaseModel):
    """Documentation content."""
    siteId: str
    page: str
    url: str
    markdown: str


class SiteListResponse(BaseModel):
    """List of sites."""
    sites: list[dict[str, Any]]
    total: int


class DocListResponse(BaseModel):
    """List of docs for a site."""
    siteId: str
    docs: list[dict[str, Any]]
    total: int


# Helper functions

async def convex_query(function_path: str, args: dict = None) -> Any:
    """Call a Convex query function."""
    url = f"{get_convex_url()}/api/query"
    payload = {
        "path": function_path,
        "args": args or {},
        "format": "json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            raise HTTPException(status_code=500, detail=data["error"])

        return data.get("value")


async def convex_mutation(function_path: str, args: dict) -> Any:
    """Call a Convex mutation function."""
    url = f"{get_convex_url()}/api/mutation"
    payload = {
        "path": function_path,
        "args": args,
        "format": "json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

        if "error" in data:
            raise HTTPException(status_code=500, detail=data["error"])

        return data.get("value")


def calculate_content_hash(content: str) -> str:
    """Calculate SHA-256 hash of content."""
    return hashlib.sha256(content.encode()).hexdigest()


# API Endpoints

@web_app.get("/")
async def root():
    """API information."""
    return {
        "name": "Convex Data Store API",
        "version": "1.0",
        "endpoints": {
            "/sites": "GET - List all configured sites",
            "/sites/{siteId}": "GET - Get a specific site configuration",
            "/sites/create": "POST - Create or update a site configuration",
            "/sites/{siteId}/docs": "GET - List all docs for a site",
            "/sites/{siteId}/docs/{page}": "GET - Get a specific doc",
            "/sites/{siteId}/docs/save": "POST - Save/update documentation",
        },
    }


@web_app.get("/health")
async def health():
    """Health check."""
    return {"status": "healthy", "convex_url": get_convex_url()}


# --- Site Endpoints ---

@web_app.get("/sites", response_model=SiteListResponse)
async def list_sites():
    """List all configured documentation sites."""
    sites = await convex_query("sites:list")
    return SiteListResponse(sites=sites, total=len(sites))


@web_app.get("/sites/{site_id}")
async def get_site(site_id: str):
    """Get a specific site configuration."""
    site = await convex_query("sites:get", {"siteId": site_id})

    if not site:
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found")

    return site


@web_app.post("/sites/create")
async def create_site(site: SiteConfig):
    """Create or update a site configuration."""
    result = await convex_mutation(
        "sites:upsert",
        {
            "siteId": site.siteId,
            "name": site.name,
            "baseUrl": site.baseUrl,
            "selector": site.selector,
            "method": site.method,
            "pages": site.pages,
            "sections": site.sections,
        },
    )

    return {
        "siteId": site.siteId,
        "updated": result.get("updated", False),
        "id": str(result.get("id", "")),
    }


@web_app.delete("/sites/{site_id}")
async def delete_site(site_id: str):
    """Delete a site configuration."""
    result = await convex_mutation("sites:remove", {"siteId": site_id})

    if not result.get("deleted"):
        raise HTTPException(status_code=404, detail=f"Site '{site_id}' not found")

    return {"siteId": site_id, "deleted": True}


# --- Docs Endpoints ---

@web_app.get("/sites/{site_id}/docs", response_model=DocListResponse)
async def list_site_docs(site_id: str):
    """List all docs for a site."""
    docs = await convex_query("docs:listBySite", {"siteId": site_id})
    return DocListResponse(siteId=site_id, docs=docs, total=len(docs))


@web_app.get("/sites/{site_id}/docs/{page}")
async def get_doc(site_id: str, page: str):
    """Get a specific documentation page."""
    doc = await convex_query("docs:get", {"siteId": site_id, "page": page})

    if not doc:
        raise HTTPException(
            status_code=404,
            detail=f"Doc '{page}' not found for site '{site_id}'",
        )

    return doc


@web_app.post("/sites/{site_id}/docs/save")
async def save_doc(site_id: str, doc: DocContent):
    """Save or update documentation content."""
    if doc.siteId != site_id:
        raise HTTPException(
            status_code=400,
            detail="siteId in path must match siteId in body",
        )

    content_hash = calculate_content_hash(doc.markdown)

    result = await convex_mutation(
        "docs:upsert",
        {
            "siteId": doc.siteId,
            "page": doc.page,
            "url": doc.url,
            "markdown": doc.markdown,
            "contentHash": content_hash,
        },
    )

    return {
        "siteId": doc.siteId,
        "page": doc.page,
        "updated": result.get("updated", False),
        "id": str(result.get("id", "")),
        "contentHash": content_hash,
        "updatedAt": result.get("updatedAt"),
    }


@web_app.delete("/sites/{site_id}/docs/{page}")
async def delete_doc(site_id: str, page: str):
    """Delete a documentation page."""
    result = await convex_mutation("docs:remove", {"siteId": site_id, "page": page})

    if not result.get("deleted"):
        raise HTTPException(
            status_code=404,
            detail=f"Doc '{page}' not found for site '{site_id}'",
        )

    return {"siteId": site_id, "page": page, "deleted": True}


# --- Additional Endpoints ---

@web_app.get("/docs/by-url")
async def get_doc_by_url(url: str):
    """Get documentation by URL."""
    doc = await convex_query("docs:getByUrl", {"url": url})

    if not doc:
        raise HTTPException(status_code=404, detail=f"Doc with URL '{url}' not found")

    return doc


@app.function(
    secrets=[modal.Secret.from_name("convex-secrets")]
)
@modal.asgi_app()
def fastapi_app():
    convex_url = get_convex_url()
    print(f"Convex backend is running at {convex_url}")
    # response = httpx.get(convex_url)
    # response.raise_for_status()
    # if not response.text.startswith("This Convex deployment is running"):
    #     print(f"Convex backend is not running at {convex_url}")
    return web_app
