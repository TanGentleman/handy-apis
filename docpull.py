#!/usr/bin/env python3
"""CLI tool to fetch documentation from the content-scraper API."""

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

    # Sanitize path for filename
    safe_path = path.strip("/").replace("/", "_") or "index"
    out_dir = f"./docs/{site_id}"
    os.makedirs(out_dir, exist_ok=True)
    out_path = f"{out_dir}/{safe_path}.md"

    with open(out_path, "w") as f:
        f.write(data["content"])

    cache_status = "(cached)" if data.get("from_cache") else "(fresh)"
    print(f"Saved to {out_path} ({data['content_length']} chars) {cache_status}")


def print_usage():
    print("""Usage: docpull <command> [args]

Commands:
  sites                            List all available site IDs
  links <site_id>                  Get all doc links for a site
  links <site_id> --save           Also save links to ./data/<site_id>_links.json
  content <site_id> <path>         Get content (uses cache if <1hr old)
  content <site_id> <path> --force Force fresh scrape, ignore cache

Examples:
  docpull sites
  docpull links cursor --save
  docpull content modal /guide
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
    elif cmd in ("--help", "-h", "help"):
        print_usage()
    else:
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()