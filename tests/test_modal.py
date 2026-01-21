"""Tests for the content-scraper Modal API endpoints."""

import os
import pytest
import httpx
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.environ.get(
    "SCRAPER_API_URL",
    "https://tangentleman--content-scraper-api-fastapi-app-dev.modal.run"
)


def get_auth_headers() -> dict:
    """Get Modal auth headers from environment variables."""
    key = os.environ.get("MODAL_KEY")
    secret = os.environ.get("MODAL_SECRET")
    if key and secret:
        return {"Modal-Key": key, "Modal-Secret": secret}
    return {}


# Default timeout for requests
DEFAULT_TIMEOUT = 15.0

ALL_SITES = ["modal", "convex", "terraform-aws", "cursor", "claude-platform", "claude-code", "unsloth", "playwright", "datadog"]


class TestRootAndHealth:
    """Test basic API endpoints."""

    def test_root_endpoint(self):
        """Test the root endpoint returns API info."""
        resp = httpx.get(f"{API_BASE}/", headers=get_auth_headers(), timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert "name" in data
        assert "endpoints" in data
        assert data["name"] == "Content Scraper API"

    def test_health_endpoint(self):
        """Test the health endpoint returns healthy status."""
        resp = httpx.get(f"{API_BASE}/health", headers=get_auth_headers(), timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"


class TestSitesEndpoint:
    """Test the /sites endpoint."""

    def test_list_sites(self):
        """Test listing all available sites."""
        resp = httpx.get(f"{API_BASE}/sites", headers=get_auth_headers(), timeout=DEFAULT_TIMEOUT)
        assert resp.status_code == 200
        data = resp.json()
        assert "sites" in data
        assert "count" in data
        assert isinstance(data["sites"], list)
        assert data["count"] == len(data["sites"])
        # Check that expected sites are present
        for site in ALL_SITES:
            assert site in data["sites"], f"Expected site '{site}' not found"


class TestLinksEndpoint:
    """Test the /sites/{site_id}/links endpoint."""

    @pytest.mark.parametrize("site_id", ["modal", "convex", "terraform-aws"])
    def test_get_site_links(self, site_id):
        """Test getting links for supported sites."""
        resp = httpx.get(
            f"{API_BASE}/sites/{site_id}/links",
            headers=get_auth_headers(),
            timeout=180.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["site_id"] == site_id
        assert data["count"] == len(data["links"])
        assert len(data["links"]) > 0
        assert all(link.startswith("http") for link in data["links"][:5])

    def test_get_invalid_site_links(self):
        """Test that invalid site returns an error."""
        resp = httpx.get(
            f"{API_BASE}/sites/nonexistent-site/links",
            headers=get_auth_headers(),
            timeout=30.0,
        )
        assert resp.status_code == 404


class TestContentEndpoint:
    """Test the /sites/{site_id}/content endpoint."""

    @pytest.mark.parametrize("site_id,path", [
        ("modal", "/guide"),
        ("convex", "/functions"),
        ("terraform-aws", ""),
    ])
    def test_get_site_content(self, site_id, path):
        """Test getting content from supported sites."""
        resp = httpx.get(
            f"{API_BASE}/sites/{site_id}/content",
            params={"path": path},
            headers=get_auth_headers(),
            timeout=180.0,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["site_id"] == site_id
        assert data["path"] == path
        assert data["content_length"] == len(data["content"])
        assert data["content_length"] > 0

    def test_get_invalid_site_content(self):
        """Test that invalid site returns an error."""
        resp = httpx.get(
            f"{API_BASE}/sites/nonexistent-site/content",
            params={"path": "/test"},
            headers=get_auth_headers(),
            timeout=30.0,
        )
        assert resp.status_code == 404


# --- Manual testing functions (run with python tests/test_modal.py) ---


def run_manual_tests():
    """Run tests manually with verbose output."""
    print(f"Testing API: {API_BASE}")
    print("=" * 60)

    # Test root endpoint
    print("\n1. Testing root endpoint...")
    resp = httpx.get(f"{API_BASE}/", headers=get_auth_headers(), timeout=DEFAULT_TIMEOUT)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"   API Name: {data.get('name')}")
        print(f"   Version: {data.get('version')}")
        print("   ✓ Root endpoint works")
    else:
        print(f"   ✗ Failed: {resp.text[:100]}")

    # Test health endpoint
    print("\n2. Testing health endpoint...")
    resp = httpx.get(f"{API_BASE}/health", headers=get_auth_headers(), timeout=DEFAULT_TIMEOUT)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        print(f"   Health: {resp.json()}")
        print("   ✓ Health endpoint works")
    else:
        print(f"   ✗ Failed: {resp.text[:100]}")

    # Test sites endpoint
    print("\n3. Testing sites endpoint...")
    resp = httpx.get(f"{API_BASE}/sites", headers=get_auth_headers(), timeout=DEFAULT_TIMEOUT)
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"   Sites: {data['sites']}")
        print(f"   Count: {data['count']}")
        print("   ✓ Sites endpoint works")
    else:
        print(f"   ✗ Failed: {resp.text[:100]}")

    # Test links endpoint
    print("\n4. Testing links endpoint (modal)...")
    print("   This may take a moment...")
    resp = httpx.get(
        f"{API_BASE}/sites/modal/links",
        headers=get_auth_headers(),
        timeout=120.0,
    )
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"   Site ID: {data['site_id']}")
        print(f"   Link count: {data['count']}")
        print(f"   First 3 links:")
        for link in data["links"][:3]:
            print(f"     - {link}")
        print("   ✓ Links endpoint works")
    else:
        print(f"   ✗ Failed: {resp.text[:100]}")

    # Test content endpoint
    print("\n5. Testing content endpoint (modal /guide)...")
    print("   This may take a moment...")
    resp = httpx.get(
        f"{API_BASE}/sites/modal/content",
        params={"path": "/guide"},
        headers=get_auth_headers(),
        timeout=120.0,
    )
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"   Site ID: {data['site_id']}")
        print(f"   Path: {data['path']}")
        print(f"   Content length: {data['content_length']} chars")
        preview = data["content"][:200].replace("\n", " ")
        print(f"   Preview: {preview}...")
        print("   ✓ Content endpoint works")
    else:
        print(f"   ✗ Failed: {resp.text[:200]}")

    print("\n" + "=" * 60)
    print("Manual tests completed!")


if __name__ == "__main__":
    run_manual_tests()
