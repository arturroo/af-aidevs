"""LangChain 1.2.15 Implementation for direct structured tool invocations and task orchestration."""

import asyncio
import json
import logging
from typing import Optional

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

import config
from schemas import (
    Tool1PostFlightInput,
    Tool1PostFlightOutput,
    Tool1PreFlightOutput,
    Tool2PreFlightOutput,
)
from services.audit_service import AuditService, BigQueryCallbackHandler

logger = logging.getLogger(__name__)


def get_langchain_model(model_name: Optional[str] = None, location: Optional[str] = None):
    """Create ChatGoogleGenerativeAI instance with low thinking level for low latency."""
    kwargs = {
        "model": model_name or config.GEMINI_MODEL,
        "temperature": 0.1,
        "thinking_level": config.THINKING_LEVEL,
    }
    if config.GOOGLE_CLOUD_PROJECT:
        kwargs["project"] = config.GOOGLE_CLOUD_PROJECT
        kwargs["location"] = location or config.GOOGLE_CLOUD_LOCATION
        kwargs["vertexai"] = True
    return ChatGoogleGenerativeAI(**kwargs)


class LangChainToolCaller:
    """Handles structured single-turn LLM calls using LangChain 1.2.15."""

    def __init__(self):
        self.synthesis_model = get_langchain_model(config.GEMINI_MODEL, config.GOOGLE_CLOUD_LOCATION)
        self.extraction_model = get_langchain_model(config.EXTRACTION_MODEL, config.EXTRACTION_LOCATION)
        self.model = self.synthesis_model

    async def extract_catalog_intent(self, user_query: str) -> Tool1PreFlightOutput:
        """Extract item technical entities from free-form user query."""
        messages = [
            SystemMessage(
                content=(
                    "Jesteś precyzyjnym analizatorem zapytań katalogowych. "
                    "Z podanego tekstu wyekstrahuj nazwy poszukiwanych przedmiotów technicznych "
                    "(wraz z przymiotnikami/specyfikacjami, np. 'kabel miedziany 10m'). "
                    "Całkowicie zignoruj daty, oznaczenia kwartałów (np. 2026Q1), narzekania i szum. "
                    "Maksymalnie wyekstrahuj do 4 przedmiotów."
                )
            ),
            HumanMessage(content=user_query),
        ]
        try:
            structured_llm = self.extraction_model.with_structured_output(Tool1PreFlightOutput)
            return await structured_llm.ainvoke(messages)
        except Exception as e:
            logger.warning(
                "Extraction model %s failed: %s. Falling back to %s",
                config.EXTRACTION_MODEL,
                e,
                config.GEMINI_MODEL,
            )
            structured_llm = self.synthesis_model.with_structured_output(Tool1PreFlightOutput)
            return await structured_llm.ainvoke(messages)

    async def synthesize_catalog_response(
        self, post_input: Tool1PostFlightInput
    ) -> Tool1PostFlightOutput:
        """Synthesize concise recommendation with item codes <= 500 bytes."""
        structured_llm = self.synthesis_model.with_structured_output(Tool1PostFlightOutput)
        context_json = json.dumps(post_input.model_dump(), ensure_ascii=False)
        messages = [
            SystemMessage(
                content=(
                    "Jesteś doradcą zaopatrzeniowym. Przeanalizuj wyniki wyszukiwania części i miast. "
                    "Zarekomenduj agentowi Centrali optymalne części, zwracając szczególną uwagę na "
                    "miasta, w których części występują jednocześnie (co_occurrence_cities). "
                    "Dla każdego proponowanego przedmiotu ZAWSZE podaj jego kod w nawiasie w formacie "
                    "'(kod: XXXXXX)', np. 'Kabel miedziany 10m (kod: KBL010) oraz Maszt (kod: MST002 - rekomendowany)'. "
                    "Odpowiedź tekstowa 'output' MUSI zawierać od 4 do maksymalnie 500 bajtów UTF-8. "
                    "Bądź zwięzły i bezpośredni."
                )
            ),
            HumanMessage(content=f"Kontekst wyszukiwania:\n{context_json}"),
        ]
        return await structured_llm.ainvoke(messages)

    async def extract_item_codes(self, user_query: str) -> Tool2PreFlightOutput:
        """Extract 6-character item codes from user query."""
        messages = [
            SystemMessage(
                content=(
                    "Z podanego tekstu wyekstrahuj wyłącznie 6-znakowe alfanumeryczne kody ID przedmiotów "
                    "(np. KBL010, MST002, TRB500). "
                    "Odrzuć oznaczenia kwartałów (np. 2026Q1) i inne niebędące kodami części. "
                    "Jeśli brak kodów przedmiotów, zwróć pustą listę."
                )
            ),
            HumanMessage(content=user_query),
        ]
        try:
            structured_llm = self.extraction_model.with_structured_output(Tool2PreFlightOutput)
            return await structured_llm.ainvoke(messages)
        except Exception as e:
            logger.warning(
                "Extraction model %s failed in extract_item_codes: %s. Falling back to %s",
                config.EXTRACTION_MODEL,
                e,
                config.GEMINI_MODEL,
            )
            structured_llm = self.synthesis_model.with_structured_output(Tool2PreFlightOutput)
            return await structured_llm.ainvoke(messages)


class LangChainOrchestrator:
    """Orchestrates Centrala tool registration and verification polling via LangChain."""

    def __init__(self, audit_service: Optional[AuditService] = None):
        self.audit = audit_service or AuditService()
        self.tool_caller = LangChainToolCaller()

    async def register_tools(self, public_url: str, session_id: str) -> dict:
        """Register the 2 tool webhooks with Centrala's verification endpoint."""
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
            actor="orchestrator",
            content=f"Registering tools at Centrala with public URL: {public_url}",
            step_type="tool_registration",
            metadata=payload,
        )

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(config.AIDEVS_VERIFY_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
            logger.info("Tool registration response from Centrala: %s", data)
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
                logger.info("Polling Centrala check status (attempt %d/%d)...", attempt, max_attempts)
                resp = await client.post(config.AIDEVS_VERIFY_URL, json=check_payload)
                data = resp.json()
                logger.info("Poll result: %s", data)

                await self.audit.log_event(
                    session_id=session_id,
                    actor="orchestrator",
                    content=f"Poll attempt {attempt}: {json.dumps(data, ensure_ascii=False)}",
                    step_type="verification_poll",
                    metadata=data,
                )

                # Check if flag or message returned
                msg = str(data)
                if "{FLG:" in msg or data.get("code") == 0 or "FLG" in msg:
                    logger.info("Task verification succeeded!")
                    return data

                await asyncio.sleep(delay_seconds)

        return {"status": "timeout", "last_response": data}

    async def solve(self, session_id: str, public_url: Optional[str] = None) -> dict:
        """Run full lifecycle: tool registration and asynchronous verification polling."""
        target_url = public_url or config.CENTRAL_PUBLIC_URL
        if not target_url:
            raise ValueError(
                "CENTRAL_PUBLIC_URL or --public-url must be specified for Centrala registration"
            )

        reg_result = await self.register_tools(target_url, session_id)
        logger.info("Waiting 20 seconds for Centrala's agent to execute turns...")
        await asyncio.sleep(20)
        verify_result = await self.poll_verification(session_id)
        return {"registration": reg_result, "verification": verify_result}
