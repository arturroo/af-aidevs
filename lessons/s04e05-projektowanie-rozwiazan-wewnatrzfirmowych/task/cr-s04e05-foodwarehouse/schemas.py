from typing import Any, Literal

from pydantic import BaseModel, Field


class RunTaskRequest(BaseModel):
    backend: Literal["langchain", "adk"] = Field(
        default="langchain",
        description="Wybor silnika agentowego: 'langchain' lub 'adk'.",
        examples=["langchain", "adk"],
    )
    session_id: str | None = Field(
        default=None,
        description="Opcjonalny unikalny identyfikator sesji dla separacji przestrzeni roboczych.",
        examples=["sess-123456"],
    )
    model: str | None = Field(
        default=None,
        description="Model Gemini do uzycia (np. 'gemini-3.5-flash-lite', 'gemini-3.8-flash').",
        examples=["gemini-3.5-flash-lite", "gemini-3.8-flash"],
    )
    max_iterations: int | None = Field(
        default=None,
        description="Maksymalna liczba iteracji/krokow petli agenta (domyslnie z config.MAX_AGENT_ITERATIONS).",
        examples=[50, 100, 120],
    )
    thinking_level: Literal["low", "medium", "high"] | None = Field(
        default=None,
        description="Poziom rozumowania modelu Gemini ('low', 'medium', 'high').",
        examples=["low", "medium"],
    )


class TaskStats(BaseModel):
    discovery_queries: int = Field(
        default=0, description="Liczba zapytan eksploracyjnych do API Centrali."
    )
    signatures_generated: int = Field(
        default=0, description="Liczba wygenerowanych podpisow SHA1."
    )
    orders_created: int = Field(
        default=0, description="Liczba utworzonych zamowien w Centrali."
    )
    items_appended: int = Field(
        default=0, description="Liczba pozycji towarowych dodanych do zamowien."
    )
    duration_seconds: float = Field(
        default=0.0, description="Calkowity czas wykonania zadania w sekundach."
    )


class RunTaskResponse(BaseModel):
    status: Literal["success", "error", "verification_failed"] = Field(
        description="Status realizacji zadania.",
        examples=["success", "error"],
    )
    flag: str | None = Field(
        default=None,
        description="Zdobyta flaga weryfikacyjna {FLG:...} z Centrali.",
        examples=["{FLG:SECRET_FLAG}"],
    )
    session_id: str = Field(
        description="Identyfikator sesji roboczej.",
        examples=["90cd212d-b3c9-40b3-991c-935c9a6c9162"],
    )
    backend: str = Field(
        description="Uzyty framework agentowy ('langchain' lub 'adk').",
        examples=["langchain", "adk"],
    )
    orders_count: int = Field(
        default=0, description="Liczba prawidlowo przetworzonych zamowien miast."
    )
    stats: TaskStats = Field(
        default_factory=TaskStats, description="Statystyki wykonawcze zadania."
    )
    message: str = Field(
        default="", description="Komunikat koncowy lub szczegoly bledu."
    )


class CentralaApiInput(BaseModel):
    tool: str = Field(
        description=(
            "Centrala tool name ('help', 'database', 'signatureGenerator', 'orders', 'reset'). "
            "NOTE: Permitted for discovery and read operations ('help', 'database', 'signatureGenerator', "
            "'orders' with action='get', and 'reset'). Mutative actions ('orders' with action='create' or 'append', "
            "and 'done') are intercepted by Circuit Breaker to enforce batch staging in workspace."
        ),
        examples=["help", "database", "signatureGenerator"],
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Dowolne parametry przekazywane do wybranego narzedzia w polu answer.",
        examples=[{"query": "show tables"}, {"action": "get"}],
    )
    reasoning: str = Field(
        default="",
        description="Strategiczny cel wywolania tego narzedzia.",
        examples=["Sprawdzenie tabel w bazie SQLite."],
    )


class ReadFileInput(BaseModel):
    file_path: str = Field(
        description="Sciezka do pliku w cr-mcp-workspace (np. 'food4cities.json', 'orders_manifest.json', 'TODOs.md').",
        examples=["food4cities.json", "orders_manifest.json", "TODOs.md"],
    )
    reasoning: str = Field(
        default="",
        description="Powod odczytu pliku z przestrzeni roboczej.",
    )


class WriteFileInput(BaseModel):
    file_path: str = Field(
        description="Sciezka do pliku w cr-mcp-workspace.",
        examples=["orders_manifest.json", "TODOs.md", "docs/api_spec.md"],
    )
    content: str = Field(
        description="Tresc pliku do zapisania w przestrzeni roboczej.",
    )
    reasoning: str = Field(
        default="",
        description="Powod zapisu pliku.",
    )


class ListFilesInput(BaseModel):
    path: str = Field(
        default=".",
        description="Katalog do wylistowania w cr-mcp-workspace (domyslnie '.').",
        examples=[".", "docs"],
    )
    reasoning: str = Field(
        default="",
        description="Powod listowania plikow.",
    )


class StagedOrderItem(BaseModel):
    city: str = Field(
        description="Znormalizowana nazwa miasta (male litery ASCII).",
        examples=["opalino", "domatowo"],
    )
    title: str = Field(
        description="Tytul dostawy (np. 'Dostawa dla Opalino').",
        examples=["Dostawa dla Opalino"],
    )
    creatorID: int = Field(
        description="ID uprawnionego tworcy zamowienia odczytane z bazy SQLite.",
        examples=[2],
    )
    destination: int | str = Field(
        description="Kod docelowy miasta w magazynie odczytany z bazy SQLite.",
        examples=[1234, "1234"],
    )
    signature: str = Field(
        description="Kryptograficzny podpis SHA1 zwrocony przez signatureGenerator.",
        examples=["5d41402abc4b2a76b9719d911017c592"],
    )
    items: dict[str, int] = Field(
        description="Slownik towarow (mianownik l.p. ASCII) mapowanych na dokladne ilosci calkowite.",
        examples=[{"chleb": 45, "woda": 120, "mlotek": 6}],
    )


class OrdersManifest(BaseModel):
    orders: list[StagedOrderItem] = Field(
        description="Lista zamowien dla dokladnie 8 miast.",
    )


class ValidationReport(BaseModel):
    valid: bool = Field(
        description="True jesli manifest spelnia wszystkie kryteria biznesowe i kontraktowe."
    )
    orders_count: int = Field(
        default=0,
        description="Liczba przetworzonych zamowien w manifeście.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Lista napotkanych bledow walidacyjnych.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Ostrzezenia lub uwagi nieblokujace wysylki.",
    )
    hint: str = Field(
        default="",
        description="Konkretne instrukcje naprawcze dla agenta.",
    )


class DispatchReport(BaseModel):
    status: Literal["success", "error", "rejected"] = Field(
        description="Status wykonania wysylki batchowej.",
    )
    orders_processed: int = Field(
        default=0,
        description="Liczba poprawnie utworzonych zamowien.",
    )
    items_appended: int = Field(
        default=0,
        description="Liczba dodanych pozycji towarowych.",
    )
    flag: str | None = Field(
        default=None,
        description="Odebrana flaga kursowa z narzedzia done.",
    )
    message: str = Field(
        default="",
        description="Komunikat zwrotny z Centrali lub szczegoly bledu.",
    )
