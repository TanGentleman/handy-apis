#!/usr/bin/env python3
"""Teardown script for docpull Modal deployments."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

# App names deployed by setup.py
DOCPULL_APP_NAMES = {"content-scraper-api", "docpull"}

# Valid states for apps we can stop
RUNNING_STATES = {"deployed", "ephemeral"}


def get_deployed_apps():
    """Get list of deployed Modal apps.

    Returns:
        list: List of app dictionaries from modal app list --json
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
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"❌ Error parsing app list: {e}")
        sys.exit(1)


def filter_docpull_apps(apps):
    """Filter for docpull-related apps.

    Args:
        apps: List of app dictionaries from modal app list --json

    Returns:
        list: Tuples of (app_id, description, state) for docpull apps
    """
    return [
        (app["App ID"], app["Description"], app["State"])
        for app in apps
        if app["Description"] in DOCPULL_APP_NAMES
        and app["State"] in RUNNING_STATES
    ]


def stop_app(app_id, description):
    """Stop a Modal app.

    Args:
        app_id: The app ID to stop
        description: The app description for display

    Returns:
        bool: True if stop succeeded
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
    """Display teardown summary."""
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
    parser = argparse.ArgumentParser(description="Stop docpull deployments on Modal")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format",
    )
    args = parser.parse_args()

    json_mode = args.json

    if not json_mode:
        print("🔧 Docpull Teardown")
        print("=" * 60)

    try:
        # Step 1: Get deployed apps
        apps = get_deployed_apps()

        # Step 2: Filter for docpull apps
        apps_to_stop = filter_docpull_apps(apps)

        if not apps_to_stop:
            if json_mode:
                print(json.dumps({"status": "success", "stopped_apps": [], "failed_apps": []}))
            else:
                print("💡 No docpull apps found to stop")
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

        # Step 4: Cleanup config
        if stopped_apps:
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
            print(json.dumps({"status": "error", "error": str(e)}))
        else:
            print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
