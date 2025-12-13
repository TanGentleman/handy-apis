# Hooks

Hooks let you observe, control, and extend the agent loop using custom scripts. Hooks are spawned processes that communicate over stdio using JSON in both directions. They run before or after defined stages of the agent loop and can observe, block, or modify behavior.

With hooks, you can:

- Run formatters after edits
- Add analytics for events
- Scan for PII or secrets
- Gate risky operations (e.g., SQL writes)

## Agent and Tab Support

Hooks work with both **Cursor Agent** (Cmd+K/Agent Chat) and **Cursor Tab** (inline completions), but they use different hook events:

**Agent (Cmd+K/Agent Chat)** uses the standard hooks:

- `beforeShellExecution` / `afterShellExecution` - Control shell commands
- `beforeMCPExecution` / `afterMCPExecution` - Control MCP tool usage
- `beforeReadFile` / `afterFileEdit` - Control file access and edits
- `beforeSubmitPrompt` - Validate prompts before submission
- `stop` - Handle agent completion
- `afterAgentResponse` / `afterAgentThought` - Track agent responses

**Tab (inline completions)** uses specialized hooks:

- `beforeTabFileRead` - Control file access for Tab completions
- `afterTabFileEdit` - Post-process Tab edits

These separate hooks allow different policies for autonomous Tab operations versus user-directed Agent operations.

## Quickstart

Create a `hooks.json` file. You can create it at the project level (`<project>/.cursor/hooks.json`) or in your home directory (`~/.cursor/hooks.json`). Project-level hooks apply only to that specific project, while home directory hooks apply globally.

```
{
  "version": 1,
  "hooks": {
    "afterFileEdit": [{ "command": "./hooks/format.sh" }]
  }
}
```

Create your hook script at `~/.cursor/hooks/format.sh`:

```
#!/bin/bash
# Read input, do something, exit 0
cat > /dev/null
exit 0
```

Make it executable:

```
chmod +x ~/.cursor/hooks/format.sh
```

Restart Cursor. Your hook now runs after every file edit.

## Examples

hooks.jsonaudit.shblock-git.sh```
{
  "version": 1,
  "hooks": {
    "beforeShellExecution": [
      {
        "command": "./hooks/audit.sh"
      },
      {
        "command": "./hooks/block-git.sh"
      }
    ],
    "beforeMCPExecution": [
      {
        "command": "./hooks/audit.sh"
      }
    ],
    "afterShellExecution": [
      {
        "command": "./hooks/audit.sh"
      }
    ],
    "afterMCPExecution": [
      {
        "command": "./hooks/audit.sh"
      }
    ],
    "afterFileEdit": [
      {
        "command": "./hooks/audit.sh"
      }
    ],
    "beforeSubmitPrompt": [
      {
        "command": "./hooks/audit.sh"
      }
    ],
    "stop": [
      {
        "command": "./hooks/audit.sh"
      }
    ],
    "beforeTabFileRead": [
      {
        "command": "./hooks/redact-secrets-tab.sh"
      }
    ],
    "afterTabFileEdit": [
      {
        "command": "./hooks/format-tab.sh"
      }
    ]
  }
}
```

## Configuration

Define hooks in a `hooks.json` file. Configuration can exist at multiple levels; higher-priority sources override lower ones:

```
~/.cursor/
├── hooks.json
└── hooks/
    ├── audit.sh
    └── block-git.sh
```

- **Global** (Enterprise-managed):
- macOS: `/Library/Application Support/Cursor/hooks.json`
- Linux/WSL: `/etc/cursor/hooks.json`
- Windows: `C:\\ProgramData\\Cursor\\hooks.json`
- **Project Directory** (Project-specific):
- `<project-root>/.cursor/hooks.json`
- Project hooks run in any trusted workspace and are checked into version control with your project
- **Home Directory** (User-specific):
- `~/.cursor/hooks.json`

Priority order (highest to lowest): Enterprise → Project → User

The `hooks` object maps hook names to arrays of hook definitions. Each definition currently supports a `command` property that can be a shell string, an absolute path, or a path relative to the `hooks.json` file.

### Configuration file

