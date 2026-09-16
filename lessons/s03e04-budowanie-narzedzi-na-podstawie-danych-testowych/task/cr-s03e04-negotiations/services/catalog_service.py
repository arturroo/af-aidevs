"""Catalog Service implementing Tool 1 (/api/search-item-in-catalog) 4-stage pipeline."""

import logging
from typing import Optional

from agents.factory import get_tool_caller
from config import MODEL_ARMOR_URL
from schemas import Tool1PostFlightInput
from services.audit_service import AuditService
from services.hybrid_search_service import HybridSearchService
from services.response_guardrail import enforce_byte_envelope

logger = logging.getLogger(__name__)


class CatalogService:
    """Orchestrates 4-stage catalog search pipeline with hybrid retrieval and co-occurrence."""

    def __init__(
        self,
        hybrid_service: Optional[HybridSearchService] = None,
        audit_service: Optional[AuditService] = None,
    ):
        self.hybrid_service = hybrid_service or HybridSearchService()
        self.audit = audit_service or AuditService()

    async def _verify_safety(self, prompt: str, session_id: str) -> None:
        """Verify prompt safety with Model Armor if configured."""
        if not MODEL_ARMOR_URL:
            return
        try:
            from af_aidevs import model_armor
            is_safe = await model_armor.verify(
                text=prompt,
                policy_context="negotiations_catalog",
                session_id=session_id,
            )
            if not is_safe:
                logger.warning("[%s] Prompt flagged as unsafe by Model Armor: %s", session_id, prompt[:100])
        except Exception as e:
            logger.warning("Model Armor verification error: %s", e)

    async def search_items(
        self, user_query: str, session_id: str, backend: str = "langchain"
    ) -> str:
        """Execute full 4-stage Tool 1 search pipeline."""
        await self._verify_safety(user_query, session_id)
        tool_caller = get_tool_caller(backend)

        # 1. Pre-flight intent extraction (strip noise, extract item specs)
        logger.info("Executing Pre-Flight intent extraction for: %s", user_query[:80])
        pre_flight_output = await tool_caller.extract_catalog_intent(user_query)

        await self.audit.log_event(
            session_id=session_id,
            actor="tool1_preflight",
            content=f"Extracted {len(pre_flight_output.items)} items: {[i.name_with_spec for i in pre_flight_output.items]}",
            step_type="preflight_intent",
            metadata={"reasoning": pre_flight_output.reasoning},
        )

        # Early return if no item entities were detected
        if not pre_flight_output.items:
            output = (
                "Nie zidentyfikowano poszukiwanych przedmiotów w Twojej wiadomości. "
                "Podaj nazwy lub opisy techniczne części (np. kabel 10m, maszt)."
            )
            return enforce_byte_envelope(output)

        # 2 & 3. Hybrid RAG Search & Co-occurrence calculation
        query_entities = [item.name_with_spec for item in pre_flight_output.items]
        logger.info("Running hybrid search & co-occurrence for: %s", query_entities)
        search_results = self.hybrid_service.search_all_entities_with_co_occurrence(query_entities)

        # 4. Post-flight synthesis with (kod: XXXXXX) and co-occurrence recommendation
        post_input = Tool1PostFlightInput(
            user_query=user_query,
            search_results=search_results,
        )
        post_flight_output = await tool_caller.synthesize_catalog_response(post_input)

        await self.audit.log_event(
            session_id=session_id,
            actor="tool1_postflight",
            content=f"Synthesized recommendation: {post_flight_output.output[:120]}...",
            step_type="postflight_synthesis",
            metadata={"reasoning": post_flight_output.reasoning, "hint": post_flight_output.hint},
        )

        # 5. Enforce strict 4 <= len(bytes) <= 500 boundary
        guarded_output = enforce_byte_envelope(post_flight_output.output)
        return guarded_output
