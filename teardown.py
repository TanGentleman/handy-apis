#!/usr/bin/env python3
"""Interactive teardown script for docpull.

Removes Modal deployments:
1. List all deployed apps using --json
2. Find docpull-related apps (content-scraper-api and docpull)
3. Stop them using modal app stop
4. Display summary
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def get_deployed_apps():
    """Get list of deployed Modal apps as JSON.

    Returns:
        list: List of app dictionaries
    """
    print("\n📋 Fetching deployed apps...")
    result = subprocess.run(
        ["modal", "app", "list", "--json"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print("❌ Error listing apps:")
        print(result.stderr)
        sys.exit(1)

    try:
        apps = json.loads(result.stdout)
        return apps
    except json.JSONDecodeError as e:
        print("❌ Error parsing app list:")
        print(str(e))
        sys.exit(1)


def filter_docpull_apps(apps, stop_all=False):
    """Filter for docpull-related apps.

    Args:
        apps: List of app dictionaries from modal app list --json
        stop_all: If True, return all apps regardless of description

    Returns:
        list: Tuples of (app_id, description, state) for relevant apps
    """
    if stop_all:
        return [
            (app["App ID"], app["Description"], app["State"])
            for app in apps
            if app["State"] in ["deployed", "ephemeral"]
        ]

    # Filter for docpull-related apps that are running
    docpull_apps = []
    for app in apps:
        description = app["Description"]
        state = app["State"]
        app_id = app["App ID"]

        # Match docpull-related apps
        if state in ["deployed", "ephemeral"] and (
            description == "docpull" or
            description == "content-scraper-api"
        ):
            docpull_apps.append((app_id, description, state))

    return docpull_apps


def stop_app(app_id, description):
    """Stop a Modal app.

    Args:
        app_id: The app ID to stop
        description: The app description for display

    Returns:
        bool: True if stop succeeded, False otherwise
    """
    print(f"\n🛑 Stopping {description} ({app_id})...")
    result = subprocess.run(
        ["modal", "app", "stop", app_id],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        print(f"❌ Error stopping {description}:")
        print(result.stderr)
        return False

    print(f"✅ Stopped {description}")
    return True


def cleanup_config():
    """Remove the UI config file if it exists."""
    config_path = Path(__file__).parent / "ui" / "config.py"

    if config_path.exists():
        print("\n🧹 Cleaning up configuration...")
        try:
            config_path.unlink()
            print(f"✅ Removed {config_path}")
        except OSError as e:
            print(f"⚠️  Could not remove {config_path}: {e}")


def display_summary(stopped_apps, failed_apps):
    """Display teardown summary.

    Args:
        stopped_apps: List of successfully stopped app descriptions
        failed_apps: List of failed app descriptions
    """
    print("\n" + "=" * 60)
    print("🎉 Teardown Complete!")
    print("=" * 60)

    if stopped_apps:
        print(f"\n✅ Successfully stopped {len(stopped_apps)} app(s):")
        for app in stopped_apps:
            print(f"  - {app}")

    if failed_apps:
        print(f"\n❌ Failed to stop {len(failed_apps)} app(s):")
        for app in failed_apps:
            print(f"  - {app}")

    if not stopped_apps and not failed_apps:
        print("\n💡 No docpull apps found to stop")

    print("=" * 60)


def main():
    """Run the teardown process."""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Stop docpull deployments on Modal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python teardown.py              # Stop docpull apps only
  python teardown.py --all        # Stop ALL Modal apps (dangerous!)
  python teardown.py --json       # Output results as JSON
        """
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format (for programmatic use)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Stop ALL Modal apps (not just docpull-related). Use with caution!",
    )
    args = parser.parse_args()

    json_mode = args.json
    stop_all = args.all

    if not json_mode:
        print("🔧 Docpull Teardown")
        print("=" * 60)
        if stop_all:
            print("⚠️  WARNING: Stopping ALL Modal apps!")

    try:
        # Step 1: Get deployed apps
        apps = get_deployed_apps()

        # Step 2: Filter apps
        apps_to_stop = filter_docpull_apps(apps, stop_all=stop_all)

        if not apps_to_stop:
            if not json_mode:
                print("💡 No apps found to stop")
            else:
                result = {
                    "status": "success",
                    "stopped_apps": [],
                    "failed_apps": []
                }
                print(json.dumps(result))
            return

        if not json_mode:
            print(f"\n📦 Found {len(apps_to_stop)} app(s) to stop:")
            for app_id, description, state in apps_to_stop:
                print(f"  - {description} ({state}) - {app_id}")

        # Step 3: Stop apps
        stopped_apps = []
        failed_apps = []

        for app_id, description, state in apps_to_stop:
            if stop_app(app_id, description):
                stopped_apps.append(description)
            else:
                failed_apps.append(description)

        # Step 4: Cleanup config (only for docpull teardown)
        if not stop_all and stopped_apps:
            cleanup_config()

        # Step 5: Display summary
        if json_mode:
            result = {
                "status": "success" if not failed_apps else "partial",
                "stopped_apps": stopped_apps,
                "failed_apps": failed_apps,
            }
            print(json.dumps(result))
        else:
            display_summary(stopped_apps, failed_apps)

    except KeyboardInterrupt:
        print("\n\n⚠️  Teardown cancelled by user")
        sys.exit(130)
    except Exception as e:
        if json_mode:
            result = {"status": "error", "error": str(e)}
            print(json.dumps(result))
        else:
            print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
