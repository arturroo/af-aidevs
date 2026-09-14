import logging
import re
from typing import Optional
import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

import config
from schemas import VerifySolutionResponse

logger = logging.getLogger("services.verification")


class VerificationService:
    """Client for submitting completed tasks to Centrala verification hub ($AIDEVS_API_VERIFY)."""

    def __init__(
        self,
        verify_url: Optional[str] = None,
        api_key: Optional[str] = None,
        task_name: Optional[str] = None,
    ):
        self.verify_url = verify_url or config.AIDEVS_VERIFY_URL
        self.api_key = api_key or config.AIDEVS_API_KEY
        self.task_name = task_name or config.TASK_NAME
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Closes the underlying HTTP client."""
        await self.client.aclose()

    async def verify_confirmation_code(
        self, confirmation_code: str, reasoning: str = ""
    ) -> VerifySolutionResponse:
        """Submits the extracted ECCS runtime confirmation code to /verify."""
        logger.info(f"Submitting confirmation code '{confirmation_code}' for task '{self.task_name}'. Reasoning: {reasoning}")

        payload = {
            "apikey": self.api_key,
            "task": self.task_name,
            "answer": {
                "confirmation": confirmation_code.strip(),
            },
        }

        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
                wait=wait_exponential(multiplier=1, min=2, max=10),
                stop=stop_after_attempt(3),
                reraise=True,
            ):
                with attempt:
                    resp = await self.client.post(self.verify_url, json=payload)
                    if resp.status_code in (500, 502, 503, 504):
                        resp.raise_for_status()

            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            resp_text = resp.text

            message = data.get("message") or resp_text
            code = data.get("code", 0 if resp.status_code == 200 else resp.status_code)

            # Search for flag pattern {FLG:...}
            flag_match = re.search(r'\{FLG:[^}]+\}', resp_text)
            flag = flag_match.group(0) if flag_match else None

            if code == 0 or flag or "ok" in str(message).lower():
                logger.info(f"Task verification successful! Flag acquired: {flag}")
                return VerifySolutionResponse(
                    status="success",
                    code=int(code),
                    flag=flag,
                    message=str(message),
                    hint="Task solved successfully. Record flag and conclude session.",
                )
            else:
                logger.warning(f"Verification rejected by server: code={code}, message={message}")
                return VerifySolutionResponse(
                    status="failed",
                    code=int(code),
                    flag=None,
                    message=str(message),
                    hint="Verify that confirmation token format matches ECCS-[a-zA-Z0-9]{40}.",
                )

        except Exception as e:
            logger.error(f"Failed to submit confirmation code: {e}")
            return VerifySolutionResponse(
                status="error",
                code=-1,
                flag=None,
                message=f"Verification request exception: {str(e)}",
                hint="Check network connection and AIDEVS_API_KEY.",
            )
