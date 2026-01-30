# CLAUDE.md

Documentation scraper: CLI fetches docs via Modal API, saves as markdown.

## Quick Reference

| Task | Command |
|------|---------|
| Get a single page | `python docpull.py content <site> <path>` |
| Download entire site as ZIP | `python docpull.py download <site>` |
| Scrape many URLs (async) | `python docpull.py bulk urls.txt` |
| Check available sites | `python docpull.py sites` |
| Add a new site | `python docpull.py discover <url>` |

## When to Use What

- **One page** → `content modal /guide`
- **Whole site** → `download modal` (returns ZIP)
- **Many URLs across sites** → `bulk urls.txt` then `job <id> --watch`
- **New site not configured** → `discover <url>`, add config to `scraper/config/sites.json`

## Common Workflows

**Download docs for a configured site:**
```bash
python docpull.py download modal
# Output: modal_docs.zip with docs/modal/*.md
```

**Bulk scrape specific URLs:**
```bash
# Create urls.txt with URLs (one per line)
python docpull.py bulk urls.txt    # Returns job_id
python docpull.py job <job_id> --watch
```

**Add a new documentation site:**
```bash
python docpull.py discover https://docs.example.com/getting-started
# Copy suggested config to scraper/config/sites.json
python docpull.py links example    # Verify links work
python docpull.py content example /getting-started  # Test content
```

## Key Files

- `scraper/config/sites.json` - Site configurations
- `README.md` - Setup, architecture, config options
- `content-scraper-api.py` - API endpoints and implementation details

## Flags

- `--force` - Bypass cache, clear error tracking, retry failed pages
- `--watch` - Live progress for bulk jobs
