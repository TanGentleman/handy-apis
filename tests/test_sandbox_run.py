"""Test: spawn a Modal Sandbox with OpenCode, run a prompt, get a response.

Usage:
    python tests/test_sandbox_run.py
    python tests/test_sandbox_run.py --prompt "What is Modal?"
    python tests/test_sandbox_run.py --docs modal --prompt "How do volumes work?"
"""
import argparse
import sys
import time

import modal

# --- Image ---
image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("curl", "git")
    .run_commands("curl -fsSL https://opencode.ai/install | bash")
    .env({"PATH": "/root/.opencode/bin:${PATH}"})
)

# Bring along your opencode config (model keys, etc.)
from pathlib import Path
config_path = Path.home() / ".config" / "opencode" / "opencode.json"
if config_path.exists():
    image = image.add_local_file(config_path, "/root/.config/opencode/opencode.json")

APP_NAME = "docpull-sandbox-test"


def run_agent(prompt: str, docs: list[str] | None = None, timeout_minutes: int = 10) -> str:
    """Spawn a sandbox, run `opencode run`, return stdout."""
    app = modal.App.lookup(APP_NAME, create_if_missing=True)

    volumes = {}
    workdir = "/root"

    # Upload docs if requested
    if docs:
        from cli.store import get_collection_path, collection_exists
        vol = modal.Volume.from_name("docpull-test-docs", create_if_missing=True)
        with vol.batch_upload(force=True) as batch:
            for coll in docs:
                if not collection_exists(coll):
                    print(f"Warning: {coll} not loaded, skipping (run docpull load {coll})")
                    continue
                coll_path = get_collection_path(coll)
                for f in coll_path.rglob("*.md"):
                    rel = f.relative_to(coll_path)
                    batch.put_file(f, f"/docs/{coll}/{rel}")
        volumes["/docs"] = vol
        workdir = "/docs"
        prompt = f"{prompt}\n\nReference documentation is available at /docs/. Browse it to inform your answer."

    print(f"Creating sandbox...")
    start = time.time()

    with modal.enable_output():
        sb = modal.Sandbox.create(
            image=image,
            app=app,
            volumes=volumes,
            workdir=workdir,
            timeout=timeout_minutes * 60,
        )

    print(f"Sandbox {sb.object_id} created in {time.time() - start:.1f}s")
    print(f"Running prompt: {prompt[:80]}...")

    # Run opencode in non-interactive batch mode
    proc = sb.exec(
        "opencode", "run", prompt,
        timeout=timeout_minutes * 60,
    )

    # Stream stdout as it arrives
    output_lines = []
    for line in proc.stdout:
        print(line, end="")
        output_lines.append(line)

    # Capture any stderr
    stderr = proc.stderr.read()
    if stderr.strip():
        print(f"\n[stderr]: {stderr[:500]}", file=sys.stderr)

    proc.wait()
    sb.terminate()

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s (exit code: {proc.returncode})")

    return "".join(output_lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test: run an agent in a Modal sandbox")
    parser.add_argument("--prompt", "-p", default="Explain what a Modal Sandbox is in 3 sentences.",
                        help="Prompt to send to the agent")
    parser.add_argument("--docs", "-d", nargs="*", default=None,
                        help="Docpull collections to mount (e.g., modal)")
    parser.add_argument("--timeout", "-t", type=int, default=10,
                        help="Timeout in minutes")
    args = parser.parse_args()

    result = run_agent(args.prompt, docs=args.docs, timeout_minutes=args.timeout)

