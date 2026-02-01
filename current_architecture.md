# Current Architecture

This document describes the existing architecture of docpull before the refactor.

## Overview

Docpull currently runs as **two separate Modal apps** that communicate via HTTP:

```
┌──────────────────────────────────────────────────────────────────┐
│                         Modal Cloud                              │
│                                                                  │
│  ┌─────────────────────────────┐  ┌─────────────────────────────┐│
│  │  content-scraper-api        │  │  docpull (UI)               ││
│  │  (api/scraper.py)           │  │  (ui/app.py)                ││
│  │                             │  │                             ││
│  │  ┌───────────────────────┐  │  │  ┌───────────────────────┐  ││
│  │  │ FastAPI Server        │◄─┼──┼──│ FastAPI Proxy         │  ││
│  │  │ (playwright_image)    │  │  │  │ (lightweight image)   │  ││
│  │  └───────────┬───────────┘  │  │  └───────────────────────┘  ││
│  │              │              │  │                             ││
│  │  ┌───────────▼───────────┐  │  │  Serves: ui.html            ││
│  │  │ Scraper (modal.cls)   │  │  │  Proxies all /api/* to API  ││
│  │  │ - scrape_content      │  │  │                             ││
│  │  │ - discover_selectors  │  │  └─────────────────────────────┘│
│  │  │ - scrape_links_browser│  │                                 │
│  │  └───────────────────────┘  │                                 │
│  │                             │                                 │
│  │  ┌───────────────────────┐  │                                 │
│  │  │ SiteWorker (modal.cls)│  │                                 │
│  │  │ - process_batch       │  │                                 │
│  │  │ (bulk job processing) │  │                                 │
│  │  └───────────────────────┘  │                                 │
│  │                             │                                 │
│  │  ┌───────────────────────┐  │                                 │
│  │  │ scrape_links_fetch    │  │                                 │
│  │  │ (modal.function)      │  │                                 │
│  │  │ HTTP-only, no browser │  │                                 │
│  │  └───────────────────────┘  │                                 │
│  └─────────────────────────────┘                                 │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │                    Modal Dicts (shared state)                ││
│  │  - scraper-cache:  Content cache (7-day TTL)                 ││
│  │  - scraper-errors: Error tracking                            ││
│  │  - scraper-sites:  Runtime site configs                      ││
│  │  - scrape-jobs:    Bulk job tracking                         ││
│  └──────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────┘
```

## Files and Their Roles

### api/scraper.py (1940 lines)
The main API file containing:
- **Modal App**: `content-scraper-api`
- **Image**: Single `playwright_image` with Chromium + FastAPI + dependencies
- **FastAPI endpoints**: 30+ endpoints for sites, content, links, cache, jobs, export
- **Scraper class**: Browser lifecycle management, content/link scraping
- **SiteWorker class**: Bulk batch processing
- **scrape_links_fetch**: HTTP-based link discovery (async function)
- **Helper functions**: URL normalization, HTML parsing, caching

### ui/app.py (464 lines)
A separate UI app that:
- Uses a **lightweight image** (no Playwright, just FastAPI + httpx)
- Serves static HTML (`ui.html`)
- **Proxies all API calls** to the main API via HTTP
- Adds some formatting for CLI-style output

### api/bulk.py (88 lines)
Bulk job utilities:
- Job creation and progress tracking
- Batch calculation for parallel processing
- Uses Modal Dict for job state

### api/urls.py (104 lines)
URL utilities:
- Asset detection, URL normalization
- Path handling for cache keys

### cli/main.py (655 lines)
Typer CLI that calls the API directly via HTTP.

## Problems with Current Architecture

### 1. Wasteful Image
Every container (including the FastAPI server) uses the heavy `playwright_image`:
```python
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
    ...
)
```
This means cold starts are slower and we pay for browser installation on containers that only serve HTTP.

### 2. Duplicate FastAPI Servers
- `api/scraper.py` has a FastAPI app with all the real logic
- `ui/app.py` has a FastAPI app that just proxies to the API

This creates:
- Extra network hop for all UI requests
- Duplicate route definitions
- Authentication forwarding complexity
- Two separate deployments to manage

### 3. Tight Coupling
The `Scraper` and `SiteWorker` classes are defined in the same file as the API:
- Hard to scale workers independently
- Can't use different container sizes for API vs workers
- Browser methods are mixed with HTTP endpoint logic

### 4. No Clean Worker Separation
The browser-based scraping (`Scraper`, `SiteWorker`) and HTTP-based scraping (`scrape_links_fetch`) are in the same file but use completely different approaches:
- Browser methods need Playwright
- HTTP methods only need httpx
- Currently both are bundled together

## Current Data Flow

### Content Scraping
```
CLI/UI → POST /sites/{site_id}/content
       → FastAPI handler checks cache
       → If miss: Scraper().scrape_content.remote.aio()
       → Modal spawns new container with playwright_image
       → Browser navigates, extracts content
       → Returns to handler, handler caches and returns
```

### Bulk Job Processing
```
CLI/UI → POST /jobs/bulk
       → Handler groups URLs by site
       → Creates job in Modal Dict
       → Spawns SiteWorker.process_batch.spawn() for each batch
       → Returns job_id immediately (fire-and-forget)
       → Workers update job progress in Modal Dict
       → CLI polls GET /jobs/{job_id} to watch
```

### Link Discovery
```
CLI/UI → GET /sites/{site_id}/links
       → Handler checks site mode (browser vs fetch)
       → If browser: Scraper().scrape_links_browser.remote.aio()
       → If fetch: scrape_links_fetch.remote.aio()
       → Returns links to handler
```

## Configuration

### sites.json
Static site configurations embedded in the image at build time.

### Modal Dicts
Runtime state stored in Modal's distributed key-value store:
- `scraper-cache`: Persisted content cache
- `scraper-sites`: Runtime site config overrides
- `scraper-errors`: Track failing URLs to avoid retries
- `scrape-jobs`: Bulk job status

### Environment (.env)
Generated by `deploy.py`:
- `SCRAPER_API_URL`: API endpoint for UI/CLI
- `IS_PROD`: Enable Modal proxy auth

## Deployment

Currently requires two separate deploys:
```bash
modal deploy api/scraper.py   # Deploy API first (generates URL)
modal deploy ui/app.py        # Deploy UI (needs API URL in .env)
```

The `deploy.py` script automates this:
1. Deploy API → capture URL
2. Write URL to `.env`
3. Deploy UI (reads `.env` into image)
