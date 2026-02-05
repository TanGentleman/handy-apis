# Architecture

## Overview

Docpull is a documentation scraper built on [Modal](https://modal.com). It scrapes documentation sites and converts them to markdown for use with LLMs.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              User Interfaces                                │
├─────────────────────┬───────────────────────┬───────────────────────────────┤
│   CLI (cli/main.py) │    Web UI (ui.html)   │       Direct API calls        │
└─────────┬───────────┴───────────┬───────────┴───────────────┬───────────────┘
          │                       │                           │
          ▼                       ▼                           ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        Modal Cloud (api/server.py)                          │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                         FastAPI Application                           │  │
│  │  • /sites/* - Site config CRUD                                        │  │
│  │  • /sites/{id}/links - Link discovery                                 │  │
│  │  • /sites/{id}/content - Content scraping                             │  │
│  │  • /jobs/* - Bulk job management                                      │  │
│  │  • /cache/* - Cache management                                        │  │
│  │  • /export/* - ZIP exports                                            │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                    │                                        │
│                    ┌───────────────┴───────────────┐                        │
│                    ▼                               ▼                        │
│  ┌──────────────────────────┐    ┌───────────────────────────────────────┐  │
│  │   HTTP Link Discovery    │    │      PlaywrightWorker (worker.py)     │  │
│  │   (inline in server.py)  │    │   • Browser-based scraping            │  │
│  │   • mode: "fetch"        │    │   • mode: "browser"                   │  │
│  └──────────────────────────┘    │   • Click-copy extraction             │  │
│                                  │   • Batch processing                  │  │
│                                  └───────────────────────────────────────┘  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │                        Modal Dicts (Persistence)                      │  │
│  │  ┌──────────────────┐ ┌──────────────────┐ ┌───────────────────────┐  │  │
│  │  │  scraper-cache   │ │  scraper-sites   │ │   scraper-errors      │  │  │
│  │  │  Content cache   │ │  Site configs    │ │   Error tracking      │  │  │
│  │  └──────────────────┘ └──────────────────┘ └───────────────────────┘  │  │
│  │  ┌──────────────────┐                                                 │  │
│  │  │   scrape-jobs    │                                                 │  │
│  │  │   Bulk job state │                                                 │  │
│  │  └──────────────────┘                                                 │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

### Content Scraping

```
Request: GET /sites/{site_id}/content?path=/guide/hello

1. Load site config from Dict (or fallback to file)
2. Check cache: cache["{site_id}:{path}"]
3. If cached & fresh → return cached content
4. Check error threshold (skip if failed 3+ times in 24h)
5. Dispatch to PlaywrightWorker.scrape_content()
6. Worker loads page, extracts content (click_copy or inner_html)
7. Cache result: cache["{site_id}:{path}"] = {content, url, timestamp}
8. Return content
```

### Link Discovery

```
Request: GET /sites/{site_id}/links

1. Load site config
2. Check cache: cache["{site_id}:links"]
3. If config.mode == "browser" → PlaywrightWorker.scrape_links()
   If config.mode == "fetch"   → scrape_links_fetch() (inline HTTP)
4. Cache links: cache["{site_id}:links"] = {links, count, timestamp}
5. Return links
```

### Bulk Jobs

```
Request: POST /jobs/bulk {urls: [...]}

1. Resolve URLs to sites using longest-prefix matching
2. Create job entry in scrape-jobs Dict
3. Calculate batches (distribute across containers)
4. Spawn workers fire-and-forget: worker.process_batch.spawn()
5. Workers write directly to cache (server can't await .spawn())
6. Workers update job progress in scrape-jobs Dict
7. Client polls GET /jobs/{job_id} for status
```

---

## Site Configuration System

### The Two Sources of Truth Problem

Site configurations exist in two places:

| Location | Description | When Updated |
|----------|-------------|--------------|
| `config/sites.json` | Static file, checked into git | Manual edit, PR/commit |
| `scraper-sites` Dict | Runtime config in Modal | Via API (`POST /sites/{id}`, UI) |

### Current Flow

```
┌─────────────────────┐                    ┌─────────────────────┐
│  config/sites.json  │                    │   scraper-sites     │
│  (Git repository)   │                    │   (Modal Dict)      │
└──────────┬──────────┘                    └──────────┬──────────┘
           │                                          │
           │  [deploy.py]                             │
           │  Bakes file into                         │
           │  Docker image                            │
           ▼                                          │
┌─────────────────────┐                              │
│  /root/sites.json   │──────────────────────────────┤
│  (In deployed image)│   load_sites_config():       │
└─────────────────────┘   1. Try Dict["_all_sites"]  │
                          2. Fallback to file        │
                          3. Populate Dict if empty  ◄┘
```

### Synchronization Commands

| Direction | Command | API Endpoint |
|-----------|---------|--------------|
| Dict → File | `docpull sync-sites` | `GET /sites/export` |
| File → Dict | `docpull reload-sites` | `POST /sites/reset` |

### The Problems

1. **Deploy overwrites runtime changes**: If you add sites via UI, then redeploy, the baked-in `sites.json` becomes the source of truth on first request (Dict is empty after fresh container).

2. **Manual sync required**: You must remember to `sync-sites` before committing and `reload-sites` after editing the file.

3. **No versioning in Dict**: Modal Dict has no history; `sites.json` in git has full history.

4. **Two-way sync is confusing**: Which direction to sync depends on where the latest changes are.

---

## Proposed: SiteConfigStore Abstraction

A cleaner approach separates concerns:

```python
# Proposed: api/sites.py

class SiteConfigStore:
    """Manages site configurations with Dict as primary store."""

    def __init__(self):
        self._dict = modal.Dict.from_name("scraper-sites", create_if_missing=True)
        self._cache: dict[str, SiteConfig] | None = None

    # --- Read operations ---
    def get(self, site_id: str) -> SiteConfig | None
    def list_all(self) -> dict[str, SiteConfig]

    # --- Write operations ---
    def put(self, site_id: str, config: SiteConfig) -> None
    def delete(self, site_id: str) -> bool

    # --- Sync operations (explicit) ---
    def export_json(self) -> dict           # Dict → JSON (for saving to file)
    def import_json(self, data: dict) -> int # JSON → Dict (replaces all)
    def import_file(self, path: str) -> int  # File → Dict
```

### Benefits

1. **Single runtime source**: Dict is always authoritative at runtime
2. **Explicit sync**: Import/export make direction clear
3. **Separation of concerns**: Storage vs. sync vs. schema validation
4. **Testable**: Can mock the Dict for unit tests

### Recommended Workflow

**Option A: Dict-primary (UI-driven)**
```
1. Add/edit sites via UI or API
2. Periodically: docpull sync-sites → git commit
3. sites.json is a backup/record, not the source
```

**Option B: File-primary (Git-driven)**
```
1. Edit sites.json locally
2. Deploy (bakes file into image)
3. On first request, Dict gets populated from file
4. Never use UI to modify sites
```

**Option C: Hybrid (current, with discipline)**
```
1. Edit sites.json for major changes → deploy
2. Use UI for quick additions → sync-sites → commit
3. Always sync-sites before deploy if UI was used
```

---

## GitHub Action for Automated Sync

To automate Dict → File sync, add `.github/workflows/sync-sites.yml`:

```yaml
name: Sync Sites Config

on:
  workflow_dispatch:  # Manual trigger
  schedule:
    - cron: '0 0 * * 0'  # Weekly on Sunday

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Fetch sites from API
        run: |
          curl -sf "${{ secrets.SCRAPER_API_URL }}/sites/export" \
            -H "X-Access-Key: ${{ secrets.ACCESS_KEY }}" \
            | jq '.' > config/sites.json

      - name: Check for changes
        id: diff
        run: |
          if git diff --quiet config/sites.json; then
            echo "changed=false" >> $GITHUB_OUTPUT
          else
            echo "changed=true" >> $GITHUB_OUTPUT
          fi

      - name: Create PR
        if: steps.diff.outputs.changed == 'true'
        uses: peter-evans/create-pull-request@v5
        with:
          commit-message: "chore: sync sites config from production"
          title: "Sync sites.json from production"
          body: |
            Automated sync of site configurations added via the UI.

            Review the changes and merge to update the repository.
          branch: sync-sites-config
```

Required secrets:
- `SCRAPER_API_URL`: Your Modal deployment URL
- `ACCESS_KEY`: API access key (if configured)

---

## Modal Dicts Reference

| Dict Name | Key Format | Value | TTL |
|-----------|------------|-------|-----|
| `scraper-cache` | `{site_id}:{path}` | `{content, url, timestamp}` | 7 days* |
| `scraper-cache` | `{site_id}:links` | `{links, count, timestamp}` | 7 days* |
| `scraper-sites` | `_all_sites` | `{site_id: config_dict, ...}` | 7 days* |
| `scraper-errors` | `{site_id}:{path}` | `{count, last_error, timestamp}` | 7 days* |
| `scrape-jobs` | `{job_id}` | `{status, progress, ...}` | 7 days* |

*Modal Dicts expire after 7 days of inactivity. The `refresh_cache()` scheduled function (runs every 6 days) touches all entries to prevent expiration.

---

## File Structure

```
docpull/
├── api/
│   ├── server.py      # FastAPI app, Modal entrypoint, inline HTTP scraping
│   ├── worker.py      # PlaywrightWorker class (browser automation)
│   ├── bulk.py        # Bulk job utilities (job creation, progress tracking)
│   └── urls.py        # URL normalization and validation
├── cli/
│   └── main.py        # Typer CLI application
├── config/
│   ├── sites.json     # Static site definitions (git-tracked)
│   └── utils.py       # Config loading (API URL, auth headers)
├── ui/
│   └── ui.html        # Single-page web UI (served by server.py)
├── deploy.py          # Deployment script (creates .env, deploys to Modal)
├── teardown.py        # Stop Modal deployments
├── .env               # Local config (API URL, access key) - gitignored
└── ARCHITECTURE.md    # This file
```

---

## Images

### api_image (lightweight)
- Base: `debian_slim`
- Packages: `fastapi`, `pydantic`, `httpx`, `markdownify`
- Includes: `api/`, `config/sites.json`, `ui/ui.html`, `.env`
- Purpose: Serve API endpoints and static UI

### playwright_image (heavyweight)
- Base: `debian_slim` + Chromium
- Packages: `playwright`, `markdownify`, `httpx`
- Includes: `api/`
- Purpose: Browser-based scraping

---

## Content Extraction Methods

### `inner_html` (default)
Extracts HTML from a CSS selector, converts to markdown.
```json
"content": {
  "selector": "main article",
  "method": "inner_html"
}
```

### `click_copy`
Clicks a "Copy page" button, reads from clipboard.
```json
"content": {
  "selector": "button[aria-label='Copy page']",
  "method": "click_copy"
}
```

### `click_copy` with sequence
For multi-step interactions (dropdowns, menus).
```json
"content": {
  "method": "click_copy",
  "clickSequence": [
    {"selector": "button[title='Copy page']", "waitAfter": 500},
    {"selector": "button:has-text('Copy as Markdown')", "waitAfter": 1000}
  ]
}
```

---

## Caching Strategy

### Cache Keys
- Content: `{site_id}:{path}` → `{content, url, timestamp}`
- Links: `{site_id}:links` → `{links, count, timestamp}`

### Cache Behavior
- Default max_age: 7 days (`DEFAULT_MAX_AGE = 604800`)
- Force refresh: `?max_age=0`
- Links cached only if count > 1

### Error Tracking
- Key: `{site_id}:{path}`
- Threshold: 3 failures within 24 hours → skip
- Force clears error tracking: `?max_age=0`

---

## Authentication

When `ACCESS_KEY` is set in `.env`:

| Endpoint | Requires Key |
|----------|--------------|
| `DELETE /cache/*` | Yes |
| `DELETE /errors/*` | Yes |
| `POST /sites/{id}/index` | Yes |
| `POST /jobs/bulk` | Yes |
| `POST /export/zip` (cached_only=false) | Yes |
| All GET endpoints | No |

Header: `X-Access-Key: <key>` or query param `?access_key=<key>`

---

## Key Design Decisions

1. **Single Modal App**: Server and worker share one app, simplifying deployment and allowing the server to call worker methods directly.

2. **Separated Images**: The API server uses a minimal image without Playwright. Browser work is dispatched to the worker class, which has its own heavyweight image with Chromium.

3. **Fire-and-forget Batches**: Bulk jobs use `.spawn()` so the server returns immediately. The worker writes results directly to the cache.

4. **Config Passed to Workers**: Workers receive full site config dicts in each call. They never read `sites.json` directly, making them stateless and testable.

5. **Inline HTTP Scraping**: Simple HTTP-based link discovery runs inline in the server (no separate Modal function), reducing latency for non-JS sites.

6. **Dict as Runtime Store**: Sites Dict allows runtime modifications without redeployment, with file as backup/version control.
