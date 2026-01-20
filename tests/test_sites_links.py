"""Tests for link discovery across supported sites."""

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


def test_convex_links():
    """Convex docs should return a non-empty link list."""
    resp = httpx.get(
        f"{API_BASE}/sites/convex/links",
        headers=get_auth_headers(),
        timeout=120.0,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["site_id"] == "convex"
    assert data["count"] == len(data["links"])
    assert len(data["links"]) > 0


def test_terraform_links():
    """Terraform AWS docs should return a non-empty link list."""
    resp = httpx.get(
        f"{API_BASE}/sites/terraform-aws/links",
        headers=get_auth_headers(),
        timeout=180.0,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["site_id"] == "terraform-aws"
    assert data["count"] == len(data["links"])
    assert len(data["links"]) > 0
    assert all(link.startswith("http") for link in data["links"][:5])

