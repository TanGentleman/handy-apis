# ---
# cmd: ["python", "sandbox/opencode.py"]
# pytest: false
# ---

# # Run OpenCode in a Modal Sandbox with Docpull Docs

# This script spins up an [OpenCode](https://opencode.ai/docs/) coding agent
# in a Modal Sandbox with your scraped documentation pre-loaded.

# The agent has access to all your docs in `/docs` and can help you:
# - Navigate and understand documentation
# - Write code with context from multiple doc sources
# - Compare APIs across different services

# ## Usage
#
# ```bash
# # Start the sandbox (prints access URLs)
# python sandbox/opencode.py
#
# # With custom options
# python sandbox/opencode.py --timeout 6 --include-repo
# ```

import secrets
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import modal
except ImportError:
    modal = None

# Ensure project root is on path for standalone execution
_project_root = str(Path(__file__).resolve().parent.parent)
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from sandbox.image import build_agent_image, add_local_repo
from sandbox.sandbox import create_sandbox

# ## Constants

MINUTES = 60  # seconds
HOURS = 60 * MINUTES
OPENCODE_PORT = 4096
DEFAULT_TIMEOUT = 12 * HOURS
APP_NAME = "docpull-opencode"
VOLUME_NAME = "docpull-docs"

here = Path(__file__).resolve()
repo_root = here.parent.parent


# ## Create the Sandbox

def create_opencode_sandbox(
    include_config: bool = True,
    include_modal_creds: bool = True,
    include_repo: bool = False,
    include_docs_volume: bool = True,
    timeout_hours: float = 12,
    password: Optional[str] = None,
    verbose: bool = True,
) -> dict:
    """Create a Modal Sandbox running OpenCode with documentation access.

    Args:
        include_config: Include local ~/.config/opencode/opencode.json
        include_modal_creds: Include Modal credentials for the agent
        include_repo: Mount the local docpull repository into the sandbox
        include_docs_volume: Mount the docpull-docs volume with scraped docs
        timeout_hours: How long the sandbox can run (max 24)
        password: Server password (auto-generated if not provided)
        verbose: Print access instructions

    Returns:
        dict with sandbox_id, web_url, tui_command, password, etc.
    """
    if modal is None:
        raise ImportError("Modal is required. Install with: pip install modal")

    # Generate password for OpenCode server
    if password is None:
        password = secrets.token_urlsafe(13)

    # Create ephemeral secret for the password
    password_secret = modal.Secret.from_dict({"OPENCODE_SERVER_PASSWORD": password})

    # Build the image
    print("🔨 Building OpenCode image...")
    image = build_agent_image(
        include_config=include_config,
        include_modal_creds=include_modal_creds,
    )

    # Determine workdir
    workdir = "/docs"

    if include_repo:
        image, workdir = add_local_repo(image)

    # Set up volumes
    volumes = {}
    if include_docs_volume:
        print(f"📚 Mounting volume {VOLUME_NAME} at /docs")
        volume = modal.Volume.from_name(VOLUME_NAME, create_if_missing=True)
        volumes["/docs"] = volume

    # Create the sandbox
    print("🏖️  Creating sandbox...")
    timeout = int(timeout_hours * HOURS)

    # idle_timeout auto-terminates after 30 min of no connections — saves cost
    idle_timeout = int(min(timeout, 30 * MINUTES))

    sandbox = create_sandbox(
        "opencode",
        "serve",
        "--hostname=0.0.0.0",
        f"--port={OPENCODE_PORT}",
        "--log-level=DEBUG",
        "--print-logs",
        image=image,
        secrets=[password_secret],
        volumes=volumes,
        workdir=workdir,
        encrypted_ports=[OPENCODE_PORT],
        timeout=timeout,
        idle_timeout=idle_timeout,
        app_name=APP_NAME,
    )

    # Wait for tunnel to be provisioned (may take a moment)
    tunnel = None
    for _ in range(10):
        tunnels = sandbox.tunnels()
        if OPENCODE_PORT in tunnels:
            tunnel = tunnels[OPENCODE_PORT]
            break
        time.sleep(1)

    if tunnel is None:
        print("⚠️  Tunnel not ready yet. Use `modal shell` to access the sandbox.")
        print(f"   modal shell {sandbox.object_id}")

    result = {
        "sandbox_id": sandbox.object_id,
        "web_url": tunnel.url if tunnel else None,
        "password": password,
        "username": "opencode",
        "workdir": workdir,
        "timeout_hours": timeout_hours,
    }

    if verbose:
        print_access_info(result)

    return result


# ## Print Access Information

def print_access_info(info: dict) -> None:
    """Print helpful access instructions."""
    print()
    print("=" * 60)
    print("🎉 OpenCode Sandbox Ready!")
    print("=" * 60)
    print()
    print("📋 Sandbox ID:")
    print(f"   {info['sandbox_id']}")
    print()
    print("🌐 Web UI:")
    print(f"   {info['web_url']}")
    print(f"   Username: {info['username']}")
    print(f"   Password: {info['password']}")
    print()
    print("💻 Terminal UI (run locally):")
    print(f"   OPENCODE_SERVER_PASSWORD={info['password']} opencode attach {info['web_url']}")
    print()
    print("🐚 Direct Shell Access:")
    print(f"   modal shell {info['sandbox_id']}")
    print()
    print(f"⏱️  Timeout: {info['timeout_hours']} hours")
    print("=" * 60)


