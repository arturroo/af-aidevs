"""Pydantic schemas and contract models for S03E04 negotiations tooling service.

Follows Google API Improvement Proposals (AIP) and GEMINI.md contract-first standards:
- Explicit Field descriptions and examples for all fields.
- Mandatory reasoning fields for structured outputs.
- Type-safe request/response envelopes.
"""

from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator


# ==============================================================================
# Public API Tool Contracts (Centrala Webhook Schemas)
# ==============================================================================

class ToolRequest(BaseModel):
    """Incoming request payload from Centrala's agent."""

    params: Any = Field(
        description="Treść zapytania lub parametry przekazane przez agenta Centrali",
        examples=["w 2026Q1 szukam kabla 10m i masztu"],
    )

    @field_validator("params", mode="before")
    @classmethod
    def coerce_params_to_str(cls, v: Any) -> str:
        """Coerce list, dict, or numbers into a normalized string representation."""
        if isinstance(v, str):
            return v
        if isinstance(v, list):
            return ", ".join(str(item) for item in v)
        if isinstance(v, dict):
            if "params" in v:
                return str(v["params"])
            return ", ".join(f"{k}: {val}" for k, val in v.items())
        return str(v)


class ToolResponse(BaseModel):
    """Outgoing response payload returned to Centrala's agent."""

    output: str = Field(
        min_length=4,
        max_length=500,
        description="Odpowiedź tekstowa narzędzia spełniająca twardy limit 4 do 500 bajtów UTF-8",
        examples=[
            "Zidentyfikowano: Kabel miedziany 10m (kod: KBL010) oraz Maszt rurowy (kod: MST002 - rekomendowany, oba w Krakowie i Warszawie). Użyj find_cities_having_items_ids z tymi kodami."
        ],
    )

    @field_validator("output")
    @classmethod
    def validate_byte_length(cls, v: str) -> str:
        byte_len = len(v.encode("utf-8"))
        if byte_len < 4:
            raise ValueError(f"Output too short: {byte_len} bytes (minimum 4 bytes)")
        if byte_len > 500:
            raise ValueError(f"Output exceeds 500 bytes limit: {byte_len} bytes")
        return v


# ==============================================================================
# Tool 1: Catalog Search Pipeline Schemas (/api/search-item-in-catalog)
# ==============================================================================

class ExtractedItemQuery(BaseModel):
    """A single technical item entity extracted from noisy conversation."""

    name_with_spec: str = Field(
        description="Pełna nazwa techniczna przedmiotu wraz ze specyfikacją/przymiotnikiem (np. kabel 10m, maszt rurowy)",
        examples=["kabel miedziany 10m", "maszt rurowy stalowy"],
    )


class Tool1PreFlightOutput(BaseModel):
    """Output of Pre-Flight LLM extracting search targets and stripping noise."""

    reasoning: str = Field(
        description="Wyjaśnienie dlaczego odrzucono szum konwersacyjny, daty (np. 2026Q1) i jak wyekstrahowano encje",
        examples=["Odrzucono wzmiankę o kwartale 2026Q1. Zidentyfikowano potrzebę znalezienia kabla oraz masztu."],
    )
    items: List[ExtractedItemQuery] = Field(
        default_factory=list,
        max_length=4,
        description="Lista wyekstrahowanych encji technicznych do wyszukania w katalogu (maksymalnie 4)",
    )


class ItemCandidate(BaseModel):
    """A candidate item retrieved from inventory.db with hybrid score and city stocking."""

    item_code: str = Field(
        description="6-znakowy alfanumeryczny unikalny kod przedmiotu",
        examples=["KBL010", "MST002"],
    )
    item_name: str = Field(
        description="Dokładna nazwa katalogowa przedmiotu",
        examples=["Kabel miedziany 10m 2x1.5mm", "Maszt rurowy 6m ocynkowany"],
    )
    hybrid_score: float = Field(
        description="Zważony wynik wyszukiwania hybrydowego (0.4 * BM25 + 0.6 * Cosine)",
        examples=[0.895],
    )
    stocking_cities: List[str] = Field(
        default_factory=list,
        description="Nazwy miast, w których ten konkretny przedmiot jest na stanie (maksymalnie 4)",
        examples=[["Krakow", "Warszawa"]],
    )
    co_occurrence_cities: List[str] = Field(
        default_factory=list,
        description="Miasta współwystępujące z kandydatami dla pozostałych poszukiwanych części",
        examples=[["Krakow"]],
    )


