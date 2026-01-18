"""Concise client for the Convex API."""

import os
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv


API_URL = os.environ.get("CONVEX_API_URL", "https://tangentleman--convex-api-fastapi-app-dev.modal.run")


def _get(url: str, **kwargs) -> Dict:
    """GET request helper."""
    response = requests.get(url, **kwargs)
    response.raise_for_status()
    return response.json()


def _post(url: str, json: Dict, **kwargs) -> Dict:
    """POST request helper."""
    response = requests.post(url, json=json, **kwargs)
    response.raise_for_status()
    return response.json()


def _delete(url: str, **kwargs) -> Dict:
    """DELETE request helper."""
    response = requests.delete(url, **kwargs)
    response.raise_for_status()
    return response.json()


# Sites
def list_sites() -> Dict:
    """List all configured sites."""
    return _get(f"{API_URL}/sites")


def get_site(site_id: str) -> Dict:
    """Get a specific site configuration."""
    return _get(f"{API_URL}/sites/{site_id}")


def create_site(site_id: str, name: str, base_url: str, selector: str, 
                pages: Dict[str, str], method: str = "click_copy", 
                sections: Optional[Dict[str, str]] = None) -> Dict:
    """Create or update a site."""
    return _post(f"{API_URL}/sites/create", json={
        "siteId": site_id,
        "name": name,
        "baseUrl": base_url,
        "selector": selector,
        "method": method,
        "pages": pages,
        "sections": sections or {}
    })


def delete_site(site_id: str) -> Dict:
    """Delete a site."""
    return _delete(f"{API_URL}/sites/{site_id}")


# Docs
def list_docs(site_id: str) -> Dict:
    """List all docs for a site."""
    return _get(f"{API_URL}/sites/{site_id}/docs")


def get_doc(site_id: str, page: str) -> Dict:
    """Get a specific doc."""
    return _get(f"{API_URL}/sites/{site_id}/docs/{page}")


def save_doc(site_id: str, page: str, url: str, markdown: str) -> Dict:
    """Save or update a doc."""
    return _post(f"{API_URL}/sites/{site_id}/docs/save", json={
        "siteId": site_id,
        "page": page,
        "url": url,
        "markdown": markdown
    })


def delete_doc(site_id: str, page: str) -> Dict:
    """Delete a doc."""
    return _delete(f"{API_URL}/sites/{site_id}/docs/{page}")


def get_doc_by_url(url: str) -> Dict:
    """Get a doc by its URL."""
    return _get(f"{API_URL}/docs/by-url", params={"url": url})


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Convex API client")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    subparsers.add_parser("list-sites", help="List all sites")
    
    get_site_parser = subparsers.add_parser("get-site", help="Get site config")
    get_site_parser.add_argument("site_id", help="Site ID")

    create_site_parser = subparsers.add_parser("create-site", help="Create site")
    create_site_parser.add_argument("site_id", help="Site ID")
    create_site_parser.add_argument("name", help="Site name")
    create_site_parser.add_argument("base_url", help="Base URL")
    create_site_parser.add_argument("selector", help="CSS selector")
    create_site_parser.add_argument("--method", default="click_copy", help="Method")
    create_site_parser.add_argument("--pages", required=True, help='JSON pages dict, e.g. \'{"page1": "/path1"}\'')

    list_docs_parser = subparsers.add_parser("list-docs", help="List docs")
    list_docs_parser.add_argument("site_id", help="Site ID")

    get_doc_parser = subparsers.add_parser("get-doc", help="Get doc")
    get_doc_parser.add_argument("site_id", help="Site ID")
    get_doc_parser.add_argument("page", help="Page name")

    save_doc_parser = subparsers.add_parser("save-doc", help="Save doc")
    save_doc_parser.add_argument("site_id", help="Site ID")
    save_doc_parser.add_argument("page", help="Page name")
    save_doc_parser.add_argument("url", help="Full URL")
    save_doc_parser.add_argument("markdown", help="Markdown content")

    args = parser.parse_args()

    load_dotenv()

    if args.command == "list-sites":
        result = list_sites()
        print(f"Total sites: {result['total']}")
        for site in result["sites"]:
            print(f"  {site['siteId']}: {site['name']}")
    elif args.command == "get-site":
        print(get_site(args.site_id))
    elif args.command == "create-site":
        import json
        pages = json.loads(args.pages)
        result = create_site(args.site_id, args.name, args.base_url, 
                           args.selector, pages, args.method)
        print(f"Site {'updated' if result.get('updated') else 'created'}: {result['siteId']}")
    elif args.command == "list-docs":
        result = list_docs(args.site_id)
        print(f"Total docs: {result['total']}")
        for doc in result["docs"]:
            print(f"  {doc['page']}: {doc['url']}")
    elif args.command == "get-doc":
        doc = get_doc(args.site_id, args.page)
        print(f"Page: {doc['page']}")
        print(f"URL: {doc['url']}")
        print(f"Content length: {len(doc['markdown'])} chars")
        print(f"\nContent:\n{doc['markdown'][:500]}...")
    elif args.command == "save-doc":
        result = save_doc(args.site_id, args.page, args.url, args.markdown)
        print(f"Doc saved: {result['siteId']}/{result['page']}")
        print(f"Content hash: {result['contentHash']}")
    else:
        parser.print_help()

