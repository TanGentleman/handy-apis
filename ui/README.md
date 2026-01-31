# Docpull UI

Web interface for managing documentation scraping.

## Deploy

**First time setup:**

```bash
# Terminal 1: Start the API first
modal serve content-scraper-api.py

# Terminal 2: Configure the UI (one-time setup)
python ui/setup.py
# Copy the API URL from Terminal 1 when prompted

# Then start the UI
modal serve ui/app.py
```

**After initial setup:**

```bash
modal serve ui/app.py
```

Open the URL shown in the terminal to access the web interface.

> **Note:** If you get an ImportError about missing config, run `python ui/setup.py` to configure the API URL.

## Features

- **View Sites** - Browse all configured documentation sites
- **View Links** - Fetch all documentation links for a site
- **Preview Content** - Test content extraction on a specific path
- **Export Site** - One-click export of all cached URLs as ZIP
- **Add New Site** - Discover URL analyzer suggests configuration
- **Export URLs** - Load cached URLs or paste custom URL lists
