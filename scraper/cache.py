"""Caching utilities for scrape results."""

import json
import uuid
from datetime import datetime
from pathlib import Path


class ScrapeCache:
    """File-based cache for scrape results."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.mappings_dir = cache_dir / "mappings"
        self.contents_dir = cache_dir / "contents"
        self._cache: dict[str, dict] | None = None

    def _ensure_dirs(self):
        self.cache_dir.mkdir(exist_ok=True)
        self.mappings_dir.mkdir(exist_ok=True)
        self.contents_dir.mkdir(exist_ok=True)

    def load(self) -> dict[str, dict]:
        """Load URL -> {uuid, timestamp} mappings."""
        if self._cache is not None:
            return self._cache

        cache = {}
        if self.mappings_dir.exists():
            for mapping_file in self.mappings_dir.glob("*.jsonl"):
                for line in mapping_file.read_text().strip().split("\n"):
                    if line:
                        entry = json.loads(line)
                        url = entry["url"]
                        if url not in cache or entry["timestamp"] > cache[url]["timestamp"]:
                            cache[url] = entry
        self._cache = cache
        return cache

    def get(self, url: str) -> list | None:
        """Get cached entries for a URL."""
        cache = self.load()
        if url not in cache:
            return None
        content_file = self.contents_dir / f"{cache[url]['uuid']}.json"
        if content_file.exists():
            return json.loads(content_file.read_text())
        return None

    def save(self, url: str, entries: list):
        """Save entries to cache."""
        self._ensure_dirs()

        entry_uuid = str(uuid.uuid4())
        (self.contents_dir / f"{entry_uuid}.json").write_text(json.dumps(entries))

        mapping = {
            "url": url,
            "uuid": entry_uuid,
            "timestamp": datetime.now().isoformat()
        }
        (self.mappings_dir / f"{entry_uuid}.jsonl").write_text(json.dumps(mapping) + "\n")

        # Update in-memory cache
        if self._cache is not None:
            self._cache[url] = mapping

    def stats(self) -> dict:
        """Get cache statistics."""
        cache = self.load()
        return {"count": len(cache), "urls": list(cache.keys())}
