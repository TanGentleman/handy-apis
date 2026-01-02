# Convex API Documentation

Simple API for using Convex as a data store for documentation scraping.

## Setup

### 1. Deploy Convex Backend

```bash
cd convex-backend
npx convex dev  # for development
# or
npx convex deploy  # for production
```

This will give you a deployment URL like: `https://your-project.convex.cloud`

### 2. Configure Modal Secret

Create a Modal secret named `convex-secrets` with:
```bash
modal secret create convex-secrets CONVEX_URL=https://your-project.convex.cloud
```

### 3. Deploy the API

```bash
modal deploy convex-api.py
```

Your API will be available at: `https://[MODAL_USERNAME]--convex-api-fastapi-app.modal.run`

## API Endpoints

### Sites Management

#### List all sites
```bash
GET /sites
```

Returns all configured documentation sites.

**Response:**
```json
{
  "sites": [
    {
      "id": "...",
      "siteId": "modal-docs",
      "name": "Modal Documentation",
      "baseUrl": "https://modal.com",
      "selector": ".docs-content",
      "method": "click_copy",
      "pages": {
        "volumes": "/docs/guide/volumes",
        "secrets": "/docs/guide/secrets"
      },
      "sections": {}
    }
  ],
  "total": 1
}
```

#### Get a specific site
```bash
GET /sites/{siteId}
```

**Example:**
```bash
curl https://[MODAL_USERNAME]--convex-api-fastapi-app.modal.run/sites/modal-docs
```

#### Create/Update a site
```bash
POST /sites/create
```

**Request Body:**
```json
{
  "siteId": "modal-docs",
  "name": "Modal Documentation",
  "baseUrl": "https://modal.com",
  "selector": ".docs-content",
  "method": "click_copy",
  "pages": {
    "volumes": "/docs/guide/volumes",
    "secrets": "/docs/guide/secrets"
  },
  "sections": {
    "guide": "/docs/guide"
  }
}
```

#### Delete a site
```bash
DELETE /sites/{siteId}
```

### Documentation Management

#### List all docs for a site
```bash
GET /sites/{siteId}/docs
```

Returns all cached documentation pages for a site.

**Example:**
```bash
curl https://[MODAL_USERNAME]--convex-api-fastapi-app.modal.run/sites/modal-docs/docs
```

**Response:**
```json
{
  "siteId": "modal-docs",
  "docs": [
    {
      "id": "...",
      "siteId": "modal-docs",
      "page": "volumes",
      "url": "https://modal.com/docs/guide/volumes",
      "contentHash": "abc123...",
      "updatedAt": 1704150000000,
      "contentLength": 5432
    }
  ],
  "total": 1
}
```

#### Get a specific doc
```bash
GET /sites/{siteId}/docs/{page}
```

Returns the full markdown content for a page.

**Example:**
```bash
curl https://[MODAL_USERNAME]--convex-api-fastapi-app.modal.run/sites/modal-docs/docs/volumes
```

**Response:**
```json
{
  "id": "...",
  "siteId": "modal-docs",
  "page": "volumes",
  "url": "https://modal.com/docs/guide/volumes",
  "markdown": "# Volumes\n\nModal volumes...",
  "contentHash": "abc123...",
  "updatedAt": 1704150000000
}
```

#### Save/Update a doc
```bash
POST /sites/{siteId}/docs/save
```

**Request Body:**
```json
{
  "siteId": "modal-docs",
  "page": "volumes",
  "url": "https://modal.com/docs/guide/volumes",
  "markdown": "# Volumes\n\nModal volumes are..."
}
```

**Response:**
```json
{
  "siteId": "modal-docs",
  "page": "volumes",
  "updated": true,
  "id": "...",
  "contentHash": "abc123...",
  "updatedAt": 1704150000000
}
```

#### Delete a doc
```bash
DELETE /sites/{siteId}/docs/{page}
```

#### Get doc by URL
```bash
GET /docs/by-url?url={url}
```

Find a doc by its original URL.

**Example:**
```bash
curl "https://[MODAL_USERNAME]--convex-api-fastapi-app.modal.run/docs/by-url?url=https://modal.com/docs/guide/volumes"
```

## Usage Examples

### Python

```python
import httpx

API_URL = "https://[MODAL_USERNAME]--convex-api-fastapi-app.modal.run"

async def list_sites():
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{API_URL}/sites")
        return response.json()

async def save_doc(site_id: str, page: str, url: str, markdown: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/sites/{site_id}/docs/save",
            json={
                "siteId": site_id,
                "page": page,
                "url": url,
                "markdown": markdown,
            }
        )
        return response.json()
```

### cURL

```bash
# List all sites
curl https://[MODAL_USERNAME]--convex-api-fastapi-app.modal.run/sites

# Get a specific doc
curl https://[MODAL_USERNAME]--convex-api-fastapi-app.modal.run/sites/modal-docs/docs/volumes

# Create a site
curl -X POST https://[MODAL_USERNAME]--convex-api-fastapi-app.modal.run/sites/create \
  -H "Content-Type: application/json" \
  -d '{
    "siteId": "modal-docs",
    "name": "Modal Documentation",
    "baseUrl": "https://modal.com",
    "selector": ".docs-content",
    "method": "click_copy",
    "pages": {"volumes": "/docs/guide/volumes"}
  }'

# Save documentation
curl -X POST https://[MODAL_USERNAME]--convex-api-fastapi-app.modal.run/sites/modal-docs/docs/save \
  -H "Content-Type: application/json" \
  -d '{
    "siteId": "modal-docs",
    "page": "volumes",
    "url": "https://modal.com/docs/guide/volumes",
    "markdown": "# Volumes\n\nContent here..."
  }'
```

## Core Use Cases

### 1. List Available Sites

The primary use case you requested - get a list of which sites are available:

```bash
curl https://[MODAL_USERNAME]--convex-api-fastapi-app.modal.run/sites
```

This returns all configured sites with their metadata.

### 2. Manage Site Configurations

Add new documentation sites to track:

```python
import httpx

async def add_site(site_config: dict):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/sites/create",
            json=site_config
        )
        return response.json()
```

### 3. Store Scraped Documentation

After scraping documentation, save it to Convex:

```python
async def scrape_and_save(site_id: str, page: str, url: str):
    # Scrape the page (using your existing scraper)
    markdown_content = await scrape_page(url)

    # Save to Convex
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{API_URL}/sites/{site_id}/docs/save",
            json={
                "siteId": site_id,
                "page": page,
                "url": url,
                "markdown": markdown_content,
            }
        )
        return response.json()
```

## Schema

The Convex backend uses the following schema:

- **sites**: Site configurations
  - `siteId`: Unique identifier (string)
  - `name`: Display name (string)
  - `baseUrl`: Base URL of the site (string)
  - `selector`: CSS selector for content (string)
  - `method`: Extraction method (string)
  - `pages`: Map of page names to paths (object)
  - `sections`: Optional sections map (object)

- **docs**: Documentation pages
  - `siteId`: Reference to site (string)
  - `page`: Page identifier (string)
  - `url`: Full URL (string)
  - `markdown`: Content (string)
  - `contentHash`: SHA-256 hash (string)
  - `updatedAt`: Timestamp (number)

## Development

To run locally:

```bash
# Start Convex backend
cd convex-backend
npx convex dev

# In another terminal, serve the Modal API
modal serve convex-api.py
```

## Notes

- The API automatically calculates content hashes when saving docs
- All timestamps are Unix timestamps in milliseconds
- The API requires the `CONVEX_URL` environment variable to be set via Modal secrets
- Authentication will be added in future versions
