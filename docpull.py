#!/usr/bin/env python3
"""CLI tool to fetch documentation from the content-scraper API."""

import re
import sys
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

API_BASE = os.environ.get(
    "SCRAPER_API_URL",
    "https://tangentleman--content-scraper-api-fastapi-app-dev.modal.run"
)


def get_auth_headers() -> dict:
    key = os.environ.get("MODAL_KEY")
    secret = os.environ.get("MODAL_SECRET")
    if key and secret:
        return {"Modal-Key": key, "Modal-Secret": secret}
    return {}


def html_to_markdown(html: str) -> str:
    """Convert HTML to markdown."""
    md = html
    # Headers
    for i in range(1, 7):
        md = re.sub(rf'<h{i}[^>]*>(.*?)</h{i}>', rf'\n{"#"*i} \1\n\n', md, flags=re.DOTALL | re.IGNORECASE)
    # Code blocks
    md = re.sub(r'<pre[^>]*><code[^>]*>(.*?)</code></pre>', r'\n```\n\1\n```\n\n', md, flags=re.DOTALL)
    md = re.sub(r'<pre[^>]*>(.*?)</pre>', r'\n```\n\1\n```\n\n', md, flags=re.DOTALL)
    md = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', md, flags=re.DOTALL)
    # Bold/italic
    md = re.sub(r'<(strong|b)[^>]*>(.*?)</\1>', r'**\2**', md, flags=re.DOTALL | re.IGNORECASE)
    md = re.sub(r'<(em|i)[^>]*>(.*?)</\1>', r'*\2*', md, flags=re.DOTALL | re.IGNORECASE)
    # Links
    md = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', md, flags=re.DOTALL)
    # Lists
    def convert_list(m, marker_fn):
        items = re.findall(r'<li[^>]*>(.*?)</li>', m.group(1), flags=re.DOTALL)
        return '\n' + '\n'.join(marker_fn(i, item.strip()) for i, item in enumerate(items)) + '\n\n'
    md = re.sub(r'<ul[^>]*>(.*?)</ul>', lambda m: convert_list(m, lambda i, t: f'- {t}'), md, flags=re.DOTALL)
    md = re.sub(r'<ol[^>]*>(.*?)</ol>', lambda m: convert_list(m, lambda i, t: f'{i+1}. {t}'), md, flags=re.DOTALL)
    # Paragraphs/breaks
    md = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', md, flags=re.DOTALL)
    md = re.sub(r'<br\s*/?>', '\n', md)
    # Strip remaining tags
    md = re.sub(r'<[^>]+>', '', md)
    # Cleanup
    md = re.sub(r'\n{3,}', '\n\n', md)
    md = re.sub(r'Copy\n', '', md)
    md = md.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&').replace('&quot;', '"').replace('&#39;', "'")
    return md.strip()


def cmd_sites():
    """List all available site IDs."""
    resp = httpx.get(f"{API_BASE}/sites", headers=get_auth_headers())
    resp.raise_for_status()
    sites = resp.json()["sites"]
    for s in sites:
        print(s)


def cmd_links(site_id: str, save: bool = False):
    """Get all documentation links for a site."""
    resp = httpx.get(
        f"{API_BASE}/sites/{site_id}/links",
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
    # Convert HTML to markdown if needed
    if content.lstrip().startswith("<"):
        content = html_to_markdown(content)

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


def cmd_cache(action: str = "stats", site_id: str = None):
    """Manage cache: stats, clear <site_id>, or clear-all."""
    if action == "stats":
        resp = httpx.get(f"{API_BASE}/cache/stats", headers=get_auth_headers())
        resp.raise_for_status()
        data = resp.json()
        print(f"Total cache entries: {data['total_entries']}")
        print(f"\nBy type:")
        for type_name, count in data["by_type"].items():
            print(f"  {type_name}: {count}")
        print(f"\nBy site:")
        for site, count in data["by_site"].items():
            print(f"  {site}: {count}")
    elif action == "clear" and site_id:
        resp = httpx.delete(
            f"{API_BASE}/cache/{site_id}", headers=get_auth_headers()
        )
        resp.raise_for_status()
        print(f"Cleared {resp.json()['deleted']} cache entries for {site_id}")
    else:
        print("Usage: docpull cache stats")
        print("       docpull cache clear <site_id>")


def print_usage():
    print("""Usage: docpull <command> [args]

Commands:
  sites                            List all available site IDs
  links <site_id>                  Get all doc links for a site
  links <site_id> --save           Also save links to ./data/<site_id>_links.json
  content <site_id> <path>         Get content (uses cache if <1hr old)
  content <site_id> <path> --force Force fresh scrape (also clears error tracking)
  index <site_id>                  Fetch and cache all pages from a site
  cache stats                      Show cache statistics
  cache clear <site_id>            Clear cache for a site

Examples:
  docpull sites
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
    elif cmd == "links" and len(sys.argv) >= 3:
        save = "--save" in sys.argv
        cmd_links(sys.argv[2], save=save)
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