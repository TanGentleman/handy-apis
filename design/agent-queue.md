# Agent Queue: Design Document

## Problem

We want a system where a user submits a high-level task and the system spawns
one or more agents in isolated sandboxes to complete it. Agents may need
different documentation, different secrets, and may need to share intermediate
work products. The system must be able to decompose tasks, manage dependencies
between subtasks, and collect results.

### Motivating Example

> **Prompt**: "Here's my Datadog key: xxx. Create a datadog skill to create
> queries and test with a custom UI. It should also listen for certain slack
> webhooks and run queries if they match a criteria. These would be replies to
> the main alert on the slack thread."
>
> **Docs**: datadog, slack

This single prompt implies multiple distinct pieces of work:

| Subtask | Docs Needed | Secrets | Depends On |
|---------|-------------|---------|------------|
| Build the Datadog query skill | datadog | DD API key | - |
| Build a test UI for the skill | datadog | DD API key | skill code |
| Build Slack webhook listener | slack | Slack webhook URL | - |
| Wire listener to run DD queries on matching alerts | datadog, slack | DD API key, Slack creds | skill + listener |
| Integration test | datadog, slack | all | everything |

Some of these can run in parallel (skill + listener). Others are sequential
(test UI needs the skill first). Some share a workspace (the final wiring agent
needs access to all prior outputs).

---

## Design Principles

1. **Agents are just OpenCode sessions in sandboxes.** No custom agent runtime.
   OpenCode already has tools, agents, permissions, MCP servers, and a
   programmable server API. We use it as-is.

2. **The unit of isolation is the sandbox.** Each agent gets its own Modal
   Sandbox. Sandboxes are cheap, disposable, and isolated by default (gVisor).

3. **The unit of sharing is the volume.** Agents that need to see each other's
   output mount the same Modal Volume. File paths are the coordination protocol.

4. **The queue is dumb.** It holds serializable job descriptions. All
   intelligence lives in the decomposition step (which itself can be an agent)
   and in the agent prompts.

5. **Docs are pre-loaded, not fetched at runtime.** docpull already handles
   downloading and caching docs to `~/.docpull/`. We upload the needed
   collections to a volume before sandbox creation.

---

## Abstractions

### 1. Job

A job is the atom of work. It describes what an agent should do, what it
needs, and how to tell if it succeeded.

```python
@dataclass
class Job:
    id: str                          # unique identifier
    prompt: str                      # what the agent should do
    docs: list[str]                  # docpull collection IDs to mount
    secrets: dict[str, str]          # env vars to inject (API keys, etc.)
    workspace: str                   # workspace ID (maps to a Volume)
    workdir: str = "/workspace"      # where to mount the workspace volume
    depends_on: list[str] = []       # job IDs that must complete first
    outcomes: list[str] = []         # observable success criteria
    timeout_minutes: int = 30        # max runtime
    agent: str = "build"             # opencode agent to use
    model: str | None = None         # model override
```

**Why this is minimal:**
- `prompt` is the only required creative input. Everything else is
  configuration.
- `docs` maps directly to docpull collections — no new doc system needed.
- `secrets` are plain env vars — Modal already handles secure injection.
- `workspace` is a string label that maps to a Modal Volume. Multiple jobs
  sharing the same `workspace` string share a filesystem.
- `depends_on` is a simple DAG expressed as a list of IDs.
- `outcomes` are human-readable strings baked into the agent's prompt so it
  knows what "done" looks like.

### 2. Workspace

A workspace is a named Modal Volume where agents read and write files. It is
the only mechanism for sharing state between agents.

```python
@dataclass
class Workspace:
    id: str                          # label, e.g. "datadog-skill-project"
    volume_name: str                 # modal volume name
    docs_loaded: list[str] = []      # which doc collections are on the volume
```

Workspaces are created lazily. When a job references a workspace that doesn't
exist yet, the dispatcher creates a new Volume for it and uploads the required
docs.

**Layout on the volume:**

