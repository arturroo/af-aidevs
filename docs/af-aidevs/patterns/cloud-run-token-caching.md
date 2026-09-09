# Cloud Run to Cloud Run Token Caching

When a Cloud Run service calls another private Cloud Run service, it must authenticate using an OIDC ID Token. Fetching this token from the Google Metadata Server on every request can introduce unnecessary latency and overhead in high-throughput systems (e.g., 200+ requests per second).

Since ID Tokens are typically valid for 1 hour, we can cache them in memory to optimize performance.

## Pattern: Caching with `cachetools`

The `cachetools` library provides a simple and effective way to implement a Time-To-Live (TTL) cache using decorators.

### Prerequisites

Add `cachetools` to your `pyproject.toml` or install it:
```bash
uv add cachetools
```

### Implementation

```python
import os
from cachetools import TTLCache, cached
import google.auth.transport.requests
from google.oauth2 import id_token

# Create a cache: max 1 element, valid for 50 minutes (3000 seconds)
token_cache = TTLCache(maxsize=1, ttl=3000)

@cached(token_cache)
def get_model_armor_token(armor_url: str) -> str:
    """
    Fetches a new OIDC ID token from the metadata server.
    This function will only be executed once every 50 minutes per instance.
    """
    print("Fetching new token from Google Metadata Server...")
    auth_req = google.auth.transport.requests.Request()
    return id_token.fetch_id_token(auth_req, audience=armor_url)

# Usage in your request loop:
# token = get_model_armor_token(os.getenv("MODEL_ARMOR_URL"))
```

## Google Best Practice Note

While `cachetools` is a great community standard for Python, Google's official client libraries often handle access token caching automatically within the credentials objects. However, for low-level ID token fetching via `id_token.fetch_id_token`, automatic caching is not provided out-of-the-box, making this pattern highly recommended for production systems.
