import os
import logging
import httpx
from datetime import datetime, timedelta
from google.oauth2 import id_token
import google.auth.transport.requests

logger = logging.getLogger(__name__)

class _Cache:
    token: str = None
    fetched_at: datetime = None

async def verify(text: str, policy_context: str, session_id: str) -> bool:
    """Verifies text safety with cr-model-armor.
    
    Acts as a lightweight client SDK for Model Armor.
    """
    armor_url = os.getenv("MODEL_ARMOR_URL")
    if not armor_url:
        logger.warning("MODEL_ARMOR_URL not set, skipping safety verification.")
        return True
        
    url = f"{armor_url.rstrip('/')}/verify"
    headers = {
        "Content-Type": "application/json",
        "X-Session-ID": session_id
    }
    
    # 1. Check cache
    token = None
    if _Cache.token and _Cache.fetched_at and (datetime.now() - _Cache.fetched_at) < timedelta(minutes=50):
        token = _Cache.token
    else:
        # 2. Check env var (local test)
        token = os.getenv("MODEL_ARMOR_TOKEN")
        
        # 3. Check metadata server (GCP Cloud Run)
        if not token:
            try:
                auth_req = google.auth.transport.requests.Request()
                token = id_token.fetch_id_token(auth_req, audience=armor_url)
                _Cache.token = token
                _Cache.fetched_at = datetime.now()
            except Exception as e:
                logger.debug(f"Could not fetch ID token from metadata server: {e}")
                pass
                
    if token:
        headers["Authorization"] = f"Bearer {token}"
        
    payload = {
        "input": text,
        "policy_context": policy_context
    }
    
    logger.info(f"Calling Model Armor at {url} with headers: {list(headers.keys())}")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=10.0)
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Model Armor decision: {result.get('decision')}")
                return result.get("decision") == "safe"
            else:
                logger.error(f"Model Armor returned status {response.status_code}")
                return False
    except Exception as e:
        logger.error(f"Failed to call Model Armor: {e}")
        return False
