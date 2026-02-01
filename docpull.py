#!/usr/bin/env python3
"""Convenience wrapper for running docpull CLI without installation.

This script ensures the project root is in sys.path before importing the CLI.
Recommended usage: install with 'pip install -e .' and use 'docpull' command instead.
"""

import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Import and run CLI
from cli.main import app

if __name__ == "__main__":
    app()
