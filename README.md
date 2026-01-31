# docpull

Modal-based documentation scraper. Fetches docs from various sites and saves locally as markdown.

## Quick Start

```bash
# Install dependencies
uv sync

# Or (preferably in a virtual environment):
pip install -r requirements.txt
```

# Set up Modal credentials (create .env file)
MODAL_KEY=wk-...
MODAL_SECRET=ws-...

# Terminal 1: Deploy the API with hot-reload server
modal serve content-scraper-api.py

# Terminal 2: Configure and serve the UI
python ui/setup.py          # Run once to configure API URL
modal serve ui/app.py        # Then start the UI
```

## Usage

### CLI

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

### Web UI

After running `modal serve ui/app.py`, open the URL shown in the terminal to access the web interface.

Output: `./docs/<site>/<path>.md`

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
