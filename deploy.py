#!/usr/bin/env python3
"""Deploy docpull to Modal.

Usage: python deploy.py [--open-browser] [--json] [--skip-install]
"""

import argparse
import json
import re
import subprocess
import sys
import webbrowser
from pathlib import Path

# App name for Modal deployment (must match teardown.py)
API_APP_NAME = "content-scraper-api"

# Delimiters for managed zshrc section
ALIAS_START = "# >>> docpull alias >>>"
ALIAS_END = "# <<< docpull alias <<<"


def check_venv():
    """Verify environment is ready for deployment."""
    project_root = Path(__file__).parent
    venv_path = project_root / ".venv"

    if has_uv():
        print("✅ Using uv for dependency management")
        # uv will create/sync .venv automatically during install_requirements
        return

    # For non-uv users, check for existing venv
    venv_python = venv_path / "bin" / "python"

    if not venv_path.exists() or not venv_python.exists():
        print("⚠️  No virtual environment found at .venv/")
        try:
            response = input("   Create one now? [Y/n]: ").strip().lower()
        except EOFError:
            response = "n"

        if response in ("", "y", "yes"):
            print("\n🔧 Creating virtual environment...")
            result = subprocess.run(
                [sys.executable, "-m", "venv", str(venv_path)],
                capture_output=True,
                text=True
            )
            if result.returncode != 0:
                print(f"❌ Error creating virtual environment:")
                print(result.stderr)
                sys.exit(1)
            print("✅ Virtual environment created")
        else:
            print("\nTo create manually:")
            print(f"  python -m venv {venv_path}")
            print(f"  source {venv_path}/bin/activate")
            print("  pip install -e .")
            sys.exit(1)
    else:
        print("✅ Virtual environment detected")

    print("✅ Virtual environment detected")


