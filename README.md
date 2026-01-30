# docpull

Modal-based documentation scraper. Fetches docs from various sites and saves locally as markdown.

## Setup

```bash
uv sync
```

Create `.env` with Modal credentials:
```
MODAL_KEY=wk-...
MODAL_SECRET=ws-...
```

Deploy:
```bash
modal deploy content-scraper-api.py
```

## Usage

```bash
python docpull.py sites                     # List available sites
python docpull.py links modal               # Get all doc links
python docpull.py content modal /guide      # Fetch single page
python docpull.py index modal               # Bulk fetch entire site
python docpull.py download modal            # Download site as ZIP

# Bulk jobs (fire-and-forget parallel scraping)
python docpull.py bulk urls.txt             # Submit job, returns job_id
python docpull.py job <job_id>              # Check job status
python docpull.py job <job_id> --watch      # Watch live progress
python docpull.py jobs                      # List recent jobs
```

Output: `./docs/<site>/<path>.md`

## Architecture

```
docpull.py (CLI) ──▶ content-scraper-api.py (Modal)
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
       modal.Dict    modal.Dict    modal.Dict
        (cache)       (errors)       (jobs)
```

**Scraping modes:**
- `index` - Sequential scraping, one container
- `bulk` - Parallel scraping, up to 100 containers via `.spawn()`

**Link discovery:**
- `mode: "fetch"` - HTTP crawl from `startUrls`, follows links to `maxDepth`
- `mode: "browser"` - Playwright extracts links from `startUrls` (no recursion)

**Content scraping:** Playwright loads page, extracts via CSS selector or copy button click.

**Error handling:** Links failing 3+ times are skipped. Use `--force` to retry.

## Configuration

Site configs in `scraper/config/sites.json`. Key fields:

| Field | Description |
|-------|-------------|
| `baseUrl` | Docs root URL |
| `mode` | `fetch` or `browser` |
| `links.startUrls` | Entry points for crawling |
| `links.maxDepth` | Recursion depth (fetch mode only) |
| `links.pattern` | URL filter pattern |
| `content.selector` | CSS/XPath for content extraction |
| `content.method` | `inner_html` or `click_copy` |
| `content.waitUntil` | `domcontentloaded` or `networkidle` |

## REST API

```
GET  /sites                    # List sites
GET  /sites/{id}/links         # Get doc links
GET  /sites/{id}/content       # Get page content
POST /sites/{id}/index         # Bulk fetch (sequential)
GET  /sites/{id}/download      # Download as ZIP

POST /jobs/bulk                # Submit parallel job
GET  /jobs/{job_id}            # Job status
GET  /jobs                     # List jobs

GET  /cache/stats              # Cache stats
DELETE /cache/{id}             # Clear cache
```