```
/workspace/
├── docs/
│   ├── datadog/          # docpull collection
│   │   └── *.md
│   └── slack/
│       └── *.md
├── output/
│   ├── job-001/          # each job writes to its own dir
│   │   ├── RESULT.md     # summary of what was done
│   │   └── skill.py      # artifacts
│   └── job-002/
│       └── ...
└── shared/               # convention for cross-job files
    └── ...
```

The `docs/` prefix contains read-only reference material. The `output/{job-id}/`
convention prevents agents from clobbering each other's work. The `shared/`
directory is for files that agents deliberately want to expose to later agents.

### 3. Runner

The runner takes a single Job and executes it in a Modal Sandbox. It is the
bridge between the job description and the OpenCode session.

```
Runner(job) →
  1. Resolve workspace volume (create if needed)
  2. Ensure docs are uploaded to volume
  3. Build sandbox image (opencode + tools)
  4. Inject secrets
  5. Create sandbox with volume mounted
  6. Run `opencode run "<augmented prompt>"` in the sandbox
  7. Wait for completion
  8. Read output/{job.id}/RESULT.md from volume
  9. Return result
```

The "augmented prompt" wraps the user's prompt with context:

```
You are working on job "{job.id}".

## Your Task
{job.prompt}

## Documentation
Reference docs are available at /workspace/docs/. The following
collections are loaded: {', '.join(job.docs)}

## Prior Work
{summary of completed dependency jobs and their RESULT.md files}

## Output
Write all output files to /workspace/output/{job.id}/.
When done, write a RESULT.md summarizing what you built,
any files created, and how to use them.

## Success Criteria
{bulleted list of job.outcomes}
```

This is the only prompt engineering in the system. The agent (OpenCode) handles
everything else — file editing, bash commands, testing, etc.

**Why `opencode run` and not `opencode serve`?**

For queued batch work, `opencode run` is better:
- Runs to completion and exits. No need for external polling.
- Process exit code tells us if it succeeded.
- Simpler lifecycle — no need to manage sessions or send HTTP requests.
- The prompt contains all context upfront.

`opencode serve` is better for interactive/long-lived sessions where a human
or orchestrator sends multiple prompts over time. We can support both modes,
but `run` is the default for queued jobs.

### 4. Dispatcher

The dispatcher is the loop that pulls jobs from the queue, respects
dependencies, and launches runners.

```
Dispatcher loop:
  1. Pull next job from modal.Queue
  2. Check depends_on — are all dependencies completed?
     - Yes → proceed
     - No → re-queue with backoff (or hold in memory)
  3. Launch Runner in a new sandbox
  4. Track: job_id → sandbox_id mapping in modal.Dict
  5. On completion, mark job as done in modal.Dict
  6. Check if any waiting jobs are now unblocked
```

The dispatcher itself runs as a Modal Function (deployed or ephemeral).

```python
@app.function()
def dispatcher():
    q = modal.Queue.from_name("agent-jobs", create_if_missing=True)
    status = modal.Dict.from_name("job-status", create_if_missing=True)

    while True:
        try:
            job_data = q.get(timeout=30)
        except queue.Empty:
            break  # no more jobs

        job = Job(**job_data)

        # Check dependencies
        blocked = [
            dep for dep in job.depends_on
            if status.get(dep, {}).get("state") != "completed"
        ]
        if blocked:
            q.put(job_data)  # re-queue
            continue

        # Launch
        status[job.id] = {"state": "running", "started": time.time()}
        sandbox_id = run_job(job)  # creates sandbox, returns ID
        status[job.id] = {
            "state": "running",
            "sandbox_id": sandbox_id,
            "started": time.time(),
        }
```

**Why a simple polling loop instead of a DAG executor?**

Simplicity. The queue + dict combination is sufficient for the dependency
patterns we care about (linear chains and simple fan-out/fan-in). A full DAG
scheduler (like Temporal or Airflow) would be over-engineering for a system
where there are typically 2-6 subtasks per top-level request.

