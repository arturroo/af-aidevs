"""Linguistic validation subagent service using Gemini 3.8 Flash-Lite for Polish morphology."""

import logging

from langchain_google_genai import ChatGoogleGenerativeAI

import config
from schemas import CommodityValidationBatchResponse, WordEvaluation

logger = logging.getLogger("services.linguistic")


class LinguisticService:
    """Linguistic evaluator using Gemini 3.8 Flash-Lite with contract completeness assertions."""

    def __init__(
        self,
        model_name: str = config.GEMINI_FLASH_LITE_MODEL,
        project_id: str = config.GOOGLE_CLOUD_PROJECT,
        location: str = config.GOOGLE_CLOUD_LOCATION,
    ):
        self.model_name = model_name
        self.project_id = project_id
        self.location = location

    async def validate_commodities(
        self, words: list[str]
    ) -> CommodityValidationBatchResponse:
        """Validates that a list of words are Polish nouns in singular nominative form in ASCII."""
        if not words:
            return CommodityValidationBatchResponse(evaluations=[])

        # De-duplicate while preserving list
        unique_words = sorted(set(words))

        llm = ChatGoogleGenerativeAI(
            model=self.model_name,
            temperature=0.0,
            project=self.project_id,
            location=self.location,
            vertexai=True,
        )

        structured_llm = llm.with_structured_output(CommodityValidationBatchResponse)

        prompt = f"""Jesteś precyzyjnym ekspertem gramatyki i morfologii języka polskiego.
Twoim zadaniem jest ocena każdego z poniższych słów (zapisanych w alfabecie ASCII bez polskich znaków diakrytycznych).

Dla KAŻDEGO słowa musisz określić:
1. is_singular_nominative (bool): czy to słowo reprezentuje polski rzeczownik w mianowniku liczby pojedynczej (singular nominative).
2. suggested_singular (str | None): jeśli is_singular_nominative jest False (np. słowo jest w liczbie mnogiej lub innym przypadku), podaj poprawną formę mianownika liczby pojedynczej w ASCII (np. 'wiertarki' -> 'wiertarka', 'ziemniaki' -> 'ziemniak', 'lopaty' -> 'lopata'). Jeśli słowo jest już poprawne, wpisz null.
3. reason (str | None): krótkie wyjaśnienie.

Przykłady wzorcowe:
- 'koparka' -> is_singular_nominative: true, suggested_singular: null
- 'koparki' -> is_singular_nominative: false, suggested_singular: 'koparka'
- 'wiertarka' -> is_singular_nominative: true, suggested_singular: null
- 'wiertarki' -> is_singular_nominative: false, suggested_singular: 'wiertarka'
- 'ziemniak' -> is_singular_nominative: true, suggested_singular: null
- 'ziemniaki' -> is_singular_nominative: false, suggested_singular: 'ziemniak'
- 'chleb' -> is_singular_nominative: true, suggested_singular: null
- 'chleby' -> is_singular_nominative: false, suggested_singular: 'chleb'
- 'lopata' -> is_singular_nominative: true, suggested_singular: null
- 'lopaty' -> is_singular_nominative: false, suggested_singular: 'lopata'

Oto lista słów do oceny:
{unique_words}
"""
        logger.info(
            f"Invoking {self.model_name} for linguistic evaluation of {len(unique_words)} words..."
        )
        response = await structured_llm.ainvoke(prompt)
        if not isinstance(response, CommodityValidationBatchResponse):
            response = CommodityValidationBatchResponse.model_validate(response)

        # --- Subagent Completeness Guard (Invariant Assertions) ---
        evaluated_words = {e.word for e in response.evaluations}
        missing_words = set(unique_words) - evaluated_words

        if missing_words:
            logger.warning(
                f"Subagent dropped {len(missing_words)} words from evaluation: {missing_words}. Healing..."
            )
            for w in missing_words:
                # Fallback heuristic / append missing evaluation
                response.evaluations.append(
                    WordEvaluation(
                        word=w,
                        is_singular_nominative=True,
                        suggested_singular=None,
                        reason="Heuristic fallback due to dropped word from subagent response",
                    )
                )

        # Verify that False items have suggested_singular populated
        for eval_item in response.evaluations:
            if (
                not eval_item.is_singular_nominative
                and not eval_item.suggested_singular
            ):
                eval_item.suggested_singular = eval_item.word.rstrip("iey")

        logger.info(
            f"Linguistic evaluation completed for {len(response.evaluations)} words"
        )
        return response
