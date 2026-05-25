import os
import time
import logging
import asyncio
import httpx
import json
from typing import Dict, Any, Type
from langchain_core.tools import BaseTool
from pydantic import BaseModel
from schemas import APICallInput
import af_aidevs.model_armor as model_armor
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

class RateLimitError(Exception):
    def __init__(self, wait_time: int):
        self.wait_time = wait_time
        super().__init__(f"429 Too Many Requests. Wait {wait_time}s")

def wait_strategy(retry_state):
    if retry_state.outcome.failed:
        exc = retry_state.outcome.exception()
        if isinstance(exc, RateLimitError):
            logger.info(f"RateLimitError detected. Waiting exactly {exc.wait_time}s as requested by server.")
            return exc.wait_time
    # Fallback to exponential wait for 503
    return wait_exponential(multiplier=1, min=2, max=60)(retry_state=retry_state)

def log_audit(actor: str, content: str, metadata: dict, session_id: str):
    """Logs interaction as a structured JSON to stdout for Cloud Logging to capture."""
    audit_entry = {
        "log_type": "AUDIT",
        "resource_name": "cr-s01e05-agent-tool",
        "session_id": session_id or "unknown",
        "actor": actor,
        "content": content,
        "metadata": metadata
    }
    print(json.dumps(audit_entry), flush=True)

class RailwayApi(BaseTool):
    name: str = "RailwayApi"
    description: str = "Calls the central /verify API to perform tasks. Provide reasoning and the 'answer' payload."
    args_schema: Type[BaseModel] = APICallInput
    
    session_id: str = ""
    policy: str = ""

    @retry(
        stop=stop_after_attempt(15),
        wait=wait_strategy,
        retry=retry_if_exception_type((ServiceUnavailableError, RateLimitError)),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
    def _execute_api_call(self, url: str, headers: dict, json_payload: dict) -> httpx.Response:
        logger.info(f"Sending POST to {url} with action: {json_payload.get('answer', {}).get('action')}")
        response = httpx.post(url, headers=headers, json=json_payload, timeout=30.0)
        
        # Simulates overload
        if response.status_code == 503:
            logger.warning("Received 503 Service Unavailable, retrying...")
            log_audit(
                actor="tool-retry",
                content="Received 503 Service Unavailable, retrying...",
                metadata={
                    "status_code": 503,
                    "headers": dict(response.headers),
                    "url": url,
                    "action": json_payload.get("answer", {}).get("action")
                },
                session_id=self.session_id
            )
            raise ServiceUnavailableError("503 Service Unavailable")
            
        # Handle 429 Rate Limit
        if response.status_code == 429:
            reset_header = response.headers.get("x-ratelimit-reset") or response.headers.get("retry-after")
            wait_time = 5 # Default fallback
            if reset_header:
                try:
                    wait_time = int(reset_header)
                    # If it's a timestamp (larger than year 2000), calculate delta
                    if wait_time > 1000000000:
                        wait_time = max(1, wait_time - int(time.time()))
                except ValueError:
                    pass
            logger.warning(f"Received 429 Too Many Requests. Server says wait {wait_time}s.")
            log_audit(
                actor="tool-retry",
                content=f"Received 429 Too Many Requests. Server says wait {wait_time}s.",
                metadata={
                    "status_code": 429,
                    "headers": dict(response.headers),
                    "url": url,
                    "action": json_payload.get("answer", {}).get("action"),
                    "wait_time": wait_time
                },
                session_id=self.session_id
            )
            raise RateLimitError(wait_time)
            
        return response

    def _run(self, reasoning: str, answer: Dict[str, Any]) -> Dict[str, Any]:
        api_url = os.getenv("AIDEVS_VERIFY")
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
            
            # Log all API response headers clearly in the format {header: value} for auditability
            logger.info(f"--- API Response Headers: {json.dumps(headers)} ---")
            
            # [COMMENTED OUT AS PER ARTUR'S REQUEST TO PREVENT 4-MINUTE WAIT ON 200 OK RESPONSES]
            # reset_header = headers.get("x-ratelimit-reset") or headers.get("retry-after")
            # if reset_header:
            #     try:
            #         wait_time = int(reset_header)
            #         if wait_time > 0 and wait_time < 300: # Sanity check
            #             logger.info(f"Rate limit header found. Sleeping for {wait_time} seconds.")
            #             time.sleep(wait_time)
            #     except ValueError:
            #         pass
            
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
        # 1. Verify Input to the tool
        if self.session_id and self.policy:
            input_text = f"Action: {answer.get('action')}. Arguments: {json.dumps(answer)}"
            logger.info("Verifying input to Railway API with Model Armor...")
            is_safe = await model_armor.verify(input_text, self.policy, self.session_id)
            if not is_safe:
                logger.warning("Input to Railway API rejected by Model Armor.")
                return {"error": "Input to Railway API was blocked by safety policy.", "reasoning_provided": reasoning}

        # 2. Execute the tool
        result = await asyncio.to_thread(self._run, reasoning, answer)

        # 3. Verify Output from the tool
        if self.session_id and self.policy and "body" in result:
            output_text = json.dumps(result["body"]) if isinstance(result["body"], dict) else str(result["body"])
            logger.info("Verifying output from Railway API with Model Armor...")
            is_safe = await model_armor.verify(output_text, self.policy, self.session_id)
            if not is_safe:
                logger.warning("Output from Railway API rejected by Model Armor.")
                return {"error": "Output from Railway API was blocked by safety policy.", "reasoning_provided": reasoning}

        return result
