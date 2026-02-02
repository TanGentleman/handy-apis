"""Central configuration for docpull.

Reads configuration from environment variables, with .env file support.
Run 'python deploy.py' to auto-generate .env after deployment.

Environment variables:
- SCRAPER_API_URL: The Modal API URL (required)
- IS_PROD: Production mode flag (optional, default: false)
- MODAL_KEY / MODAL_SECRET: Authentication credentials (optional)
"""

import os
from pathlib import Path

# Load .env file from project root if it exists
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).parent.parent / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
except (ImportError, PermissionError, OSError):
    pass  # dotenv not installed or .env not accessible, rely on environment variables

# Configuration values
SCRAPER_API_URL: str | None = os.environ.get("SCRAPER_API_URL")
IS_PROD = os.environ.get("IS_PROD", "false").lower() in ("true", "1", "yes")
ACCESS_KEY: str | None = os.environ.get("ACCESS_KEY")


def get_api_url() -> str:
    """Get the configured API URL.

    Returns:
        str: The API URL

    Raises:
        RuntimeError: If the API URL is not configured
    """
    if not SCRAPER_API_URL:
        raise RuntimeError(
            "SCRAPER_API_URL is not configured.\n"
            "Either:\n"
            "  1. Run 'python deploy.py' to deploy and auto-configure, or\n"
            "  2. Set SCRAPER_API_URL in .env or as an environment variable"
        )
    return SCRAPER_API_URL


def get_auth_headers() -> dict:
    """Get Modal authentication headers if configured.

    Returns:
        dict: Headers with Modal-Key and Modal-Secret if both are set, empty dict otherwise
    """
    key = os.environ.get("MODAL_KEY")
    secret = os.environ.get("MODAL_SECRET")
    if key and secret:
        return {"Modal-Key": key, "Modal-Secret": secret}
    return {}


def get_access_key() -> str | None:
    """Get the configured access key for protected operations.

    Returns:
        str | None: The access key if configured, None otherwise
    """
    return ACCESS_KEY


def verify_access_key(provided_key: str | None) -> bool:
    """Verify if the provided access key matches the configured one.

    Args:
        provided_key: The key provided by the client

    Returns:
        bool: True if access key is not configured (open access) or if keys match
    """
    if not ACCESS_KEY:
        return True  # No key configured = open access
    return provided_key == ACCESS_KEY