# ## Upload Documentation to Volume

def upload_docs_to_volume(
    docs_path: Optional[Path] = None,
    volume_name: str = VOLUME_NAME,
) -> int:
    """Upload local docs/ folder to the Modal volume.

    Args:
        docs_path: Path to docs folder (defaults to repo_root/docs)
        volume_name: Name of the Modal volume

    Returns:
        Number of files uploaded
    """
    if modal is None:
        raise ImportError("Modal is required. Install with: pip install modal")

    if docs_path is None:
        docs_path = repo_root / "docs"

    if not docs_path.exists():
        print(f"❌ Docs folder not found: {docs_path}")
        return 0

    volume = modal.Volume.from_name(volume_name, create_if_missing=True)

    print(f"📤 Uploading docs from {docs_path}...")
    file_count = 0

    # batch_upload handles the remote write when the context manager exits.
    # volume.commit() is only valid inside a Modal container — not needed here.
    with volume.batch_upload(force=True) as batch:
        for file_path in docs_path.rglob("*"):
            if file_path.is_file() and not file_path.name.startswith("."):
                relative = file_path.relative_to(docs_path)
                remote_path = f"/{relative}"
                batch.put_file(file_path, remote_path)
                file_count += 1
                if file_count % 10 == 0:
                    print(f"   Uploaded {file_count} files...")

    print(f"✅ Uploaded {file_count} files to {volume_name}")
    return file_count


# ## Stop Sandbox

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
        print(f"✅ Terminated sandbox {sandbox_id}")
        return True
    except Exception as e:
        print(f"❌ Failed to terminate: {e}")
        return False


# ## Get Sandbox Status

def get_sandbox_status(sandbox_id: str) -> Optional[dict]:
    """Get status of a running sandbox.

    Args:
        sandbox_id: The sandbox ID to check

    Returns:
        dict with status info, or None if not found
    """
    if modal is None:
        raise ImportError("Modal is required. Install with: pip install modal")

    try:
        sandbox = modal.Sandbox.from_id(sandbox_id)
        tunnels = sandbox.tunnels()
        return {
            "sandbox_id": sandbox_id,
            "status": "running",
            "web_url": tunnels.get(OPENCODE_PORT, {}).url if OPENCODE_PORT in tunnels else None,
        }
    except Exception:
        return None


# ## List Running Sandboxes

def list_sandboxes() -> list[dict]:
    """List all running OpenCode sandboxes.

    Returns:
        List of sandbox info dicts
    """
    if modal is None:
        raise ImportError("Modal is required. Install with: pip install modal")

    try:
        app = modal.App.lookup(APP_NAME)
        sandboxes = []
        for sb in modal.Sandbox.list(app_id=app.app_id):
            sandboxes.append({
                "sandbox_id": sb.object_id,
            })
        return sandboxes
    except Exception:
        return []


# ## Main: Run as Script

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Start an OpenCode sandbox with docpull documentation"
    )
    parser.add_argument(
        "--timeout", "-t",
        type=float,
        default=12,
        help="Sandbox timeout in hours (default: 12, max: 24)"
    )
    parser.add_argument(
        "--include-repo", "-r",
        action="store_true",
        help="Mount the local docpull repository into the sandbox"
    )
    parser.add_argument(
        "--no-config",
        action="store_true",
        help="Don't include local OpenCode config"
    )
    parser.add_argument(
        "--no-modal-creds",
        action="store_true",
        help="Don't include Modal credentials"
    )
    parser.add_argument(
        "--no-docs-volume",
        action="store_true",
        help="Don't mount the docs volume"
    )
    parser.add_argument(
        "--upload-docs",
        action="store_true",
        help="Upload local docs/ folder to volume before starting"
    )
    parser.add_argument(
        "--password", "-p",
        type=str,
        default=None,
        help="Custom server password (auto-generated if not provided)"
    )
    parser.add_argument(
        "--stop",
        type=str,
        metavar="SANDBOX_ID",
        help="Stop a running sandbox instead of starting one"
    )
    parser.add_argument(
        "--status",
        type=str,
        metavar="SANDBOX_ID",
        help="Check status of a running sandbox"
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List running sandboxes"
    )

    args = parser.parse_args()

    if args.stop:
        stop_sandbox(args.stop)
    elif args.status:
        info = get_sandbox_status(args.status)
        if info:
            print(f"Sandbox: {info['sandbox_id']}")
            print(f"Status:  {info['status']}")
            if info.get("web_url"):
                print(f"Web UI:  {info['web_url']}")
        else:
            print(f"Sandbox {args.status} not found or not running")
    elif args.list:
        sandboxes = list_sandboxes()
        if sandboxes:
            print(f"Found {len(sandboxes)} running sandbox(es):")
            for sb in sandboxes:
                print(f"  • {sb['sandbox_id']}")
        else:
            print("No running sandboxes found")
    else:
        # Upload docs if requested
        if args.upload_docs:
            upload_docs_to_volume()

        # Create the sandbox
        create_opencode_sandbox(
            include_config=not args.no_config,
            include_modal_creds=not args.no_modal_creds,
            include_repo=args.include_repo,
            include_docs_volume=not args.no_docs_volume,
            timeout_hours=min(args.timeout, 24),
            password=args.password,
        )
