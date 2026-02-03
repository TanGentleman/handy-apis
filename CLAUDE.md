# CLAUDE.md

Modal-based documentation scraper.

## Project Structure

```
docpull/
├── api/                    # Modal API
│   ├── server.py          # FastAPI endpoints + UI serving
│   ├── worker.py          # Playwright browser automation
│   ├── bulk.py            # Bulk job handling
│   └── urls.py            # URL utilities
├── cli/main.py            # Typer CLI
├── config/
│   ├── sites.json         # Site definitions
│   └── utils.py           # Env loading
├── ui/ui.html             # Web UI (served by server.py)
├── deploy.py              # Deploy script (single app)
└── teardown.py            # Stop deployments
```

## Development

```bash
modal serve api/server.py    # API + UI with hot-reload
python deploy.py             # Deploy to Modal
```

## Adding Sites

1. `docpull discover <url>` to generate config
2. Add to `config/sites.json`
3. Test: `docpull links <id>` and `docpull content <id> <path>`
4. Use `--force` to bypass cache when testing
