"""Client for interacting with Centrala's verification endpoint."""

import logging

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from config import config
from schemas import CentralaVerifyRequest, CentralaVerifyResponse, RemoteCommandPayload

logger = logging.getLogger("services.centrala")


class CentralaTransientError(Exception):
    """Raised when Centrala returns an HTTP error that can be retried (429, 5xx)."""


class CentralaService:
    """Service client for Centrala shell execution API ($AIDEVS_API_VERIFY)."""

    def __init__(
        self,
        api_url: str = config.AIDEVS_API_VERIFY,
        api_key: str = config.AIDEVS_API_KEY,
        task_name: str = config.TASK_NAME,
    ) -> None:
        self.api_url = api_url
        self.api_key = api_key
        self.task_name = task_name

        if not self.api_url:
            logger.warning(
                "AIDEVS_API_VERIFY is not set in environment or Secret Manager!"
            )
        if not self.api_key:
            logger.warning(
                "AIDEVS_API_KEY is not set in environment or Secret Manager!"
            )

    @retry(
        retry=retry_if_exception_type(CentralaTransientError),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1.0, min=1.0, max=5.0),
        reraise=True,
    )
    async def _dispatch_http(self, cmd: str) -> CentralaVerifyResponse:
        """Dispatches an HTTP POST command execution request to Centrala with retries."""
        req_payload = CentralaVerifyRequest(
            apikey=self.api_key,
            task=self.task_name,
            answer=RemoteCommandPayload(cmd=cmd),
        )

        logger.info(
            f"Dispatching shell command to Centrala (task={self.task_name}): {cmd[:120]}"
        )

        async with httpx.AsyncClient(timeout=45.0) as client:
            try:
                resp = await client.post(self.api_url, json=req_payload.model_dump())
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                logger.warning(
                    f"Connection/Timeout error to Centrala: {exc}. Retrying..."
                )
                raise CentralaTransientError(str(exc)) from exc

        if resp.status_code in (429, 500, 502, 503, 504):
            logger.warning(
                f"Centrala returned transient HTTP status {resp.status_code}: {resp.text[:200]}"
            )
            raise CentralaTransientError(f"HTTP {resp.status_code}: {resp.text[:200]}")

        try:
            data = resp.json()
        except Exception as exc:
            logger.error(
                f"Failed to parse Centrala response as JSON: {exc}. Raw text: {resp.text[:300]}"
            )
            return CentralaVerifyResponse(
                code=-1,
                message=f"HTTP {resp.status_code} parse error: {resp.text[:300]}",
            )

        raw_output = data.get("output")
        raw_message = str(data.get("message", ""))
        display_text = str(raw_output) if raw_output is not None else raw_message

        return CentralaVerifyResponse(
            code=data.get("code", 0),
            message=display_text,
            output=str(raw_output) if raw_output is not None else None,
        )

    async def execute_shell_raw(
        self, cmd: str, *, caller: str = "HUMAN_REPL"
    ) -> CentralaVerifyResponse:
        """Executes a raw, unfiltered shell command directly on the remote server.

        Restricted strictly to the human interactive REPL or internal verification gate.
        """
        if caller not in ("HUMAN_REPL", "VERIFICATION_GATE"):
            raise PermissionError(
                f"execute_shell_raw is restricted to HUMAN_REPL or VERIFICATION_GATE (received caller={caller})"
            )
        return await self._dispatch_http(cmd)

    async def execute_shell_direct(self, cmd: str) -> CentralaVerifyResponse:
        """Executes a command directly without caller check for internal tool pipelines."""
        return await self._dispatch_http(cmd)
