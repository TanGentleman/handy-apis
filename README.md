# docpull

Modal-based documentation scraper. Fetches docs from any site and saves as markdown.

## Setup

```bash
# Clone and install
git clone https://github.com/TanGentleman/docpull.git
cd docpull
uv sync

# Authenticate with Modal (one-time)
modal token new

# Deploy to Modal
python deploy.py                              # Default app name: doc
python deploy.py --app-name myapp             # Custom app name
python deploy.py --access-key secret123       # Require X-Access-Key header for API access
```

Deploy options:
- `--app-name NAME` - Set Modal app name (default: `doc`). Affects deployed URL.
- `--access-key KEY` - Enable API authentication. Requests must include `X-Access-Key: KEY` header.
- `--open-browser` - Open the UI in browser after deployment.
- `--no-alias` - Skip adding global `docpull` command to ~/.zshrc.

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
- [Architecture](ARCHITECTURE.md) - System design and components
- [Testing Guide](TESTING.md) - Verify your setup works correctly
- [Teardown](teardown.py) - Stop deployments with `python teardown.py`