```
{
  "version": 1,
  "hooks": {
    "beforeShellExecution": [{ "command": "./script.sh" }],
    "afterShellExecution": [{ "command": "./script.sh" }],
    "afterMCPExecution": [{ "command": "./script.sh" }],
    "afterFileEdit": [{ "command": "./format.sh" }],
    "beforeTabFileRead": [{ "command": "./redact-secrets-tab.sh" }],
    "afterTabFileEdit": [{ "command": "./format-tab.sh" }]
  }
}
```

The Agent hooks (`beforeShellExecution`, `afterShellExecution`, `beforeMCPExecution`, `afterMCPExecution`, `beforeReadFile`, `afterFileEdit`, `beforeSubmitPrompt`, `stop`, `afterAgentResponse`, `afterAgentThought`) apply to Cmd+K and Agent Chat operations. The Tab hooks (`beforeTabFileRead`, `afterTabFileEdit`) apply specifically to inline Tab completions.

## Team Distribution

Hooks can be distributed to team members using project hooks (via version control), MDM tools, or Cursor's cloud distribution system.

### Project Hooks (Version Control)

Project hooks are the simplest way to share hooks with your team. Place a `hooks.json` file at `<project-root>/.cursor/hooks.json` and commit it to your repository. When team members open the project in a trusted workspace, Cursor automatically loads and runs the project hooks.

Project hooks:

- Are stored in version control alongside your code
- Automatically load for all team members in trusted workspaces
- Can be project-specific (e.g., enforce formatting standards for a particular codebase)
- Require the workspace to be trusted to run (for security)

### MDM Distribution

Distribute hooks across your organization using Mobile Device Management (MDM) tools. Place the `hooks.json` file and hook scripts in the target directories on each machine.

**User home directory** (per-user distribution):

- `~/.cursor/hooks.json`
- `~/.cursor/hooks/` (for hook scripts)

**Global directories** (system-wide distribution):

- macOS: `/Library/Application Support/Cursor/hooks.json`
- Linux/WSL: `/etc/cursor/hooks.json`
- Windows: `C:\\ProgramData\\Cursor\\hooks.json`

Note: MDM-based distribution is fully managed by your organization. Cursor does not deploy or manage files through your MDM solution. Ensure your internal IT or security team handles configuration, deployment, and updates in accordance with your organization's policies.

### Cloud Distribution (Enterprise Only)

Enterprise teams can use Cursor's native cloud distribution to automatically sync hooks to all team members. Configure hooks in the [web dashboard](https://cursor.com/dashboard?tab=team-content&section=hooks). Cursor automatically delivers configured hooks to all client machines when team members log in.

Cloud distribution provides:

- Automatic synchronization to all team members (every thirty minutes)
- Operating system targeting for platform-specific hooks
- Centralized management through the dashboard

Enterprise administrators can create, edit, and manage team hooks from the dashboard without requiring access to individual machines.

## Reference

### Common schema

#### Input (all hooks)

All hooks receive a base set of fields in addition to their hook-specific fields:

```
{
  "conversation_id": "string",
  "generation_id": "string",
  "model": "string",
  "hook_event_name": "string",
  "cursor_version": "string",
  "workspace_roots": ["<path>"],
  "user_email": "string | null"
}
```

FieldTypeDescription`conversation_id`stringStable ID of the conversation across many turns`generation_id`stringThe current generation that changes with every user message`model`stringThe model configured for the composer that triggered the hook`hook_event_name`stringWhich hook is being run`cursor_version`stringCursor application version (e.g. "1.7.2")`workspace_roots`string[]The list of root folders in the workspace (normally just one, but multiroot workspaces can have multiple)`user_email`string | nullEmail address of the authenticated user, if available
### Hook events

#### beforeShellExecution / beforeMCPExecution

Called before any shell command or MCP tool is executed. Return a permission decision.

```
// beforeShellExecution input
{
  "command": "<full terminal command>",
  "cwd": "<current working directory>"
}

// beforeMCPExecution input
{
  "tool_name": "<tool name>",
  "tool_input": "<json params>"
}
// Plus either:
{ "url": "<server url>" }
// Or:
{ "command": "<command string>" }

// Output
{
  "permission": "allow" | "deny" | "ask",
  "user_message": "<message shown in client>",
  "agent_message": "<message sent to agent>"
}
```

#### afterShellExecution

Fires after a shell command executes; useful for auditing or collecting metrics from command output.

```
// Input
{
  "command": "<full terminal command>",
  "output": "<full terminal output>",
  "duration": 1234
}
```

