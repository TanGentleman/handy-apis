"""Extraction strategies for scraping."""

from playwright.async_api import Page


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
}
