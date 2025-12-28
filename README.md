im gonna add some simple api endpoints that are helpful for me.

i draw heavily from: https://github.com/modal-labs/modal-examples

## what's here

**content-scraper-api**: a playwright-based scraper that updates and caches documentation for agents.

## quick start

```bash
# install deps
uv sync

# deploy to modal
modal deploy content-scraper-api.py

# or hot test local edits with dev
modal serve content-scraper-api.py
```

## using the api

the scraper has a few endpoints:

```bash

# scrape a single page
curl -X POST https://[your-username]--content-scraper-api-fastapi-app.modal.run/scrape \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "selector": "#copy-button"}'

# scrape multiple pages in parallel
curl -X POST https://[your-username]--content-scraper-api-fastapi-app.modal.run/scrape/batch \
  -H "Content-Type: application/json" \
  -d '{
    "requests": [
      {"url": "https://example.com/page1", "selector": "#copy-button"},
      {"url": "https://example.com/page2", "selector": "#copy-button"}
    ]
  }'
```

## github actions

there's a workflow for batch scraping that saves results to `docs/`.

**setup**: add these secrets to your repo (Settings → Secrets and variables → Actions):
- `MODAL_USERNAME`: your username from `https://[your-username]--{project-name}.modal.run/`
- `MODAL_KEY`: proxy auth token ID (starts with `wk-`, create at https://modal.com/settings/proxy-auth-tokens)
- `MODAL_SECRET`: proxy auth token secret (starts with `ws-`)

the workflow needs write permissions to push changes.

to run manually: Actions → Batch Scraper Test → Run workflow
