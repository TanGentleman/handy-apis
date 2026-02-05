"""Modal Sandbox with OpenCode for cloud-based agent chat.

This module provides utilities for creating and managing Modal Sandboxes
with OpenCode pre-installed and configured for documentation-aware coding.

Based on Modal's Sandbox documentation and OpenCode server integration.
"""

import secrets
import time
from pathlib import Path
from typing import Optional

try:
    import modal
except ImportError:
    modal = None


def get_opencode_image() -> "modal.Image":
    """Create a Modal Image with OpenCode installed."""
    if modal is None:
        raise ImportError("Modal is required. Install with: pip install modal")

    return (
        modal.Image.debian_slim(python_version="3.11")
        .apt_install("git", "curl", "build-essential")
        .run_commands(
            # Install Go 1.22 (required for OpenCode)
            "curl -L https://go.dev/dl/go1.22.0.linux-amd64.tar.gz | tar -C /usr/local -xzf -",
            "ln -s /usr/local/go/bin/go /usr/local/bin/go",
            # Install OpenCode
            "GOBIN=/usr/local/bin /usr/local/go/bin/go install github.com/opencode-ai/opencode@latest",
        )
        .env({
            "PATH": "/usr/local/bin:/usr/local/go/bin:/root/go/bin:/usr/bin:/bin",
            "HOME": "/root",
        })
    )


def create_opencode_sandbox(
    volume_name: str = "docpull-docs",
    docs_mount_path: str = "/docs",
    timeout_seconds: int = 3600,
    password: Optional[str] = None,
) -> dict:
    """Create a Modal Sandbox with OpenCode server.

    Args:
        volume_name: Name of the Modal Volume containing docs
        docs_mount_path: Where to mount the docs volume
        timeout_seconds: Sandbox timeout (default: 1 hour)
        password: OpenCode server password (auto-generated if not provided)

    Returns:
        dict with sandbox info (sandbox_id, web_url, password, etc.)
    """
    if modal is None:
        raise ImportError("Modal is required. Install with: pip install modal")

    if password is None:
        password = secrets.token_urlsafe(12)

    # Get or create volume
    volume = modal.Volume.from_name(volume_name, create_if_missing=True)

    # Build image with password set
    image = get_opencode_image().env({
        "OPENCODE_SERVER_PASSWORD": password,
    })

    # Create sandbox
    sandbox = modal.Sandbox.create(
        image=image,
        volumes={docs_mount_path: volume},
        timeout=timeout_seconds,
        encrypted_ports=[8080],
        workdir=docs_mount_path,
        entrypoint=[
            "opencode", "server",
            "--port", "8080",
            "--host", "0.0.0.0",
        ],
    )

    # Wait for sandbox to be ready
    time.sleep(3)

    # Get tunnel URL
    tunnels = sandbox.tunnels()
    web_url = tunnels.get(8080, {}).url if 8080 in tunnels else None

    return {
        "sandbox_id": sandbox.object_id,
        "web_url": web_url,
        "password": password,
        "username": "opencode",
        "volume": volume_name,
        "docs_path": docs_mount_path,
        "timeout_seconds": timeout_seconds,
    }


def upload_collection_to_volume(
    collection_path: Path,
    collection_name: str,
    volume_name: str = "docpull-docs",
) -> int:
    """Upload a collection folder to a Modal Volume.

    Args:
        collection_path: Local path to the collection folder
        collection_name: Name to use in the volume (e.g., "modal")
        volume_name: Modal Volume name

    Returns:
        Number of files uploaded
    """
    if modal is None:
        raise ImportError("Modal is required. Install with: pip install modal")

    volume = modal.Volume.from_name(volume_name, create_if_missing=True)

    file_count = 0
    with volume.batch_upload() as batch:
        for file_path in collection_path.rglob("*"):
            if file_path.is_file():
                relative = file_path.relative_to(collection_path)
                remote_path = f"/docs/{collection_name}/{relative}"
                batch.put_file(file_path, remote_path)
                file_count += 1

    volume.commit()
    return file_count


def stop_sandbox(sandbox_id: str) -> bool:
    """Terminate a running sandbox.

    Args:
        sandbox_id: The sandbox ID to terminate

    Returns:
        True if terminated successfully
    """
    if modal is None:
        raise ImportError("Modal is required. Install with: pip install modal")

    try:
        sandbox = modal.Sandbox.from_id(sandbox_id)
        sandbox.terminate()
        return True
    except Exception:
        return False


def get_sandbox_status(sandbox_id: str) -> Optional[dict]:
    """Get status of a sandbox.

    Args:
        sandbox_id: The sandbox ID to check

    Returns:
        dict with status info, or None if not found
    """
    if modal is None:
        raise ImportError("Modal is required. Install with: pip install modal")

    try:
        sandbox = modal.Sandbox.from_id(sandbox_id)
        return {
            "sandbox_id": sandbox_id,
            "status": "running",  # Modal doesn't expose detailed status
        }
    except Exception:
        return None
