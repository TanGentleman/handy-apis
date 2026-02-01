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

import re
import subprocess
import sys
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
    # Looking for pattern: https://[username]--content-scraper-api-[hash].modal.run
    url_pattern = r'(https://[^/]+--content-scraper-api[^/\s]+\.modal\.run)'
    match = re.search(url_pattern, result.stdout)

    if not match:
        print("❌ Error: Could not extract API URL from deployment output")
        print("\nDeployment output:")
        print(result.stdout)
        sys.exit(1)

    api_url = match.group(1)
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

API_URL = "{api_url}"
'''

    config_path.write_text(config_content)
    print(f"✅ Configuration saved to {config_path}")


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
    # Looking for pattern: https://[username]--docpull-[hash].modal.run
    url_pattern = r'(https://[^/]+--docpull[^/\s]+\.modal\.run)'
    match = re.search(url_pattern, result.stdout)

    if not match:
        print("❌ Error: Could not extract UI URL from deployment output")
        print("\nDeployment output:")
        print(result.stdout)
        sys.exit(1)

    ui_url = match.group(1)
    print(f"✅ UI deployed: {ui_url}")
    return ui_url


def display_summary(api_url, ui_url):
    """Display deployment summary.

    Args:
        api_url: The deployed API URL
        ui_url: The deployed UI URL
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
    print("=" * 60)


def main():
    """Run the deployment process."""
    print("🔧 Docpull Deployment Setup")
    print("=" * 60)

    # Step 1: Check virtual environment
    check_venv()

    # Step 2: Install dependencies
    install_requirements()

    # Step 3: Deploy API
    api_url = deploy_api()

    # Step 4: Save configuration
    save_config(api_url)

    # Step 5: Deploy UI
    ui_url = deploy_ui()

    # Step 6: Display summary
    display_summary(api_url, ui_url)


if __name__ == "__main__":
    main()
