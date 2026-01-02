"""Client for the documentation collection API endpoints."""

import os
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv


def validate_api_url() -> str:
    """Validate API URL and return it with the correct suffix."""
    required = ["MODAL_USERNAME", "MODAL_KEY", "MODAL_SECRET"]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

    env = os.environ.get("ENVIRONMENT", "prod")
    url_suffix = "-dev" if env == "dev" else ""
    return f"https://{os.environ['MODAL_USERNAME']}--content-scraper-api-fastapi-app{url_suffix}.modal.run"


def get_headers() -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "Modal-Key": os.environ.get("MODAL_KEY"),
        "Modal-Secret": os.environ.get("MODAL_SECRET")
    }


def list_sites(verbose: bool = True) -> Dict:
    """List all configured documentation sites."""
    load_dotenv()
    base_url = validate_api_url()

    response = requests.get(f"{base_url}/sites", headers=get_headers())
    result = response.json()

    if verbose:
        print("Configured Sites:")
        for site_id, site_info in result.get("sites", {}).items():
            pages = site_info.get("pages", [])
            print(f"  {site_id} ({site_info.get('name')})")
            print(f"    Base URL: {site_info.get('base_url')}")
            print(f"    Sections: {site_info.get('sections')}")
            print(f"    Pages: {pages}")

    return result


def list_site_docs(site: str, verbose: bool = True) -> Dict:
    """List cached and configured pages for a site."""
    load_dotenv()
    base_url = validate_api_url()

    response = requests.get(f"{base_url}/docs/{site}", headers=get_headers())

    if response.status_code == 404:
        print(f"Error: {response.json().get('detail')}")
        return {}

    result = response.json()

    if verbose:
        print(f"Site: {result.get('name')} ({site})")
        print(f"  Configured pages: {result.get('configured_pages')}")
        print(f"  Cached pages: {result.get('cached_pages')}")
        stats = result.get("cache_stats", {})
        print(f"  Cache stats: {stats.get('pages')} pages, {stats.get('size_mb')} MB")

    return result


def get_doc(site: str, page: str, verbose: bool = True) -> str | None:
    """Get cached documentation content."""
    load_dotenv()
    base_url = validate_api_url()

    response = requests.get(f"{base_url}/docs/{site}/{page}", headers=get_headers())

    if response.status_code == 404:
        if verbose:
            print(f"Not cached: {response.json().get('detail')}")
        return None

    result = response.json()
    content = result.get("content", "")

    if verbose:
        print(f"Doc: {site}/{page}")
        print(f"  Scraped at: {result.get('scraped_at')}")
        print(f"  Content length: {result.get('content_length')} chars")
        print(f"  Preview: {content[:200]}..." if len(content) > 200 else f"  Content: {content}")

    return content


def refresh_doc(site: str, page: str, verbose: bool = True) -> Dict:
    """Scrape/refresh a documentation page."""
    load_dotenv()
    base_url = validate_api_url()

    if verbose:
        print(f"Refreshing {site}/{page}...")

    response = requests.post(f"{base_url}/docs/{site}/{page}/refresh", headers=get_headers())

    if response.status_code == 404:
        print(f"Error: {response.json().get('detail')}")
        return {}

    if response.status_code == 500:
        print(f"Scraping failed: {response.json().get('detail')}")
        return {}

    result = response.json()

    if verbose:
        print(f"  URL: {result.get('url')}")
        print(f"  Content length: {result.get('content_length')} chars")
        print(f"  Processing time: {result.get('processing_time_seconds'):.2f}s")

    return result


def refresh_all_docs(sites_list: Optional[List[str]] = None, verbose: bool = True) -> Dict[str, Dict]:
    """Refresh all configured pages for specified sites (or all sites)."""
    load_dotenv()
    base_url = validate_api_url()

    # Get all sites
    sites_response = requests.get(f"{base_url}/sites", headers=get_headers())
    all_sites = sites_response.json().get("sites", {})

    if sites_list:
        all_sites = {k: v for k, v in all_sites.items() if k in sites_list}

    results = {}
    for site_id, site_info in all_sites.items():
        results[site_id] = {}
        for page in site_info.get("pages", []):
            if verbose:
                print(f"Refreshing {site_id}/{page}...")
            result = refresh_doc(site_id, page, verbose=False)
            results[site_id][page] = result
            if verbose and result:
                print(f"  Done: {result.get('content_length')} chars in {result.get('processing_time_seconds', 0):.2f}s")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Documentation collection client")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # list-sites
    subparsers.add_parser("list-sites", help="List all configured sites")

    # list-docs
    list_docs_parser = subparsers.add_parser("list-docs", help="List docs for a site")
    list_docs_parser.add_argument("site", help="Site ID")

    # get
    get_parser = subparsers.add_parser("get", help="Get cached doc content")
    get_parser.add_argument("site", help="Site ID")
    get_parser.add_argument("page", help="Page name")
    get_parser.add_argument("--full", action="store_true", help="Print full content")

    # refresh
    refresh_parser = subparsers.add_parser("refresh", help="Refresh a doc")
    refresh_parser.add_argument("site", help="Site ID")
    refresh_parser.add_argument("page", help="Page name")

    # refresh-all
    refresh_all_parser = subparsers.add_parser("refresh-all", help="Refresh all docs")
    refresh_all_parser.add_argument("--sites", nargs="+", help="Limit to specific sites")

    args = parser.parse_args()

    if args.command == "list-sites":
        list_sites()
    elif args.command == "list-docs":
        list_site_docs(args.site)
    elif args.command == "get":
        content = get_doc(args.site, args.page, verbose=not args.full)
        if args.full and content:
            print(content)
    elif args.command == "refresh":
        refresh_doc(args.site, args.page)
    elif args.command == "refresh-all":
        refresh_all_docs(args.sites)
    else:
        parser.print_help()