class EntitySearchResult(BaseModel):
    """Top-3 candidates retrieved for a single extracted entity query."""

    query_entity: str = Field(
        description="Szukana fraza techniczna z pre-flightu",
        examples=["kabel 10m"],
    )
    candidates: List[ItemCandidate] = Field(
        default_factory=list,
        max_length=3,
        description="Top-3 najlepiej dopasowane przedmioty z katalogu",
    )


class Tool1PostFlightInput(BaseModel):
    """Contextual input fed into Post-Flight LLM to synthesize final recommendation."""

    user_query: str = Field(
        description="Pierwotna wiadomość od agenta Centrali dla zachowania kontekstu",
        examples=["w 2026Q1 szukam kabla 10m i masztu"],
    )
    search_results: List[EntitySearchResult] = Field(
        description="Hierarchiczne wyniki wyszukiwania kandydatów per każda wyszukiwana encja",
    )


class Tool1PostFlightOutput(BaseModel):
    """Synthesized recommendation generated by Post-Flight LLM for Tool 1."""

    reasoning: str = Field(
        description="Uzasadnienie doboru optymalnych kodów pod kątem współwystępowania w tych samych miastach",
        examples=["Wybrano KBL010 i MST002, ponieważ oba przedmioty są jednocześnie dostępne w Krakowie."],
    )
    output: str = Field(
        min_length=4,
        max_length=500,
        description="Zwięzła odpowiedź z kodami w formacie (kod: XXXXXX) mieszcząca się w 500 bajtach UTF-8",
        examples=[
            "Zidentyfikowano: Kabel miedziany 10m (kod: KBL010) oraz Maszt rurowy (kod: MST002 - rekomendowany, oba w Krakowie i Warszawie). Użyj find_cities_having_items_ids z tymi kodami."
        ],
    )
    hint: Optional[str] = Field(
        default=None,
        description="Wskazówka progressive disclosure dla agenta Centrali na kolejny krok",
        examples=["Przekaż kody do find_cities_having_items_ids"],
    )


# ==============================================================================
# Tool 2: City Intersection Pipeline Schemas (/api/find-cities-having-items-ids)
# ==============================================================================

class Tool2PreFlightOutput(BaseModel):
    """Output of Pre-Flight LLM extracting 6-character item codes."""

    reasoning: str = Field(
        description="Uzasadnienie ekstrakcji kodów lub wyjaśnienie ich braku",
        examples=["Wyekstrahowano kody KBL010 i MST002. Odrzucono oznaczenie kwartału 2026Q1."],
    )
    item_codes: List[str] = Field(
        default_factory=list,
        max_length=4,
        description="Lista 6-znakowych alfanumerycznych kodów przedmiotów",
        examples=[["KBL010", "MST002"]],
    )


# ==============================================================================
# Management & Orchestration Schemas
# ==============================================================================

class RunTaskRequest(BaseModel):
    """Request schema for canonical POST /run orchestrator endpoint."""

    backend: str = Field(
        default="langchain",
        description="Wybór frameworka orkiestrującego: 'langchain' lub 'adk'",
        examples=["langchain", "adk"],
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Opcjonalny unikalny identyfikator sesji audytowej",
        examples=["s03e04_langchain_20260915_233000"],
    )
    public_url: Optional[str] = Field(
        default=None,
        description="Opcjonalny publiczny URL serwisu Cloud Run do rejestracji w Centrali",
        examples=["https://cr-s03e04-negotiations-qsvqxjqyrq-oa.a.run.app"],
    )


class RunTaskResponse(BaseModel):
    """Response schema for canonical POST /run orchestrator endpoint."""

    session_id: str = Field(description="Identyfikator sesji wykonania")
    backend: str = Field(description="Użyty backend")
    status: str = Field(description="Status wykonania zadania (np. success, error)")
    result: dict = Field(default_factory=dict, description="Szczegóły wykonania i weryfikacji")


class ReloadDbResponse(BaseModel):
    """Response schema for administrative POST /reload-db endpoint."""

    status: str = Field(description="Status odświeżenia bazy (ok, error)")
    message: str = Field(description="Komunikat informacyjny")
    timestamp: str = Field(description="Czas wykonania operacji")
