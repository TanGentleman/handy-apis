"""Manual tests for the content-scraper Modal API endpoints.

Usage:
    python tests/test_modal.py           # Run all tests sequentially
    python tests/test_modal.py parallel  # Fetch all 9 sites in parallel
"""

import asyncio
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.environ.get(
    "SCRAPER_API_URL",
    "https://tangentleman--content-scraper-api-fastapi-app-dev.modal.run",
)

DEFAULT_TIMEOUT = 15.0
CONTENT_TIMEOUT = 180.0
MAX_CONCURRENCY = 50

ALL_SITES = [
    "modal",
    "convex",
    "terraform-aws",
    "cursor",
    "claude-platform",
    "claude-code",
    "unsloth",
    "playwright",
    "datadog",
]

SITE_TEST_PATHS = {
    "modal": "/guide/dicts",
    "convex": "/functions/http-actions",
    "terraform-aws": "/resources/acm_certificate",
    "cursor": "/agent/browser",
    "claude-platform": "/agent-sdk/mcp",
    "claude-code": "/headless",
    "unsloth": "/basics/chat-templates",
    "playwright": "/evaluating",
    "datadog": "/tracing/trace_explorer",
}


def get_auth_headers() -> dict:
    """Get Modal auth headers from environment variables."""
    key = os.environ.get("MODAL_KEY")
    secret = os.environ.get("MODAL_SECRET")
    if key and secret:
        return {"Modal-Key": key, "Modal-Secret": secret}
    return {}


async def _fetch_with_semaphore(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    site_id: str,
    path: str,
) -> dict:
    """Fetch content for a single site with semaphore control."""
    async with semaphore:
        try:
            resp = await client.get(
                f"{API_BASE}/sites/{site_id}/content",
                params={"path": path},
                headers=get_auth_headers(),
            )
            if resp.status_code != 200:
                return {"site_id": site_id, "error": f"HTTP {resp.status_code}"}
            data = resp.json()
            return {
                "site_id": site_id,
                "path": data["path"],
                "content_length": data["content_length"],
                "from_cache": data.get("from_cache", False),
            }
        except Exception as e:
            return {"site_id": site_id, "error": str(e)}


async def fetch_all_parallel() -> tuple[dict, bool]:
    """Fetch content from all providers in parallel using semaphore."""
    print(f"\nFetching content from {len(ALL_SITES)} sites (max concurrency: {MAX_CONCURRENCY})...")
    print("=" * 60)

    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    results = {}
    all_ok = True

    async with httpx.AsyncClient(timeout=CONTENT_TIMEOUT) as client:
        tasks = [
            _fetch_with_semaphore(client, semaphore, site_id, SITE_TEST_PATHS[site_id])
            for site_id in ALL_SITES
        ]
        responses = await asyncio.gather(*tasks)

    for result in responses:
        site_id = result["site_id"]
        results[site_id] = result
        if "error" in result:
            print(f"  {site_id}: ✗ {result['error']}")
            all_ok = False
        else:
            status = "from_cache" if result["from_cache"] else "fresh"
            print(f"  {site_id}: ✓ {result['content_length']} chars ({status})")

    return results, all_ok


async def verify_all_cached() -> bool:
    """Verify all providers return cached responses."""
    print("\nVerifying cache status...")
    print("=" * 60)

    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
    all_cached = True

    async with httpx.AsyncClient(timeout=CONTENT_TIMEOUT) as client:
        tasks = [
            _fetch_with_semaphore(client, semaphore, site_id, SITE_TEST_PATHS[site_id])
            for site_id in ALL_SITES
        ]
        results = await asyncio.gather(*tasks)

    for result in results:
        site_id = result["site_id"]
        if "error" in result:
            print(f"  {site_id}: ✗ {result['error']}")
            all_cached = False
        elif result.get("from_cache"):
            print(f"  {site_id}: ✓ cached")
        else:
            print(f"  {site_id}: ✗ not cached")
            all_cached = False

    return all_cached


def run_sequential_tests():
    """Run all tests sequentially with verbose output."""
    print(f"Testing API: {API_BASE}")
    print("=" * 60)

    # Basic endpoints
    tests = [
        ("Root", f"{API_BASE}/", None),
        ("Health", f"{API_BASE}/health", None),
        ("Sites", f"{API_BASE}/sites", None),
    ]

    for name, url, params in tests:
        print(f"\n{name} endpoint...")
        resp = httpx.get(url, params=params, headers=get_auth_headers(), timeout=DEFAULT_TIMEOUT)
        if resp.status_code == 200:
            print(f"  ✓ {resp.json()}")
        else:
            print(f"  ✗ HTTP {resp.status_code}: {resp.text[:100]}")

    # Links endpoint
    print("\nLinks (modal)...")
    resp = httpx.get(
        f"{API_BASE}/sites/modal/links",
        headers=get_auth_headers(),
        timeout=CONTENT_TIMEOUT,
    )
    if resp.status_code == 200:
        print(f"  ✓ {resp.json()['count']} links")
    else:
        print(f"  ✗ HTTP {resp.status_code}")

    # Content endpoint
    print("\nContent (modal /guide)...")
    resp = httpx.get(
        f"{API_BASE}/sites/modal/content",
        params={"path": "/guide"},
        headers=get_auth_headers(),
        timeout=CONTENT_TIMEOUT,
    )
    if resp.status_code == 200:
        print(f"  ✓ {resp.json()['content_length']} chars")
    else:
        print(f"  ✗ HTTP {resp.status_code}")

    print("\n" + "=" * 60)
    print("Sequential tests completed!")


async def run_parallel_tests():
    """Fetch all 9 sites in parallel, then verify caching."""
    print(f"Testing API: {API_BASE}")

    _, all_ok = await fetch_all_parallel()
    if not all_ok:
        print("\n⚠ Some providers failed")

    all_cached = await verify_all_cached()

    print("\n" + "=" * 60)
    print("✓ All cached!" if all_cached else "✗ Some not cached")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "parallel":
        asyncio.run(run_parallel_tests())
    else:
        run_sequential_tests()
