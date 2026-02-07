"""Generic Modal Sandbox creation.

Provides create_sandbox() for arbitrary entrypoints and run_prompt()
as a one-shot convenience for `opencode run` batch jobs.
"""

import sys

try:
    import modal
except ImportError:
    modal = None

DEFAULT_APP_NAME = "docpull-opencode"
MINUTES = 60


def create_sandbox(
    *entrypoint: str,
    image=None,
    volumes: dict | None = None,
    secrets: list | None = None,
    workdir: str = "/workspace",
    timeout: int = 30 * MINUTES,
    idle_timeout: int | None = None,
    encrypted_ports: list[int] | None = None,
    app_name: str = DEFAULT_APP_NAME,
    name: str | None = None,
    tags: dict | None = None,
) -> "modal.Sandbox":
    """Create a Modal Sandbox with the given configuration.

    Low-level — callers build their own image and volumes.
    Supports both ``opencode serve`` (interactive) and ``opencode run`` (batch)
    via the entrypoint parameter.

    Args:
        *entrypoint: Command to run (e.g. "opencode", "serve", ...).
                     Omit for a bare sandbox you can exec into.
        image: Modal Image to use
        volumes: Dict of mount_path -> Volume
        secrets: List of Modal Secrets
        workdir: Working directory inside the sandbox
        timeout: Max lifetime in seconds (default 30 min)
        idle_timeout: Auto-terminate after this many idle seconds
        encrypted_ports: Ports to expose via encrypted tunnel
        app_name: Modal App name
        name: Named sandbox (prevents duplicates)
        tags: Metadata tags

    Returns:
        A running modal.Sandbox
    """
    if modal is None:
        raise ImportError("Modal is required. Install with: pip install modal")

    app = modal.App.lookup(app_name, create_if_missing=True)

    kwargs = {
        "image": image,
        "app": app,
        "timeout": timeout,
        "workdir": workdir,
    }
    if volumes:
        kwargs["volumes"] = volumes
    if secrets:
        kwargs["secrets"] = secrets
    if idle_timeout is not None:
        kwargs["idle_timeout"] = idle_timeout
    if encrypted_ports:
        kwargs["encrypted_ports"] = encrypted_ports
    if name:
        kwargs["name"] = name
    if tags:
        kwargs["tags"] = tags

    with modal.enable_output():
        sandbox = modal.Sandbox.create(*entrypoint, **kwargs)

    return sandbox


def run_prompt(
    prompt: str,
    image=None,
    volumes: dict | None = None,
    secrets: list | None = None,
    workdir: str = "/workspace",
    timeout_minutes: int = 10,
    app_name: str = DEFAULT_APP_NAME,
) -> tuple[str, int]:
    """One-shot: create sandbox, run ``opencode run``, return (stdout, exit_code).

    Creates a bare sandbox, execs ``opencode run <prompt>``, streams stdout,
    then terminates.

    Args:
        prompt: The prompt to send to the agent
        image: Modal Image (should have opencode installed)
        volumes: Dict of mount_path -> Volume
        secrets: List of Modal Secrets
        workdir: Working directory
        timeout_minutes: Max runtime in minutes
        app_name: Modal App name

    Returns:
        Tuple of (stdout_text, exit_code)
    """
    sb = create_sandbox(
        image=image,
        volumes=volumes,
        secrets=secrets,
        workdir=workdir,
        timeout=timeout_minutes * MINUTES,
        app_name=app_name,
    )

    proc = sb.exec("opencode", "run", prompt, timeout=timeout_minutes * MINUTES)

    output_lines = []
    for line in proc.stdout:
        print(line, end="")
        output_lines.append(line)

    stderr = proc.stderr.read()
    if stderr.strip():
        print(f"\n[stderr]: {stderr[:500]}", file=sys.stderr)

    proc.wait()
    sb.terminate()

    return "".join(output_lines), proc.returncode
