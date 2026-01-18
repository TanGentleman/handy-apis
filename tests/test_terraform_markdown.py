"""Test script for scraping Terraform AWS provider docs via Modal API."""

import asyncio
import re
import os
import httpx
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

SCRAPER_API = "https://tangentleman--content-scraper-api-fastapi-app-dev.modal.run"
TERRAFORM_AWS_DOCS_URL = "https://registry.terraform.io/providers/hashicorp/aws/latest/docs"

ROOT_DIR = Path(__file__).parent.parent
OUTPUT_DIR = ROOT_DIR / "docs" / "terraform"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_MARKDOWN_PATH = OUTPUT_DIR / "aws-docs.md"


def get_auth_headers() -> dict:
    """Get Modal auth headers from environment variables."""
    key = os.environ.get("MODAL_KEY")
    secret = os.environ.get("MODAL_SECRET")
    if key and secret:
        return {"Modal-Key": key, "Modal-Secret": secret}
    return {}


def html_to_markdown(html: str) -> str:
    """Convert HTML to markdown using regex-based parsing."""
    md = html

    # Headers
    md = re.sub(r'<h1[^>]*>(.*?)</h1>', r'\n# \1\n\n', md, flags=re.DOTALL | re.IGNORECASE)
    md = re.sub(r'<h2[^>]*>(.*?)</h2>', r'\n## \1\n\n', md, flags=re.DOTALL | re.IGNORECASE)
    md = re.sub(r'<h3[^>]*>(.*?)</h3>', r'\n### \1\n\n', md, flags=re.DOTALL | re.IGNORECASE)
    md = re.sub(r'<h4[^>]*>(.*?)</h4>', r'\n#### \1\n\n', md, flags=re.DOTALL | re.IGNORECASE)
    md = re.sub(r'<h5[^>]*>(.*?)</h5>', r'\n##### \1\n\n', md, flags=re.DOTALL | re.IGNORECASE)
    md = re.sub(r'<h6[^>]*>(.*?)</h6>', r'\n###### \1\n\n', md, flags=re.DOTALL | re.IGNORECASE)

    # Code blocks (pre before inline code)
    md = re.sub(r'<pre[^>]*><code[^>]*>(.*?)</code></pre>', r'\n```\n\1\n```\n\n', md, flags=re.DOTALL | re.IGNORECASE)
    md = re.sub(r'<pre[^>]*>(.*?)</pre>', r'\n```\n\1\n```\n\n', md, flags=re.DOTALL | re.IGNORECASE)

    # Inline code
    md = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', md, flags=re.DOTALL | re.IGNORECASE)

    # Bold/strong
    md = re.sub(r'<(strong|b)[^>]*>(.*?)</\1>', r'**\2**', md, flags=re.DOTALL | re.IGNORECASE)

    # Italic/em
    md = re.sub(r'<(em|i)[^>]*>(.*?)</\1>', r'*\2*', md, flags=re.DOTALL | re.IGNORECASE)

    # Links
    md = re.sub(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', r'[\2](\1)', md, flags=re.DOTALL | re.IGNORECASE)

    # Lists - unordered
    md = re.sub(r'<ul[^>]*>(.*?)</ul>', lambda m: convert_ul(m.group(1)), md, flags=re.DOTALL | re.IGNORECASE)

    # Lists - ordered
    md = re.sub(r'<ol[^>]*>(.*?)</ol>', lambda m: convert_ol(m.group(1)), md, flags=re.DOTALL | re.IGNORECASE)

    # Blockquotes
    md = re.sub(r'<blockquote[^>]*>(.*?)</blockquote>', lambda m: '\n> ' + m.group(1).strip().replace('\n', '\n> ') + '\n\n', md, flags=re.DOTALL | re.IGNORECASE)

    # Paragraphs
    md = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', md, flags=re.DOTALL | re.IGNORECASE)

    # Line breaks
    md = re.sub(r'<br\s*/?>', '\n', md, flags=re.IGNORECASE)

    # Remove remaining HTML tags
    md = re.sub(r'<[^>]+>', '', md)

    # Clean up: multiple newlines -> max 2, remove "Copy" artifacts
    md = re.sub(r'\n{3,}', '\n\n', md)
    md = re.sub(r'Copy\n', '', md)

    # Decode HTML entities
    md = md.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&').replace('&quot;', '"').replace('&#39;', "'")

    return md.strip()


def convert_ul(inner: str) -> str:
    """Convert unordered list items."""
    items = re.findall(r'<li[^>]*>(.*?)</li>', inner, flags=re.DOTALL | re.IGNORECASE)
    if not items:
        return inner
    lines = [f'- {item.strip()}' for item in items]
    return '\n' + '\n'.join(lines) + '\n\n'


def convert_ol(inner: str) -> str:
    """Convert ordered list items."""
    items = re.findall(r'<li[^>]*>(.*?)</li>', inner, flags=re.DOTALL | re.IGNORECASE)
    if not items:
        return inner
    lines = [f'{i+1}. {item.strip()}' for i, item in enumerate(items)]
    return '\n' + '\n'.join(lines) + '\n\n'


async def scrape_terraform_docs():
    """Scrape Terraform AWS provider docs via Modal API."""
    print("=" * 60)
    print("Scraping Terraform AWS Provider Docs via Modal API")
    print("=" * 60)
    print(f"\nAPI: {SCRAPER_API}")
    print(f"URL: {TERRAFORM_AWS_DOCS_URL}")
    print(f"Output: {OUTPUT_MARKDOWN_PATH}")
    print()

    async with httpx.AsyncClient(timeout=120.0) as client:
        print("Calling /scrape endpoint with terraform_registry method...")
        resp = await client.post(
            f"{SCRAPER_API}/scrape",
            headers=get_auth_headers(),
            json={
                "url": TERRAFORM_AWS_DOCS_URL,
                "selector": "#provider-docs-content",
                "method": "terraform_registry",
                "timeout": 60000,
                "wait_until": "domcontentloaded",
            },
        )

        print(f"Response status: {resp.status_code}")

        if resp.status_code != 200:
            print(f"Error: {resp.text}")
            return False

        data = resp.json()
        print(f"Success: {data.get('success')}")

        if not data.get("success"):
            print(f"Scrape failed: {data.get('error')}")
            return False

        html_content = data.get("content", "")
        print(f"HTML content length: {len(html_content)} chars")

        if not html_content:
            print("No content returned")
            return False

        # Convert HTML to markdown
        print("Converting to markdown...")
        markdown_content = html_to_markdown(html_content)
        print(f"Markdown content length: {len(markdown_content)} chars")

        # Save to file
        with open(OUTPUT_MARKDOWN_PATH, "w", encoding="utf-8") as f:
            f.write(markdown_content)
        print(f"\nMarkdown saved to: {OUTPUT_MARKDOWN_PATH}")

        # Preview
        print(f"\n--- Content preview (first 2000 chars) ---")
        print(markdown_content[:2000] if len(markdown_content) > 2000 else markdown_content)
        print(f"\n--- End preview ---")

        return True


def main():
    success = asyncio.run(scrape_terraform_docs())
    exit(0 if success else 1)


if __name__ == "__main__":
    main()
