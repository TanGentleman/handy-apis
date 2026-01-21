# CLAUDE.md

Documentation scraper: CLI fetches docs via Modal API, saves as markdown.

## Commands

```bash
uv sync                                # Install deps
modal serve content-scraper-api.py     # Dev server
modal deploy content-scraper-api.py    # Deploy

python docpull.py sites                # List sites
python docpull.py links <site>         # Get links (--force bypasses cache)
python docpull.py content <site> <path> # Fetch page (--force clears errors)
python docpull.py index <site>         # Bulk fetch all pages
python docpull.py cache stats          # Cache stats
python docpull.py cache clear <site>   # Clear cache
```

## Key Files

- `docpull.py` - CLI client
- `content-scraper-api.py` - Modal API (FastAPI + Playwright)
- `scraper/config/sites.json` - Site configs

## Adding a Site

Add to `scraper/config/sites.json`:

```json
"site-id": {
  "name": "Site Name",
  "baseUrl": "https://docs.example.com",
  "mode": "fetch",
  "links": {
    "startUrls": ["/section1", "/section2"],
    "pattern": "docs.example.com",
    "maxDepth": 1
  },
  "content": {
    "mode": "browser",
    "selector": "#content",
    "method": "inner_html"
  }
}
```

- `mode`: `fetch` (HTTP crawl) or `browser` (Playwright for JS sites)
- `maxDepth`: Only affects fetch mode (browser just extracts from startUrls)
- `method`: `inner_html` or `click_copy` (for copy buttons)
