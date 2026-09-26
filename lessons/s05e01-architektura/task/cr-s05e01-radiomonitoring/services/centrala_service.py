import logging
from typing import Any

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

import config
from schemas import (
    CentralaEnvelope,
    CentralaListenPayload,
    CentralaListenResponse,
    CentralaStartPayload,
    CentralaTransmitPayload,
)
from services.audit_service import AuditService, mask_binary_output

logger = logging.getLogger("services.centrala")


class CentralaRateLimitError(Exception):
    """Raised when Centrala returns HTTP 429 Too Many Requests."""


class CentralaService:
    """Client for Centrala's radiomonitoring protocol endpoints."""

    def __init__(
        self,
        audit_service: AuditService | None = None,
        verify_url: str = config.AIDEVS_API_VERIFY,
        api_key: str = config.AIDEVS_API_KEY,
    ):
        self.verify_url = verify_url
        self.api_key = api_key
        self.audit = audit_service

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, CentralaRateLimitError)),
        wait=wait_random_exponential(multiplier=1, max=15),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def start(self, session_id: str) -> dict[str, Any]:
        """Initializes the radio monitoring session."""
        envelope = CentralaEnvelope(
            apikey=self.api_key,
            task="radiomonitoring",
            answer=CentralaStartPayload(action="start"),
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.verify_url, json=envelope.model_dump())
            if resp.status_code == 429:
                raise CentralaRateLimitError("Rate limit exceeded on Centrala start")
            resp.raise_for_status()
            data = resp.json()

        if self.audit:
            await self.audit.log_event(
                session_id=session_id,
                actor="centrala",
                content=f"Radio session started: {data.get('message', 'OK')}",
                step_type="centrala_start",
                metadata={"code": data.get("code")},
            )
        return data

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, CentralaRateLimitError)),
        wait=wait_random_exponential(multiplier=1, max=10),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def listen(self, session_id: str) -> CentralaListenResponse:
        """Polls the next intercepted packet from Centrala."""
        envelope = CentralaEnvelope(
            apikey=self.api_key,
            task="radiomonitoring",
            answer=CentralaListenPayload(action="listen"),
        )
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.verify_url, json=envelope.model_dump())
            if resp.status_code == 429:
                raise CentralaRateLimitError("Rate limit exceeded on Centrala listen")
            resp.raise_for_status()
            raw_data = resp.json()

        listen_resp = CentralaListenResponse.model_validate(raw_data)

        if self.audit:
            preview = (
                listen_resp.transcription[:150]
                if listen_resp.transcription
                else f"Attachment: meta={listen_resp.meta}, size={listen_resp.filesize}"
            )
            await self.audit.log_event(
                session_id=session_id,
                actor="centrala",
                content=f"Signal captured: {preview}",
                step_type="centrala_listen",
                metadata=mask_binary_output(raw_data),
            )
        return listen_resp

    @retry(
        retry=retry_if_exception_type((httpx.RequestError, CentralaRateLimitError)),
        wait=wait_random_exponential(multiplier=1, max=15),
        stop=stop_after_attempt(5),
        reraise=True,
    )
    async def transmit(
        self,
        session_id: str,
        city_name: str,
        city_area: str,
        warehouses_count: int,
        phone_number: str,
    ) -> dict[str, Any]:
        """Transmits the final synthesis report to Centrala."""
        payload = CentralaTransmitPayload(
            action="transmit",
            cityName=city_name,
            cityArea=city_area,
            warehousesCount=warehouses_count,
            phoneNumber=phone_number,
        )
        envelope = CentralaEnvelope(
            apikey=self.api_key,
            task="radiomonitoring",
            answer=payload,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.verify_url, json=envelope.model_dump())
            if resp.status_code == 429:
                raise CentralaRateLimitError("Rate limit exceeded on Centrala transmit")
            resp.raise_for_status()
            data = resp.json()

        flag = data.get("flag")
        if (
            not flag
            and isinstance(data.get("message"), str)
            and "{FLG:" in data["message"]
        ):
            flag = data["message"]
            data["flag"] = flag
        if self.audit:
            await self.audit.log_event(
                session_id=session_id,
                actor="centrala",
                content=f"Final transmission result: code={data.get('code')}, msg={data.get('message')}",
                step_type="centrala_transmit",
                metadata={"payload": payload.model_dump(), "response": data},
                flag=flag,
            )
        return data
