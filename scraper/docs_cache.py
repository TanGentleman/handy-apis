"""Documentation cache with markdown file storage."""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from .types import CachedDoc


class DocsCache:
    """File-based cache storing documentation as markdown files."""

    def __init__(self, cache_dir: Path | str):
        self.cache_dir = Path(cache_dir)
        self.docs_dir = self.cache_dir / "docs"
        self.index_path = self.cache_dir / "index.json"
        self._index: dict[str, dict[str, dict]] | None = None

    def _ensure_dirs(self, site: str | None = None):
        """Ensure cache directories exist."""
        self.cache_dir.mkdir(exist_ok=True)
        self.docs_dir.mkdir(exist_ok=True)
        if site:
            (self.docs_dir / site).mkdir(exist_ok=True)

    def _load_index(self) -> dict[str, dict[str, dict]]:
        """Load the cache index."""
        if self._index is not None:
            return self._index

        if self.index_path.exists():
            self._index = json.loads(self.index_path.read_text())
        else:
            self._index = {}
        return self._index

    def _save_index(self):
        """Save the cache index."""
        self._ensure_dirs()
        self.index_path.write_text(json.dumps(self._index, indent=2, default=str))

    def _content_hash(self, content: str) -> str:
        """Generate hash of content."""
        return hashlib.md5(content.encode()).hexdigest()[:12]

    def _get_doc_path(self, site: str, page: str) -> Path:
        """Get the path to a cached markdown file."""
        return self.docs_dir / site / f"{page}.md"

    def get(self, site: str, page: str) -> CachedDoc | None:
        """Get cached doc metadata. Returns None if not cached."""
        index = self._load_index()
        if site not in index or page not in index[site]:
            return None

        entry = index[site][page]
        doc_path = self._get_doc_path(site, page)
        if not doc_path.exists():
            return None

        return CachedDoc(
            site=site,
            page=page,
            url=entry["url"],
            path=entry["path"],
            scraped_at=datetime.fromisoformat(entry["scraped_at"]),
            content_hash=entry["content_hash"],
            size_bytes=entry["size_bytes"],
        )

    def get_content(self, site: str, page: str) -> str | None:
        """Get the actual markdown content for a cached page."""
        doc_path = self._get_doc_path(site, page)
        if doc_path.exists():
            return doc_path.read_text()
        return None

    def save(self, site: str, page: str, url: str, content: str):
        """Save documentation content to cache."""
        self._ensure_dirs(site)
        index = self._load_index()

        # Write markdown file
        doc_path = self._get_doc_path(site, page)
        doc_path.write_text(content)

        # Update index
        if site not in index:
            index[site] = {}

        relative_path = f"docs/{site}/{page}.md"
        index[site][page] = {
            "url": url,
            "path": relative_path,
            "scraped_at": datetime.now().isoformat(),
            "content_hash": self._content_hash(content),
            "size_bytes": len(content.encode()),
        }
        self._save_index()

    def list_sites(self) -> list[str]:
        """List all sites with cached docs."""
        return list(self._load_index().keys())

    def list_pages(self, site: str) -> list[str]:
        """List all cached pages for a site."""
        index = self._load_index()
        return list(index.get(site, {}).keys())

    def has(self, site: str, page: str) -> bool:
        """Check if a page is cached."""
        return self.get(site, page) is not None

    def delete(self, site: str, page: str) -> bool:
        """Delete a cached page. Returns True if deleted."""
        index = self._load_index()
        if site not in index or page not in index[site]:
            return False

        doc_path = self._get_doc_path(site, page)
        if doc_path.exists():
            doc_path.unlink()

        del index[site][page]
        if not index[site]:
            del index[site]
        self._save_index()
        return True

    def stats(self) -> dict:
        """Get cache statistics."""
        index = self._load_index()
        total_pages = sum(len(pages) for pages in index.values())
        total_bytes = sum(
            entry["size_bytes"]
            for pages in index.values()
            for entry in pages.values()
        )
        return {
            "sites": len(index),
            "pages": total_pages,
            "size_bytes": total_bytes,
            "size_mb": round(total_bytes / (1024 * 1024), 2),
        }
