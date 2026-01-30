"""
Docpull UI - Lightweight Modal app for managing documentation scraping.

Separate from the main scraper API (no Playwright needed).
Calls the scraper API via HTTP.
"""

import os

import modal
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# Lightweight image - just FastAPI + httpx
image = modal.Image.debian_slim(python_version="3.11").pip_install(
    "fastapi[standard]", "httpx"
)

app = modal.App("docpull-ui", image=image)

# Get scraper API URL from environment or derive from Modal
SCRAPER_API_URL = os.environ.get(
    "SCRAPER_API_URL",
    "https://YOUR_MODAL_USERNAME--content-scraper-api-fastapi-app.modal.run"
)

web_app = FastAPI(title="Docpull UI")


# --- Request Models ---
class DiscoverRequest(BaseModel):
    url: str


class BulkRequest(BaseModel):
    urls: list[str]


# --- API Proxy Helpers ---
async def call_scraper_api(
    method: str,
    path: str,
    request: Request,
    json_body: dict | None = None,
    params: dict | None = None,
) -> dict:
    """Proxy request to scraper API, forwarding auth headers."""
    import httpx

    # Forward Modal auth headers from the incoming request
    headers = {}
    if "modal-key" in request.headers:
        headers["Modal-Key"] = request.headers["modal-key"]
    if "modal-secret" in request.headers:
        headers["Modal-Secret"] = request.headers["modal-secret"]

    url = f"{SCRAPER_API_URL}{path}"

    async with httpx.AsyncClient(timeout=120.0) as client:
        if method == "GET":
            resp = await client.get(url, headers=headers, params=params)
        elif method == "POST":
            resp = await client.post(url, headers=headers, json=json_body, params=params)
        elif method == "DELETE":
            resp = await client.delete(url, headers=headers, params=params)
        else:
            raise ValueError(f"Unsupported method: {method}")

        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=resp.text)

        return resp.json()


