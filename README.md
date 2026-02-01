# docpull

Modal-based documentation scraper. Fetches docs from any site and saves as markdown.

## Setup

```bash
# Clone and install
git clone https://github.com/yourusername/docpull.git
cd docpull
uv sync

# Authenticate with Modal (one-time)
modal token new

# Deploy to Modal (will prompt to set up global 'docpull' command)
python deploy.py
```

## Usage

After deployment, use the CLI via one of:
- `docpull` - if you set up the global alias during deploy
- `./docpull` - from the project directory
- `python -m cli.main` - direct module invocation

```bash
# List available sites
docpull sites

# Get all doc links for a site
docpull links modal

# Fetch a single page
docpull content modal /docs/guide

# Download entire site
docpull index modal

# Discover config for new sites
docpull discover https://example.com/docs
```

Output is saved to `./docs/<site-id>/<page-path>.md`.

## Adding Sites

1. Run `docpull discover <url>` to generate config
2. Add to `config/sites.json`
3. Test with `docpull links <site-id>` and `docpull content <site-id> <path>`

## More

- [API Reference](API.md) - REST API, bulk jobs, export, cache
- [Teardown](teardown.py) - Stop deployments with `python teardown.py`
