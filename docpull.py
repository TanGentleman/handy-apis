#!/usr/bin/env python3
"""CLI tool to fetch documentation from the content-scraper API."""

import json
import os
import sys
from urllib.parse import urlparse

import httpx

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

_ENV = os.environ.get("ENVIRONMENT", "dev")
_USERNAME = os.environ.get("MODAL_USERNAME", "tangentleman")
_SUFFIX = "-dev" if _ENV == "dev" else ""

API_BASE = f"https://{_USERNAME}--content-scraper-api-fastapi-app{_SUFFIX}.modal.run"


def get_auth_headers() -> dict:
    key = os.environ.get("MODAL_KEY")
    secret = os.environ.get("MODAL_SECRET")
    if key and secret:
        return {"Modal-Key": key, "Modal-Secret": secret}
    return {}


def cmd_sites():
    """List all available site IDs."""
    resp = httpx.get(f"{API_BASE}/sites", headers=get_auth_headers())
    resp.raise_for_status()
    data = resp.json()
    for site in data["sites"]:
        print(site["id"])


def cmd_links(site_id: str, save: bool = False, force: bool = False):
    """Get all documentation links for a site."""
    params = {"max_age": 0} if force else {}
    resp = httpx.get(
        f"{API_BASE}/sites/{site_id}/links",
        params=params,
        headers=get_auth_headers(),
        timeout=120.0,
    )
    resp.raise_for_status()
    data = resp.json()
    for link in data["links"]:
        print(link)
    print(f"\nTotal: {data['count']} links", file=sys.stderr)

    if save:
        out_dir = "./data"
        os.makedirs(out_dir, exist_ok=True)
        out_path = f"{out_dir}/{site_id}_links.json"
        import json

        with open(out_path, "w") as f:
            json.dump({f"{site_id}_links": data["links"]}, f, indent=2)
        print(f"Saved to {out_path}", file=sys.stderr)


