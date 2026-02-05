"""~/.docpull/ folder management for agent-ready documentation.

This module handles:
- Global store at ~/.docpull/
- manifest.json tracking of loaded collections
- Downloading and extracting documentation from the API
"""

import json
import os
import time
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Optional

import httpx

from config.utils import get_api_url, get_auth_headers

# Global docpull home directory
DOCPULL_HOME = Path.home() / ".docpull"
MANIFEST_FILE = DOCPULL_HOME / "manifest.json"


def ensure_home() -> Path:
    """Ensure ~/.docpull/ directory exists."""
    DOCPULL_HOME.mkdir(parents=True, exist_ok=True)
    return DOCPULL_HOME


def get_manifest() -> dict:
    """Load manifest.json or return empty manifest."""
    if not MANIFEST_FILE.exists():
        return {
            "version": "1.0",
            "api_url": None,
            "collections": {},
        }
    try:
        with open(MANIFEST_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {
            "version": "1.0",
            "api_url": None,
            "collections": {},
        }


def save_manifest(manifest: dict) -> None:
    """Save manifest.json to disk."""
    ensure_home()
    with open(MANIFEST_FILE, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")


def update_manifest(collection: str, metadata: dict) -> None:
    """Update manifest with collection metadata."""
    manifest = get_manifest()
    manifest["api_url"] = get_api_url()
    manifest["collections"][collection] = {
        **metadata,
        "loaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    save_manifest(manifest)


def remove_from_manifest(collection: str) -> bool:
    """Remove a collection from manifest. Returns True if found and removed."""
    manifest = get_manifest()
    if collection in manifest.get("collections", {}):
        del manifest["collections"][collection]
        save_manifest(manifest)
        return True
    return False


def get_collection_path(collection: str) -> Path:
    """Get the path to a collection folder."""
    return DOCPULL_HOME / collection


def collection_exists(collection: str) -> bool:
    """Check if a collection exists locally."""
    return get_collection_path(collection).is_dir()


def list_local_collections() -> list[dict]:
    """List all locally loaded collections with their metadata."""
    manifest = get_manifest()
    collections = []
    for coll_id, meta in manifest.get("collections", {}).items():
        path = get_collection_path(coll_id)
        collections.append({
            "id": coll_id,
            "exists": path.is_dir(),
            "path": str(path),
            **meta,
        })
    return collections


def get_available_sites(timeout: float = 30.0) -> list[dict]:
    """Fetch available sites from the API."""
    api_url = get_api_url()
    resp = httpx.get(
        f"{api_url}/sites",
        headers=get_auth_headers(),
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json().get("sites", [])


def download_collection(
    collection: str,
    force: bool = False,
    timeout: float = 300.0,
    on_progress: Optional[callable] = None,
) -> tuple[Path, dict]:
    """Download a collection from the API and extract to ~/.docpull/<collection>/.

    Args:
        collection: The site ID to download
        force: If True, re-download even if exists
        timeout: HTTP timeout in seconds
        on_progress: Optional callback for progress updates

    Returns:
        Tuple of (collection_path, stats_dict)

    Raises:
        httpx.HTTPStatusError: If API request fails
        ValueError: If collection not found
    """
    api_url = get_api_url()
    collection_path = get_collection_path(collection)

    # Check if already exists
    if collection_path.is_dir() and not force:
        manifest = get_manifest()
        if collection in manifest.get("collections", {}):
            return collection_path, manifest["collections"][collection]

    if on_progress:
        on_progress(f"Downloading {collection}...")

    # Download ZIP from API
    resp = httpx.get(
        f"{api_url}/sites/{collection}/download",
        headers=get_auth_headers(),
        timeout=timeout,
    )
    resp.raise_for_status()

    # Parse stats from headers
    stats = {
        "total": int(resp.headers.get("X-Download-Total", 0)),
        "cached": int(resp.headers.get("X-Download-Cached", 0)),
        "scraped": int(resp.headers.get("X-Download-Scraped", 0)),
        "failed": int(resp.headers.get("X-Download-Failed", 0)),
        "size_bytes": len(resp.content),
    }

    if on_progress:
        on_progress(f"Extracting {collection} ({stats['total']} pages)...")

    # Extract ZIP to collection folder
    # The ZIP contains files like: <collection>/page.md
    # We want to extract to ~/.docpull/<collection>/page.md
    collection_path.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(BytesIO(resp.content)) as zf:
        for member in zf.namelist():
            # ZIP structure: <site_id>/path.md
            # We strip the site_id prefix and extract directly to collection_path
            parts = member.split("/", 1)
            if len(parts) == 2 and parts[0] == collection:
                relative_path = parts[1]
                if relative_path:  # Skip the directory entry itself
                    target_path = collection_path / relative_path
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target_path, "wb") as dst:
                        dst.write(src.read())

    # Update manifest
    manifest = get_manifest()
    manifest["api_url"] = api_url
    manifest["collections"][collection] = {
        "pages": stats["total"],
        "size_bytes": stats["size_bytes"],
        "loaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    save_manifest(manifest)

    return collection_path, stats


def delete_collection(collection: str) -> bool:
    """Delete a collection from ~/.docpull/.

    Returns True if deleted, False if not found.
    """
    import shutil

    collection_path = get_collection_path(collection)
    removed_manifest = remove_from_manifest(collection)

    if collection_path.is_dir():
        shutil.rmtree(collection_path)
        return True

    return removed_manifest


def get_collection_stats(collection: str) -> Optional[dict]:
    """Get stats for a loaded collection."""
    manifest = get_manifest()
    if collection not in manifest.get("collections", {}):
        return None

    meta = manifest["collections"][collection]
    path = get_collection_path(collection)

    # Count actual files
    file_count = 0
    total_size = 0
    if path.is_dir():
        for f in path.rglob("*.md"):
            file_count += 1
            total_size += f.stat().st_size

    return {
        "id": collection,
        "path": str(path),
        "exists": path.is_dir(),
        "file_count": file_count,
        "total_size": total_size,
        **meta,
    }
