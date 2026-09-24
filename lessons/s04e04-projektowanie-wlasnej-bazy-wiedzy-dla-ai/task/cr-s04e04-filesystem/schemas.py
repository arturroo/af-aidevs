from typing import Literal

from pydantic import BaseModel, Field

BackendType = Literal["langchain", "adk"]
CentralaActionType = Literal[
    "help",
    "reset",
    "createFile",
    "createDirectory",
    "deleteFile",
    "deleteDirectory",
    "listFiles",
    "done",
]

# --- Structured Extraction Schemas (Gemini 3.8 Flash) ---


class CityDemandExtract(BaseModel):
    """Normalized demand profile of a single settlement."""

    city_name: str = Field(
        description="Nazwa miasta w mianowniku, zapisana czystym ASCII bez polskich znakow diakrytycznych (np. 'opalino', 'domatowo').",
        examples=["opalino", "domatowo", "brudzewo"],
    )
    demands: dict[str, int] = Field(
        description=(
            "Slownik zapotrzebowania: klucz to nazwa towaru jako polski rzeczownik w mianowniku liczby pojedynczej w ASCII "
            "(np. 'chleb', 'woda', 'mlotek', 'ziemniak', 'lopata'), wartosc to liczba calkowita bez zadnych jednostek miar."
        ),
        examples=[{"chleb": 45, "woda": 120, "mlotek": 6}],
    )


class CoordinatorExtract(BaseModel):
    """Normalized profile of a municipal trade coordinator."""

    person_name: str = Field(
        description="Imie i nazwisko koordynatora z podkresleniem zamiast spacji, w alfabecie ASCII (np. 'Iga_Kapecka', 'Natan_Rams').",
        examples=["Iga_Kapecka", "Natan_Rams", "Rafal_Kisiel"],
    )
    city_name: str = Field(
        description="Nazwa zarzadzanego miasta w mianowniku ASCII (np. 'opalino', 'domatowo').",
        examples=["opalino", "domatowo"],
    )


class TransactionExtract(BaseModel):
    """Normalized record of a completed barter transaction."""

    seller_city: str = Field(
        description="Miasto sprzedajace/oferujace dany towar w mianowniku ASCII.",
        examples=["domatowo", "darzlubie", "opalino"],
    )
    commodity: str = Field(
        description="Nazwa oferowanego towaru w polskim mianowniku liczby pojedynczej w ASCII (np. 'chleb', 'ryz', 'wiertarka').",
        examples=["chleb", "ryz", "wiertarka", "ziemniak"],
    )
    buyer_city: str = Field(
        description="Miasto kupujace/odbierajace towar w mianowniku ASCII.",
        examples=["opalino", "puck", "mechowo"],
    )


class RawExtractionResult(BaseModel):
    """Aggregated result of structured extraction from Natan's notes."""

    cities: list[CityDemandExtract] = Field(
        description="Lista 8 miast wraz z ich zapotrzebowaniem."
    )
    coordinators: list[CoordinatorExtract] = Field(
        description="Lista 8 koordynatorow handlu zarzadzajacych miastami."
    )
    transactions: list[TransactionExtract] = Field(
        description="Lista transakcji barterowych okreslajaca, ktore miasto sprzedaje jakie towary."
    )


# --- Linguistic Subagent Schemas (Gemini 3.8 Flash-Lite) ---


class WordEvaluation(BaseModel):
    """Linguistic evaluation of a single commodity word."""

    word: str = Field(
        description="Oceniane slowo zapisane w ASCII.", examples=["wiertarka", "lopaty"]
    )
    is_singular_nominative: bool = Field(
        description="Czy slowo reprezentuje polski rzeczownik w mianowniku liczby pojedynczej (singular nominative).",
        examples=[True, False],
    )
    suggested_singular: str | None = Field(
        default=None,
        description="Jesli is_singular_nominative jest False, poprawna sugerowana forma mianownika liczby pojedynczej w ASCII.",
        examples=["wiertarka", "lopata", "ziemniak"],
    )
    reason: str | None = Field(
        default=None,
        description="Krotkie lingwistyczne uzasadnienie decyzji.",
        examples=["Liczba mnoga (mianownik lp to wiertarka)"],
    )


class CommodityValidationBatchResponse(BaseModel):
    """Batch evaluation response from the linguistic subagent."""

    evaluations: list[WordEvaluation] = Field(
        description="Lista ocen gramatycznych dla 100% zgloszonych slow towarowych."
    )


