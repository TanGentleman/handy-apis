from .core import get_all_links
import asyncio

async def get_modal_links() -> list[str]:
    urls = [
        "https://modal.com/docs",
        "https://modal.com/docs/guide"
    ]
    tasks = [asyncio.create_task(get_all_links(url)) for url in urls]
    results = await asyncio.gather(*tasks)
    all_docs = set()
    for result in results:
        for link in result:
            if "docs" in link:
                if link.startswith("/"):
                    link = "https://modal.com" + link
                    all_docs.add(link)
                elif link.startswith("https://modal.com"):
                    all_docs.add(link)
                else:
                    print(f"found third party URL: {link}")
    print(f"Found {len(all_docs)} docs links")
    return list(all_docs)