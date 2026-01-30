"""Local UI server for docpull workflow."""

import ipaddress
import json
import socket
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

app = FastAPI(title="Docpull UI Server")

# Restrict CORS to local UI only
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8080", "http://localhost:8080"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)


def validate_url(url: str) -> str | None:
    """Validate URL to prevent SSRF attacks. Returns error message or None if valid."""
    try:
        parsed = urlparse(url)
    except Exception:
        return "Invalid URL format"

    # Only allow http/https
    if parsed.scheme not in ("http", "https"):
        return f"Invalid scheme '{parsed.scheme}'. Only http/https allowed"

    if not parsed.netloc:
        return "Missing hostname"

    hostname = parsed.hostname
    if not hostname:
        return "Missing hostname"

    # Block localhost variants
    blocked_hosts = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
    if hostname.lower() in blocked_hosts:
        return "Localhost URLs are not allowed"

    # Resolve hostname and check for internal IPs
    try:
        resolved_ips = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for family, _, _, _, sockaddr in resolved_ips:
            ip_str = sockaddr[0]
            ip = ipaddress.ip_address(ip_str)

            # Block private, loopback, and link-local addresses
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return f"Internal/private IP addresses are not allowed ({ip_str})"
    except socket.gaierror:
        # Can't resolve - let the CLI handle it
        pass

    return None

SITES_JSON = Path(__file__).parent / "scraper" / "config" / "sites.json"


class DiscoverRequest(BaseModel):
    url: str


class AddSiteRequest(BaseModel):
    site_id: str
    config: dict


class LinksRequest(BaseModel):
    site_id: str
    save: bool = False
    force: bool = False


def run_command(cmd: list[str], timeout: int = 120) -> dict:
    """Run a CLI command and return stdout/stderr."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=Path(__file__).parent,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Command timed out", "returncode": -1}
    except Exception as e:
        return {"success": False, "stdout": "", "stderr": str(e), "returncode": -1}


@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    """Serve the HTML UI."""
    html_path = Path(__file__).parent / "ui.html"
    if html_path.exists():
        return FileResponse(html_path, media_type="text/html")
    return HTMLResponse("<h1>ui.html not found</h1>", status_code=404)


@app.get("/api/sites")
async def list_sites():
    """List all configured sites."""
    if not SITES_JSON.exists():
        return {"sites": {}}
    data = json.loads(SITES_JSON.read_text())
    return {"sites": data.get("sites", {})}


@app.post("/api/discover")
async def discover(req: DiscoverRequest):
    """Run docpull discover on a URL."""
    # Validate URL to prevent SSRF
    if error := validate_url(req.url):
        raise HTTPException(400, error)

    result = run_command(["python", "docpull.py", "discover", req.url], timeout=60)
    return result


@app.post("/api/add-site")
async def add_site(req: AddSiteRequest):
    """Add or update a site in sites.json."""
    if not SITES_JSON.exists():
        data = {"sites": {}}
    else:
        data = json.loads(SITES_JSON.read_text())

    data["sites"][req.site_id] = req.config
    SITES_JSON.write_text(json.dumps(data, indent=2))

    return {"success": True, "message": f"Site '{req.site_id}' saved"}


@app.post("/api/links")
async def get_links(req: LinksRequest):
    """Run docpull links for a site."""
    cmd = ["python", "docpull.py", "links", req.site_id]
    if req.save:
        cmd.append("--save")
    if req.force:
        cmd.append("--force")

    result = run_command(cmd, timeout=120)
    return result


@app.delete("/api/sites/{site_id}")
async def delete_site(site_id: str):
    """Delete a site from sites.json."""
    if not SITES_JSON.exists():
        raise HTTPException(404, "sites.json not found")

    data = json.loads(SITES_JSON.read_text())
    if site_id not in data.get("sites", {}):
        raise HTTPException(404, f"Site '{site_id}' not found")

    del data["sites"][site_id]
    SITES_JSON.write_text(json.dumps(data, indent=2))

    return {"success": True, "message": f"Site '{site_id}' deleted"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8080)
