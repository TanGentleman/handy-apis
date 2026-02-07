"""Test: two sandboxes share a workspace volume.

Agent A writes a file. Agent B reads it and responds about its contents.

Usage:
    python tests/test_shared_workspace.py
"""
import time
import modal

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("curl", "git")
    .run_commands("curl -fsSL https://opencode.ai/install | bash")
    .env({"PATH": "/root/.opencode/bin:${PATH}"})
)

from pathlib import Path
config_path = Path.home() / ".config" / "opencode" / "opencode.json"
if config_path.exists():
    image = image.add_local_file(config_path, "/root/.config/opencode/opencode.json")

APP_NAME = "docpull-workspace-test"


def test_shared_workspace():
    app = modal.App.lookup(APP_NAME, create_if_missing=True)

    # Shared volume
    vol = modal.Volume.from_name("docpull-test-workspace", create_if_missing=True)

    # --- Agent A: write a file ---
    print("=== Agent A: writing to shared workspace ===")
    sb_a = modal.Sandbox.create(
        image=image, app=app,
        volumes={"/workspace": vol},
        workdir="/workspace",
        timeout=5 * 60,
    )

    prompt_a = (
        "Create a Python file at /workspace/shared/utils.py with a function "
        "called `greet(name: str) -> str` that returns a greeting string. "
        "Also create /workspace/output/agent-a/RESULT.md summarizing what you did."
    )
    proc_a = sb_a.exec("opencode", "run", prompt_a, timeout=5 * 60)
    for line in proc_a.stdout:
        print(f"  [A] {line}", end="")
    proc_a.wait()

    # Commit volume changes (v2) or terminate (v1 auto-commits on terminate)
    sb_a.terminate()
    sb_a.wait(raise_on_termination=False)
    print(f"  Agent A exit code: {proc_a.returncode}")

    # --- Agent B: read the file ---
    print("\n=== Agent B: reading from shared workspace ===")
    sb_b = modal.Sandbox.create(
        image=image, app=app,
        volumes={"/workspace": vol},
        workdir="/workspace",
        timeout=5 * 60,
    )

    prompt_b = (
        "Read the file at /workspace/shared/utils.py. "
        "Write a test file at /workspace/output/agent-b/test_utils.py that "
        "imports and tests the greet function. Run the test and report results "
        "in /workspace/output/agent-b/RESULT.md."
    )
    proc_b = sb_b.exec("opencode", "run", prompt_b, timeout=5 * 60)
    for line in proc_b.stdout:
        print(f"  [B] {line}", end="")
    proc_b.wait()
    sb_b.terminate()
    sb_b.wait(raise_on_termination=False)
    print(f"  Agent B exit code: {proc_b.returncode}")

    # --- Verify: read results from volume ---
    print("\n=== Results ===")
    for path in ["shared/utils.py", "output/agent-a/RESULT.md",
                  "output/agent-b/test_utils.py", "output/agent-b/RESULT.md"]:
        try:
            content = b""
            for chunk in vol.read_file(path):
                content += chunk
            print(f"\n--- {path} ---")
            print(content.decode()[:500])
        except Exception as e:
            print(f"\n--- {path} --- MISSING: {e}")


if __name__ == "__main__":
    test_shared_workspace()

