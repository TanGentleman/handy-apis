"""Core scraping functionality."""

from typing import Callable
from playwright.async_api import Page

from .types import ScrapeJob, ScrapeResult, ExtractFn, ParseFn
from .extract import EXTRACTORS
from .cache import ScrapeCache


async def scrape(
    job: ScrapeJob,
    parse_fn: ParseFn | None = None,
    extract_fn: ExtractFn | None = None,
    cache: ScrapeCache | None = None,
) -> ScrapeResult:
    """
    Execute a scrape job.

    Args:
        job: Scrape job configuration
        parse_fn: Optional function to parse raw strings into dicts
        extract_fn: Custom extraction function (overrides job.method)
        cache: Optional cache instance
    """
    # Check cache first
    if cache and job.use_cache:
        cached = cache.get(job.url)
        if cached is not None:
            print(f"Cache hit: {job.url}")
            return ScrapeResult(
                job_name=job.name,
                url=job.url,
                success=True,
                entries=cached,
                cached=True,
            )

    # Resolve extraction function
    if extract_fn is None:
        if job.method == "custom":
            raise ValueError(f"Job '{job.name}' has method='custom' but no extract_fn provided")
        extract_fn = EXTRACTORS[job.method]

    print(f"Scraping: {job.url}")
    from playwright.async_api import async_playwright

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            if job.method == "click_copy":
                permissions = ["clipboard-read", "clipboard-write"]
            else:
                permissions = []
            context = await browser.new_context(permissions=permissions)
            page = await context.new_page()

            await page.goto(job.url, wait_until=job.wait_until, timeout=job.timeout)
            await page.wait_for_selector(job.selector, state="visible", timeout=job.timeout)

            raw_entries = await extract_fn(page, job.selector)
            await browser.close()

            # Parse if function provided, otherwise keep raw strings
            if parse_fn:
                entries = [parse_fn(r) for r in raw_entries if r]
            else:
                entries = raw_entries
            if len(entries) == 0:
                print(f"No entries found for {job.url}")
                return ScrapeResult(
                    job_name=job.name,
                    url=job.url,
                    success=False,
                    entries=[],
                    error="No entries found",
                )
            print(f"Scraped {len(entries)} entries from {job.url}")
            # Cache results
            if cache and job.use_cache and entries:
                cache.save(job.url, entries)

            return ScrapeResult(
                job_name=job.name,
                url=job.url,
                success=True,
                entries=entries,
            )

    except Exception as e:
        print(f"Error scraping {job.url}: {e}")
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
    cache: ScrapeCache | None = None,
) -> list[ScrapeResult]:
    """
    Execute multiple scrape jobs.

    Args:
        jobs: List of scrape jobs
        parse_fns: Dict mapping job name -> parse function
        extract_fns: Dict mapping job name -> extract function
        cache: Optional shared cache instance
    """
    import asyncio

    parse_fns = parse_fns or {}
    extract_fns = extract_fns or {}

    tasks = [
        scrape(
            job,
            parse_fn=parse_fns.get(job.name),
            extract_fn=extract_fns.get(job.name),
            cache=cache,
        )
        for job in jobs
    ]
    return await asyncio.gather(*tasks)




def get_all_links(url):
    import re
    import urllib.request
    response = urllib.request.urlopen(url)
    html = response.read().decode("utf8")
    links = []
    for match in re.finditer('href="(.*?)"', html):
        links.append(match.group(1))
    return links
