"""Bulk job processing for parallel documentation scraping."""

import math
import time
import uuid
from enum import Enum

import modal

from scraper.urls import is_asset_url  # noqa: F401 - re-exported for backwards compat

# Shared Modal Dicts (same names as main API for interop)
jobs = modal.Dict.from_name("scrape-jobs", create_if_missing=True)

# Constants
MAX_CONTAINERS = 100
DEFAULT_DELAY_MS = 1000
USER_AGENT = "DocPull/1.0 (+https://github.com/TanGentleman/docpull)"


class JobStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


def create_job(urls: list[str], by_site: dict, assets: list, unknown: list) -> str:
    """Create a new job entry and return job_id."""
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {
        "status": JobStatus.PENDING,
        "created_at": time.time(),
        "updated_at": time.time(),
        "input": {
            "total_urls": len(urls),
            "to_scrape": sum(len(p) for p in by_site.values()),
            "assets": len(assets),
            "unknown": len(unknown),
            "sites": list(by_site.keys()),
        },
        "progress": {"completed": 0, "success": 0, "skipped": 0, "failed": 0},
        "workers": {"total": 0, "completed": 0},
        "errors": [],
    }
    return job_id


def update_job_progress(job_id: str, result: dict):
    """Update job progress from a worker result."""
    try:
        job = jobs[job_id]
        job["progress"]["completed"] += result.get("success", 0) + result.get("skipped", 0) + result.get("failed", 0)
        job["progress"]["success"] += result.get("success", 0)
        job["progress"]["skipped"] += result.get("skipped", 0)
        job["progress"]["failed"] += result.get("failed", 0)
        job["workers"]["completed"] += 1
        job["updated_at"] = time.time()

        if result.get("errors") and len(job["errors"]) < 20:
            job["errors"].extend(result["errors"][:20 - len(job["errors"])])

        if job["workers"]["completed"] >= job["workers"]["total"]:
            job["status"] = JobStatus.COMPLETED

        jobs[job_id] = job
    except Exception as e:
        print(f"[update_job_progress] Error: {e}")


def calculate_batches(by_site: dict[str, list[str]], max_containers: int = MAX_CONTAINERS) -> list[dict]:
    """Distribute containers across sites proportionally."""
    if not by_site:
        return []

    total_urls = sum(len(paths) for paths in by_site.values())
    batches = []

    for site_id, paths in by_site.items():
        if not paths:
            continue

        # Proportional allocation (min 1, max len(paths))
        containers = max(1, min(len(paths), round(len(paths) / total_urls * max_containers)))
        batch_size = math.ceil(len(paths) / containers)

        for i in range(0, len(paths), batch_size):
            batches.append({"site_id": site_id, "paths": paths[i:i + batch_size]})

    return batches
