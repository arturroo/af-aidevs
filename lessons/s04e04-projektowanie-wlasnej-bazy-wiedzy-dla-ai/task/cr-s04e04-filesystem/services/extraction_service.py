"""Ingestion and structured entity extraction service for S04E04 using Gemini 3.8 Flash."""

import io
import json
import logging
import unicodedata
import zipfile
from collections import defaultdict
from pathlib import Path

import httpx
from langchain_google_genai import ChatGoogleGenerativeAI

import config
from schemas import FilesystemFile, RawExtractionResult

logger = logging.getLogger("services.extraction")

POLISH_ASCII_MAP = str.maketrans(
    {
        "ą": "a",
        "ć": "c",
        "ę": "e",
        "ł": "l",
        "ń": "n",
        "ó": "o",
        "ś": "s",
        "ź": "z",
        "ż": "z",
        "Ą": "A",
        "Ć": "C",
        "Ę": "E",
        "Ł": "L",
        "Ń": "N",
        "Ó": "O",
        "Ś": "S",
        "Ź": "Z",
        "Ż": "Z",
    }
)


def to_ascii(text: str) -> str:
    """Transliterates Polish diacritics to pure ASCII equivalents."""
    cleaned = text.translate(POLISH_ASCII_MAP)
    normalized = unicodedata.normalize("NFKD", cleaned)
    return "".join(c for c in normalized if not unicodedata.combining(c))


