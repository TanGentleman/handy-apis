"""URL utilities for documentation scraping."""

import re
from pathlib import PurePosixPath
from urllib.parse import unquote, urlparse, urlunparse

# File extensions that indicate non-scrapeable assets
ASSET_EXTENSIONS = frozenset({
    # Archives
    ".pdf", ".zip", ".tar", ".gz", ".tgz", ".rar", ".7z",
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
    # Media
    ".mp4", ".mp3", ".wav", ".webm", ".mov",
    # Documents
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    # Executables
    ".exe", ".dmg", ".pkg", ".deb", ".rpm",
    # Feeds
    ".xml", ".rss", ".atom",
    # Web assets (stylesheets, scripts, fonts, source maps)
    ".css", ".js", ".mjs", ".ts", ".jsx", ".tsx",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".map",
})


def is_asset_url(url: str) -> bool:
    """Check if URL points to a non-scrapeable asset (binary, feed, etc.)."""
    path = unquote(urlparse(url).path)
    return PurePosixPath(path).suffix.lower() in ASSET_EXTENSIONS


def clean_url(url: str) -> str:
    """Remove query params and fragments from URL."""
    return url.split("?")[0].split("#")[0].rstrip("/")


def normalize_url(url: str) -> str:
    """Normalize URL for consistent matching.

    - Lowercase scheme and host
    - Remove query/fragment
    - Collapse duplicate slashes in path
    - Remove trailing slash (always, for consistent prefix matching)
    """
    url = url.strip()
    p = urlparse(url)

    scheme = (p.scheme or "https").lower()
    netloc = (p.netloc or "").lower()

    # Normalize path - keep empty for root, always strip trailing slash
    path = p.path or ""
    path = re.sub(r"/{2,}", "/", path)  # collapse //
    path = path.rstrip("/")  # always remove trailing slash

    return urlunparse((scheme, netloc, path, "", "", ""))


def normalize_path(path: str) -> str:
    """Normalize a URL path for cache keys.

    - Empty string for base page
    - Always starts with / otherwise
    - No trailing slash
    - No duplicate slashes
    """
    if not path:
        return ""
    path = re.sub(r"/{2,}", "/", path)
    if not path.startswith("/"):
        path = "/" + path
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return "" if path == "/" else path


def normalize_page_path(path: str, base_url: str) -> str:
    """Normalize a page path relative to a base URL.

    Handles various input formats:
    - Full URL starting with base_url: extracts path portion
    - Path without leading slash: adds leading slash
    - Already normalized path: returns as-is

    Examples with base_url="https://docs.modal.com":
    - "https://docs.modal.com/guide/hello" -> "/guide/hello"
    - "guide/hello" -> "/guide/hello"
    - "/guide/hello" -> "/guide/hello"
    """
    if not path:
        return ""

    path = path.strip()

    # Check if it's a full URL that starts with the base URL
    if path.startswith(("http://", "https://")):
        norm_base = normalize_url(base_url)
        norm_full = normalize_url(path)
        if norm_full == norm_base:
            return ""
        if norm_full.startswith(norm_base + "/"):
            return norm_full[len(norm_base):]

    # Otherwise, just normalize the path
    return normalize_path(path)
