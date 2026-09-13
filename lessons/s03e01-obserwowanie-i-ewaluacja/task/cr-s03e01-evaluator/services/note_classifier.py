import asyncio
import json
import logging
from typing import Dict, List, Optional
from langsmith.run_helpers import traceable

import config
from schemas import BatchNoteAnomalyEvaluation, OperatorNoteEvaluation

logger = logging.getLogger("services.note_classifier")

SYSTEM_INSTRUCTION = """You are an industrial telemetry QA auditor inspecting human technician logs for nuclear/thermal power plant sensors.
Analyze the provided technician note.
Determine whether the technician claims, reports, warns, or implies an anomaly, failure, defect, malfunction, alarm, breakdown, or problem (operator_claims_anomaly = true).
If the technician reports that readings/conditions are normal, nominal, stable, expected, or within limits (operator_claims_anomaly = false).

Be strict and objective. Return structured JSON matching OperatorNoteEvaluation."""


class NoteClassifier:
    """Evaluates operator notes to detect false positives (operator claims an error when readings are nominal)."""

    def __init__(self, backend: str = "langchain"):
        self.backend = backend.strip().lower()
        self._cache: Dict[str, OperatorNoteEvaluation] = {}
        self._langchain_chain = None
        self._langchain_batch_chain = None
        self._genai_client = None

    def _init_langchain(self):
        if self._langchain_chain is None:
            from langchain_google_genai import ChatGoogleGenerativeAI

            llm = ChatGoogleGenerativeAI(
                model=config.GEMINI_MODEL,
                temperature=0.0,
                project=config.GOOGLE_CLOUD_PROJECT,
                location=config.GOOGLE_CLOUD_LOCATION,
                vertexai=True,
                thinking_level=config.THINKING_LEVEL,
            )
            self._langchain_chain = llm.with_structured_output(OperatorNoteEvaluation)

    def _init_langchain_batch(self):
        if self._langchain_batch_chain is None:
            from langchain_google_genai import ChatGoogleGenerativeAI

            llm = ChatGoogleGenerativeAI(
                model=config.GEMINI_MODEL,
                temperature=0.0,
                project=config.GOOGLE_CLOUD_PROJECT,
                location=config.GOOGLE_CLOUD_LOCATION,
                vertexai=True,
                thinking_level=config.THINKING_LEVEL,
            )
            self._langchain_batch_chain = llm.with_structured_output(BatchNoteAnomalyEvaluation)

    def _init_genai(self):
        if self._genai_client is None:
            from google import genai

            self._genai_client = genai.Client(
                vertexai=True,
                project=config.GOOGLE_CLOUD_PROJECT,
                location=config.GOOGLE_CLOUD_LOCATION,
            )

    @traceable(run_type="llm", name="classify_operator_note_langchain")
    async def _classify_langchain(self, note: str) -> OperatorNoteEvaluation:
        self._init_langchain()
        prompt = (
            f"{SYSTEM_INSTRUCTION}\n\n"
            f"Technician Note to evaluate:\n"
            f"\"\"\"{note}\"\"\""
        )
        return await self._langchain_chain.ainvoke(prompt)

    @traceable(run_type="llm", name="classify_operator_note_genai")
    async def _classify_genai(self, note: str) -> OperatorNoteEvaluation:
        self._init_genai()
        from google.genai import types

        prompt = (
            f"{SYSTEM_INSTRUCTION}\n\n"
            f"Technician Note to evaluate:\n"
            f"\"\"\"{note}\"\"\""
        )
        response = await self._genai_client.aio.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=OperatorNoteEvaluation,
                temperature=0.0,
            ),
        )
        data = json.loads(response.text)
        return OperatorNoteEvaluation(**data)

    async def classify_note(self, note: str) -> OperatorNoteEvaluation:
        """Classifies a single operator note with local caching."""
        stripped = note.strip()
        if stripped in self._cache:
            return self._cache[stripped]

        if not stripped:
            eval_result = OperatorNoteEvaluation(
                reasoning="Empty note defaults to no anomaly reported",
                operator_claims_anomaly=False,
            )
            self._cache[stripped] = eval_result
            return eval_result

        if self.backend in ("genai", "adk", "google-adk"):
            eval_result = await self._classify_genai(stripped)
        else:
            eval_result = await self._classify_langchain(stripped)

        self._cache[stripped] = eval_result
        return eval_result

    @traceable(run_type="llm", name="classify_all_notes_langchain")
    async def _classify_all_langchain(self, prompt: str) -> List[int]:
        self._init_langchain_batch()
        res = await self._langchain_batch_chain.ainvoke(prompt)
        return res.anomaly_indices

    @traceable(run_type="llm", name="classify_all_notes_genai")
    async def _classify_all_genai(self, prompt: str) -> List[int]:
        self._init_genai()
        from google.genai import types

        response = await self._genai_client.aio.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=BatchNoteAnomalyEvaluation,
                temperature=0.0,
                thinking_config=types.ThinkingConfig(thinking_level="low"),
            ),
        )
        data = json.loads(response.text)
        return data.get("anomaly_indices", [])

    async def classify_all_notes(self, unique_notes: List[str]) -> List[int]:
        """Classifies all unique notes in a single high-efficiency prompt returning only anomaly indices."""
        formatted_lines = [
            f"{idx}: {note.replace(chr(10), ' ').strip()}"
            for idx, note in enumerate(unique_notes)
        ]
        notes_block = "\n".join(formatted_lines)

        prompt = f"""You are an industrial QA telemetry auditor for a nuclear/thermal power plant.
The physical telemetry readings for all {len(unique_notes)} records below have been mathematically and physically audited and verified to be 100% NOMINAL and within safe operational bounds.
However, human technicians sometimes enter false alarms, erroneous defect reports, or claim malfunctions when the hardware is actually operating normally.

Examine EVERY SINGLE note from index 0 to {len(unique_notes)-1} below.
Identify ALL note indices where the technician claims, reports, warns, or implies an anomaly, problem, error, defect, malfunction, alarm, breakdown, or abnormal condition.
If a note says that readings/operations are normal, nominal, stable, routine, expected, or within limits, do NOT include it.

Numbered Notes:
{notes_block}

Return strictly a JSON object with 'anomaly_indices' containing a list of integer indices where the technician claimed a problem."""

        if self.backend in ("genai", "adk", "google-adk"):
            return await self._classify_all_genai(prompt)
        else:
            return await self._classify_all_langchain(prompt)

    async def classify_notes_batch(
        self, unique_notes: List[str], concurrency_limit: int = 10
    ) -> Dict[str, OperatorNoteEvaluation]:
        """Classifies a list of unique notes concurrently with a semaphore."""
        sem = asyncio.Semaphore(concurrency_limit)

        async def _bounded_classify(note: str) -> tuple[str, OperatorNoteEvaluation]:
            async with sem:
                res = await self.classify_note(note)
                return note, res

        tasks = [_bounded_classify(note) for note in unique_notes]
        results = await asyncio.gather(*tasks)
        return dict(results)
