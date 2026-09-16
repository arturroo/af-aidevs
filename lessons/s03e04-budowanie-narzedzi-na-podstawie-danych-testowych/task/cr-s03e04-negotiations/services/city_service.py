"""City Service implementing Tool 2 (/api/find-cities-having-items-ids) relational set pipeline."""

import logging
from typing import Optional

from agents.factory import get_tool_caller
from config import MODEL_ARMOR_URL
from services.audit_service import AuditService
from services.db_service import DatabaseService
from services.response_guardrail import enforce_byte_envelope

logger = logging.getLogger(__name__)


class CityService:
    """Orchestrates relational set intersection query for item availability across cities."""

    def __init__(
        self,
        db_service: Optional[DatabaseService] = None,
        audit_service: Optional[AuditService] = None,
    ):
        self.db_service = db_service or DatabaseService.get_instance()
        self.audit = audit_service or AuditService()

    async def _verify_safety(self, prompt: str, session_id: str) -> None:
        """Verify prompt safety with Model Armor if configured."""
        if not MODEL_ARMOR_URL:
            return
        try:
            from af_aidevs import model_armor
            is_safe = await model_armor.verify(
                text=prompt,
                policy_context="negotiations_city",
                session_id=session_id,
            )
            if not is_safe:
                logger.warning("[%s] Prompt flagged as unsafe by Model Armor: %s", session_id, prompt[:100])
        except Exception as e:
            logger.warning("Model Armor verification error: %s", e)

    async def find_cities(
        self, user_query: str, session_id: str, backend: str = "langchain"
    ) -> str:
        """Execute Tool 2 relational set intersection pipeline."""
        await self._verify_safety(user_query, session_id)
        tool_caller = get_tool_caller(backend)

        # 1. Pre-flight 6-char code extraction
        logger.info("Extracting item codes from: %s", user_query[:80])
        pre_flight_output = await tool_caller.extract_item_codes(user_query)
        item_codes = pre_flight_output.item_codes

        await self.audit.log_event(
            session_id=session_id,
            actor="tool2_preflight",
            content=f"Extracted {len(item_codes)} item codes: {item_codes}",
            step_type="preflight_codes",
            metadata={"reasoning": pre_flight_output.reasoning},
        )

        # 2. Fail-Fast Guardrail: If no valid codes detected, return helpful 404 guidance
        if not item_codes:
            output = (
                "Błąd: Nie znaleziono 6-znakowych kodów w Twojej wiadomości. "
                "Użyj najpierw narzędzia search_item_in_catalog, aby uzyskać kody ID na podstawie opisów."
            )
            return enforce_byte_envelope(output)

        # 3. Parametric SQL Query (HAVING COUNT(DISTINCT) = N)
        logger.info("Querying cities stocking all codes: %s", item_codes)
        matching_cities = self.db_service.find_cities_stocking_all_items(item_codes)

        # 4. Deterministic Python formatting (<90 bytes, <0.001 ms)
        if not matching_cities:
            output = (
                f"Żadne miasto nie posiada jednocześnie wszystkich wskazanych przedmiotów ({', '.join(item_codes)}). "
                "Wybierz alternatywne warianty części z katalogu."
            )
        else:
            formatted_cities = [f"{c['name']} ({c['code']})" for c in matching_cities]
            output = (
                f"Miasta posiadające wszystkie {len(item_codes)} przedmioty jednocześnie: "
                f"{', '.join(formatted_cities)}."
            )

        await self.audit.log_event(
            session_id=session_id,
            actor="tool2_result",
            content=f"Matching cities for {item_codes}: {output}",
            step_type="sql_intersection",
            metadata={"item_codes": item_codes, "matching_cities_count": len(matching_cities)},
        )

        # 5. Enforce strict 4 <= len(bytes) <= 500 boundary
        return enforce_byte_envelope(output)
