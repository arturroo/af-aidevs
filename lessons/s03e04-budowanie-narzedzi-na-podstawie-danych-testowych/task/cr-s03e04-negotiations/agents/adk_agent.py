"""Google ADK 1.33.0 & GenAI SDK Implementation for structured tool invocations and orchestration."""

import asyncio
import json
import logging
from typing import Optional

import httpx
from google import genai
from google.adk import Agent, Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types

import config
from schemas import (
    Tool1PostFlightInput,
    Tool1PostFlightOutput,
    Tool1PreFlightOutput,
    Tool2PreFlightOutput,
)
from services.audit_service import AuditService

logger = logging.getLogger(__name__)


class ADKToolCaller:
    """Handles structured single-turn LLM calls using Google GenAI SDK."""

    def __init__(self):
        self.client = genai.Client(
            vertexai=True,
            project=config.GOOGLE_CLOUD_PROJECT,
            location=config.GOOGLE_CLOUD_LOCATION,
        )
        if config.EXTRACTION_LOCATION != config.GOOGLE_CLOUD_LOCATION:
            self.extraction_client = genai.Client(
                vertexai=True,
                project=config.GOOGLE_CLOUD_PROJECT,
                location=config.EXTRACTION_LOCATION,
            )
        else:
            self.extraction_client = self.client

    async def extract_catalog_intent(self, user_query: str) -> Tool1PreFlightOutput:
        """Extract item technical entities from free-form user query via GenAI SDK."""
        prompt = (
            "Jesteś precyzyjnym analizatorem zapytań katalogowych. "
            "Z podanego tekstu wyekstrahuj nazwy poszukiwanych przedmiotów technicznych "
            "(wraz z przymiotnikami/specyfikacjami, np. 'kabel miedziany 10m'). "
            "Całkowicie zignoruj daty, oznaczenia kwartałów (np. 2026Q1), narzekania i szum. "
            "Maksymalnie wyekstrahuj do 4 przedmiotów.\n\n"
            f"Zapytanie:\n{user_query}"
        )
        try:
            response = await self.extraction_client.aio.models.generate_content(
                model=config.EXTRACTION_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=Tool1PreFlightOutput,
                    temperature=0.1,
                ),
            )
            return Tool1PreFlightOutput.model_validate_json(response.text)
        except Exception as e:
            logger.warning(
                "ADK extraction model %s failed: %s. Falling back to %s",
                config.EXTRACTION_MODEL,
                e,
                config.GEMINI_MODEL,
            )
            response = await self.client.aio.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=Tool1PreFlightOutput,
                    temperature=0.1,
                ),
            )
            return Tool1PreFlightOutput.model_validate_json(response.text)

    async def synthesize_catalog_response(
        self, post_input: Tool1PostFlightInput
    ) -> Tool1PostFlightOutput:
        """Synthesize concise recommendation with item codes <= 500 bytes via GenAI SDK."""
        context_json = json.dumps(post_input.model_dump(), ensure_ascii=False)
        prompt = (
            "Jesteś doradcą zaopatrzeniowym. Przeanalizuj wyniki wyszukiwania części i miast. "
            "Zarekomenduj agentowi Centrali optymalne części, zwracając szczególną uwagę na "
            "miasta, w których części występują jednocześnie (co_occurrence_cities). "
            "Dla każdego proponowanego przedmiotu ZAWSZE podaj jego kod w nawiasie w formacie "
            "'(kod: XXXXXX)', np. 'Kabel miedziany 10m (kod: KBL010) oraz Maszt (kod: MST002 - rekomendowany)'. "
            "Odpowiedź tekstowa 'output' MUSI zawierać od 4 do maksymalnie 500 bajtów UTF-8. "
            "Bądź zwięzły i bezpośredni.\n\n"
            f"Kontekst wyszukiwania:\n{context_json}"
        )
        response = await self.client.aio.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=Tool1PostFlightOutput,
                temperature=0.1,
            ),
        )
        return Tool1PostFlightOutput.model_validate_json(response.text)

    async def extract_item_codes(self, user_query: str) -> Tool2PreFlightOutput:
        """Extract 6-character item codes from user query via GenAI SDK."""
        prompt = (
            "Z podanego tekstu wyekstrahuj wyłącznie 6-znakowe alfanumeryczne kody ID przedmiotów "
            "(np. KBL010, MST002, TRB500). "
            "Odrzuć oznaczenia kwartałów (np. 2026Q1) i inne niebędące kodami części. "
            "Jeśli brak kodów przedmiotów, zwróć pustą listę.\n\n"
            f"Tekst:\n{user_query}"
        )
        try:
            response = await self.extraction_client.aio.models.generate_content(
                model=config.EXTRACTION_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=Tool2PreFlightOutput,
                    temperature=0.1,
                ),
            )
            return Tool2PreFlightOutput.model_validate_json(response.text)
        except Exception as e:
            logger.warning(
                "ADK extraction model %s failed in extract_item_codes: %s. Falling back to %s",
                config.EXTRACTION_MODEL,
                e,
                config.GEMINI_MODEL,
            )
            response = await self.client.aio.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=Tool2PreFlightOutput,
                    temperature=0.1,
                ),
            )
            return Tool2PreFlightOutput.model_validate_json(response.text)


