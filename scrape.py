import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv


@dataclass
class PageInfo:
    """URL and associated selectors for a page."""
    url: str
    selectors: Dict[str, str]
    site_name: str


def _load_selectors_data() -> Dict:
    """Load selectors data from JSON file."""
    with open(Path(__file__).parent / "selectors.json") as f:
        return json.load(f)


SELECTORS_DATA = _load_selectors_data()


def get_page_info(site_name: str, page_name: str) -> PageInfo:
    """Get PageInfo for a specific site and page."""
    site = SELECTORS_DATA["sites"].get(site_name)
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
    for site_name, site in SELECTORS_DATA["sites"].items():
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
        {"url": p.url, "selector": p.selectors["copyButton"], "site_name": p.site_name}
        for p in get_all_pages(sites_list)
        if "copyButton" in p.selectors
    ]


def get_available_sites() -> List[str]:
    """Get list of all available site names."""
    return list(SELECTORS_DATA["sites"].keys())


def batch_scrape(sites_list: Optional[List[str]] = None, verbose: bool = True) -> Dict[str, Dict[str, str]]:
    """Scrape all pages and return docs organized by site/page."""
    load_dotenv()
    
    modal_username = os.environ.get("MODAL_USERNAME")
    modal_key = os.environ.get("MODAL_KEY")
    modal_secret = os.environ.get("MODAL_SECRET")
    env = os.environ.get("ENVIRONMENT", "prod")
    url_suffix = "-dev" if env == "dev" else ""
    
    base_url = f"https://{modal_username}--content-scraper-api-fastapi-app{url_suffix}.modal.run"
    
    if verbose:
        print(f"Using environment: {env}")
        print(f"API URL: {base_url}")
    
    scrape_requests = get_scrape_requests(sites_list)
    
    if verbose:
        print("Calling batch scrape endpoint...")
    
    response = requests.post(
        f"{base_url}/scrape/batch",
        headers={
            "Content-Type": "application/json",
            "Modal-Key": modal_key,
            "Modal-Secret": modal_secret
        },
        json={"requests": scrape_requests}
    )
    
    result = response.json()
    
    if verbose:
        print("Response received!")
        print(f"Total: {result.get('total')} | Success: {result.get('successful')} | Failed: {result.get('failed')}")
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