If we later need more sophisticated scheduling, we can swap the dispatcher
implementation without changing the Job/Workspace/Runner abstractions.

---

## Task Decomposition

The hardest part of the system is turning a high-level user prompt into a set
of Jobs with correct dependencies. This is itself an LLM task.

### Approach: Planner Agent

Before any sandboxes are created, run a "planner" step that takes the user's
prompt and produces a job manifest:

```
User prompt + available docs list
        │
        ▼
┌─────────────────────┐
│   Planner (LLM)     │
│                     │
│   Input:            │
│   - User prompt     │
│   - Available docs  │
│   - Available       │
│     secrets         │
│                     │
│   Output:           │
│   - List of Jobs    │
│     with deps       │
│   - Workspace ID    │
└─────────────────────┘
        │
        ▼
   Job 1, Job 2, ... → Queue
```

The planner runs locally (not in a sandbox) using `opencode run` or a direct
API call. Its system prompt instructs it to output structured JSON:

```json
{
  "workspace": "dd-skill-20260205",
  "jobs": [
    {
      "id": "dd-skill",
      "prompt": "Create a Python module that wraps the Datadog API...",
      "docs": ["datadog"],
      "secrets": ["DD_API_KEY"],
      "depends_on": [],
      "outcomes": [
        "A file at /workspace/shared/dd_skill.py exists",
        "The module has functions for creating and running queries",
        "Basic error handling for API failures"
      ]
    },
    {
      "id": "slack-listener",
      "prompt": "Create a webhook listener that receives Slack events...",
      "docs": ["slack"],
      "secrets": ["SLACK_WEBHOOK_SECRET"],
      "depends_on": [],
      "outcomes": [
        "A file at /workspace/shared/slack_listener.py exists",
        "It can parse incoming webhook payloads",
        "It filters for thread replies to alert messages"
      ]
    },
    {
      "id": "test-ui",
      "prompt": "Create a simple web UI for testing Datadog queries...",
      "docs": ["datadog"],
      "secrets": ["DD_API_KEY"],
      "depends_on": ["dd-skill"],
      "outcomes": [
        "A standalone HTML+JS or Streamlit app at /workspace/output/test-ui/",
        "Uses the dd_skill module from /workspace/shared/",
        "Has a text input for queries and displays results"
      ]
    },
    {
      "id": "integration",
      "prompt": "Wire the Slack listener to trigger Datadog queries...",
      "docs": ["datadog", "slack"],
      "secrets": ["DD_API_KEY", "SLACK_WEBHOOK_SECRET"],
      "depends_on": ["dd-skill", "slack-listener"],
      "outcomes": [
        "When a matching Slack thread reply is received, a DD query runs",
        "Query results are posted back to the Slack thread",
        "End-to-end test script at /workspace/output/integration/test.py"
      ]
    }
  ]
}
```

### Why the planner is separate from the workers

- **Different context requirements.** The planner needs to understand the full
  scope. Workers only need their subtask + docs.
- **Cheaper.** Planning can use a fast model. Workers can use a more capable
  model.
- **Debuggable.** The job manifest is inspectable JSON. You can review the
  plan before any sandboxes are created.
- **Retryable.** If a single worker fails, you can re-run just that job.
  You don't have to re-plan.

---

## Execution Flow (End to End)

```
User submits task
       │
       ▼
┌─────────────────┐
│  1. Plan         │  opencode run (local or lightweight sandbox)
│     Decompose    │  Output: Job manifest (JSON)
│     into Jobs    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  2. Setup        │  Create workspace Volume
│     Workspace    │  Upload required docs from ~/.docpull/
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  3. Enqueue      │  Put all jobs into modal.Queue
│     Jobs         │  (respecting partition by workspace)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  4. Dispatch     │  Loop: pull job, check deps, launch sandbox
│                  │
│  ┌──────┐ ┌──────┐
│  │ SB 1 │ │ SB 2 │  Independent jobs run in parallel
│  │dd-   │ │slack-│
│  │skill │ │list. │
│  └──┬───┘ └──┬───┘
│     │        │
│     ▼        ▼
│  ┌──────┐ ┌──────┐
│  │ SB 3 │ │ SB 4 │  Dependent jobs wait, then run
│  │test- │ │integ-│
│  │ui    │ │ration│
│  └──────┘ └──────┘
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  5. Collect      │  Read RESULT.md from each job's output dir
│     Results      │  Compile final summary
└─────────────────┘
```

