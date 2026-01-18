import json
import os
import time
import asyncio
from pathlib import Path
import httpx
from dotenv import load_dotenv

load_dotenv()

SCRAPER_API = "https://tangentleman--content-scraper-api-fastapi-app-dev.modal.run"
CONVEX_API = "https://tangentleman--convex-api-fastapi-app-dev.modal.run"

def get_auth_headers() -> dict:
    """Get Modal auth headers from environment variables."""
    key = os.environ.get("MODAL_KEY")
    secret = os.environ.get("MODAL_SECRET")
    if key and secret:
        return {"Modal-Key": key, "Modal-Secret": secret}
    return {}

async def add_pages_to_site(pages_dict: dict[str, str], site_id: str = "modal") -> dict:
    """Add pages to a site's config in Convex."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Get current site config
        resp = await client.get(
            f"{CONVEX_API}/sites/{site_id}",
            headers=get_auth_headers(),
        )
        if resp.status_code == 404:
            raise Exception(f"Site '{site_id}' not found")
        resp.raise_for_status()
        current_site = resp.json()
        
        # Merge new pages with existing pages
        new_pages = {**current_site.get("pages", {}), **pages_dict}
        
        # Update the site with merged pages
        updated_site = {
            "siteId": site_id,
            "name": current_site["name"],
            "baseUrl": current_site["baseUrl"],
            "selector": current_site["selector"],
            "method": current_site.get("method", "click_copy"),
            "pages": new_pages,
            "sections": current_site.get("sections"),
        }
        
        resp = await client.post(
            f"{CONVEX_API}/sites/create",
            headers=get_auth_headers(),
            json=updated_site,
        )
        resp.raise_for_status()
        result = resp.json()
        
        return {
            "siteId": site_id,
            "updated": result.get("updated", False),
        }


async def scrape_modal_links(limit: int = 5):
    """Read modal_links.json and spawn scrape jobs for all links."""
    with open(Path(__file__).parent.parent / "data" / "modal_links.json", "r") as f:
        data = json.load(f)
    
    links = data.get("modal_links", [])[:limit]
    print(f"Spawning scrape jobs for {len(links)} links")
    
    # First, register all pages with the site config
    # Build a pages dict: page_key -> path (e.g., "guide-volumes" -> "/guide/volumes")
    pages_dict = {}
    for url in links:
        path = url.replace("https://modal.com/docs", "")  # e.g., "/guide/volumes"
        # Create a page key by replacing slashes with dashes and removing leading slash
        page_key = path.lstrip("/").replace("/", "-")  # e.g., "guide-volumes"
        pages_dict[page_key] = path
    
    print(f"Registering {len(pages_dict)} pages with site config...")
    update_result = await add_pages_to_site(pages_dict)
    if "error" in update_result:
        print(f"Warning: Failed to update pages: {update_result['error']}")
    else:
        print(f"Pages registered successfully")
    
    async def spawn_scrape(client: httpx.AsyncClient, url: str) -> dict:
        """Spawn a scrape job for a URL using the /docs/{site_id}/{page}/spawn endpoint."""
        start = time.time()
        try:
            # Extract page path from URL and convert to page key
            path = url.replace("https://modal.com/docs", "")
            page_key = path.lstrip("/").replace("/", "-")
            site_id = "modal"
            
            resp = await client.post(
                f"{SCRAPER_API}/docs/{site_id}/{page_key}/spawn",
                # params={"max_age": 0},  # Force fresh scrape
                headers=get_auth_headers(),
                timeout=30,
            )
            elapsed = time.time() - start
            if resp.status_code == 200:
                data = resp.json()
                # Response is either:
                # - {"cached": True, "doc": DocResponse} if fresh cache exists
                # - {"cached": False, "task": TaskResponse} if scrape was spawned
                if data.get("cached"):
                    doc = data["doc"]
                    return {
                        "url": url,
                        "success": True,
                        "cached": True,
                        "time": elapsed,
                        "site_id": doc["site_id"],
                        "page": doc["page"],
                        "content_length": doc["content_length"],
                    }
                else:
                    task = data["task"]
                    return {
                        "url": url,
                        "success": True,
                        "cached": False,
                        "time": elapsed,
                        "task_id": task["task_id"],
                        "site_id": task["site_id"],
                        "page": task["page"],
                    }
            else:
                return {
                    "url": url,
                    "success": False,
                    "time": elapsed,
                    "error": resp.text[:100],
                }
        except Exception as e:
            return {
                "url": url,
                "success": False,
                "time": time.time() - start,
                "error": str(e),
            }
    
    # Spawn scrape tasks in parallel
    print(f"\nSpawning scrape tasks for {len(links)} URLs...")
    async with httpx.AsyncClient() as client:
        tasks = [spawn_scrape(client, url) for url in links]
        results = await asyncio.gather(*tasks)
    
    # Print results
    print("\nResults:")
    print("-" * 60)
    for r in results:
        status = "✓" if r["success"] else "✗"
        if r["success"]:
            if r.get("cached"):
                print(f"  {status} {r['url']} (cached)")
                print(f"      {r['content_length']} chars")
            else:
                print(f"  {status} {r['url']} (spawned)")
                print(f"      task_id: {r['task_id']}")
        else:
            print(f"  {status} {r['url']}")
            print(f"      Error: {r.get('error', 'Unknown')[:80]}")
    
    successful = sum(1 for r in results if r["success"])
    total_time = sum(r["time"] for r in results)
    print("-" * 60)
    print(f"Spawned {successful}/{len(results)} scrape tasks in {total_time:.1f}s total")
    
    return results

def main():
    import asyncio
    results = asyncio.run(scrape_modal_links(limit=400))
    print(f"results={results}")

if __name__ == "__main__":
    main()