# CLAUDE.md

Documentation scraper with caching. Fetches docs from various sites and saves locally.

## docpull CLI

```bash
# List available sites
python docpull.py sites

# Get all doc links for a site
python docpull.py links modal
python docpull.py links terraform-aws

# Fetch content (cached for 1 hour)
python docpull.py content modal /guide

# Force fresh scrape
python docpull.py content modal /guide --force
```

Output saved to `./docs/<site>/<path>.md`

## Adding a New Site

1. Add config to `scraper/config/sites.json`:
```json
{
  "new-site": {
    "name": "New Site",
    "baseUrl": "https://docs.example.com",
    "mode": "fetch",
    "extractor": "default",
    "links": {
      "startUrls": [""],
      "pattern": "docs.example.com",
      "maxDepth": 2
    },
    "content": {
      "mode": "browser",
      "selector": "#copy-button",
      "method": "click_copy"
    }
  }
}
```

2. If custom logic needed, create `scraper/extractors/new_site.py` and import in `scraper/extractors/__init__.py`

## Key Files

- `docpull.py` - CLI client
- `content-scraper-api.py` - Modal API (deploy this)
- `scraper/config/sites.json` - Site definitions
- `scraper/extractors/` - Site-specific scraping logic

## Commands

```bash
uv sync                                    # Install deps
modal serve content-scraper-api.py         # Dev server (hot reload)
python tests/test_modal.py                 # Test API
```
