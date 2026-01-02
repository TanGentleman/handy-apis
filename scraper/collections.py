"""Collection management for documentation sites."""

import json
from pathlib import Path

from .types import SiteConfig, ScrapeJob, ExtractMethod


class CollectionManager:
    """Manages documentation site configurations from selectors.json."""

    def __init__(self, config_path: Path | str):
        self.config_path = Path(config_path)
        self._sites: dict[str, SiteConfig] | None = None

    def _load_config(self) -> dict[str, SiteConfig]:
        """Load and parse site configurations from JSON."""
        if self._sites is not None:
            return self._sites

        with open(self.config_path) as f:
            data = json.load(f)

        sites = {}
        for site_id, site_data in data.get("sites", {}).items():
            sites[site_id] = SiteConfig(
                name=site_data.get("name", site_id),
                base_url=site_data["baseUrl"],
                sections=site_data.get("sections", {}),
                pages=site_data.get("pages", {}),
                selector=site_data["selectors"]["copyButton"],
                method=site_data["selectors"].get("method", "click_copy"),
            )
        self._sites = sites
        return sites

    def list_sites(self) -> list[str]:
        """List all configured site IDs."""
        return list(self._load_config().keys())

    def get_site(self, site_id: str) -> SiteConfig:
        """Get configuration for a specific site."""
        sites = self._load_config()
        if site_id not in sites:
            raise ValueError(f"Site '{site_id}' not found. Available: {list(sites.keys())}")
        return sites[site_id]

    def get_page_url(self, site_id: str, page: str) -> str:
        """Get the full URL for a page on a site."""
        site = self.get_site(site_id)
        return site.get_page_url(page)

    def list_pages(self, site_id: str) -> list[str]:
        """List all configured pages for a site."""
        site = self.get_site(site_id)
        return list(site.pages.keys())

    def create_job(self, site_id: str, page: str, use_cache: bool = True) -> ScrapeJob:
        """Create a ScrapeJob for a specific site/page."""
        site = self.get_site(site_id)
        return ScrapeJob(
            name=f"{site_id}/{page}",
            url=site.get_page_url(page),
            selector=site.selector,
            method=site.method,
            use_cache=use_cache,
        )

    def create_all_jobs(self, site_id: str, use_cache: bool = True) -> list[ScrapeJob]:
        """Create ScrapeJobs for all pages in a site."""
        return [self.create_job(site_id, page, use_cache) for page in self.list_pages(site_id)]
