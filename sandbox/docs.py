"""Documentation upload to Modal Volumes.

Canonical functions for uploading docpull collections to Modal Volumes,
replacing the divergent upload paths in opencode.py and chat.py.
"""

try:
    import modal
except ImportError:
    modal = None

DEFAULT_VOLUME_NAME = "docpull-docs"
DEFAULT_REMOTE_PREFIX = "/docs"


def get_docs_volume(volume_name=DEFAULT_VOLUME_NAME):
    """Get or create a Modal Volume for docs.

    Args:
        volume_name: Name of the Modal Volume

    Returns:
        A modal.Volume instance
    """
    if modal is None:
        raise ImportError("Modal is required. Install with: pip install modal")

    return modal.Volume.from_name(volume_name, create_if_missing=True)


def upload_collections(
    collections: list[str],
    volume_name=DEFAULT_VOLUME_NAME,
    remote_prefix=DEFAULT_REMOTE_PREFIX,
) -> int:
    """Upload docpull collections from ~/.docpull/ to a Modal Volume.

    Each collection is uploaded to {remote_prefix}/{collection}/ on the volume.
    Uses cli.store to locate collection paths.

    Args:
        collections: List of collection IDs to upload
        volume_name: Name of the Modal Volume
        remote_prefix: Remote directory prefix on the volume

    Returns:
        Total number of files uploaded
    """
    if modal is None:
        raise ImportError("Modal is required. Install with: pip install modal")

    # Lazy import to avoid circular deps
    from cli.store import collection_exists, get_collection_path

    volume = get_docs_volume(volume_name)
    total_files = 0

    with volume.batch_upload(force=True) as batch:
        for collection in collections:
            if not collection_exists(collection):
                print(f"⚠️  Collection '{collection}' not found, skipping")
                continue

            collection_path = get_collection_path(collection)
            file_count = 0

            for file_path in collection_path.rglob("*.md"):
                relative = file_path.relative_to(collection_path)
                remote_path = f"{remote_prefix}/{collection}/{relative}"
                batch.put_file(file_path, remote_path)
                file_count += 1

            total_files += file_count
            print(f"📤 Queued {file_count} files from {collection}")

    print(f"✅ Uploaded {total_files} files to {volume_name}")
    return total_files