---

## What Makes This Different from "Just Running One Agent"

| Concern | Single Agent | Agent Queue |
|---------|-------------|-------------|
| Context window | Everything in one context, gets huge | Each agent has focused context |
| Failure blast radius | One error can derail the whole task | Failure is isolated to one job |
| Parallelism | Sequential tool calls | Independent subtasks run simultaneously |
| Docs | All docs loaded at once | Each agent only loads what it needs |
| Secrets | All secrets visible | Each agent only sees its secrets |
| Cost | One long expensive session | Multiple shorter, cheaper sessions |
| Observability | One long transcript | Per-job results + status tracking |
| Retry | Start from scratch | Retry individual failed jobs |

---

## Integration with Existing docpull

The agent queue builds on top of existing docpull infrastructure:

| Component | Exists Today | Used By Agent Queue |
|-----------|-------------|-------------------|
| `docpull load` | Downloads docs to `~/.docpull/` | Planner checks available docs |
| `cli/store.py` | Manages manifest + collections | Runner reads collection paths |
| `cli/chat.py:setup_cloud_chat` | Uploads docs to Volume | Runner reuses this pattern |
| `sandbox/opencode.py` | Creates OpenCode sandboxes | Runner extends this for batch mode |
| `config/sites.json` | Site definitions | Planner validates doc IDs |

### New code needed

```
docpull/
├── queue/
│   ├── __init__.py
│   ├── job.py          # Job dataclass + serialization
│   ├── workspace.py    # Volume management + doc upload
│   ├── runner.py       # Sandbox creation + opencode run
│   ├── dispatcher.py   # Queue consumer + dependency tracking
│   └── planner.py      # LLM-based task decomposition
├── cli/
│   └── main.py         # New commands: docpull run, docpull jobs
```

### New CLI surface

```bash
# Submit a task (plans + queues + dispatches)
docpull run "Create a datadog skill..." --docs datadog slack --secret DD_API_KEY=xxx

# Check job status
docpull jobs

# View results
docpull jobs <workspace-id>

# Cancel a workspace
docpull jobs cancel <workspace-id>
```

---

## Open Questions

1. **How to handle agent failure and retry?** If an agent produces output but
   it doesn't meet the outcomes, should we automatically retry with the error
   context? Or surface it to the user?

2. **Should the planner validate its own plan?** Running a second LLM pass to
   check the plan for missing dependencies or unrealistic outcomes could
   catch errors early but adds latency and cost.

3. **Volume version.** Volumes v2 supports concurrent writes from hundreds of
   containers and has no file count limit. v1 caps at 5 concurrent writers and
   50K files. For this use case v2 is likely necessary, but it's still in beta.

4. **How much structure to impose on outputs?** The current design uses
   `RESULT.md` as the contract between agents. This is flexible but loosely
   typed. An alternative is structured JSON output, but that fights against how
   coding agents naturally work (they write files, not JSON reports).

5. **Interactive mode.** For some tasks, a human might want to interact with an
   agent mid-job (e.g., to clarify requirements or approve a direction). This
   would require `opencode serve` instead of `opencode run`, plus a mechanism
   to route human input to the right sandbox. Not in scope for v1 but the
   architecture should not preclude it.

6. **Sandbox pooling.** Cold-starting a sandbox takes seconds. For latency-
   sensitive use cases, pre-warming a pool of sandboxes could help. Modal
   supports keeping sandboxes alive via `idle_timeout`. The dispatcher could
   maintain a warm pool and reuse sandboxes across jobs that have the same
   image + docs configuration.
