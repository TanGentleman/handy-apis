"""Tests for content extraction across supported sites."""

import os

import httpx
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.environ.get(
    "SCRAPER_API_URL",
    "https://tangentleman--content-scraper-api-fastapi-app-dev.modal.run",
)


def get_auth_headers() -> dict:
    """Get Modal auth headers from environment variables."""
    key = os.environ.get("MODAL_KEY")
    secret = os.environ.get("MODAL_SECRET")
    if key and secret:
        return {"Modal-Key": key, "Modal-Secret": secret}
    return {}


def test_convex_content():
    """Convex /functions should return content."""
    resp = httpx.get(
        f"{API_BASE}/sites/convex/content",
        params={"path": "/functions"},
        headers=get_auth_headers(),
        timeout=120.0,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["site_id"] == "convex"
    assert data["path"] == "/functions"
    assert data["content_length"] == len(data["content"])
    assert data["content_length"] > 0


def test_terraform_content():
    """Terraform root docs should return content."""
    resp = httpx.get(
        f"{API_BASE}/sites/terraform-aws/content",
        params={"path": ""},
        headers=get_auth_headers(),
        timeout=180.0,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["site_id"] == "terraform-aws"
    assert data["path"] == ""
    assert data["content_length"] == len(data["content"])
    assert data["content_length"] > 0