class ADKOrchestrator:
    """Orchestrates Centrala tool registration and verification polling via Google ADK."""

    def __init__(self, audit_service: Optional[AuditService] = None):
        self.audit = audit_service or AuditService()
        self.tool_caller = ADKToolCaller()
        self.session_service = InMemorySessionService()

    async def register_tools(self, public_url: str, session_id: str) -> dict:
        """Register tools with Centrala's verification endpoint."""
        payload = {
            "apikey": config.AIDEVS_API_KEY,
            "task": config.TASK_NAME,
            "answer": {
                "tools": [
                    {
                        "URL": f"{public_url.rstrip('/')}/api/search-item-in-catalog",
                        "description": (
                            "Wyszukiwanie kodów ID przedmiotów w katalogu na podstawie opisu lub nazwy technicznej. "
                            "Przyjmuje zapytanie w 'params'. Zwraca nazwy z kodami w formacie (kod: XXXXXX)."
                        ),
                    },
                    {
                        "URL": f"{public_url.rstrip('/')}/api/find-cities-having-items-ids",
                        "description": (
                            "Wyszukiwanie miast posiadających jednocześnie wszystkie wskazane przedmioty. "
                            "Wymaga podania 6-znakowych kodów ID przedmiotów w parametrze 'params'. Zwraca listę miast."
                        ),
                    },
                ]
            },
        }

        await self.audit.log_event(
            session_id=session_id,
            actor="orchestrator_adk",
            content=f"Registering tools at Centrala with public URL: {public_url}",
            step_type="tool_registration",
            metadata=payload,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(config.AIDEVS_VERIFY_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
            logger.info("Tool registration response from Centrala (ADK): %s", data)
            return data

    async def poll_verification(self, session_id: str, max_attempts: int = 30, delay_seconds: int = 5) -> dict:
        """Poll Centrala's check endpoint until execution completes or flag is returned."""
        check_payload = {
            "apikey": config.AIDEVS_API_KEY,
            "task": config.TASK_NAME,
            "answer": {"action": "check"},
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(1, max_attempts + 1):
                logger.info("Polling Centrala check status (attempt %d/%d) [ADK]...", attempt, max_attempts)
                resp = await client.post(config.AIDEVS_VERIFY_URL, json=check_payload)
                data = resp.json()
                logger.info("Poll result: %s", data)

                await self.audit.log_event(
                    session_id=session_id,
                    actor="orchestrator_adk",
                    content=f"Poll attempt {attempt}: {json.dumps(data, ensure_ascii=False)}",
                    step_type="verification_poll",
                    metadata=data,
                )

                msg = str(data)
                if "{FLG:" in msg or data.get("code") == 0 or "FLG" in msg:
                    logger.info("Task verification succeeded!")
                    return data

                await asyncio.sleep(delay_seconds)

        return {"status": "timeout", "last_response": data}

    async def solve(self, session_id: str, public_url: Optional[str] = None) -> dict:
        """Run full lifecycle: tool registration and asynchronous verification polling via ADK."""
        target_url = public_url or config.CENTRAL_PUBLIC_URL
        if not target_url:
            raise ValueError(
                "CENTRAL_PUBLIC_URL or --public-url must be specified for Centrala registration"
            )

        reg_result = await self.register_tools(target_url, session_id)
        logger.info("Waiting 20 seconds for Centrala's agent to execute turns (ADK)...")
        await asyncio.sleep(20)
        verify_result = await self.poll_verification(session_id)
        return {"registration": reg_result, "verification": verify_result}