# --- UI HTML ---
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Docpull</title>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      max-width: 900px;
      margin: 0 auto;
      padding: 20px;
      background: #0d1117;
      color: #c9d1d9;
    }
    h1 { color: #58a6ff; margin-bottom: 8px; }
    h2 { color: #8b949e; font-size: 14px; font-weight: normal; margin-bottom: 24px; }

    .tabs {
      display: flex;
      gap: 4px;
      margin-bottom: 20px;
      border-bottom: 1px solid #30363d;
    }
    .tab {
      padding: 10px 16px;
      background: transparent;
      border: none;
      color: #8b949e;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      margin-bottom: -1px;
    }
    .tab:hover { color: #c9d1d9; }
    .tab.active {
      color: #58a6ff;
      border-bottom-color: #58a6ff;
    }

    .panel { display: none; }
    .panel.active { display: block; }

    .card {
      background: #161b22;
      border: 1px solid #30363d;
      border-radius: 8px;
      padding: 20px;
      margin-bottom: 16px;
    }

    label { display: block; margin-bottom: 6px; color: #8b949e; font-size: 14px; }
    input, textarea, select {
      width: 100%;
      padding: 10px 12px;
      background: #0d1117;
      border: 1px solid #30363d;
      border-radius: 6px;
      color: #c9d1d9;
      font-size: 14px;
    }
    input:focus, textarea:focus, select:focus {
      outline: none;
      border-color: #58a6ff;
    }
    textarea {
      font-family: 'SF Mono', Consolas, monospace;
      font-size: 13px;
      resize: vertical;
    }

    .row { display: flex; gap: 12px; align-items: flex-end; margin-bottom: 12px; }
    .row > * { flex: 1; }
    .row > button { flex: none; }

    button {
      padding: 10px 20px;
      border: none;
      border-radius: 6px;
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
    }
    .btn-primary { background: #238636; color: white; }
    .btn-primary:hover { background: #2ea043; }
    .btn-primary:disabled { background: #21262d; color: #484f58; cursor: not-allowed; }
    .btn-secondary { background: #21262d; color: #c9d1d9; border: 1px solid #30363d; }
    .btn-secondary:hover { background: #30363d; }

    .output {
      background: #0d1117;
      border: 1px solid #30363d;
      border-radius: 6px;
      padding: 12px;
      font-family: 'SF Mono', Consolas, monospace;
      font-size: 12px;
      white-space: pre-wrap;
      max-height: 400px;
      overflow-y: auto;
      margin-top: 12px;
    }
    .output.success { border-color: #238636; }
    .output.error { border-color: #f85149; }
    .hidden { display: none; }

    .spinner {
      display: inline-block;
      width: 14px;
      height: 14px;
      border: 2px solid #30363d;
      border-top-color: #58a6ff;
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      margin-right: 8px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    .site-list {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
      gap: 12px;
    }
    .site-item {
      background: #0d1117;
      border: 1px solid #30363d;
      border-radius: 6px;
      padding: 12px;
      cursor: pointer;
    }
    .site-item:hover { border-color: #58a6ff; }
    .site-item .name { font-weight: 500; color: #c9d1d9; }
    .site-item .url { font-size: 12px; color: #8b949e; margin-top: 4px; word-break: break-all; }

    .progress-bar {
      height: 8px;
      background: #21262d;
      border-radius: 4px;
      overflow: hidden;
      margin: 12px 0;
    }
    .progress-fill {
      height: 100%;
      background: #238636;
      transition: width 0.3s;
    }
    .job-stats { display: flex; gap: 16px; font-size: 14px; color: #8b949e; }
    .job-stats span { color: #c9d1d9; }
  </style>
</head>
<body>
  <h1>Docpull</h1>
  <h2>Documentation Scraper</h2>

  <div class="tabs">
    <button class="tab active" onclick="showTab('sites')">Sites</button>
    <button class="tab" onclick="showTab('discover')">Discover</button>
    <button class="tab" onclick="showTab('bulk')">Bulk Jobs</button>
  </div>

  <!-- Sites Tab -->
  <div id="sites-panel" class="panel active">
    <div class="card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
        <label style="margin: 0;">Configured Sites</label>
        <button class="btn-secondary" onclick="loadSites()">Refresh</button>
      </div>
      <div id="siteList" class="site-list">Loading...</div>
    </div>

    <div class="card">
      <label>Test Site</label>
      <div class="row">
        <select id="testSiteId"></select>
        <input type="text" id="testPath" placeholder="/path/to/page" style="flex: 2;">
        <button class="btn-primary" id="testLinksBtn" onclick="testLinks()">Links</button>
        <button class="btn-primary" id="testContentBtn" onclick="testContent()">Content</button>
      </div>
      <div id="testOutput" class="output hidden"></div>
    </div>
  </div>

  <!-- Discover Tab -->
  <div id="discover-panel" class="panel">
    <div class="card">
      <label>Documentation URL</label>
      <div class="row">
        <input type="text" id="discoverUrl" placeholder="https://docs.example.com/getting-started">
        <button class="btn-primary" id="discoverBtn" onclick="discover()">Discover</button>
      </div>
      <div id="discoverOutput" class="output hidden"></div>
    </div>

    <div class="card">
      <label>Suggested Configuration</label>
      <p style="color: #8b949e; font-size: 13px; margin-bottom: 12px;">
        Copy this to <code>scraper/config/sites.json</code> and redeploy.
      </p>
      <textarea id="configOutput" rows="15" readonly placeholder="Run discover to generate config..."></textarea>
    </div>
  </div>

  <!-- Bulk Jobs Tab -->
  <div id="bulk-panel" class="panel">
    <div class="card">
      <label>Submit Bulk Job</label>
      <textarea id="bulkUrls" rows="8" placeholder="Paste URLs (one per line)"></textarea>
      <div style="margin-top: 12px;">
        <button class="btn-primary" id="submitBulkBtn" onclick="submitBulk()">Submit Job</button>
      </div>
      <div id="bulkOutput" class="output hidden"></div>
    </div>

    <div class="card">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
        <label style="margin: 0;">Recent Jobs</label>
        <button class="btn-secondary" onclick="loadJobs()">Refresh</button>
      </div>
      <div id="jobsList"></div>
    </div>

    <div class="card" id="jobDetail" style="display: none;">
      <label>Job Progress</label>
      <div class="progress-bar"><div class="progress-fill" id="jobProgress"></div></div>
      <div class="job-stats">
        <div>Completed: <span id="jobCompleted">0</span></div>
        <div>Success: <span id="jobSuccess">0</span></div>
        <div>Failed: <span id="jobFailed">0</span></div>
        <div>Skipped: <span id="jobSkipped">0</span></div>
      </div>
      <div id="jobErrors" class="output hidden" style="margin-top: 12px;"></div>
    </div>
  </div>

  <script>
    const API = window.location.origin + '/api';
    let pollInterval = null;

    function showTab(name) {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
      document.querySelector(`[onclick="showTab('${name}')"]`).classList.add('active');
      document.getElementById(`${name}-panel`).classList.add('active');

      if (name === 'sites') loadSites();
      if (name === 'bulk') loadJobs();
    }

    function showOutput(el, text, success = true) {
      el.textContent = text;
      el.classList.remove('hidden', 'success', 'error');
      el.classList.add(success ? 'success' : 'error');
    }

    function setLoading(btn, loading) {
      if (loading) {
        btn.disabled = true;
        btn.dataset.original = btn.textContent;
        btn.innerHTML = '<span class="spinner"></span>';
      } else {
        btn.disabled = false;
        btn.textContent = btn.dataset.original;
      }
    }

    async function loadSites() {
      try {
        const res = await fetch(`${API}/sites`);
        const data = await res.json();

        const list = document.getElementById('siteList');
        const select = document.getElementById('testSiteId');

        if (!data.sites || data.sites.length === 0) {
          list.innerHTML = '<p style="color: #8b949e;">No sites configured</p>';
          return;
        }

        list.innerHTML = data.sites.map(s => `
          <div class="site-item" onclick="selectSite('${s.id}')">
            <div class="name">${s.id}</div>
          </div>
        `).join('');

        select.innerHTML = data.sites.map(s =>
          `<option value="${s.id}">${s.id}</option>`
        ).join('');
      } catch (err) {
        document.getElementById('siteList').innerHTML = `<p style="color: #f85149;">Error: ${err.message}</p>`;
      }
    }

    function selectSite(siteId) {
      document.getElementById('testSiteId').value = siteId;
    }

    async function testLinks() {
      const siteId = document.getElementById('testSiteId').value;
      if (!siteId) return alert('Select a site');

      const btn = document.getElementById('testLinksBtn');
      const output = document.getElementById('testOutput');

      setLoading(btn, true);
      try {
        const res = await fetch(`${API}/sites/${siteId}/links`);
        const data = await res.json();
        showOutput(output, JSON.stringify(data, null, 2), res.ok);
      } catch (err) {
        showOutput(output, err.message, false);
      }
      setLoading(btn, false);
    }

    async function testContent() {
      const siteId = document.getElementById('testSiteId').value;
      const path = document.getElementById('testPath').value.trim();
      if (!siteId) return alert('Select a site');
      if (!path) return alert('Enter a path');

      const btn = document.getElementById('testContentBtn');
      const output = document.getElementById('testOutput');

      setLoading(btn, true);
      try {
        const res = await fetch(`${API}/sites/${siteId}/content?path=${encodeURIComponent(path)}`);
        const data = await res.json();

        if (data.content) {
          const preview = data.content.substring(0, 2000);
          showOutput(output, `${data.content_length} chars (${data.from_cache ? 'cached' : 'fresh'})\\n\\n${preview}${data.content.length > 2000 ? '\\n...' : ''}`, res.ok);
        } else {
          showOutput(output, JSON.stringify(data, null, 2), res.ok);
        }
      } catch (err) {
        showOutput(output, err.message, false);
      }
      setLoading(btn, false);
    }

    async function discover() {
      const url = document.getElementById('discoverUrl').value.trim();
      if (!url) return alert('Enter a URL');

      const btn = document.getElementById('discoverBtn');
      const output = document.getElementById('discoverOutput');
      const configOutput = document.getElementById('configOutput');

      setLoading(btn, true);
      output.classList.add('hidden');

      try {
        const res = await fetch(`${API}/discover?url=${encodeURIComponent(url)}`);
        const data = await res.json();

        if (data.success) {
          showOutput(output, `Framework: ${data.framework}\\nBase URL: ${data.base_url_suggestion}\\nCopy buttons: ${data.copy_buttons?.length || 0}\\nContent selectors: ${data.content_selectors?.length || 0}\\nLinks found: ${data.link_analysis?.total_internal_links || 0}`, true);

          // Generate suggested config
          const config = generateConfig(data);
          configOutput.value = JSON.stringify(config, null, 2);
        } else {
          showOutput(output, data.error || 'Discovery failed', false);
        }
      } catch (err) {
        showOutput(output, err.message, false);
      }
      setLoading(btn, false);
    }

    function generateConfig(data) {
      const siteId = new URL(data.url).hostname.replace(/\\./g, '-').replace(/^docs-|^www-/, '');

      const config = {
        [siteId]: {
          name: siteId,
          baseUrl: data.base_url_suggestion,
          mode: "browser",
          links: {
            startUrls: [""],
            pattern: new URL(data.base_url_suggestion).hostname
          },
          content: {
            mode: "browser",
            method: "inner_html"
          }
        }
      };

      // Add best content selector
      if (data.content_selectors?.length > 0) {
        config[siteId].content.selector = data.content_selectors[0].selector;
      }

      // Check for working copy button
      const workingCopy = data.copy_buttons?.find(b => b.works);
      if (workingCopy) {
        config[siteId].content.method = "click_copy";
        config[siteId].content.selector = workingCopy.selector;
      }

      return config;
    }

    async function submitBulk() {
      const urls = document.getElementById('bulkUrls').value.trim().split('\\n').filter(u => u.trim());
      if (urls.length === 0) return alert('Enter at least one URL');

      const btn = document.getElementById('submitBulkBtn');
      const output = document.getElementById('bulkOutput');

      setLoading(btn, true);
      try {
        const res = await fetch(`${API}/jobs/bulk`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ urls })
        });
        const data = await res.json();
        showOutput(output, `Job ID: ${data.job_id}\\nStatus: ${data.status}\\nBatches: ${data.batches}`, res.ok);

        if (data.job_id) {
          watchJob(data.job_id);
        }
        loadJobs();
      } catch (err) {
        showOutput(output, err.message, false);
      }
      setLoading(btn, false);
    }

    async function loadJobs() {
      try {
        const res = await fetch(`${API}/jobs`);
        const data = await res.json();

        const list = document.getElementById('jobsList');
        if (!data.jobs || data.jobs.length === 0) {
          list.innerHTML = '<p style="color: #8b949e;">No recent jobs</p>';
          return;
        }

        list.innerHTML = data.jobs.slice(0, 10).map(j => `
          <div class="site-item" onclick="watchJob('${j.job_id}')" style="margin-bottom: 8px;">
            <div class="name">${j.job_id.substring(0, 8)}...</div>
            <div class="url">${j.status} - ${j.progress} - ${j.sites?.join(', ') || ''}</div>
          </div>
        `).join('');
      } catch (err) {
        document.getElementById('jobsList').innerHTML = `<p style="color: #f85149;">Error: ${err.message}</p>`;
      }
    }

    async function watchJob(jobId) {
      if (pollInterval) clearInterval(pollInterval);

      document.getElementById('jobDetail').style.display = 'block';

      const updateJob = async () => {
        try {
          const res = await fetch(`${API}/jobs/${jobId}`);
          const data = await res.json();

          const pct = data.progress_pct || 0;
          document.getElementById('jobProgress').style.width = `${pct}%`;
          document.getElementById('jobCompleted').textContent = data.progress?.completed || 0;
          document.getElementById('jobSuccess').textContent = data.progress?.success || 0;
          document.getElementById('jobFailed').textContent = data.progress?.failed || 0;
          document.getElementById('jobSkipped').textContent = data.progress?.skipped || 0;

          if (data.errors?.length > 0) {
            const errEl = document.getElementById('jobErrors');
            errEl.classList.remove('hidden');
            showOutput(errEl, data.errors.map(e => `${e.path}: ${e.error}`).join('\\n'), false);
          }

          if (data.status === 'completed') {
            clearInterval(pollInterval);
            pollInterval = null;
          }
        } catch (err) {
          console.error(err);
        }
      };

      updateJob();
      pollInterval = setInterval(updateJob, 2000);
    }

    // Initial load
    loadSites();
  </script>
</body>
</html>
"""


# --- Routes ---
@web_app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """Serve the UI."""
    return HTML_CONTENT


@web_app.get("/api/sites")
async def list_sites(request: Request):
    """List configured sites."""
    return await call_scraper_api("GET", "/sites", request)


@web_app.get("/api/sites/{site_id}/links")
async def get_links(site_id: str, request: Request):
    """Get links for a site."""
    return await call_scraper_api("GET", f"/sites/{site_id}/links", request)


@web_app.get("/api/sites/{site_id}/content")
async def get_content(site_id: str, path: str, request: Request):
    """Get content for a page."""
    return await call_scraper_api("GET", f"/sites/{site_id}/content", request, params={"path": path})


@web_app.get("/api/discover")
async def discover(url: str, request: Request):
    """Discover selectors for a URL."""
    return await call_scraper_api("GET", "/discover", request, params={"url": url})


@web_app.post("/api/jobs/bulk")
async def submit_bulk(req: BulkRequest, request: Request):
    """Submit a bulk scrape job."""
    return await call_scraper_api("POST", "/jobs/bulk", request, json_body={"urls": req.urls})


@web_app.get("/api/jobs/{job_id}")
async def get_job(job_id: str, request: Request):
    """Get job status."""
    return await call_scraper_api("GET", f"/jobs/{job_id}", request)


@web_app.get("/api/jobs")
async def list_jobs(request: Request):
    """List recent jobs."""
    return await call_scraper_api("GET", "/jobs", request)


# --- Modal Entrypoint ---
@app.function()
@modal.asgi_app(requires_proxy_auth=True)
def ui():
    """Serve the UI app."""
    return web_app
