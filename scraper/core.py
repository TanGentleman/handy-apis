"""Core scraping functionality."""

from .models import ScrapeJob, ScrapeResult, ExtractFn, ParseFn
from .extract import EXTRACTORS


async def _save_debug_output(page, job: ScrapeJob) -> None:
    """Save debug HTML and screenshot if paths are configured."""
    if job.debug_html_path:
        try:
            html_content = await page.content()
            with open(job.debug_html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            print(f"Debug HTML saved to: {job.debug_html_path}")
        except Exception as html_err:
            print(f"Failed to save debug HTML: {html_err}")

    if job.debug_screenshot_path:
        try:
            await page.screenshot(path=job.debug_screenshot_path, full_page=True)
            print(f"Debug screenshot saved to: {job.debug_screenshot_path}")
        except Exception as ss_err:
            print(f"Failed to save debug screenshot: {ss_err}")


async def scrape(
    job: ScrapeJob,
    parse_fn: ParseFn | None = None,
    extract_fn: ExtractFn | None = None,
) -> ScrapeResult:
    """
    Execute a scrape job.

    Args:
        job: Scrape job configuration
        parse_fn: Optional function to parse raw strings into dicts
        extract_fn: Custom extraction function (overrides job.method)
    """
    # Resolve extraction function
    if extract_fn is None:
        if job.method == "custom":
            raise ValueError(f"Job '{job.name}' has method='custom' but no extract_fn provided")
        extract_fn = EXTRACTORS[job.method]

    print(f"Scraping: {job.url}")
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        if job.method == "click_copy":
            permissions = ["clipboard-read", "clipboard-write"]
        else:
            permissions = []
        context = await browser.new_context(permissions=permissions)
        page = await context.new_page()

        try:
            await page.goto(job.url, wait_until=job.wait_until, timeout=job.timeout)

            # Skip wait_for_selector for methods that handle their own waiting
            if job.method not in ("custom", "terraform_registry", "terraform_links"):
                await page.wait_for_selector(job.selector, state="visible", timeout=job.timeout)

            raw_entries = await extract_fn(page, job.selector)

            # Parse if function provided, otherwise keep raw strings
            if parse_fn:
                entries = [parse_fn(r) for r in raw_entries if r]
            else:
                entries = raw_entries

            if len(entries) == 0:
                print(f"No entries found for {job.url}")
                await _save_debug_output(page, job)
                return ScrapeResult(
                    job_name=job.name,
                    url=job.url,
                    success=False,
                    entries=[],
                    error="No entries found",
                )

            print(f"Scraped {len(entries)} entries from {job.url}")
            return ScrapeResult(
                job_name=job.name,
                url=job.url,
                success=True,
                entries=entries,
            )

        except Exception as e:
            print(f"Error scraping {job.url}: {e}")
            await _save_debug_output(page, job)
            return ScrapeResult(
                job_name=job.name,
                url=job.url,
                success=False,
                entries=[],
                error=str(e),
            )


async def scrape_batch(
    jobs: list[ScrapeJob],
    parse_fns: dict[str, ParseFn] | None = None,
    extract_fns: dict[str, ExtractFn] | None = None,
) -> list[ScrapeResult]:
    """
    Execute multiple scrape jobs.

    Args:
        jobs: List of scrape jobs
        parse_fns: Dict mapping job name -> parse function
        extract_fns: Dict mapping job name -> extract function
    """
    import asyncio

    parse_fns = parse_fns or {}
    extract_fns = extract_fns or {}

    tasks = [
        scrape(
            job,
            parse_fn=parse_fns.get(job.name),
            extract_fn=extract_fns.get(job.name),
        )
        for job in jobs
    ]
    return await asyncio.gather(*tasks)
