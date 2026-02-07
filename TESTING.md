# Testing Guide

This guide covers how to verify that docpull is working correctly at every level—from local setup through cloud deployment to the OpenCode sandbox.

## Quick Health Check

After deployment, run these commands to verify everything is working:

```bash
# 1. Check the API is responding
curl $(cat .env | grep SCRAPER_API_URL | cut -d= -f2)/health

# 2. List available sites
docpull sites

# 3. Test link discovery
docpull links modal

# 4. Test content scraping
docpull content modal /guide
```

If all four commands succeed, your deployment is healthy.

---

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Unit Tests](#unit-tests)
3. [Integration Tests](#integration-tests)
4. [End-to-End Workflow Tests](#end-to-end-workflow-tests)
5. [Sandbox Testing](#sandbox-testing)
6. [Volume Testing](#volume-testing)
7. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### 1. Environment Setup

```bash
# Clone and install
git clone https://github.com/TanGentleman/docpull.git
cd docpull
uv sync

# Verify Modal authentication
modal token show

# If not authenticated:
modal token new
```

### 2. Deploy to Modal

```bash
python deploy.py
```

This creates a `.env` file with your `SCRAPER_API_URL`. All tests depend on this.

### 3. Verify Configuration

```bash
# Check .env exists and has the API URL
cat .env

# Expected output:
# APP_NAME=doc
# SCRAPER_API_URL=https://your-workspace--doc-pull.modal.run
```

---

## Unit Tests

Unit tests run locally without hitting the deployed API.

### Run All Unit Tests

```bash
# Using pytest directly
uv run pytest tests/ -v

# Or with coverage
uv run pytest tests/ -v --cov=api --cov-report=term-missing
```

### Run Specific Test Files

```bash
# URL utilities
uv run pytest tests/test_urls.py -v

# Bulk job logic
uv run pytest tests/test_bulk.py -v
```

### What Unit Tests Cover

| File | Tests |
|------|-------|
| `test_urls.py` | URL normalization, asset detection, path cleaning |
| `test_bulk.py` | Batch calculation, job status enum, container allocation |

### Expected Output

```
tests/test_urls.py::TestIsAssetUrl::test_pdf_files PASSED
tests/test_urls.py::TestIsAssetUrl::test_image_files PASSED
tests/test_urls.py::TestCleanUrl::test_removes_query_params PASSED
...
tests/test_bulk.py::TestJobStatus::test_status_values PASSED
tests/test_bulk.py::TestCalculateBatches::test_empty_input PASSED
...

====================== 25 passed in 0.5s ======================
```

---

## Integration Tests

Integration tests hit the deployed Modal API. They require a working deployment.

### Sequential API Tests

Test basic endpoints one by one:

```bash
uv run python tests/test_modal.py
```

**Tests performed:**
- `GET /` - Root endpoint
- `GET /health` - Health check
- `GET /sites` - List all sites
- `GET /sites/modal/links` - Link discovery
- `GET /sites/modal/content?path=/guide` - Content scraping
- `GET /jobs` - List jobs

### Parallel Content Tests

Fetch content from ALL configured sites simultaneously:

```bash
uv run python tests/test_modal.py parallel
```

This tests:
1. Concurrent scraping across all sites
2. Cache behavior (second fetch should be cached)

**Expected output:**
```
Fetching content from 18 sites (max concurrency: 50)...
============================================================
  modal: ✓ 15234 chars (fresh)
  convex: ✓ 8921 chars (fresh)
  cursor: ✓ 12045 chars (fresh)
  ...

Verifying cache status...
============================================================
  modal: ✓ cached
  convex: ✓ cached
  ...
✓ All cached!
```

### Bulk Job Tests

Test the bulk scraping job system:

```bash
uv run python tests/test_modal.py bulk
```

**Tests performed:**
- List existing jobs
- Query non-existent job (should 404)
- Submit empty URL list (should 400)
- Submit unknown URLs (no job created)
- Submit asset URLs (filtered out)
- Submit valid URLs (job created)
- Poll job until completion
- Test cache skip behavior

---

## End-to-End Workflow Tests

These tests verify complete user workflows.

### Test 1: Single Site Scraping

```bash
# Step 1: Get links from a site
docpull links modal --save

# Step 2: Verify links were saved
cat data/modal_links.json | head -20

# Step 3: Scrape a single page
docpull content modal /guide/volumes

# Step 4: Verify content was saved
ls -la docs/modal/
cat docs/modal/guide_volumes.md | head -50
```

### Test 2: Full Site Index

```bash
# Index all pages from a small site
docpull index opencode

# Expected output:
# Indexing opencode...
# Total: 15 pages | Cached: 0 | Scraped: 15
# Success: 15 | Failed: 0
```

### Test 3: Download as ZIP

```bash
# Download entire site as ZIP
docpull download modal -o ./downloads/

# Verify
ls -la downloads/modal_docs.zip
unzip -l downloads/modal_docs.zip | head -20
```

### Test 4: Bulk Export

```bash
# Create a URL list
cat > /tmp/urls.txt << 'EOF'
https://modal.com/docs/guide
https://modal.com/docs/guide/volumes
https://docs.convex.dev/functions/http-actions
EOF

# Export as ZIP
docpull export /tmp/urls.txt -o /tmp/docs_export.zip --unzip

# Verify
ls -la docs/
```

### Test 5: Site Discovery

```bash
# Discover configuration for a new site
docpull discover https://docs.anthropic.com/en/docs/intro-to-claude

# Expected output: Suggested configuration JSON
```

### Test 6: Agent Workflow (Local)

```bash
# Load docs to ~/.docpull/
docpull load modal

# Check status
docpull status

# Set up local chat environment
docpull chat modal

# Verify symlink and context file
ls -la docs/
cat DOCS.md
```

---

## Sandbox Testing

Test the Modal Sandbox with OpenCode.

### Prerequisites

```bash
# Ensure Modal and OpenCode are installed
modal --version
opencode --version  # Install from https://opencode.ai if missing
```

### Test 1: Basic Sandbox Creation

```bash
# Start the sandbox
uv run python sandbox/opencode.py --timeout 1

# Expected output:
# 🔨 Building OpenCode image...
# 📚 Mounting volume docpull-docs at /docs
# 🏖️  Creating sandbox...
# ============================================================
# 🎉 OpenCode Sandbox Ready!
# ============================================================
# 📋 Sandbox ID: sb-XXXXX
# 🌐 Web UI: https://...
# ...
```

### Test 2: Access the Sandbox

**Web UI:**
1. Open the printed Web URL in browser
2. Login with username: `opencode`, password: (from output)
3. Verify the `/docs` directory is accessible

**Terminal UI:**
```bash
# Copy the TUI command from the output
OPENCODE_SERVER_PASSWORD=<password> opencode attach <url>
```

**Direct Shell:**
```bash
# Access sandbox shell directly
modal shell <sandbox_id>

# Inside sandbox:
ls /docs
cat /docs/modal/guide_volumes.md | head -20
```

### Test 3: Upload Docs Then Start

```bash
# Upload local docs to the volume first
uv run python sandbox/opencode.py --upload-docs

# Verify in sandbox shell
modal shell <sandbox_id>
ls -la /docs/
```

### Test 4: Include Local Repo

```bash
# Start sandbox with local repo mounted
uv run python sandbox/opencode.py --include-repo --timeout 1

# In sandbox, your code is at /root/docpull
modal shell <sandbox_id>
ls /root/docpull
```

### Test 5: List and Stop Sandboxes

```bash
# List running sandboxes
uv run python sandbox/opencode.py --list

# Stop a specific sandbox
uv run python sandbox/opencode.py --stop sb-XXXXX
```

---

## Volume Testing

Test the Modal Volume for persistent documentation storage.

### Create and Inspect Volume

```bash
# List volumes
modal volume list

# Create the docs volume if it doesn't exist
modal volume create docpull-docs

# List contents
modal volume ls docpull-docs

# Upload local docs
modal volume put docpull-docs ./docs/ /
```

### Volume Shell Access

```bash
# Open shell with volume mounted
modal shell --volume docpull-docs

# Inside shell:
ls /mnt/docpull-docs/
cat /mnt/docpull-docs/modal/guide_volumes.md | head -20
```

### Upload via Python

```python
# In Python REPL or script
import modal

volume = modal.Volume.from_name("docpull-docs", create_if_missing=True)

# Batch upload
with volume.batch_upload() as batch:
    batch.put_directory("./docs/modal/", "/modal/")

volume.commit()
print("Upload complete!")
```

### Verify in Sandbox

```bash
# Start sandbox and check docs are there
uv run python sandbox/opencode.py --timeout 0.5

# In the WebUI or TUI, run:
# ls /docs
# Should show your uploaded documentation
```

---

## Troubleshooting

### Common Issues

#### 1. "SCRAPER_API_URL is not configured"

**Cause:** `.env` file missing or incomplete.

**Fix:**
```bash
# Re-deploy to regenerate .env
python deploy.py
```

#### 2. "modal: command not found"

**Cause:** Modal CLI not installed or not in PATH.

**Fix:**
```bash
# Install Modal
uv add modal

# Or authenticate with existing install
modal token new
```

#### 3. Content scraping returns empty/error

**Possible causes:**
- Site requires browser mode but config uses `fetch`
- Content selector is wrong
- Site structure changed

**Debug:**
```bash
# Force fresh scrape
docpull content <site> <path> --force

# Check error tracking
curl "$SCRAPER_API_URL/errors/<site>"

# Re-discover configuration
docpull discover <url>
```

#### 4. Sandbox fails to start

**Possible causes:**
- OpenCode installation failed
- Modal credentials missing

**Debug:**
```bash
# Check Modal auth
modal token show

# Run with verbose output
uv run python sandbox/opencode.py 2>&1 | tee sandbox.log
```

#### 5. Volume appears empty in sandbox

**Cause:** Volume wasn't committed or mounted incorrectly.

**Fix:**
```bash
# Upload docs to volume
uv run python sandbox/opencode.py --upload-docs

# Or manually:
modal volume put docpull-docs ./docs/ /

# For v2 volumes, ensure sync:
# Inside sandbox: sync /docs
```

#### 6. Tests timeout

**Cause:** Cold start latency or slow network.

**Fix:**
```bash
# Increase timeout for integration tests
# Edit tests/test_modal.py:
CONTENT_TIMEOUT = 300.0  # 5 minutes

# Or run a warm-up request first:
curl $SCRAPER_API_URL/health
```

### Diagnostic Commands

```bash
# Check API health
curl $SCRAPER_API_URL/health

# List running Modal apps
modal app list

# View Modal logs
modal app logs doc

# Check cache stats
docpull cache stats

# List cached pages for a site
docpull cache keys modal

# Clear cache for a site (requires access key)
docpull cache clear modal
```

### Getting Help

1. Check `ARCHITECTURE.md` for system design details
2. Check `API.md` for API endpoint documentation
3. Open an issue on GitHub with:
   - Command that failed
   - Full error output
   - Output of `modal --version` and `uv --version`

---

## Test Matrix

| Level | Command | What It Tests |
|-------|---------|---------------|
| Unit | `pytest tests/` | Local logic (no network) |
| Integration | `python tests/test_modal.py` | API endpoints |
| Integration | `python tests/test_modal.py parallel` | Concurrent scraping + caching |
| Integration | `python tests/test_modal.py bulk` | Job queue system |
| E2E | `docpull links <site>` | Link discovery workflow |
| E2E | `docpull content <site> <path>` | Content scraping workflow |
| E2E | `docpull index <site>` | Full site indexing |
| E2E | `docpull download <site>` | ZIP export workflow |
| Sandbox | `python sandbox/opencode.py` | OpenCode cloud environment |

Run the full test suite in order:

```bash
# 1. Unit tests
uv run pytest tests/ -v

# 2. API integration
uv run python tests/test_modal.py

# 3. Parallel scraping
uv run python tests/test_modal.py parallel

# 4. Bulk jobs
uv run python tests/test_modal.py bulk

# 5. E2E workflow
docpull links modal && docpull content modal /guide

# 6. Sandbox (optional, requires longer timeout)
uv run python sandbox/opencode.py --timeout 1
```

All tests passing? Your docpull installation is fully operational! 🎉

