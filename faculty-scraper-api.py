# ---
# deploy: true
# ---

# # Faculty Scraper API
#
# Scrapes faculty listings from UCSF BMS pages and returns text content.

import re
import modal
from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

# Set up Playwright image with Chromium
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
web_app = FastAPI(title="Faculty Scraper API")

BASE_URL = "https://bms.ucsf.edu/faculty"
SELECTOR = ".person-teaser__content"


def clean_text(text: str) -> str:
    """Remove HTML comments and normalize whitespace."""
    # Remove HTML comments
    text = re.sub(r'<!--.*?-->', '', text, flags=re.DOTALL)
    # Split by lines, strip each, filter empty, rejoin
    lines = [line.strip() for line in text.split('\n')]
    lines = [line for line in lines if line]
    return '\n'.join(lines)


def parse_faculty_entry(raw_text: str) -> dict:
    """Parse raw faculty text into structured fields."""
    text = clean_text(raw_text)
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    result = {
        "name": "",
        "title": "",
        "department": "",
        "primary_thematic_area": "",
        "secondary_thematic_area": "",
        "research_summary": "",
        "mentorship_development": ""
    }

    if not lines:
        return result

    # First line is always name with credentials
    result["name"] = lines[0]

    # Parse remaining lines by looking for field markers
    current_field = None
    field_map = {
        "Primary Thematic Area": "primary_thematic_area",
        "Secondary Thematic Area": "secondary_thematic_area",
        "Research Summary": "research_summary",
        "Mentorship Development": "mentorship_development"
    }

    i = 1
    while i < len(lines):
        line = lines[i]

        # Check if this line is a field header
        matched_field = None
        for marker, field in field_map.items():
            if marker in line:
                matched_field = field
                break

        if matched_field:
            current_field = matched_field
            i += 1
            continue

        # If we have a current field, append to it
        if current_field:
            if result[current_field]:
                result[current_field] += " " + line
            else:
                result[current_field] = line
        else:
            # Before any field markers, collect title/department
            if not result["title"]:
                result["title"] = line
            elif not result["department"]:
                result["department"] = line

        i += 1

    return result


def entries_to_markdown(entries: list[dict], include_header: bool = True) -> str:
    """Convert parsed faculty entries to clean markdown."""
    lines = []

    if include_header:
        lines.append("# UCSF BMS Faculty Directory\n")

    for entry in entries:
        lines.append(f"## {entry['name']}")
        if entry['title']:
            lines.append(f"**Title:** {entry['title']}")
        if entry['department']:
            lines.append(f"**Department:** {entry['department']}")
        if entry['primary_thematic_area']:
            lines.append(f"**Primary Thematic Area:** {entry['primary_thematic_area']}")
        if entry['secondary_thematic_area'] and entry['secondary_thematic_area'] != "None":
            lines.append(f"**Secondary Thematic Area:** {entry['secondary_thematic_area']}")
        if entry['research_summary']:
            lines.append(f"**Research Summary:** {entry['research_summary']}")
        lines.append("")  # Blank line between entries

    return "\n".join(lines)


class PageScrapeRequest(BaseModel):
    start_page: int = 1
    end_page: int = 26


class PersonEntry(BaseModel):
    page: int
    text: str


class FacultyEntry(BaseModel):
    page: int
    name: str
    title: str
    department: str
    primary_thematic_area: str
    secondary_thematic_area: str
    research_summary: str


class FacultyScrapeResponse(BaseModel):
    success: bool
    entries: list[PersonEntry]
    total_entries: int
    pages_scraped: int
    processing_time_seconds: float
    error: str | None = None


class SinglePageResponse(BaseModel):
    success: bool
    page: int
    entries: list[str]
    entry_count: int
    processing_time_seconds: float
    error: str | None = None


async def scrape_page(page_num: int) -> dict:
    """
    Scrape a single faculty page and extract person entries.

    Args:
        page_num: Page number to scrape (1-26)

    Returns:
        Dictionary with entries and metadata
    """
    import time
    from playwright.async_api import async_playwright

    start_time = time.time()
    url = f"{BASE_URL}?page={page_num}"

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()

            print(f"Navigating to {url}...")
            await page.goto(url, wait_until="networkidle")

            print(f"Waiting for elements: {SELECTOR}")
            await page.wait_for_selector(SELECTOR, state="visible", timeout=10000)

            # Extract text from all person entries
            entries = await page.evaluate(f"""
                () => {{
                    const elements = document.querySelectorAll('{SELECTOR}');
                    return Array.from(elements).map(el => el.textContent.trim());
                }}
            """)

            await browser.close()

            processing_time = time.time() - start_time
            return {
                "success": True,
                "page": page_num,
                "entries": entries,
                "entry_count": len(entries),
                "processing_time_seconds": processing_time,
                "error": None
            }

    except Exception as e:
        processing_time = time.time() - start_time
        return {
            "success": False,
            "page": page_num,
            "entries": [],
            "entry_count": 0,
            "processing_time_seconds": processing_time,
            "error": str(e)
        }


