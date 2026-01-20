# handy-apis

Simple Modal-based API endpoints for web automation and scraping.

Draws heavily from: https://github.com/modal-labs/modal-examples

## Quick Start

```bash
# install deps
uv sync

# deploy stable version
modal deploy content-scraper-api.py

# while developing, use the hot-reloading dev server
modal serve content-scraper-api.py
```

## docpull CLI

The main way to use this tool. Fetches documentation from supported sites and saves it locally.

**Setup:** Create a `.env` file with your Modal credentials:
```bash
MODAL_KEY=wk-...
MODAL_SECRET=ws-...
```

**Usage:**

```bash
# List available sites
python docpull.py sites

# Get all doc links for a site
python docpull.py links modal
python docpull.py links terraform-aws

# Fetch content from a page (saves to ./docs/<site>/<path>.md)
python docpull.py content modal /guide
python docpull.py content modal /guide/gpu
python docpull.py content terraform-aws /resources/aws_instance
```

Content is saved to `./docs/<site>/` with paths converted to filenames:
- `/guide` → `guide.md`
- `/guide/gpu` → `guide_gpu.md`
- `/resources/aws_instance` → `resources_aws_instance.md`

## Supported Sites

| Site | Mode | Description |
|------|------|-------------|
| `modal` | fetch | Modal documentation |
| `convex` | fetch | Convex documentation |
| `terraform-aws` | browser | Terraform AWS provider docs |
| `cursor` | browser | Cursor documentation |
| `claude-code` | fetch | Claude Code documentation |
| `unsloth` | fetch | Unsloth documentation |

## REST API

Deploy `content-scraper-api.py` to get these endpoints:

```
GET  /sites                        # List available site IDs
GET  /sites/{site_id}/links        # Get all doc links for a site
GET  /sites/{site_id}/content      # Get content from a page

# Legacy endpoints
GET  /docs/{site_id}/{page}        # Get doc (cached or fresh scrape)
POST /scrape                       # Scrape any URL (stateless)
```

## GitHub Actions

There's a workflow for batch scraping that saves results to `docs/`.

**Setup**: add these secrets to your repo (Settings → Secrets and variables → Actions):
- `MODAL_USERNAME`: your username from `https://[your-username]--{project-name}.modal.run/`
- `MODAL_KEY`: proxy auth token ID (starts with `wk-`)
- `MODAL_SECRET`: proxy auth token secret (starts with `ws-`)

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed architecture documentation.
