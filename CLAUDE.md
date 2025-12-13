# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Modal-based serverless API endpoints for web automation and scraping. The primary application uses Playwright for browser automation to extract content from websites.

## Technology Stack

- **Modal**: Serverless deployment platform
- **FastAPI**: Web framework
- **Playwright**: Browser automation
- **Python 3.12+**: Required version
- **uv**: Package manager

## Essential Commands

### Setup
```bash
uv sync
```

### Deployment
```bash
# Deploy to production
modal deploy <filename>.py

# Deploy to development environment
modal deploy <filename>.py --env dev

# Local development server
modal serve <filename>.py
```

## Architecture

### Modal Application Pattern

Applications follow Modal's serverless architecture:

1. **Custom Image**: Debian slim base with system dependencies and Python packages installed via `.run_commands()` and `.uv_pip_install()`
2. **App Definition**: Modal App with descriptive name
3. **ASGI Integration**: FastAPI apps mounted via `@modal.asgi_app()` decorator
4. **Deploy Marker**: `# deploy: true` comment at top of file

### Browser Automation

- Headless Chromium with custom permissions (clipboard access)
- Async operations using Playwright's async API
- Structured error handling with consistent response schemas

### GitHub Actions Integration

Workflows can call deployed Modal endpoints to automate content updates. API URLs follow the pattern:
```
https://[MODAL_USERNAME]--[app-name]-[function-name][-dev].modal.run
```

The `-dev` suffix is added for development deployments.

## Future Considerations

Authentication will be added to endpoints, which will require authentication tokens in deployment commands and API requests.
