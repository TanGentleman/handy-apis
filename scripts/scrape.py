import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
from typing_extensions import TypedDict

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

@dataclass
class PageInfo:
    """URL and associated selectors for a page."""
    url: str
    selectors: Dict[str, str]
    site_name: str


def load_selectors_data() -> Dict:
    """Load selectors data from JSON file."""
    with open(Path(__file__).parent.parent / "data" / "selectors.json") as f:
        return json.load(f)


SELECTORS_DATA = load_selectors_data()

def get_page_info(site_name: str, page_name: str) -> PageInfo:
    """Get PageInfo for a specific site and page."""
    data = load_selectors_data()
    site = data["sites"].get(site_name)
    if not site:
        raise ValueError(f"Site '{site_name}' not found")
    
    page_path = site["pages"].get(page_name)
    if not page_path:
        raise ValueError(f"Page '{page_name}' not found in site '{site_name}'")
    
    return PageInfo(
        url=site["baseUrl"] + page_path,
        selectors=site.get("selectors", {}),
        site_name=site_name
    )


def get_all_pages(sites_list: Optional[List[str]] = None) -> List[PageInfo]:
    """Get all pages, optionally filtered by site names."""
    pages = []
    data = load_selectors_data()
    for site_name, site in data["sites"].items():
        if sites_list and site_name not in sites_list:
            continue
        selectors = site.get("selectors", {})
        for page_path in site["pages"].values():
            pages.append(PageInfo(
                url=site["baseUrl"] + page_path,
                selectors=selectors,
                site_name=site_name
            ))
    return pages


def get_scrape_requests(sites_list: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """Get scrape request payloads for pages with copyButton selector."""
    return [
        {
            "url": p.url,
            "selector": p.selectors["copyButton"],
            "method": p.selectors.get("method", "click_copy"),
            "site_name": p.site_name,
        }
        for p in get_all_pages(sites_list)
        if "copyButton" in p.selectors
    ]


def get_available_sites() -> List[str]:
    """Get list of all available site names."""
    data = load_selectors_data()
    return list(data["sites"].keys())


def batch_scrape(
    sites_list: Optional[List[str]] = None,
    use_cache: bool = True,
    verbose: bool = True,
) -> Dict[str, Dict[str, str]]:
    """Scrape all pages and return docs organized by site/page."""
    load_dotenv()

    base_url = validate_api_url()
    env = os.environ.get("ENVIRONMENT", "prod")

    if verbose:
        print(f"Using environment: {env}")
        print(f"API URL: {base_url}")
        print(f"Cache enabled: {use_cache}")

    scrape_requests = get_scrape_requests(sites_list)

    if verbose:
        print("Calling batch scrape endpoint...")

    response = requests.post(
        f"{base_url}/scrape/batch",
        headers=get_headers(),
        json={"requests": scrape_requests, "use_cache": use_cache}
    )
    
    result = response.json()

    if verbose:
        print("Response received!")
        print(f"Total: {result.get('total')} | Success: {result.get('successful')} | Failed: {result.get('failed')} | Cached: {result.get('cached', 0)}")
        print(f"Processing time: {result.get('total_processing_time_seconds')}s")
    
    # Build docs dictionary from results
    docs = {}
    for i, res in enumerate(result.get('results', [])):
        if i < len(scrape_requests):
            site_name = scrape_requests[i].get('site_name', 'unknown')
            url = scrape_requests[i].get('url', '')
            page_name = url.rstrip('/').split('/')[-1] if url else f'page_{i}'
            content = res.get('content', '')
            
            if site_name not in docs:
                docs[site_name] = {}
            docs[site_name][page_name] = content
            
            if verbose:
                print(f"  {site_name}/{page_name}: {res.get('processing_time_seconds', 0)}s ({len(content)} chars)")
    
    return docs