def install_requirements():
    """Install Python dependencies."""
    print("\n📦 Installing dependencies...")

    project_root = Path(__file__).parent

    if has_uv():
        # uv sync creates .venv if needed and installs project + dependencies
        result = subprocess.run(
            ["uv", "sync"],
            capture_output=True,
            text=True,
            cwd=project_root
        )
        if result.returncode != 0:
            print("❌ Error running uv sync:")
            print(result.stderr)
            sys.exit(1)
    else:
        # For non-uv: use the project's venv Python for pip install
        venv_python = project_root / ".venv" / "bin" / "python"
        if not venv_python.exists():
            print("❌ Error: Virtual environment not found")
            print(f"Please create it first: python -m venv {project_root}/.venv")
            sys.exit(1)

        result = subprocess.run(
            [str(venv_python), "-m", "pip", "install", "-e", str(project_root)],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print("❌ Error installing dependencies:")
            print(result.stderr)
            sys.exit(1)

    print("✅ Dependencies installed")


def has_uv():
    """Check if uv is available on the system."""
    try:
        result = subprocess.run(["uv", "--version"], capture_output=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def get_modal_command():
    """Get the appropriate modal command prefix.

    Returns:
        list: Command prefix for running modal
    """
    project_root = Path(__file__).parent
    if has_uv():
        # Use --directory to ensure we're in the project context
        return ["uv", "run", "--directory", str(project_root), "modal"]
    else:
        # Use the project's venv Python directly (avoids activation issues)
        venv_python = project_root / ".venv" / "bin" / "python"
        if venv_python.exists():
            return [str(venv_python), "-m", "modal"]
        # Fallback to current Python
        return [sys.executable, "-m", "modal"]


def get_existing_apps():
    """Get list of existing Modal apps.

    Returns:
        dict: Map of app description to app ID for docpull apps
    """
    try:
        modal_cmd = get_modal_command()
        result = subprocess.run(
            modal_cmd + ["app", "list", "--json"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return {}

        apps = json.loads(result.stdout)
        return {
            app["Description"]: app["App ID"]
            for app in apps
            if app["State"] == "deployed"
            and app["Description"] == API_APP_NAME
        }
    except (json.JSONDecodeError, KeyError, FileNotFoundError):
        return {}


def deploy_api():
    """Deploy Modal API and extract URL.

    Returns:
        str: API URL from deployment output
    """
    print("\n🚀 Deploying Modal API...")
    api_path = Path(__file__).parent / "api" / "server.py"

    if not api_path.exists():
        print(f"❌ Error: {api_path} not found")
        sys.exit(1)

    # Check for existing deployment
    existing_apps = get_existing_apps()
    if API_APP_NAME in existing_apps:
        print(f"⚠️  Note: Redeploying existing app (ID: {existing_apps[API_APP_NAME]})")

    modal_cmd = get_modal_command()
    result = subprocess.run(
        modal_cmd + ["deploy", str(api_path)],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("❌ Error deploying API:")
        print(result.stderr)
        sys.exit(1)

    # Extract API URL from deployment output
    # Example: https://<username>--content-scraper-api-fastapi-app.modal.run
    url_pattern = rf'https://[^\s]+--{API_APP_NAME}[^\s]+\.modal\.run'
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
    """Save API URL to .env file.

    Args:
        api_url: The Modal API URL to save
    """
    print("\n💾 Saving configuration...")
    env_path = Path(__file__).parent / ".env"

    env_content = f"""# Docpull configuration - auto-generated by deploy.py
# Do not commit this file (it's in .gitignore)

# Modal API URL (required)
SCRAPER_API_URL={api_url}

# Production mode (optional)
IS_PROD=false

# Modal authentication (optional - uncomment to enable secured endpoints)
# MODAL_KEY=your-modal-key
# MODAL_SECRET=your-modal-secret
"""

    try:
        env_path.write_text(env_content)
        print(f"✅ Configuration saved to {env_path}")
    except OSError as e:
        print(f"❌ Error saving configuration: {e}")
        sys.exit(1)



def setup_global_alias(skip_prompt=False):
    """Add global docpull alias to zshrc.

    Args:
        skip_prompt: If True, add alias without prompting (default behavior)

    Returns:
        bool: True if alias was added or already exists, False otherwise
    """
    project_dir = Path(__file__).parent.resolve()
    zshrc_path = Path.home() / ".zshrc"

    # Check if alias already exists
    if zshrc_path.exists():
        content = zshrc_path.read_text()
        if ALIAS_START in content:
            print("\n✅ Global docpull alias already configured in ~/.zshrc")
            return True

    if not skip_prompt:
        print("\n🔧 Setup global 'docpull' command?")
        print(f"   This will add an alias to ~/.zshrc pointing to {project_dir}/docpull")

        try:
            response = input("   Add global docpull command? [Y/n]: ").strip().lower()
        except EOFError:
            response = "n"

        if response not in ("", "y", "yes"):
            print("   Skipped. Use 'python -m cli.main' for local CLI access.")
            return False
    else:
        print(f"\n🔧 Adding global 'docpull' command to ~/.zshrc...")

    # Build the alias block
    alias_block = f"""\n{ALIAS_START}
alias docpull="{project_dir}/docpull"
{ALIAS_END}\n"""

    try:
        with open(zshrc_path, "a") as f:
            f.write(alias_block)
        print("   ✅ Added to ~/.zshrc")
        print("   Run 'source ~/.zshrc' or open a new terminal to use 'docpull'")
        return True
    except OSError as e:
        print(f"   ❌ Failed to update ~/.zshrc: {e}")
        return False


def display_summary(api_url, open_browser=False):
    """Display deployment summary.

    Args:
        api_url: The deployed API URL (also serves the UI at /)
        open_browser: Whether to open the URL in browser
    """
    print("\n" + "=" * 60)
    print("🎉 Deployment Complete!")
    print("=" * 60)
    print(f"\n🌐 URL:      {api_url}")
    print("\n📚 Next steps:")
    print("  - Open in browser for the UI")
    print("  - Test the API: curl " + api_url + "/health")
    print("  - Use the CLI: python -m cli.main sites")
    print("\n🛑 To stop deployments:")
    print("  python teardown.py")
    print("=" * 60)

    if open_browser:
        print("\n🌐 Opening in browser...")
        webbrowser.open(api_url)


def main():
    """Run the deployment process."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Deploy docpull to Modal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python deploy.py                    # Standard deployment
  python deploy.py --open-browser     # Deploy and open UI
  python deploy.py --json             # Output as JSON
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
    parser.add_argument(
        "--no-alias",
        action="store_true",
        help="Skip adding global docpull alias to ~/.zshrc",
    )
    args = parser.parse_args()

    json_mode = args.json
    open_browser = args.open_browser
    skip_install = args.skip_install
    no_alias = args.no_alias

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

        # Step 3: Deploy API (also serves the UI)
        api_url = deploy_api()

        # Step 4: Save configuration
        save_config(api_url)

        # Step 5: Setup global alias (by default, skip prompt)
        if not json_mode and not no_alias:
            setup_global_alias(skip_prompt=True)

        # Step 6: Display summary
        if json_mode:
            result = {
                "status": "success",
                "api_url": api_url,
            }
            print(json.dumps(result))
        else:
            display_summary(api_url, open_browser=open_browser)

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
