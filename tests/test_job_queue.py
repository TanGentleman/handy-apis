"""Test: enqueue jobs and dispatch them to sandboxes.

Usage:
    python tests/test_job_queue.py
    python tests/test_job_queue.py enqueue
    python tests/test_job_queue.py dispatch
    python tests/test_job_queue.py both
"""
import json
import queue
import time
from dataclasses import dataclass, field, asdict

import modal

# --- Job definition (from design doc) ---
@dataclass
class Job:
    id: str
    prompt: str
    docs: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    outcomes: list[str] = field(default_factory=list)
    timeout_minutes: int = 10

QUEUE_NAME = "docpull-test-jobs"
STATUS_DICT = "docpull-test-status"
APP_NAME = "docpull-queue-test"

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


def enqueue_jobs():
    """Put test jobs into the queue."""
    q = modal.Queue.from_name(QUEUE_NAME, create_if_missing=True)

    jobs = [
        Job(
            id="greeting-module",
            prompt="Create /workspace/shared/greeter.py with a function greet(name) that returns 'Hello, {name}!'.",
            outcomes=["File /workspace/shared/greeter.py exists"],
        ),
        Job(
            id="greeting-test",
            prompt=(
                "Read /workspace/shared/greeter.py (written by a prior agent). "
                "Write /workspace/output/greeting-test/test_greeter.py that tests it. Run the test."
            ),
            depends_on=["greeting-module"],
            outcomes=["Tests pass"],
        ),
    ]

    for job in jobs:
        q.put(asdict(job))
        print(f"Enqueued: {job.id}")

    return len(jobs)


def dispatch():
    """Pull jobs from queue, respect dependencies, run in sandboxes."""
    q = modal.Queue.from_name(QUEUE_NAME)
    status = modal.Dict.from_name(STATUS_DICT, create_if_missing=True)
    app = modal.App.lookup(APP_NAME, create_if_missing=True)
    vol = modal.Volume.from_name("docpull-test-queue-workspace", create_if_missing=True)

    max_rounds = 10
    for round_num in range(max_rounds):
        try:
            job_data = q.get(timeout=5)
        except queue.Empty:
            print("Queue empty, done.")
            break

        job = Job(**job_data)
        print(f"\n--- Round {round_num + 1}: job={job.id} ---")

        # Check dependencies
        blocked = [d for d in job.depends_on if status.get(d) != "completed"]
        if blocked:
            print(f"  Blocked by: {blocked}. Re-queuing.")
            q.put(job_data)
            time.sleep(2)
            continue

        # Build augmented prompt
        augmented = f"You are working on job '{job.id}'.\n\n{job.prompt}"
        if job.outcomes:
            augmented += "\n\nSuccess criteria:\n" + "\n".join(f"- {o}" for o in job.outcomes)

        # Run
        status[job.id] = "running"
        print(f"  Running...")
        sb = modal.Sandbox.create(
            image=image, app=app,
            volumes={"/workspace": vol},
            workdir="/workspace",
            timeout=job.timeout_minutes * 60,
        )

        proc = sb.exec("opencode", "run", augmented, timeout=job.timeout_minutes * 60)
        for line in proc.stdout:
            print(f"  [{job.id}] {line}", end="")
        proc.wait()
        sb.terminate()
        sb.wait(raise_on_termination=False)

        if proc.returncode == 0:
            status[job.id] = "completed"
            print(f"  Completed.")
        else:
            status[job.id] = "failed"
            print(f"  Failed (exit {proc.returncode}).")

    # Summary
    print("\n=== Job Status ===")
    for key in status.keys():
        print(f"  {key}: {status[key]}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["enqueue", "dispatch", "both"], default="both", nargs="?")
    args = parser.parse_args()

    if args.action in ("enqueue", "both"):
        enqueue_jobs()
    if args.action in ("dispatch", "both"):
        dispatch()

