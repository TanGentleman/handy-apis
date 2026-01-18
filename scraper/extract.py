"""Extraction strategies for scraping."""

from playwright.async_api import Page


async def terraform_registry(page: Page, selector: str) -> list[str]:
    """Custom extraction for Terraform Registry - handles cookie consent and JS rendering."""
    # Handle cookie consent banner if present
    try:
        accept_button = page.locator('button:has-text("Accept All")')
        await accept_button.wait_for(state="visible", timeout=5000)
        await accept_button.click()
        await page.wait_for_timeout(1000)
    except Exception:
        pass  # No cookie banner or already dismissed

    # Wait for the actual content to render (JS-heavy SPA)
    await page.wait_for_selector(selector, state="visible", timeout=30000)
    await page.wait_for_timeout(1000)  # Extra time for JS to settle

    # Extract innerHTML
    elements = await page.query_selector_all(selector)
    results = []
    for el in elements:
        html = await el.inner_html()
        results.append(html.strip() if html else "")
    return results


async def terraform_links(page: Page, selector: str) -> list[str]:
    """
    Extract all documentation links from Terraform Registry.

    Handles cookie consent and JS rendering, then extracts all hrefs
    that match the base docs URL pattern. The selector parameter is used
    as the base URL prefix to filter links.
    """
    # Handle cookie consent banner if present
    try:
        accept_button = page.locator('button:has-text("Accept All")')
        await accept_button.wait_for(state="visible", timeout=5000)
        await accept_button.click()
        await page.wait_for_timeout(1000)
    except Exception:
        pass  # No cookie banner or already dismissed

    # Wait for the main content to render
    await page.wait_for_selector("#provider-docs-content", state="visible", timeout=30000)
    await page.wait_for_timeout(2000)  # Extra time for JS to settle

    # Extract all links from the page
    links = await page.eval_on_selector_all(
        "a[href]",
        "elements => elements.map(e => e.href)"
    )

    # Filter to only include links that extend the base docs URL (passed as selector)
    base_url = selector  # Repurpose selector as the base URL filter
    results = set()
    for link in links:
        # Remove query params and fragments
        clean_link = link.split("?")[0].split("#")[0].rstrip("/")
        if clean_link.startswith(base_url):
            results.add(clean_link)

    return sorted(results)


async def click_copy(page: Page, selector: str) -> list[str]:
    """Click a copy button and read clipboard content."""
    await page.click(selector)
    await page.wait_for_timeout(1000)

    content = await page.evaluate("""
        async () => {
            try {
                return await navigator.clipboard.readText();
            } catch (err) {
                return `Error reading clipboard: ${err.message}`;
            }
        }
    """)
    return [content] if content else []


async def text_content(page: Page, selector: str) -> list[str]:
    """Extract textContent from all matching elements. Supports CSS and XPath."""
    elements = await page.query_selector_all(selector)
    results = []
    for el in elements:
        text = await el.text_content()
        results.append(text.strip() if text else "")
    return results


async def inner_html(page: Page, selector: str) -> list[str]:
    """Extract innerHTML from all matching elements. Supports CSS and XPath."""
    elements = await page.query_selector_all(selector)
    results = []
    for el in elements:
        html = await el.inner_html()
        results.append(html.strip() if html else "")
    return results


# Registry for string-based lookup
EXTRACTORS = {
    "click_copy": click_copy,
    "text_content": text_content,
    "inner_html": inner_html,
    "terraform_registry": terraform_registry,
    "terraform_links": terraform_links,
}