@web_app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Faculty Scraper API",
        "version": "1.0",
        "target": "UCSF BMS Faculty Directory",
        "endpoints": {
            "/scrape": "POST - Scrape page range, raw text (default: pages 1-26)",
            "/scrape/structured": "POST - Scrape with parsed fields (JSON)",
            "/scrape/markdown": "POST - Scrape and return clean markdown",
            "/scrape/page/{n}": "GET - Scrape a single page (raw)",
            "/health": "GET - Health check"
        }
    }


@web_app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@web_app.get("/scrape/page/{page_num}", response_model=SinglePageResponse)
async def scrape_single_page(page_num: int):
    """
    Scrape a single faculty page.

    Args:
        page_num: Page number (1-26)
    """
    result = await scrape_page(page_num)
    return SinglePageResponse(**result)


@web_app.post("/scrape", response_model=FacultyScrapeResponse)
async def scrape_range(request: PageScrapeRequest):
    """
    Scrape a range of faculty pages in parallel.

    Example request:
    {
        "start_page": 1,
        "end_page": 26
    }
    """
    import asyncio
    import time

    start_time = time.time()

    # Scrape all pages in parallel
    tasks = [
        scrape_page(page_num)
        for page_num in range(request.start_page, request.end_page + 1)
    ]
    results = await asyncio.gather(*tasks)

    # Flatten entries with page info
    all_entries = []
    pages_scraped = 0
    errors = []

    for result in results:
        if result["success"]:
            pages_scraped += 1
            for text in result["entries"]:
                all_entries.append(PersonEntry(page=result["page"], text=text))
        else:
            errors.append(f"Page {result['page']}: {result['error']}")

    total_time = time.time() - start_time

    return FacultyScrapeResponse(
        success=len(errors) == 0,
        entries=all_entries,
        total_entries=len(all_entries),
        pages_scraped=pages_scraped,
        processing_time_seconds=total_time,
        error="; ".join(errors) if errors else None
    )


@web_app.post("/scrape/structured")
async def scrape_structured(request: PageScrapeRequest):
    """
    Scrape faculty pages and return parsed structured data.

    Returns faculty entries with parsed fields:
    - name, title, department
    - primary_thematic_area, secondary_thematic_area
    - research_summary
    """
    import asyncio
    import time

    start_time = time.time()

    tasks = [
        scrape_page(page_num)
        for page_num in range(request.start_page, request.end_page + 1)
    ]
    results = await asyncio.gather(*tasks)

    all_entries = []
    pages_scraped = 0
    errors = []

    for result in results:
        if result["success"]:
            pages_scraped += 1
            for raw_text in result["entries"]:
                parsed = parse_faculty_entry(raw_text)
                all_entries.append(FacultyEntry(
                    page=result["page"],
                    name=parsed["name"],
                    title=parsed["title"],
                    department=parsed["department"],
                    primary_thematic_area=parsed["primary_thematic_area"],
                    secondary_thematic_area=parsed["secondary_thematic_area"],
                    research_summary=parsed["research_summary"]
                ))
        else:
            errors.append(f"Page {result['page']}: {result['error']}")

    total_time = time.time() - start_time

    return {
        "success": len(errors) == 0,
        "entries": all_entries,
        "total_entries": len(all_entries),
        "pages_scraped": pages_scraped,
        "processing_time_seconds": total_time,
        "error": "; ".join(errors) if errors else None
    }


@web_app.post("/scrape/markdown", response_class=PlainTextResponse)
async def scrape_markdown(request: PageScrapeRequest):
    """
    Scrape faculty pages and return clean markdown.

    Returns plain text markdown suitable for LLM consumption.
    """
    import asyncio

    tasks = [
        scrape_page(page_num)
        for page_num in range(request.start_page, request.end_page + 1)
    ]
    results = await asyncio.gather(*tasks)

    all_parsed = []
    for result in results:
        if result["success"]:
            for raw_text in result["entries"]:
                parsed = parse_faculty_entry(raw_text)
                parsed["page"] = result["page"]
                all_parsed.append(parsed)

    return entries_to_markdown(all_parsed)


@app.function()
@modal.asgi_app(requires_proxy_auth=False)
def fastapi_app():
    """Mount the FastAPI app to Modal."""
    return web_app
