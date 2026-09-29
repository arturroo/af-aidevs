import logging

from google import genai
from google.genai import types

from config import settings
from schemas import StabilizationDecision

logger = logging.getLogger("stabilization_service")


class StabilizationService:
    """Interprets temporal distortion advice from Central using Vertex AI Gemini models."""

    def __init__(self) -> None:
        self.project = settings.GOOGLE_CLOUD_PROJECT
        self.location = settings.GOOGLE_CLOUD_LOCATION

    def _get_client(self) -> genai.Client:
        """Instantiates google-genai client configured for Vertex AI IAM mode."""
        return genai.Client(
            vertexai=True,
            project=self.project,
            location=self.location,
        )

    async def resolve_stabilization(
        self,
        api_hint: str,
        target_date: str,
        model: str | None = None,
        thinking_level: str | None = None,
    ) -> str:
        """Analyzes API advice and determines the exact stabilization value."""
        chosen_model = model or settings.GEMINI_MODEL
        chosen_thinking = thinking_level or settings.THINKING_LEVEL

        logger.info(
            "Resolving stabilization with model=%s, thinking=%s for hint='%s' (date=%s)",
            chosen_model,
            chosen_thinking,
            api_hint,
            target_date,
        )

        client = self._get_client()

        system_instruction = (
            "You are the ACME CHRONOS-P1 Temporal Stabilization Resolver. "
            "Your task is to analyze advice and hints returned by the Central API regarding "
            "environmental anomalies, temporal distortion, and lunar/solar flux, and determine "
            "the EXACT required parameter value for 'stabilization'. "
            "The advice is frequently phrased in Polish, often describing numbers using Polish number words "
            "(e.g. 'dziewięćset' = 900, 'siedemset jedenaście' = 711) and arithmetic operations "
            "(e.g. 'sugerują zwykle dziewięćset jednostek ... zalecane jest obniżenie poziomu o siedemset jedenaście' -> 900 - 711 = 189). "
            "Calculate all required arithmetic operations carefully and output the final single number. "
            "The stabilization parameter MUST always be a numeric value (e.g. 189, 0, 42). "
            "Never return words like 'default', 'auto', 'standard', or 'nominal'. "
            "If conditions are nominal or no offset is specified, return '0'."
        )

        prompt = (
            f"Target Temporal Destination: {target_date}\n"
            f'Central API Advice / Telemetry Hint: "{api_hint}"\n\n'
            "Determine the exact numeric value to configure for the 'stabilization' parameter. Return strictly a number string (e.g. '0')."
        )

        try:
            response = client.models.generate_content(
                model=chosen_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.0,
                    response_mime_type="application/json",
                    response_schema=StabilizationDecision,
                ),
            )

            parsed = StabilizationDecision.model_validate_json(response.text)
            import re

            val = parsed.stabilization_value.strip()
            if not re.match(r"^-?\d+(\.\d+)?$", val):
                digits = re.findall(r"-?\d+(?:\.\d+)?", val)
                val = digits[0] if digits else "0"

            logger.info(
                "Stabilization resolved: value='%s' (raw='%s'), reasoning='%s'",
                val,
                parsed.stabilization_value,
                parsed.reasoning,
            )
            return val
        except Exception as e:
            logger.error(
                "LLM stabilization resolution encountered error: %s. Using heuristic fallback.",
                e,
            )
            # Heuristic fallback: search for digits or default to '0'
            import re

            digits = re.findall(r"-?\d+", api_hint)
            fallback = digits[0] if digits else "0"
            logger.info("Heuristic fallback selected: '%s'", fallback)
            return fallback


stabilization_service = StabilizationService()
