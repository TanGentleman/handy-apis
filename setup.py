#!/usr/bin/env python3
"""Interactive deployment script for docpull.

Automates the deployment process:
1. Check for virtual environment
2. Install requirements
3. Deploy Modal API
4. Save API URL to ui/config.py
5. Deploy Modal UI
6. Display summary with URLs
"""

import argparse
import json
import re
import subprocess
import sys
import webbrowser
from pathlib import Path


def check_venv():
    """Verify running in a virtual environment."""
    if sys.prefix == sys.base_prefix:
        print("❌ Error: Not running in a virtual environment")
        print("\nPlease activate a virtual environment first:")
        print("  python -m venv venv")
        print("  source venv/bin/activate  # On macOS/Linux")
        print("  venv\\Scripts\\activate     # On Windows")
        sys.exit(1)
    print("✅ Virtual environment detected")


def install_requirements():
    """Install Python dependencies from requirements.txt."""
    print("\n📦 Installing dependencies...")
    requirements_path = Path(__file__).parent / "requirements.txt"

    if not requirements_path.exists():
        print("❌ Error: requirements.txt not found")
        sys.exit(1)

    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "-r", str(requirements_path)],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("❌ Error installing dependencies:")
        print(result.stderr)
        sys.exit(1)

    print("✅ Dependencies installed")


def get_existing_apps():
    """Get list of existing Modal apps.

    Returns:
        dict: Map of app description to app ID for deployed apps
    """
    result = subprocess.run(
        ["modal", "app", "list", "--json"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        # Modal CLI not set up or error - not fatal, just return empty
        return {}

    try:
        apps = json.loads(result.stdout)
        return {
            app["Description"]: app["App ID"]
            for app in apps
            if app["State"] == "deployed"
        }
    except (json.JSONDecodeError, KeyError):
        return {}


def deploy_api():
    """Deploy Modal API and extract URL.

    Returns:
        str: API URL from deployment output
    """
    print("\n🚀 Deploying Modal API...")
    api_path = Path(__file__).parent / "api" / "scraper.py"

    if not api_path.exists():
        print(f"❌ Error: {api_path} not found")
        sys.exit(1)

    # Check for existing deployment
    existing_apps = get_existing_apps()
    if "content-scraper-api" in existing_apps:
        print(f"⚠️  Note: Redeploying existing app (ID: {existing_apps['content-scraper-api']})")

    result = subprocess.run(
        [sys.executable, "-m", "modal", "deploy", str(api_path)],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("❌ Error deploying API:")
        print(result.stderr)
        sys.exit(1)

    # Extract API URL from deployment output
    # Looking for the web function URL in the deploy output
    # Example: https://tangentleman--content-scraper-api-fastapi-app.modal.run
    url_pattern = r'https://[^\s]+--content-scraper-api[^\s]+\.modal\.run'
    match = re.search(url_pattern, result.stdout)

    if not match:
        print("❌ Error: Could not extract API URL from deployment output")
        print("\nDeployment output:")
        print(result.stdout)
        print("\nSearching for URL pattern:", url_pattern)
        sys.exit(1)

    api_url = match.group(0)
    print(f"✅ API deployed: {api_url}")
    return api_url


def save_config(api_url):
    """Save API URL to ui/config.py.

    Args:
        api_url: The Modal API URL to save
    """
    print("\n💾 Saving configuration...")
    config_path = Path(__file__).parent / "ui" / "config.py"

    config_content = f'''"""Configuration for docpull UI."""

SCRAPER_API_URL = "{api_url}"
IS_PROD = False
'''

    try:
        config_path.write_text(config_content)
        print(f"✅ Configuration saved to {config_path}")
    except OSError as e:
        print(f"❌ Error saving configuration: {e}")
        sys.exit(1)


def deploy_ui():
    """Deploy Modal UI and extract URL.

    Returns:
        str: UI URL from deployment output
    """
    print("\n🚀 Deploying Modal UI...")
    ui_path = Path(__file__).parent / "ui" / "app.py"

    if not ui_path.exists():
        print(f"❌ Error: {ui_path} not found")
        sys.exit(1)

    # Check for existing deployment
    existing_apps = get_existing_apps()
    if "docpull" in existing_apps:
        print(f"⚠️  Note: Redeploying existing app (ID: {existing_apps['docpull']})")

    result = subprocess.run(
        [sys.executable, "-m", "modal", "deploy", str(ui_path)],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("❌ Error deploying UI:")
        print(result.stderr)
        sys.exit(1)

    # Extract UI URL from deployment output
    # Looking for the web function URL
    # Example: https://tangentleman--docpull-web.modal.run
    url_pattern = r'https://[^\s]+--docpull[^\s]+\.modal\.run'
    match = re.search(url_pattern, result.stdout)

    if not match:
        print("❌ Error: Could not extract UI URL from deployment output")
        print("\nDeployment output:")
        print(result.stdout)
        print("\nSearching for URL pattern:", url_pattern)
        sys.exit(1)

    ui_url = match.group(0)
    print(f"✅ UI deployed: {ui_url}")
    return ui_url


def display_summary(api_url, ui_url, open_browser=False):
    """Display deployment summary.

    Args:
        api_url: The deployed API URL
        ui_url: The deployed UI URL
        open_browser: Whether to open the UI in browser
    """
    print("\n" + "=" * 60)
    print("🎉 Deployment Complete!")
    print("=" * 60)
    print(f"\n📡 API URL:  {api_url}")
    print(f"🌐 UI URL:   {ui_url}")
    print("\n📚 Next steps:")
    print("  - Test the API: curl " + api_url)
    print("  - Visit the UI in your browser")
    print("  - Use the CLI: python cli/main.py sites")
    print("\n🛑 To stop deployments:")
    print("  python teardown.py")
    print("=" * 60)

    if open_browser:
        print("\n🌐 Opening UI in browser...")
        webbrowser.open(ui_url)


def main():
    """Run the deployment process."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Deploy docpull to Modal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python setup.py                    # Standard deployment
  python setup.py --open-browser     # Deploy and open UI
  python setup.py --json             # Output as JSON
        """
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format (for programmatic use)",
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the deployed UI in your browser after deployment",
    )
    parser.add_argument(
        "--skip-install",
        action="store_true",
        help="Skip dependency installation (assumes already installed)",
    )
    args = parser.parse_args()

    json_mode = args.json
    open_browser = args.open_browser
    skip_install = args.skip_install

    if not json_mode:
        print("🔧 Docpull Deployment Setup")
        print("=" * 60)

    try:
        # Step 1: Check virtual environment
        check_venv()

        # Step 2: Install dependencies (optional skip)
        if not skip_install:
            install_requirements()
        elif not json_mode:
            print("\n⏭️  Skipping dependency installation")

        # Step 3: Deploy API
        api_url = deploy_api()

        # Step 4: Save configuration
        save_config(api_url)

        # Step 5: Deploy UI
        ui_url = deploy_ui()

        # Step 6: Display summary
        if json_mode:
            # Output JSON for programmatic parsing
            result = {
                "status": "success",
                "api_url": api_url,
                "ui_url": ui_url,
            }
            print(json.dumps(result))
        else:
            display_summary(api_url, ui_url, open_browser=open_browser)

    except KeyboardInterrupt:
        print("\n\n⚠️  Deployment cancelled by user")
        sys.exit(130)
    except SystemExit as e:
        if json_mode and e.code != 0:
            result = {"status": "error", "error": "Deployment failed"}
            print(json.dumps(result))
        raise
    except Exception as e:
        if json_mode:
            result = {"status": "error", "error": str(e)}
            print(json.dumps(result))
        else:
            print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
