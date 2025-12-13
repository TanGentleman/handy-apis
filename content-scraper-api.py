# ---
# deploy: true
# ---

# # Content Scraper API for Documentation Updates
#
# This API provides endpoints to scrape documentation pages and return their content
# for use in GitHub workflows or other automation.

import modal
from fastapi import FastAPI
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

app = modal.App("content-scraper-api", image=playwright_image)
web_app = FastAPI(title="Content Scraper API")


class ScrapeRequest(BaseModel):
    url: str
    selector: str


class BatchScrapeRequest(BaseModel):
    requests: list[ScrapeRequest]


class ScrapeResponse(BaseModel):
    success: bool
    content: str
    content_length: int
    url: str
    page_title: str
    processing_time_seconds: float
    error: str | None = None


class BatchScrapeResponse(BaseModel):
    results: list[ScrapeResponse]
    total: int
    successful: int
    failed: int
    total_processing_time_seconds: float


async def scrape_and_copy(url: str, selector: str) -> dict:
    """
    Navigate to a URL, click a copy button, and capture clipboard contents.

    Args:
        url: Target URL to scrape
        selector: CSS selector for the copy button

    Returns:
        Dictionary with content and metadata
    """
    import time
    from playwright.async_api import async_playwright

    start_time = time.time()
    try:
        async with async_playwright() as p:
            # Launch browser with clipboard permissions
            browser = await p.chromium.launch()
            context = await browser.new_context(
                permissions=["clipboard-read", "clipboard-write"]
            )
            page = await context.new_page()

            print(f"Navigating to {url}...")
            await page.goto(url, wait_until="networkidle")

            print(f"Waiting for element: {selector}")
            await page.wait_for_selector(selector, state="visible", timeout=10000)

            print(f"Clicking copy button: {selector}")
            await page.click(selector)

            # Wait for the copy action to complete
            await page.wait_for_timeout(1000)

            print("Reading clipboard contents...")
            clipboard_content = await page.evaluate("""
                async () => {
                    try {
                        return await navigator.clipboard.readText();
                    } catch (err) {
                        return `Error reading clipboard: ${err.message}`;
                    }
                }
            """)

            title = await page.title()
            await browser.close()

            processing_time = time.time() - start_time
            return {
                "success": True,
                "content": clipboard_content,
                "content_length": len(clipboard_content) if clipboard_content else 0,
                "url": url,
                "page_title": title,
                "processing_time_seconds": processing_time,
                "error": None
            }

    except Exception as e:
        processing_time = time.time() - start_time
        return {
            "success": False,
            "content": "",
            "content_length": 0,
            "url": url,
            "page_title": "",
            "processing_time_seconds": processing_time,
            "error": str(e)
        }


@web_app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Content Scraper API",
        "version": "1.0",
        "endpoints": {
            "/scrape": "POST - Scrape content from any URL with a copy button",
            "/scrape/batch": "POST - Scrape multiple URLs in parallel",
            "/hooks": "GET - Get Claude Code hooks documentation",
            "/health": "GET - Health check"
        }
    }


@web_app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@web_app.post("/scrape", response_model=ScrapeResponse)
async def scrape_content(request: ScrapeRequest):
    """
    Generic scraping endpoint. Provide a URL and selector for a copy button.

    Example request:
    {
        "url": "https://code.claude.com/docs/en/hooks",
        "selector": "#page-context-menu-button"
    }
    """
    result = await scrape_and_copy(request.url, request.selector)
    return ScrapeResponse(**result)


@web_app.post("/scrape/batch", response_model=BatchScrapeResponse)
async def scrape_batch(batch: BatchScrapeRequest):
    """
    Scrape multiple URLs in parallel.

    Example request:
    {
        "requests": [
            {"url": "https://code.claude.com/docs/en/hooks", "selector": "#page-context-menu-button"},
            {"url": "https://code.claude.com/docs/en/slash-commands", "selector": "#page-context-menu-button"}
        ]
    }
    """
    import asyncio
    import time

    start_time = time.time()

    # Run all scrapes in parallel
    tasks = [
        scrape_and_copy(req.url, req.selector)
        for req in batch.requests
    ]
    results = await asyncio.gather(*tasks)

    # Convert to response models
    scrape_responses = [ScrapeResponse(**result) for result in results]

    total_processing_time = time.time() - start_time

    return BatchScrapeResponse(
        results=scrape_responses,
        total=len(scrape_responses),
        successful=sum(1 for r in scrape_responses if r.success),
        failed=sum(1 for r in scrape_responses if not r.success),
        total_processing_time_seconds=total_processing_time
    )


@web_app.get("/hooks", response_model=ScrapeResponse)
async def get_hooks_docs():
    """
    Get Claude Code hooks documentation content.
    This is a convenience endpoint for the hooks documentation.
    """
    result = await scrape_and_copy(
        url="https://code.claude.com/docs/en/hooks",
        selector="#page-context-menu-button"
    )
    return ScrapeResponse(**result)


# You can add more specific endpoints here for other documentation pages
# Example:
# @web_app.get("/slash-commands", response_model=ScrapeResponse)
# async def get_slash_commands_docs():
#     """Get Claude Code slash commands documentation."""
#     result = await scrape_and_copy(
#         url="https://code.claude.com/docs/en/slash-commands",
#         selector="#page-context-menu-button"
#     )
#     return ScrapeResponse(**result)


@app.function()
@modal.asgi_app()
def fastapi_app():
    """Mount the FastAPI app to Modal."""
    return web_app


# Optional: Scheduled job to keep content fresh
# @app.function(schedule=modal.Period(hours=6))
# async def scheduled_scrape():
#     """
#     Optional scheduled function to scrape content periodically.
#     Can be used to cache results or update external systems.
#     """
#     result = await scrape_and_copy(
#         url="https://code.claude.com/docs/en/hooks",
#         selector="#page-context-menu-button"
#     )
#     print(f"Scheduled scrape completed: {result['content_length']} characters")
#     return result
