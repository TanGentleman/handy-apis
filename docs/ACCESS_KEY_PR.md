# Access Key Authentication PR

## Summary

This PR adds access key infrastructure for protecting sensitive operations in docpull. The key can be configured server-side and entered by users in the UI to unlock protected features.

## What Was Implemented

### Backend (`config/utils.py`)
- `ACCESS_KEY` environment variable loaded from root `.env`
- `get_access_key()` - returns the configured key (or None if not set)
- `verify_access_key(provided_key)` - returns True if key matches or no key is configured

### Frontend (`ui/ui.html`)
- Access key input field in the header (password type, hidden characters)
- Green status indicator when a key is entered
- `getAccessKey()` - retrieves current key value
- `withAccessKey(url)` - appends `?access_key=...` query parameter to URLs
- localStorage persistence (`docpull_access_key`)

### Configuration
- `.env.example` - template showing `ACCESS_KEY=your-secret-key-here`
- `.env` - actual config (gitignored)

---

## Integration Points

### Endpoints That Should Be Protected

**High Priority (destructive/expensive operations):**

| Endpoint | File | Line | Description |
|----------|------|------|-------------|
| `DELETE /cache/{site_id}` | `api/scraper.py` | 1194 | Clears all cached content for a site |
| `DELETE /errors` | `api/scraper.py` | 1237 | Clears all error tracking data |
| `DELETE /errors/{site_id}` | `api/scraper.py` | 1245 | Clears error tracking for a site |
| `POST /jobs/bulk` | `api/scraper.py` | 1724 | Submits bulk scrape job (spawns workers) |
| `POST /sites/{site_id}/index` | `api/scraper.py` | 1262 | Indexes entire site (50 concurrent requests) |

**Medium Priority (resource-intensive):**

| Endpoint | File | Line | Description |
|----------|------|------|-------------|
| `POST /export/zip` | `api/scraper.py` | 1505 | Exports URLs as ZIP (can trigger scraping) |
| `GET /sites/{site_id}/download` | `api/scraper.py` | 1355 | Downloads entire site as ZIP |

### UI Proxy Routes (`ui/app.py`)

The UI proxies requests to the API. These routes should forward the access key:

| UI Route | Proxies To | Notes |
|----------|------------|-------|
| `POST /api/jobs/bulk` | `/jobs/bulk` | Line 293 |
| `POST /api/export` | `/export/zip` | Line 320 |

---

## Implementation Guide

### Backend: Protecting an Endpoint

```python
# In api/scraper.py
from fastapi import Query, HTTPException

# Import the helper (add to imports)
import sys
sys.path.insert(0, "/root")  # For Modal deployment
from config.utils import verify_access_key

@web_app.delete("/cache/{site_id}")
async def clear_cache(
    site_id: str,
    access_key: str = Query(default=None, description="Access key for protected operations")
):
    """Clear cache for a site (requires access key)."""
    if not verify_access_key(access_key):
        raise HTTPException(status_code=403, detail="Invalid or missing access key")

    # ... existing implementation
```

### Frontend: Using Access Key in Requests

```javascript
// For fetch requests that need authentication
async function submitBulkJob(urls) {
  const response = await fetch(withAccessKey('/api/jobs/bulk'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ urls })
  });
  // ...
}
```

### UI Proxy: Forwarding Access Key

```python
# In ui/app.py - update call_scraper_api to forward access_key
async def call_scraper_api(
    method: str,
    path: str,
    request: Request,
    json_body: dict | None = None,
    params: dict | None = None,
) -> dict:
    # ... existing header forwarding ...

    # Forward access_key from query params
    access_key = request.query_params.get("access_key")
    if access_key:
        params = params or {}
        params["access_key"] = access_key

    # ... rest of implementation
```

---

## Security Considerations

### Current Approach (Simple Gate)
- Single shared key for all protected operations
- Key transmitted as query parameter (visible in logs/URLs)
- No rate limiting or brute-force protection
- Suitable for: personal deployments, trusted teams

### Future Enhancements (If Needed)
1. **Move to headers**: Use `X-Access-Key` header instead of query param
2. **Per-operation keys**: Different keys for different sensitivity levels
3. **Rate limiting**: Add request throttling for protected endpoints
4. **Audit logging**: Log access key usage with timestamps

### Key Storage
- Never commit `.env` (gitignored)
- Use strong, random keys (e.g., `openssl rand -hex 32`)
- Rotate keys periodically

---

## Testing Checklist

### Manual Testing

- [ ] **No key configured**: All operations work without access key
- [ ] **Key configured, not provided**: Protected operations return 403
- [ ] **Key configured, wrong key**: Protected operations return 403
- [ ] **Key configured, correct key**: Protected operations succeed
- [ ] **UI persistence**: Key persists across page refreshes (localStorage)
- [ ] **UI indicator**: Green dot shows when key is entered

### Test Commands

```bash
# Start local API
modal serve api/scraper.py

# Test without key (should work if no key configured)
curl -X DELETE "http://localhost:8000/cache/test-site"

# Set key in .env
echo "ACCESS_KEY=test-key-123" >> .env

# Test without key (should fail)
curl -X DELETE "http://localhost:8000/cache/test-site"
# Expected: 403 Forbidden

# Test with correct key (should work)
curl -X DELETE "http://localhost:8000/cache/test-site?access_key=test-key-123"
# Expected: 200 OK

# Test with wrong key (should fail)
curl -X DELETE "http://localhost:8000/cache/test-site?access_key=wrong"
# Expected: 403 Forbidden
```

---

## Remaining Work

1. **Add access key validation to protected endpoints** (see Integration Guide above)
2. **Update UI to use `withAccessKey()` for protected operations**
3. **Add access key forwarding in UI proxy** (`ui/app.py`)
4. **Document which operations require access key in API root response**

---

## Files Changed

| File | Changes |
|------|---------|
| `config/utils.py` | Added `ACCESS_KEY`, `get_access_key()`, `verify_access_key()` |
| `.env.example` | New file with key template |
| `ui/ui.html` | Access key input, JS helpers, localStorage |
