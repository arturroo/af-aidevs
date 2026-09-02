import os
import time
from typing import Optional
import httpx
from google.auth.transport.requests import Request
from google.oauth2 import id_token


class GoogleOIDCAuth(httpx.Auth):
    """Custom HTTPX Auth to fetch and cache Google OIDC tokens for Cloud Run and local environments."""

    def __init__(self, audience: str, token_override_env: Optional[str] = "MCP_WORKSPACE_TOKEN"):
        self.audience = audience
        self.token_override_env = token_override_env
        self._token: Optional[str] = None
        self._expiry: float = 0.0

    def _get_token(self) -> str:
        # Support local manual testing via environment variable override
        if self.token_override_env:
            env_token = os.getenv(self.token_override_env)
            if env_token:
                return env_token

        now = time.time()
        # Return cached token if valid for at least 5 more minutes
        if self._token and (now < self._expiry):
            return self._token

        try:
            # Fetch fresh token from metadata server or ADC
            self._token = id_token.fetch_id_token(Request(), self.audience)
            self._expiry = now + 3000  # Cache for 50 minutes
            return self._token
        except Exception:
            return ""

    def auth_flow(self, request: httpx.Request):
        token = self._get_token()
        if token:
            request.headers["Authorization"] = f"Bearer {token}"
        yield request
