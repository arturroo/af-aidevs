import os
import time
import logging
import asyncio
import httpx
from typing import Dict, Any, Type
from langchain_core.tools import BaseTool
from pydantic import BaseModel
from schemas import APICallInput
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)

logger = logging.getLogger(__name__)

class ServiceUnavailableError(Exception):
    pass

class APICallTool(BaseTool):
    name: str = "api_call"
    description: str = "Calls the central /verify API to perform tasks. Provide reasoning and the 'answer' payload."
    args_schema: Type[BaseModel] = APICallInput

    @retry(
        stop=stop_after_attempt(10),
        wait=wait_exponential(multiplier=1, min=2, max=60),
        retry=retry_if_exception_type(ServiceUnavailableError),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    def _execute_api_call(self, url: str, headers: dict, json_payload: dict) -> httpx.Response:
        logger.info(f"Sending POST to {url} with action: {json_payload.get('answer', {}).get('action')}")
        response = httpx.post(url, headers=headers, json=json_payload, timeout=30.0)
        
        # Simulates overload
        if response.status_code == 503:
            logger.warning("Received 503 Service Unavailable, retrying...")
            raise ServiceUnavailableError("503 Service Unavailable")
            
        return response

    def _run(self, reasoning: str, answer: Dict[str, Any]) -> Dict[str, Any]:
        api_url = os.getenv("AIDEVS_VERIFY") or "https://hub.ag3nts.org/verify"
        api_key = os.getenv("AIDEVS_API_KEY")
        
        if not api_key:
            return {"error": "AIDEVS_API_KEY environment variable is not set."}

        payload = {
            "apikey": api_key,
            "task": "railway",
            "answer": answer
        }

        try:
            response = self._execute_api_call(api_url, {"Content-Type": "application/json"}, payload)
            
            headers = dict(response.headers)
            
            # Simple handling of rate limit reset if provided in headers
            # (e.g. X-RateLimit-Reset, Retry-After)
            # This is a good practice as per instructions.
            reset_header = headers.get("x-ratelimit-reset") or headers.get("retry-after")
            if reset_header:
                try:
                    # If it's a relative wait time in seconds
                    wait_time = int(reset_header)
                    if wait_time > 0 and wait_time < 300: # Sanity check
                        logger.info(f"Rate limit header found. Sleeping for {wait_time} seconds.")
                        time.sleep(wait_time)
                except ValueError:
                    pass
            
            try:
                body = response.json()
            except Exception:
                body = response.text
                
            result = {
                "status_code": response.status_code,
                "headers": headers,
                "body": body,
                "reasoning_provided": reasoning
            }
            return result
        except Exception as e:
            logger.error(f"API Call failed: {e}")
            return {"error": str(e), "reasoning_provided": reasoning}

    async def _arun(self, reasoning: str, answer: Dict[str, Any]) -> Dict[str, Any]:
        return await asyncio.to_thread(self._run, reasoning, answer)
