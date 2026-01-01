# ---
# deploy: true
# ---
# Faculty Scraper API - Scrapes UCSF BMS faculty pages with caching

import asyncio
import json
import re
import uuid
from datetime import datetime
from pathlib import Path

import modal
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

playwright_image = modal.Image.debian_slim(python_version="3.10").run_commands(
    "apt-get update",
    "apt-get install -y software-properties-common",
    "apt-add-repository non-free",
    "apt-add-repository contrib",
    "pip install playwright==1.42.0",
    "playwright install-deps chromium",
    "playwright install chromium",
).uv_pip_install("fastapi[standard]", "pydantic")

app = modal.App("faculty-scraper-api", image=playwright_image)
web_app = FastAPI()

volume = modal.Volume.from_name("scraping-volume", create_if_missing=True)
CACHE = Path("/cache")
MAPPINGS_DIR = CACHE / "mappings"
CONTENTS = CACHE / "contents"

BASE_URL = "https://bms.ucsf.edu/faculty"
SELECTOR = ".person-teaser__content"


# --- Cache functions ---

def load_cache() -> dict[str, dict]:
    """Load URL -> {uuid, timestamp} mappings from all mapping files."""
    cache = {}
    if MAPPINGS_DIR.exists():
        for mapping_file in MAPPINGS_DIR.glob("*.jsonl"):
            for line in mapping_file.read_text().strip().split("\n"):
                if line:
                    entry = json.loads(line)
                    # Only keep the latest entry for each URL
                    if entry["url"] not in cache or entry["timestamp"] > cache[entry["url"]]["timestamp"]:
                        cache[entry["url"]] = entry
    return cache


def get_cached(url: str, cache: dict) -> list[dict] | None:
    """Get cached parsed entries for a URL."""
    if url not in cache:
        return None
    content_file = CONTENTS / f"{cache[url]['uuid']}.json"
    if content_file.exists():
        return json.loads(content_file.read_text())
    return None


def save_cache(url: str, entries: list[dict]):
    """Save parsed entries to cache."""
    CACHE.mkdir(exist_ok=True)
    CONTENTS.mkdir(exist_ok=True)
    MAPPINGS_DIR.mkdir(exist_ok=True)

    entry_uuid = str(uuid.uuid4())
    (CONTENTS / f"{entry_uuid}.json").write_text(json.dumps(entries))

    # Write to a new unique jsonl file to avoid concurrency issues
    mapping_file = MAPPINGS_DIR / f"{entry_uuid}.jsonl"
    mapping_file.write_text(json.dumps({
        "url": url,
        "uuid": entry_uuid,
        "timestamp": datetime.now().isoformat()
    }) + "\n")


# --- Parsing functions ---

def parse_entry(raw: str) -> dict:
    """Parse raw faculty text into structured fields."""
    # Clean HTML comments and whitespace
    text = re.sub(r'<!--.*?-->', '', raw, flags=re.DOTALL)
    lines = [l.strip() for l in text.split('\n') if l.strip()]

    if not lines:
        return {}

    result = {"name": lines[0], "title": "", "department": "",
              "primary_area": "", "secondary_area": "", "research": ""}

    field_map = {
        "Primary Thematic Area": "primary_area",
        "Secondary Thematic Area": "secondary_area",
        "Research Summary": "research"
    }

    current = None
    for line in lines[1:]:
        matched = next((f for m, f in field_map.items() if m in line), None)
        if matched:
            current = matched
        elif current:
            result[current] = (result[current] + " " + line).strip()
        elif not result["title"]:
            result["title"] = line
        elif not result["department"]:
            result["department"] = line

    return result


def to_markdown(entries: list[dict]) -> str:
    """Convert entries to markdown."""
    lines = ["# UCSF BMS Faculty Directory\n"]
    # sort
    entries.sort(key=lambda x: x["name"])
    for e in entries:
        if not e.get("name"):
            continue
        lines.append(f"## {e['name']}")
        if e.get("title"): lines.append(f"**Title:** {e['title']}")
        if e.get("department"): lines.append(f"**Department:** {e['department']}")
        if e.get("primary_area"): lines.append(f"**Primary Area:** {e['primary_area']}")
        if e.get("secondary_area") and e["secondary_area"] != "None":
            lines.append(f"**Secondary Area:** {e['secondary_area']}")
        if e.get("research"): lines.append(f"**Research:** {e['research']}")
        lines.append("")
    return "\n".join(lines)


# --- Scraping ---

async def scrape_page(url: str, cache: dict) -> list[dict]:
    """Scrape a page, using cache if available."""
    cached = get_cached(url, cache)
    if cached is not None:
        print(f"Cache hit: {url}")
        return cached

    print(f"Scraping: {url}")
    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(url, wait_until="networkidle")
            await page.wait_for_selector(SELECTOR, state="visible", timeout=10000)

            raw_entries = await page.evaluate(f"""
                () => Array.from(document.querySelectorAll('{SELECTOR}'))
                    .map(el => el.textContent.trim())
            """)
            await browser.close()

            entries = [parse_entry(r) for r in raw_entries]
            if entries:
                save_cache(url, entries)
            return entries
    except Exception as e:
        print(f"Error scraping {url}: {e}")
        return []


# --- Endpoints ---

class ScrapeRequest(BaseModel):
    start_page: int = 1
    end_page: int = 26


@web_app.get("/")
async def root():
    return {"endpoints": {
        "POST /scrape/markdown": "Get faculty as markdown (cached)",
        "GET /cache": "View cache stats",
        "DELETE /cache": "Clear cache"
    }}


@web_app.post("/scrape/markdown", response_class=PlainTextResponse)
async def scrape_markdown(req: ScrapeRequest, use_cache: bool = True):
    """Scrape faculty pages and return markdown."""
    cache = load_cache() if use_cache else {}

    urls = [f"{BASE_URL}?page={i}" for i in range(req.start_page, req.end_page + 1)]
    results = await asyncio.gather(*[scrape_page(url, cache) for url in urls])

    all_entries = [e for page_entries in results for e in page_entries]

    if use_cache:
        volume.commit()

    return to_markdown(all_entries)


@web_app.get("/cache")
async def cache_stats():
    cache = load_cache()
    return {"count": len(cache), "urls": list(cache.keys())}


@web_app.delete("/cache")
async def clear_cache():
    import shutil
    if CACHE.exists():
        shutil.rmtree(CACHE)
        volume.commit()
    return {"status": "cleared"}


@app.function(volumes={"/cache": volume})
@modal.asgi_app(requires_proxy_auth=True)
def fastapi_app():
    return web_app