# --- Virtual Filesystem & Verification Schemas ---


class FilesystemFile(BaseModel):
    """In-memory representation of a virtual file to be staged and uploaded."""

    path: str = Field(
        description="Wzgledna lub absolutna sciezka w wirtualnym filesystemie (np. '/miasta/domatowo').",
        examples=[
            "/miasta/domatowo",
            "/osoby/natan_rams",
            "/towary/wiertarka",
        ],
    )
    content: str = Field(
        description="Tresc pliku (JSON dla /miasta, Markdown z linkami dla /osoby i /towary).",
        examples=['{"woda": 150, "makaron": 60}', "[Domatowo](/miasta/domatowo)"],
    )


class FilesystemActionPayload(BaseModel):
    """Single API action payload for Centrala /verify/."""

    action: CentralaActionType = Field(
        description="Nazwa akcji filesystemu.", examples=["createFile", "reset", "done"]
    )
    path: str | None = Field(
        default=None,
        description="Sciezka pliku wirtualnego (dla akcji createFile/deleteFile).",
        examples=["/miasta/opalino"],
    )
    content: str | None = Field(
        default=None,
        description="Zawartosc pliku (dla akcji createFile).",
        examples=['{"chleb": 45, "woda": 120}'],
    )


class ValidationViolation(BaseModel):
    """Detailed diagnostic violation reported by validate_workspace."""

    path: str = Field(
        description="Sciezka pliku naruszajacego regule.",
        examples=["/towary/wiertarki"],
    )
    rule: str = Field(
        description="Identyfikator zlamanej reguly.",
        examples=[
            "ASCII_PURITY",
            "JSON_SCHEMA",
            "SINGULAR_NOMINATIVE",
            "REFERENTIAL_INTEGRITY",
        ],
    )
    message: str = Field(
        description="Precyzyjny komunikat bledu z instrukcja naprawy dla agenta."
    )
    suggestion: str | None = Field(
        default=None, description="Opcjonalna sugerowana wartosc naprawcza."
    )


class ValidationReport(BaseModel):
    """Comprehensive diagnostic report emitted by validate_workspace tool."""

    valid: bool = Field(
        description="Czy caly workspace spelnia 100% regul i jest gotowy do wysylki."
    )
    total_files: int = Field(description="Liczba zwalidowanych plikow.")
    cities_count: int = Field(description="Liczba poprawnych plikow w /miasta.")
    persons_count: int = Field(description="Liczba poprawnych plikow w /osoby.")
    commodities_count: int = Field(description="Liczba poprawnych plikow w /towary.")
    errors: list[str] = Field(
        default_factory=list,
        description="Podsumowanie bledow blokujacych wysylke.",
    )
    violations: list[ValidationViolation] = Field(
        default_factory=list, description="Lista szczegolowych naruszen per plik."
    )
    hint: str | None = Field(
        default=None,
        description="Wskazowka operacyjna dla agenta jak zaplanowac i wykonac naprawe.",
    )


# --- Microservice API Schemas ---


class TaskStats(BaseModel):
    """Statistics of the executed filesystem generation."""

    cities_count: int = Field(examples=[8])
    persons_count: int = Field(examples=[8])
    commodities_count: int = Field(examples=[13])
    files_uploaded: int = Field(examples=[29])


class RunTaskRequest(BaseModel):
    """Execution request payload for POST /run."""

    backend: BackendType = Field(
        default="langchain",
        description="Wybór frameworka agentowego (langchain lub adk).",
        examples=["langchain", "adk"],
    )
    session_id: str | None = Field(
        default=None,
        description="Opcjonalny identyfikator sesji audytowej.",
        examples=["session-s04e04-001"],
    )
    reset_remote: bool = Field(
        default=True,
        description="Czy wyczyscic zdalny filesystem przed wysylka.",
    )


class RunTaskResponse(BaseModel):
    """Execution response returned by POST /run."""

    status: Literal["success", "error"] = Field(examples=["success"])
    backend: BackendType = Field(examples=["langchain"])
    flag: str | None = Field(
        default=None,
        description="Zdobyta flaga Centrali.",
        examples=["{FLG:...}"],
    )
    stats: TaskStats | None = None
    audit_logged: bool = Field(
        default=False, description="Czy telemetry zostala zapisana do BigQuery."
    )
    error: str | None = None