class ExtractionService:
    """Downloads Natan's notes and runs structured extraction via Gemini 3.8 Flash on Vertex AI."""

    def __init__(
        self,
        notes_url: str = config.AIDEVS_NOTES_URL,
        model_name: str = config.GEMINI_MODEL,
        project_id: str = config.GOOGLE_CLOUD_PROJECT,
        location: str = config.GOOGLE_CLOUD_LOCATION,
    ):
        self.notes_url = notes_url
        self.model_name = model_name
        self.project_id = project_id
        self.location = location

    async def fetch_notes(self) -> dict[str, str]:
        """Fetches and unzips Natan's notes, returning filename -> content map."""
        # Check if local extracted files exist in lesson data folder first
        local_extracted = Path(__file__).resolve().parents[2] / "data" / "extracted"
        if local_extracted.exists():
            notes: dict[str, str] = {}
            for f in local_extracted.glob("*.txt"):
                notes[to_ascii(f.name)] = f.read_text(
                    encoding="utf-8", errors="replace"
                )
            if notes:
                logger.info(
                    f"Loaded {len(notes)} notes files from local path {local_extracted}"
                )
                return notes

        logger.info(f"Downloading notes archive from {self.notes_url}")
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(self.notes_url)
            resp.raise_for_status()
            archive_bytes = resp.content

        notes_map: dict[str, str] = {}
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as z:
            for item in z.infolist():
                if item.filename.endswith(".txt"):
                    raw = z.read(item).decode("utf-8", errors="replace")
                    clean_name = to_ascii(Path(item.filename).name)
                    notes_map[clean_name] = raw
        logger.info(
            f"Extracted {len(notes_map)} files from notes archive: {list(notes_map.keys())}"
        )
        return notes_map

    async def extract_structured_plan(
        self, notes: dict[str, str]
    ) -> RawExtractionResult:
        """Invokes Gemini 3.8 Flash with Pydantic structured output to parse Natan's notes."""
        llm = ChatGoogleGenerativeAI(
            model=self.model_name,
            temperature=0.1,
            project=self.project_id,
            location=self.location,
            vertexai=True,
            thinking_level=config.THINKING_LEVEL,
        )

        structured_llm = llm.with_structured_output(RawExtractionResult)

        prompt = f"""Przeanalizuj ponizsze notatki handlowe Natana Ramsa sporzadzone w jezyku polskim i wyodrebnij scisle encje:

1. Z pliku 'ogloszenia.txt':
   Wyciagnij zapotrzebowanie kazdego miasta:
   - city_name: nazwa miasta w mianowniku, male litery, czyste ASCII (np. 'opalino', 'domatowo', 'brudzewo', 'darzlubie', 'celbowo', 'mechowo', 'puck', 'karlinkowo').
   - demands: slownik, w ktorym kluczem jest nazwa towaru jako polski rzeczownik w mianowniku liczby pojedynczej w ASCII (np. 'chleb', 'woda', 'mlotek', 'ziemniak', 'lopata', 'wiertarka', 'ryz', 'wolowina', 'kurczak', 'kapusta', 'marchew', 'makaron'), a wartoscia jest liczba calkowita (usun wszelkie jednostki miar, np. 'workow', 'kg', 'butelek', 'porcji').

2. Z pliku 'rozmowy.txt':
   Zidentyfikuj 8 koordynatorow handlu zarzadzajacych miastami:
   - person_name: 'Imie_Nazwisko' w ASCII (np. 'Iga_Kapecka', 'Natan_Rams', 'Rafal_Kisiel', 'Marta_Frantz', 'Oskar_Radtke', 'Eliza_Redmann', 'Damian_Kroll', 'Lena_Konkel').
   - city_name: zarzadzane miasto w mianowniku ASCII.

3. Z pliku 'transakcje.txt':
   Dla kazdego wpisu 'MiastoA -> towar -> MiastoB':
   - seller_city: MiastoA (sprzedawca/oferent) w mianowniku ASCII
   - commodity: nazwa towaru w mianowniku liczby pojedynczej w ASCII (np. 'chleb', 'woda', 'lopata', 'wiertarka', 'ziemniak', 'ryz')
   - buyer_city: MiastoB (odbiorca) w mianowniku ASCII

--- TRESC NOTATEK ---
OGLOSZENIA:
{notes.get("ogloszenia.txt", "")}

ROZMOWY:
{notes.get("rozmowy.txt", "")}

TRANSAKCJE:
{notes.get("transakcje.txt", "")}
"""
        logger.info("Extracting entities via Gemini 3.8 Flash structured output...")
        result = await structured_llm.ainvoke(prompt)
        if not isinstance(result, RawExtractionResult):
            # In case LLM returns dict or wrapped object
            result = RawExtractionResult.model_validate(result)

        logger.info(
            f"Extraction complete: {len(result.cities)} cities, "
            f"{len(result.coordinators)} coordinators, {len(result.transactions)} transactions"
        )
        return result

    def build_virtual_files(
        self, extraction: RawExtractionResult
    ) -> list[FilesystemFile]:
        """Translates RawExtractionResult into standardized FilesystemFile instances."""
        files: list[FilesystemFile] = []

        # 1. Cities (/miasta/<city_name>)
        for city in extraction.cities:
            city_slug = to_ascii(city.city_name.lower().strip())
            # Ensure demands keys are ASCII singular nominative
            clean_demands = {
                to_ascii(k.lower().strip()): int(v) for k, v in city.demands.items()
            }
            content_json = json.dumps(clean_demands, ensure_ascii=True)
            files.append(
                FilesystemFile(
                    path=f"/miasta/{city_slug}",
                    content=content_json,
                )
            )

        # 2. Persons (/osoby/<person_name>)
        for person in extraction.coordinators:
            p_name = to_ascii(person.person_name.strip()).replace(" ", "_")
            c_slug = to_ascii(person.city_name.lower().strip())
            display_name = p_name.replace("_", " ")
            city_display = c_slug.capitalize()
            # Requirement: person file contains name and markdown link to city
            content_md = f"{display_name} [{city_display}](/miasta/{c_slug})"
            files.append(
                FilesystemFile(
                    path=f"/osoby/{p_name.lower()}",
                    content=content_md,
                )
            )

        # 3. Commodities (/towary/<commodity>)
        # Group selling cities per commodity
        sellers_by_commodity: dict[str, set[str]] = defaultdict(set)
        for tx in extraction.transactions:
            comm = to_ascii(tx.commodity.lower().strip())
            seller = to_ascii(tx.seller_city.lower().strip())
            sellers_by_commodity[comm].add(seller)

        for comm, sellers in sellers_by_commodity.items():
            sorted_sellers = sorted(sellers)
            links = [f"[{s.capitalize()}](/miasta/{s})" for s in sorted_sellers]
            content_md = "\n".join(links)
            files.append(
                FilesystemFile(
                    path=f"/towary/{comm}",
                    content=content_md,
                )
            )

        logger.info(f"Built {len(files)} virtual filesystem files in total")
        return files
