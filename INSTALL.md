# Installation

## Prerequisites

- Python 3.12+
- [Modal](https://modal.com) account

## Setup

```bash
# Clone the repo
git clone https://github.com/your-username/docpull.git
cd docpull

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Or with uv (faster):
uv sync
source .venv/bin/activate
```

## Modal Authentication (one-time)

```bash
modal token set
```

This opens a browser window to authenticate with your Modal account.

## Deploy

```bash
python setup.py
```

This deploys both the API and UI to Modal and displays the URLs.

**Options:**
- `--open-browser` — Open the deployed UI in your browser automatically
- `--json` — Output results as JSON (for scripting)

## Post-Installation

### Use the CLI

```bash
python cli/main.py sites        # List available sites
python cli/main.py links <url>  # Get documentation links
python cli/main.py content <url> # Fetch content as markdown
```

### Redeploy Changes

```bash
python setup.py
```

## Teardown

Stop the deployed apps:

```bash
python teardown.py
```

**Options:**
- `--json` — Output results as JSON

## Full Uninstall

```bash
# Stop deployments
python teardown.py

# Remove local files
rm -rf .venv
```
