# CLAUDE.md

Agent-ready documentation system. Downloads docs for use with coding agents.

## Quick Start

```bash
# List available documentation collections
docpull list

# Download docs to ~/.docpull/
docpull load modal fasthtml

# Set up docs for your agent in current project
docpull chat modal

# Check what's loaded
docpull status
```

## Project Structure

```
docpull/
├── cli/
│   ├── main.py            # Typer CLI with agent-ready commands
│   ├── store.py           # ~/.docpull/ folder management
│   └── chat.py            # Local + cloud chat environment setup
├── api/                    # Modal API (backend)
│   ├── server.py          # FastAPI endpoints + UI serving
│   ├── worker.py          # Playwright browser automation
│   ├── bulk.py            # Bulk job handling
│   └── urls.py            # URL utilities
├── sandbox/
│   └── opencode.py        # Modal Sandbox with OpenCode
├── config/
│   ├── sites.json         # Site definitions
│   └── utils.py           # Env loading
├── ui/ui.html             # Web UI (served by server.py)
├── deploy.py              # Deploy script
└── teardown.py            # Stop deployments
```

## Commands

### Agent-Ready (Primary)

```bash
docpull load <collections...>   # Download docs to ~/.docpull/
docpull list                    # Show available collections
docpull status                  # Show loaded collections
docpull update [collection]     # Refresh from API
docpull remove <collection>     # Delete local docs
docpull chat <collection>       # Set up local agent environment
docpull chat --cloud <coll>     # Set up cloud sandbox with OpenCode
```

### Advanced (Backend)

```bash
docpull sites                   # List API sites
docpull discover <url>          # Analyze page for config
docpull links <id>              # Get doc links
docpull content <id> <path>     # Get single page
docpull download <id>           # Download as ZIP
docpull index <id>              # Index entire site
docpull cache stats             # Cache statistics
```

## Development

```bash
modal serve api/server.py    # API + UI with hot-reload
python deploy.py             # Deploy to Modal
```

## Adding Sites

1. `docpull discover <url>` to generate config
2. Add to `config/sites.json`
3. Test: `docpull links <id>` and `docpull content <id> <path>`
4. Use `--force` to bypass cache when testing

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              docpull CLI                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  docpull load <collections...>     docpull chat <collection>               │
│         │                                   │                               │
│         ▼                                   ▼                               │
│  ┌─────────────────┐              ┌─────────────────────────────────────┐  │
│  │  Modal API      │              │  Environment Manager                │  │
│  │  (scrape/cache) │              │  • Local: symlink + DOCS.md         │  │
│  └────────┬────────┘              │  • Cloud: Modal Sandbox + Volume    │  │
│           │                       └─────────────────────────────────────┘  │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    ~/.docpull/ (Global Store)                        │   │
│  │  ├── manifest.json          # Collections metadata                   │   │
│  │  ├── modal/                 # One folder per collection              │   │
│  │  │   └── *.md                                                        │   │
│  │  └── fasthtml/                                                       │   │
│  │      └── *.md                                                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```
