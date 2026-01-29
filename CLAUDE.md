# CLAUDE.md

Documentation scraper: CLI fetches docs via Modal API, saves as markdown.

## Commands

```bash
uv sync                                # Install deps
modal serve content-scraper-api.py     # Dev server
modal deploy content-scraper-api.py    # Deploy

python docpull.py sites                # List sites
python docpull.py discover <url>       # Auto-discover selectors for new site
python docpull.py links <site>         # Get links (--force bypasses cache)
python docpull.py content <site> <path> # Fetch page (--force clears errors)
python docpull.py index <site>         # Bulk fetch all pages
python docpull.py download <site>      # Download site as ZIP
python docpull.py export urls.txt      # Export URLs to ZIP (auto-resolves sites)
python docpull.py export urls.txt --unzip --scrape  # Export, scrape missing, extract
python docpull.py cache stats          # Cache stats
python docpull.py cache clear <site>   # Clear cache
```

## Key Files

- `docpull.py` - CLI client
- `content-scraper-api.py` - Modal API (FastAPI + Playwright)
- `scraper/config/sites.json` - Site configs

## Adding a Site (Fast Way)

Use the `discover` command to automatically find selectors:

```bash
python docpull.py discover https://developers.example.com/docs/getting-started
```

This will:
1. Detect the documentation framework (Docusaurus, Mintlify, GitBook, etc.)
2. Test copy buttons and find working selectors
3. Rank content selectors by quality
4. Analyze link patterns
5. Generate ready-to-use configuration

Copy the suggested config to `scraper/config/sites.json`, then test:

```bash
python docpull.py links your-site-id
python docpull.py content your-site-id <path>
python docpull.py index your-site-id
```

## Adding a Site (Manual)

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

### Configuration Options

- `mode`: `fetch` (HTTP crawl) or `browser` (Playwright for JS sites)
- `maxDepth`: Only affects fetch mode (browser just extracts from startUrls)
- `method`: `inner_html` (extract HTML) or `click_copy` (for copy buttons)
- `clickSequence`: For multi-step copy buttons (e.g., dropdown menus), use an array of click steps:

```json
"content": {
  "method": "click_copy",
  "clickSequence": [
    { "selector": "//button[@title='Copy page']", "waitAfter": 500 },
    { "selector": "button.menu-item:has-text('Copy page')", "waitAfter": 1000 }
  ]
}
```

Each step requires `selector` and optionally `waitAfter` (ms, default 500).

**Note:** `waitFor` is auto-derived from `clickSequence[0].selector` or `selector` if not explicitly set, so you rarely need to specify it.