def cmd_content(site_id: str, path: str, force: bool = False):
    """Get content from a specific page path."""
    params = {"path": path}
    if force:
        params["max_age"] = 0  # Force fresh scrape

    resp = httpx.get(
        f"{API_BASE}/sites/{site_id}/content",
        params=params,
        headers=get_auth_headers(),
        timeout=120.0,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["content"]

    # Sanitize path for filename
    safe_path = path.strip("/").replace("/", "_") or "index"
    out_dir = f"./docs/{site_id}"
    os.makedirs(out_dir, exist_ok=True)
    out_path = f"{out_dir}/{safe_path}.md"

    with open(out_path, "w") as f:
        f.write(content)

    cache_status = "(cached)" if data.get("from_cache") else "(fresh)"
    print(f"Saved to {out_path} ({len(content)} chars) {cache_status}")


def cmd_index(site_id: str, max_concurrent: int = 50):
    """Fetch and save all pages from a site using parallel bulk API."""
    print(f"Indexing {site_id}...", file=sys.stderr)

    # Use the parallel bulk indexing API endpoint
    resp = httpx.post(
        f"{API_BASE}/sites/{site_id}/index",
        params={"max_concurrent": max_concurrent},
        headers=get_auth_headers(),
        timeout=600.0,  # 10 minute timeout for large sites
    )
    resp.raise_for_status()
    data = resp.json()

    cached = data.get("cached", 0)
    scraped = data.get("scraped", 0)
    print(
        f"\nTotal: {data['total']} pages | Cached: {cached} | Scraped: {scraped}",
        file=sys.stderr,
    )
    print(
        f"Success: {data['successful']} | Failed: {data['failed']}",
        file=sys.stderr,
    )
    if data.get("errors"):
        print("\nFirst 10 errors:", file=sys.stderr)
        for err in data["errors"]:
            print(f"  {err['path']}: {err['error']}", file=sys.stderr)


def cmd_discover(url: str):
    """Analyze a documentation page and suggest configuration.

    Args:
        url: Full URL of a documentation page to analyze

    Prints comprehensive discovery results including:
    - Framework detection
    - Working copy buttons
    - Ranked content selectors
    - Link patterns
    - Ready-to-use configuration snippet
    """
    # Validate URL format
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        print(f"Error: Invalid URL format: {url}", file=sys.stderr)
        print("URL must include protocol (e.g., https://example.com)", file=sys.stderr)
        sys.exit(1)

    if parsed.scheme not in ('http', 'https'):
        print(f"Error: Unsupported protocol: {parsed.scheme}", file=sys.stderr)
        print("Only http:// and https:// URLs are supported", file=sys.stderr)
        sys.exit(1)

    print(f"Analyzing {url}...\n", file=sys.stderr)

    try:
        resp = httpx.get(
            f"{API_BASE}/discover",
            params={"url": url},
            headers=get_auth_headers(),
            timeout=60.0,
        )
        resp.raise_for_status()
        data = resp.json()
    except httpx.HTTPStatusError as e:
        print(f"Error: HTTP {e.response.status_code}", file=sys.stderr)
        try:
            error_detail = e.response.json().get("detail", str(e))
            print(f"Details: {error_detail}", file=sys.stderr)
        except Exception:
            print(f"Details: {e}", file=sys.stderr)
        sys.exit(1)
    except httpx.TimeoutException:
        print("Error: Request timed out (60s)", file=sys.stderr)
        print("The page may be slow to load or unresponsive", file=sys.stderr)
        sys.exit(1)
    except httpx.HTTPError as e:
        print(f"Error: Failed to connect to API: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse URL for fallback suggestions
    parsed = urlparse(url)

    print("=" * 70)
    print(f"DISCOVERY RESULTS FOR: {url}")
    print("=" * 70)

    # Framework detection
    framework = data.get('framework', 'unknown')
    print(f"\nFramework Detected: {framework.upper()}")
    print(f"Suggested Base URL: {data['base_url_suggestion']}")

    # Copy buttons section
    print("\n" + "-" * 70)
    print("COPY BUTTONS (tested with live page load):")
    print("-" * 70)
    copy_buttons = data.get("copy_buttons", [])
    if copy_buttons:
        working_buttons = [b for b in copy_buttons if b.get("works")]
        if working_buttons:
            print(f"\n  Found {len(working_buttons)} working copy button(s):\n")
            for i, btn in enumerate(working_buttons, 1):
                print(f"  {i}. {btn['selector']}")
                print(f"     Tested: {btn['chars']:,} chars extracted\n")

        failed_buttons = [b for b in copy_buttons if not b.get("works")]
        if failed_buttons:
            print(f"  Found {len(failed_buttons)} non-working button(s):")
            for btn in failed_buttons:
                error = btn.get('error', 'unknown')[:60]
                print(f"    - {btn['selector']} (Error: {error})")
    else:
        print("  No copy buttons detected")

    # Content selectors section
    print("\n" + "-" * 70)
    print("CONTENT SELECTORS (ranked by quality):")
    print("-" * 70)
    content_selectors = data.get("content_selectors", [])
    if content_selectors:
        print(f"\n  Found {len(content_selectors)} viable selector(s):\n")
        for i, sel in enumerate(content_selectors[:5], 1):
            marker = "[RECOMMENDED]" if sel.get("recommended") else ""
            print(f"  {i}. {sel['selector']} {marker}")
            print(f"     {sel['text_chars']:,} text chars | {sel['chars']:,} HTML chars\n")
    else:
        print("  WARNING: No content selectors found with substantial content")

    # Link analysis section
    link_data = data.get("link_analysis", {})
    total_links = link_data.get('total_internal_links', 0)

    print("-" * 70)
    print(f"LINK ANALYSIS:")
    print("-" * 70)
    print(f"\n  Total internal links: {total_links}")

    patterns = link_data.get("path_patterns", [])
    if patterns:
        print(f"\n  Path patterns (by frequency):")
        for pattern, count in patterns[:5]:
            pct = (count / total_links * 100) if total_links > 0 else 0
            print(f"    {pattern:20} {count:4} links ({pct:.1f}%)")
    else:
        print("\n  No clear path patterns detected")

    samples = link_data.get("sample_links", [])
    if samples:
        print(f"\n  Sample links ({min(5, len(samples))} of {len(samples)}):")
        for link in samples[:5]:
            print(f"    {link}")

    # Generate suggested config
    print("\n" + "=" * 70)
    print("SUGGESTED CONFIGURATION:")
    print("=" * 70)

    # Determine best content extraction method
    if copy_buttons and any(b.get("works") for b in copy_buttons):
        best_copy = next(b for b in copy_buttons if b.get("works"))
        content_config = f'''  "content": {{
    "mode": "browser",
    "waitFor": "{best_copy['selector']}",
    "selector": "{best_copy['selector']}",
    "method": "click_copy"
  }}'''
        method_note = "  # Using copy button (most reliable)"
    elif content_selectors:
        best_selector = content_selectors[0]
        content_config = f'''  "content": {{
    "mode": "browser",
    "waitFor": "{best_selector['selector']}",
    "selector": "{best_selector['selector']}",
    "method": "inner_html"
  }}'''
        method_note = "  # Using content selector"
    else:
        content_config = '''  "content": {
    "mode": "browser",
    "selector": "main",
    "method": "inner_html"
  }'''
        method_note = "  # WARNING: Using fallback selector - may need adjustment"

    # Determine link crawling config
    if patterns:
        best_pattern = patterns[0][0].rstrip('/')
        link_config = f'''  "links": {{
    "startUrls": [""],
    "pattern": "{best_pattern}",
    "maxDepth": 2
  }}'''
        link_note = f"  # Pattern covers {patterns[0][1]} links"
    else:
        fallback_pattern = f"/{parsed.path.split('/')[1]}" if parsed.path and len(parsed.path.split('/')) > 1 else ""
        link_config = f'''  "links": {{
    "startUrls": [""],
    "pattern": "{fallback_pattern}",
    "maxDepth": 2
  }}'''
        link_note = "  # WARNING: No clear pattern found - verify this setting"

    # Print final config
    print(f'''
"your-site-id": {{
  "name": "Your Site Name",
  "baseUrl": "{data['base_url_suggestion']}",
  "mode": "fetch",
{link_config},
{link_note}
{content_config}
{method_note}
}}
''')

    print("=" * 70)
    print("NEXT STEPS:")
    print("=" * 70)
    print("""
1. Review the suggested configuration above
2. Add it to scraper/config/sites.json (replace 'your-site-id')
3. Test link discovery:
   python docpull.py links your-site-id

4. Test content extraction (use a path from sample links):
   python docpull.py content your-site-id <path>

5. If tests pass, index the entire site:
   python docpull.py index your-site-id
""")
    print("=" * 70)


def cmd_cache(action: str = "stats", site_id: str = None):
    """Manage cache: stats, clear <site_id>, or clear-all."""
    if action == "stats":
        resp = httpx.get(f"{API_BASE}/cache/stats", headers=get_auth_headers())
        resp.raise_for_status()
        data = resp.json()
        print(f"Total cache entries: {data['total_entries']}")
        print("\nBy type:")
        for type_name, count in data["by_type"].items():
            print(f"  {type_name}: {count}")
        print("\nBy site:")
        for site, count in data["by_site"].items():
            print(f"  {site}: {count}")
    elif action == "clear" and site_id:
        resp = httpx.delete(f"{API_BASE}/cache/{site_id}", headers=get_auth_headers())
        resp.raise_for_status()
        print(f"Cleared {resp.json()['deleted']} cache entries for {site_id}")
    else:
        print("Usage: docpull cache stats")
        print("       docpull cache clear <site_id>")


def print_usage():
    print("""Usage: docpull <command> [args]

Commands:
  sites                            List all available site IDs
  discover <url>                   Analyze a docs page and suggest selectors
  links <site_id>                  Get all doc links for a site
  links <site_id> --save           Also save links to ./data/<site_id>_links.json
  links <site_id> --force          Force fresh crawl (bypass cache)
  content <site_id> <path>         Get content (uses cache if <1hr old)
  content <site_id> <path> --force Force fresh scrape (also clears error tracking)
  index <site_id>                  Fetch and cache all pages from a site
  cache stats                      Show cache statistics
  cache clear <site_id>            Clear cache for a site

Examples:
  docpull sites
  docpull discover https://cursor.com/docs/get-started/quickstart
  docpull links cursor --save
  docpull content modal /guide
  docpull index modal
  docpull cache stats
""")


def main():
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "sites":
        cmd_sites()
    elif cmd == "discover" and len(sys.argv) >= 3:
        cmd_discover(sys.argv[2])
    elif cmd == "links" and len(sys.argv) >= 3:
        save = "--save" in sys.argv
        force = "--force" in sys.argv
        cmd_links(sys.argv[2], save=save, force=force)
    elif cmd == "content" and len(sys.argv) >= 4:
        force = "--force" in sys.argv
        cmd_content(sys.argv[2], sys.argv[3], force=force)
    elif cmd == "index" and len(sys.argv) >= 3:
        cmd_index(sys.argv[2])
    elif cmd == "cache" and len(sys.argv) >= 2:
        if len(sys.argv) == 2 or sys.argv[2] == "stats":
            cmd_cache("stats")
        elif len(sys.argv) >= 4 and sys.argv[2] == "clear":
            cmd_cache("clear", sys.argv[3])
        else:
            print_usage()
            sys.exit(1)
    elif cmd in ("--help", "-h", "help"):
        print_usage()
    else:
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