FieldTypeDescription`command`stringThe full terminal command that was executed`output`stringFull output captured from the terminal`duration`numberDuration in milliseconds spent executing the shell command (excludes approval wait time)
#### afterMCPExecution

Fires after an MCP tool executes; includes the tool's input parameters and full JSON result.

```
// Input
{
  "tool_name": "<tool name>",
  "tool_input": "<json params>",
  "result_json": "<tool result json>",
  "duration": 1234
}
```

FieldTypeDescription`tool_name`stringName of the MCP tool that was executed`tool_input`stringJSON params string passed to the tool`result_json`stringJSON string of the tool response`duration`numberDuration in milliseconds spent executing the MCP tool (excludes approval wait time)
#### afterFileEdit

Fires after the Agent edits a file; useful for formatters or accounting of agent-written code.

```
// Input
{
  "file_path": "<absolute path>",
  "edits": [{ "old_string": "<search>", "new_string": "<replace>" }]
}
```

#### beforeTabFileRead

Called before Tab (inline completions) reads a file. Enable redaction or access control before Tab accesses file contents.

**Key differences from `beforeReadFile`:**

- Only triggered by Tab, not Agent
- Does not include `attachments` field (Tab doesn't use prompt attachments)
- Useful for applying different policies to autonomous Tab operations

```
// Input
{
  "file_path": "<absolute path>",
  "content": "<file contents>"
}

// Output
{
  "permission": "allow" | "deny"
}
```

#### afterTabFileEdit

Called after Tab (inline completions) edits a file. Useful for formatters or auditing of Tab-written code.

**Key differences from `afterFileEdit`:**

- Only triggered by Tab, not Agent
- Includes detailed edit information: `range`, `old_line`, and `new_line` for precise edit tracking
- Useful for fine-grained formatting or analysis of Tab edits

```
// Input
{
  "file_path": "<absolute path>",
  "edits": [
    {
      "old_string": "<search>",
      "new_string": "<replace>",
      "range": {
        "start_line_number": 10,
        "start_column": 5,
        "end_line_number": 10,
        "end_column": 20
      },
      "old_line": "<line before edit>",
      "new_line": "<line after edit>"
    }
  ]
}

// Output
{
  // No output fields currently supported
}
```

#### beforeSubmitPrompt

Called right after user hits send but before backend request. Can prevent submission.

```
// Input
{
  "prompt": "<user prompt text>",
  "attachments": [
    {
      "type": "file" | "rule",
      "filePath": "<absolute path>"
    }
  ]
}

// Output
{
  "continue": true | false,
  "user_message": "<message shown to user when blocked>"
}
```

Output FieldTypeDescription`continue`booleanWhether to allow the prompt submission to proceed`user_message`string (optional)Message shown to the user when the prompt is blocked
#### afterAgentResponse

Called after the agent has completed an assistant message.

```
// Input
{
  "text": "<assistant final text>"
}
```

#### afterAgentThought

Called after the agent completes a thinking block. Useful for observing the agent's reasoning process.

```
// Input
{
  "text": "<fully aggregated thinking text>",
  "duration_ms": 5000
}

// Output
{
  // No output fields currently supported
}
```

FieldTypeDescription`text`stringFully aggregated thinking text for the completed block`duration_ms`number (optional)Duration in milliseconds for the thinking block
#### stop

Called when the agent loop ends. Can optionally auto-submit a follow-up user message to keep iterating.

```
// Input
{
  "status": "completed" | "aborted" | "error",
  "loop_count": 0
}
```

```
// Output
{
  "followup_message": "<message text>"
}
```

- The optional `followup_message` is a string. When provided and non-empty, Cursor will automatically submit it as the next user message. This enables loop-style flows (e.g., iterate until a goal is met).
- The `loop_count` field indicates how many times the stop hook has already triggered an automatic follow-up for this conversation (starts at 0). To prevent infinite loops, a maximum of 5 auto follow-ups is enforced.

## Troubleshooting

**How to confirm hooks are active**

There is a Hooks tab in Cursor Settings to debug configured and executed hooks, as well as a Hooks output channel to see errors.

**If hooks are not working**

- Restart Cursor to ensure the hooks service is running.
- Ensure hook script paths are relative to `hooks.json` when using relative paths.
