"""Modal image building for OpenCode sandboxes.

Functions for constructing Docker images with OpenCode, configuration,
credentials, and local repositories baked in.
"""

import os
from pathlib import Path
from typing import Optional

try:
    import modal
except ImportError:
    modal = None

repo_root = Path(__file__).resolve().parent.parent


def get_opencode_image():
    """Create a Modal Image with OpenCode and useful tools installed.

    Uses the official OpenCode installer for reliable installation.
    Includes common dev tools for documentation work.
    """
    if modal is None:
        raise ImportError("Modal is required. Install with: pip install modal")

    image = (
        modal.Image.debian_slim(python_version="3.12")
        .apt_install("curl", "git", "vim", "tree")
        .run_commands("curl -fsSL https://opencode.ai/install | bash")
        .env({"PATH": "/root/.opencode/bin:${PATH}"})
    )

    return image


def add_opencode_config(image):
    """Add local OpenCode configuration if it exists.

    This brings your personal OpenCode settings (model preferences,
    API keys for other services, etc.) into the sandbox.
    """
    config_path = Path.home() / ".config" / "opencode" / "opencode.json"
    if config_path.exists():
        print(f"📦 Including OpenCode config from {config_path}")
        image = image.add_local_file(config_path, "/root/.config/opencode/opencode.json")
    return image


def add_modal_credentials(image):
    """Add Modal credentials so the agent can deploy and test Modal code.

    Checks for ~/.modal.toml first, falls back to environment variables.
    """
    modal_path = Path.home() / ".modal.toml"

    if modal_path.exists():
        print(f"🔑 Including Modal credentials from {modal_path}")
        image = image.add_local_file(modal_path, "/root/.modal.toml")
    else:
        token_id = os.environ.get("MODAL_TOKEN_ID")
        token_secret = os.environ.get("MODAL_TOKEN_SECRET")
        if token_id and token_secret:
            print("🔑 Including Modal credentials from environment")
            image = image.env({
                "MODAL_TOKEN_ID": token_id,
                "MODAL_TOKEN_SECRET": token_secret,
            })

    return image


def add_local_repo(
    image,
    local_path: Optional[Path] = None,
    remote_path: Optional[str] = None,
) -> tuple:
    """Mount a local directory into the sandbox.

    Args:
        image: The Modal image to add to
        local_path: Local directory to mount (defaults to docpull repo)
        remote_path: Where to mount in the container (defaults to /root/{dirname})

    Returns:
        Tuple of (image, workdir) where workdir is the mounted path
    """
    if local_path is None:
        local_path = repo_root

    if remote_path is None:
        remote_path = f"/root/{local_path.name}"

    print(f"📁 Mounting {local_path} → {remote_path}")
    image = image.add_local_dir(local_path, remote_path, ignore=[
        ".git",
        "__pycache__",
        "*.pyc",
        ".env",
        ".venv",
        "node_modules",
        "*.egg-info",
    ])

    return image, remote_path


def build_agent_image(include_config=True, include_modal_creds=True):
    """Combines get_opencode_image + config + creds into one call.

    Args:
        include_config: Include local ~/.config/opencode/opencode.json
        include_modal_creds: Include Modal credentials for the agent

    Returns:
        A Modal Image ready for sandbox creation
    """
    image = get_opencode_image()

    if include_config:
        image = add_opencode_config(image)

    if include_modal_creds:
        image = add_modal_credentials(image)

    return image
