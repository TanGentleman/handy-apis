# Architecture (Proposed Refactor)

This document describes the new architecture: a single FastAPI server with a separate Playwright worker image.

## Overview

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              Modal Cloud                                 │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐  │
│  │                    docpull-api (single Modal app)                  │  │
│  │                                                                    │  │
│  │  ┌──────────────────────────┐    ┌──────────────────────────────┐  │  │
│  │  │   FastAPI Server         │    │   PlaywrightWorker           │  │  │
│  │  │   (api_image)            │    │   (playwright_image)         │  │  │
│  │  │                          │    │                              │  │  │
│  │  │   - All HTTP endpoints   │    │   - scrape_content()         │  │  │
│  │  │   - Static UI serving    │───▶│   - scrape_links()           │  │  │
│  │  │   - Cache management     │    │   - discover_selectors()     │  │  │
│  │  │   - Job orchestration    │    │   - process_batch()          │  │  │
│  │  │   - HTTP link discovery  │    │                              │  │  │
│  │  │                          │    │   Browser lifecycle:         │  │  │
│  │  │   Lightweight:           │    │   @enter: launch browser     │  │  │
│  │  │   - No Playwright        │    │   @exit: close browser       │  │  │
│  │  │   - Fast cold starts     │    │                              │  │  │
│  │  └──────────────────────────┘    └──────────────────────────────┘  │  │
│  │                                                                    │  │
│  └────────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌────────────────────────────┐                                          │
│  │   refresh_cache.py         │  Separate scheduled script               │
│  │   (minimal_image)          │  Runs every 6 days to prevent            │
│  │   @modal.schedule          │  Modal Dict expiration                   │
│  └────────────────────────────┘                                          │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐│
│  │                    Modal Dicts (shared state)                        ││
│  │  - scraper-cache:  Content cache (7-day TTL)                         ││
│  │  - scraper-errors: Error tracking                                    ││
│  │  - scraper-sites:  Runtime site configs                              ││
│  │  - scrape-jobs:    Bulk job tracking                                 ││
│  └──────────────────────────────────────────────────────────────────────┘│
└──────────────────────────────────────────────────────────────────────────┘
```

## File Structure (After Refactor)

```
docpull/
├── api/
│   ├── server.py           # FastAPI app + all endpoints (renamed from scraper.py)
│   ├── worker.py           # PlaywrightWorker class (NEW)
│   ├── bulk.py             # Bulk job utilities (unchanged)
│   └── urls.py             # URL utilities (unchanged)
├── cli/main.py             # Typer CLI (unchanged)
├── config/
│   ├── sites.json          # Site definitions
│   └── utils.py            # Env loading
├── ui/
│   └── ui.html             # Static UI (served by FastAPI)
├── scripts/
│   └── refresh_cache.py    # Scheduled cache refresh (NEW)
├── deploy.py               # Deploy script (simplified)
└── teardown.py             # Stop deployments
```

## Components

### 1. FastAPI Server (`api/server.py`)

**Image**: Lightweight, no Playwright
```python
api_image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi[standard]",
        "pydantic",
        "httpx",
        "markdownify",
    )
    .add_local_file("config/sites.json", "/app/sites.json")
    .add_local_file("ui/ui.html", "/app/ui.html")
)
```

**Responsibilities**:
- All HTTP endpoints (sites, content, links, cache, jobs, export)
- Static UI serving (`/` serves ui.html, `/api/*` for API routes)
- Cache management (read/write Modal Dicts)
- Job orchestration (create jobs, track progress)
- HTTP-based link discovery (`scrape_links_fetch` runs inline)
- Dispatching work to PlaywrightWorker

**Concurrency**: `@modal.concurrent(max_inputs=100)`

### 2. PlaywrightWorker (`api/worker.py`)

**Image**: Heavy, with Chromium
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
    .pip_install("markdownify", "httpx")
)
```

**Class Definition**:
```python
@app.cls(
    image=playwright_image,
    container_idle_timeout=300,
    timeout=120,
)
class PlaywrightWorker:
    @modal.enter()
    def setup(self):
        """Launch browser on container start."""
        from playwright.sync_api import sync_playwright
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch()

    @modal.exit()
    def cleanup(self):
        """Close browser on container stop."""
        self.browser.close()
        self.playwright.stop()

    @modal.method()
    def scrape_content(self, site_id: str, path: str, config: dict) -> dict:
        """Scrape content from a single page.

        Returns:
            {"content": str, "metadata": dict}  on success
            {"error": str, "code": str}         on failure
        """
        ...

    @modal.method()
    def scrape_links(self, site_id: str, config: dict) -> dict:
        """Browser-based link discovery (for JS-rendered pages).

        Returns:
            {"content": list[str], "metadata": dict}  on success
            {"error": str, "code": str}               on failure
        """
        ...

    @modal.method()
    def discover_selectors(self, url: str) -> dict:
        """Analyze page structure for site configuration.

        Returns:
            {"content": dict, "metadata": dict}  on success
            {"error": str, "code": str}          on failure
        """
        ...

    @modal.method()
    def process_batch(self, job_id: str, site_id: str, paths: list[str], config: dict, batch_size: int = 25) -> dict:
        """Process a batch of pages for bulk jobs.

        Returns:
            {"content": list[dict], "metadata": dict}  on success
            {"error": str, "code": str}                on failure
        """
        ...
```

**Key Design Decisions**:
- Single class keeps browser lifecycle simple
- Methods receive full `config` dict (entire site configuration) to avoid coupling to sites.json
- All methods return `dict`: either `{"content": ..., "metadata": ...}` on success or `{"error": "message", "code": "..."}` on failure
- Workers never write to cache — they return data, and the server handles all cache writes
- `process_batch` accepts a configurable `batch_size` parameter (default: 25)

### 3. Cache Refresh Script (`scripts/refresh_cache.py`)

**Image**: Minimal
```python
minimal_image = modal.Image.debian_slim(python_version="3.11")

@app.function(image=minimal_image, schedule=modal.Period(days=6))
def refresh_cache():
    """Touch Modal Dicts to prevent 7-day expiration."""
    cache = modal.Dict.from_name("scraper-cache", create_if_missing=True)
    # Read a key to refresh TTL
    try:
        _ = cache.get("__heartbeat__")
    except KeyError:
        pass
    cache["__heartbeat__"] = datetime.now().isoformat()
```

## Data Flow

### Content Scraping (Cache Miss)
```
CLI/UI
   │
   ▼
┌─────────────────────────────────────────────────────┐
│  FastAPI Server                                     │
│  POST /sites/{site_id}/content                      │
│                                                     │
│  1. Validate site_id, get config from sites.json   │
│  2. Check cache (Modal Dict)                        │
│  3. If miss: call PlaywrightWorker                  │
│     result = PlaywrightWorker().scrape_content      │
│               .remote.aio(site_id, path, config)    │
│  4. Cache result                                    │
│  5. Return content                                  │
└──────────────────────┬──────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────┐
│  PlaywrightWorker (separate container)              │
│                                                     │
│  1. Browser navigates to URL                        │
│  2. Wait for content selector                       │
│  3. Extract content (click_copy or inner_html)      │
│  4. Convert to markdown                             │
│  5. Return {content, metadata}                      │
└─────────────────────────────────────────────────────┘
```

### Link Discovery (HTTP Mode)
```
CLI/UI
   │
   ▼
┌─────────────────────────────────────────────────────┐
│  FastAPI Server                                     │
│  GET /sites/{site_id}/links                         │
│                                                     │
│  1. Get site config                                 │
│  2. If mode == "fetch":                             │
│     - Run scrape_links_fetch() INLINE (no .remote)  │
│     - Uses httpx, no browser needed                 │
│  3. If mode == "browser":                           │
│     - Call PlaywrightWorker().scrape_links.remote() │
│  4. Return links                                    │
└─────────────────────────────────────────────────────┘
```

### Bulk Job Processing
```
CLI/UI
   │
   ▼
┌─────────────────────────────────────────────────────┐
│  FastAPI Server                                     │
│  POST /jobs/bulk  (optional: batch_size)            │
│                                                     │
│  1. Parse URLs, group by site                       │
│  2. Filter cached URLs (only scrape misses)         │
│  3. Create job record in Modal Dict                 │
│  4. Split uncached paths into chunks of batch_size  │
│     (default: 25)                                   │
│  5. For each chunk:                                 │
│     PlaywrightWorker().process_batch.spawn(         │
│         job_id, site_id, paths, config, batch_size  │
│     )                                               │
│  6. Return job_id immediately (fire-and-forget)     │
└─────────────────────────────────────────────────────┘
                       │
                       │ (async, parallel)
                       ▼
┌─────────────────────────────────────────────────────┐
│  PlaywrightWorker.process_batch (multiple workers)  │
│                                                     │
│  1. For each path in batch:                         │
│     - Scrape content                                │
│     - Return {content, metadata} or {error, code}   │
│  2. Return all batch results to server              │
└─────────────────────────────────────────────────────┘
                       │
                       │ (results returned to server)
                       ▼
┌─────────────────────────────────────────────────────┐
│  FastAPI Server (cache write)                       │
│                                                     │
│  1. Receive batch results from worker               │
│  2. Write successful results to Modal Dict cache    │
│  3. Log errors from error dicts                     │
│  4. Update job progress in Modal Dict               │
└─────────────────────────────────────────────────────┘
```

## API Changes

### Merged Endpoints (from ui/app.py)
The UI proxy routes become direct routes:
- `GET /` → Serve ui.html
- `GET /api/*` → Handled directly (no proxy hop)

### Unchanged Endpoints
All existing API endpoints remain the same, with the following additions:
- `GET /sites` - List sites
- `GET /sites/{site_id}/links` - Get links
- `GET /sites/{site_id}/content` - Get content
- `POST /sites/{site_id}/index` - Index entire site (optional `batch_size`, default: 25)
- `GET /sites/{site_id}/download` - Download as ZIP
- `POST /export/zip` - Export URLs as ZIP
- `POST /jobs/bulk` - Submit bulk job (optional `batch_size`, default: 25)
- `GET /jobs/{job_id}` - Job status
- `GET /jobs` - List jobs
- `GET /cache/stats` - Cache stats
- `GET /cache/keys` - List cached URLs
- `DELETE /cache/{site_id}` - Clear cache
- `GET /discover` - Discover selectors

### Internal Changes
- `scrape_links_fetch()` runs inline (not as `.remote()`) since it doesn't need Playwright
- PlaywrightWorker methods receive config dict instead of reading sites.json

## Benefits of New Architecture

### 1. Faster Cold Starts
- API server uses lightweight image (~200MB vs ~1.5GB)
- Most requests never need Playwright
- Only browser work spawns heavy containers

### 2. Single Deployment
- One `modal deploy` command
- No coordination between apps
- No inter-service HTTP calls

### 3. Better Resource Usage
- API containers: small, fast, cheap
- Worker containers: large, only when needed
- Independent scaling for API vs workers

### 4. Simpler Code Organization
- Clear separation: server.py (HTTP) vs worker.py (browser)
- No duplicate routes
- No proxy complexity

### 5. Easier Testing
- Can test API without browser
- Can test worker in isolation
- Mock PlaywrightWorker for API tests

## Migration Path

### Phase 1: Extract Worker
1. Create `api/worker.py` with PlaywrightWorker class
2. Move browser logic from scraper.py
3. Keep scraper.py working, import from worker.py

### Phase 2: Merge UI
1. Add static file serving to FastAPI
2. Remove proxy routes from ui/app.py
3. Delete ui/app.py

### Phase 3: Refactor Server
1. Rename scraper.py → server.py
2. Remove Playwright from api_image
3. Update all imports

### Phase 4: Extract Refresh Script
1. Create scripts/refresh_cache.py
2. Remove @modal.schedule from main app
3. Deploy as separate function

### Phase 5: Update Deploy
1. Simplify deploy.py (single app)
2. Update teardown.py
3. Test full flow

## Design Decisions

The following decisions were made during architecture planning and are reflected throughout this document.

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Cache writes** | Server caches | Workers return data; the FastAPI server handles all writes to Modal Dict. Keeps workers stateless and simplifies cache logic. |
| **Error handling** | Return error dicts | All worker methods return `{"error": "message", "code": "..."}` on failure instead of raising exceptions. Allows the server to handle errors uniformly and log/retry without catching scattered exceptions. |
| **Config passing** | Full config dict | Workers receive the entire site config dict. Avoids coupling workers to `sites.json` and keeps the worker interface stable as config fields evolve. |
| **Batch size** | Configurable | `POST /jobs/bulk` and `POST /sites/{id}/index` accept an optional `batch_size` parameter (default: 25). Allows tuning throughput vs. per-container memory for different sites. |
| **Migration phases** | 5-phase approach | The migration path above follows the documented 5 phases (extract worker → merge UI → refactor server → extract refresh script → update deploy). Each phase keeps the app in a working state. |
