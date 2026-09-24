"""Deterministic pre-flight quality gate and contract guard service."""

import json
import logging
import re

from schemas import FilesystemFile, ValidationReport, ValidationViolation
from services.linguistic_service import LinguisticService

logger = logging.getLogger("services.validation")

ASCII_PATTERN = re.compile(r"^[\x00-\x7F]+$")
MD_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\((/miasta/[a-z0-9_]+)\)")
CENTRALA_NAME_PATTERN = re.compile(r"^[a-z0-9_]+$")


class ValidationService:
    """Validates virtual filesystem files against hard syntax, schemas, referential links, and morphology."""

    def __init__(self, linguistic_service: LinguisticService | None = None):
        self.linguistic = linguistic_service or LinguisticService()

    async def validate_filesystem(
        self, files: list[FilesystemFile], skip_linguistic: bool = False
    ) -> ValidationReport:
        """Runs the complete three-phase pre-flight quality gate on a list of FilesystemFile instances."""
        violations: list[ValidationViolation] = []
        errors: list[str] = []

        files_by_path = {f.path: f for f in files}

        cities: set[str] = set()
        persons: set[str] = set()
        commodities: set[str] = set()

        # Categorize and check path structure
        for f in files:
            p = f.path
            parts = p.strip("/").split("/")
            if len(parts) == 2:
                _, filename = parts[0], parts[1]
                if not CENTRALA_NAME_PATTERN.match(filename):
                    msg = f"Nazwa pliku '{filename}' w '{p}' nie spelnia wymogu Centrali ^[a-z0-9_]+$ (dozwolone tylko male litery, cyfry i podkreslenia)."
                    violations.append(
                        ValidationViolation(
                            path=p, rule="CENTRALA_NAME_PATTERN", message=msg
                        )
                    )
                    errors.append(msg)
                if len(filename) > 20:
                    msg = f"Nazwa pliku '{filename}' w '{p}' przekracza maksymalna dlugosc 20 znakow."
                    violations.append(
                        ValidationViolation(path=p, rule="MAX_NAME_LENGTH", message=msg)
                    )
                    errors.append(msg)

            if p.startswith("/miasta/"):
                city_slug = p.replace("/miasta/", "").strip()
                cities.add(city_slug)
            elif p.startswith("/osoby/"):
                person_slug = p.replace("/osoby/", "").strip()
                persons.add(person_slug)
            elif p.startswith("/towary/"):
                comm_slug = p.replace("/towary/", "").strip()
                commodities.add(comm_slug)
            else:
                msg = f"Nieprawidlowy katalog glowny w sciezce: '{p}'. Dozwolone: /miasta/, /osoby/, /towary/."
                violations.append(
                    ValidationViolation(path=p, rule="DIRECTORY_STRUCTURE", message=msg)
                )
                errors.append(msg)

        # 1. ASCII Invariant check across all files and contents
        for f in files:
            if not ASCII_PATTERN.match(f.path):
                msg = f"Sciezka '{f.path}' zawiera niedozwolone znaki spoza ASCII (np. polskie ogonki)."
                violations.append(
                    ValidationViolation(path=f.path, rule="ASCII_PURITY", message=msg)
                )
                errors.append(msg)

            if not ASCII_PATTERN.match(f.content):
                msg = f"Zawartosc pliku '{f.path}' zawiera znaki spoza ASCII."
                violations.append(
                    ValidationViolation(path=f.path, rule="ASCII_PURITY", message=msg)
                )
                errors.append(msg)

        # 2. JSON contract check on /miasta/*
        for city_slug in cities:
            path = f"/miasta/{city_slug}"
            file_obj = files_by_path[path]
            try:
                data = json.loads(file_obj.content)
                if not isinstance(data, dict):
                    raise TypeError(
                        "JSON w /miasta musi byc obiektem slownikowym (dict)."
                    )
                for k, v in data.items():
                    if not isinstance(k, str) or not k:
                        msg = f"Nieprawidlowy klucz towaru w {path}: '{k}'."
                        violations.append(
                            ValidationViolation(
                                path=path, rule="JSON_SCHEMA", message=msg
                            )
                        )
                        errors.append(msg)
                    if not isinstance(v, int) or v <= 0:
                        msg = f"Wartosc zapotrzebowania dla towaru '{k}' w {path} musi byc liczba calkowita > 0 (bez jednostek miar), otrzymano: {v}."
                        violations.append(
                            ValidationViolation(
                                path=path, rule="JSON_SCHEMA", message=msg
                            )
                        )
                        errors.append(msg)
            except Exception as e:
                msg = f"Blad parsowania JSON w {path}: {e}"
                violations.append(
                    ValidationViolation(path=path, rule="JSON_SCHEMA", message=msg)
                )
                errors.append(msg)

        # 3. Markdown link checks on /osoby/*
        for person_slug in persons:
            path = f"/osoby/{person_slug}"
            content = files_by_path[path].content
            links = MD_LINK_PATTERN.findall(content)
            if not links:
                msg = f"Plik {path} nie zawiera wymaganego linku Markdown do miasta w formacie [Nazwa](/miasta/slug)."
                violations.append(
                    ValidationViolation(
                        path=path, rule="MARKDOWN_LINK_SYNTAX", message=msg
                    )
                )
                errors.append(msg)
            else:
                for display_name, city_target in links:
                    target_city_slug = city_target.replace("/miasta/", "")
                    if target_city_slug not in cities:
                        msg = f"Integralnosc referencyjna zerwana w {path}: link '{city_target}' wskazuje na nieistniejacy plik miasta."
                        violations.append(
                            ValidationViolation(
                                path=path, rule="REFERENTIAL_INTEGRITY", message=msg
                            )
                        )
                        errors.append(msg)

        # 4. Markdown link checks on /towary/*
        for comm_slug in commodities:
            path = f"/towary/{comm_slug}"
            content = files_by_path[path].content
            links = MD_LINK_PATTERN.findall(content)
            if not links:
                msg = f"Plik {path} nie zawiera linku Markdown do oferujacego miasta."
                violations.append(
                    ValidationViolation(
                        path=path, rule="MARKDOWN_LINK_SYNTAX", message=msg
                    )
                )
                errors.append(msg)
            else:
                for display_name, city_target in links:
                    target_city_slug = city_target.replace("/miasta/", "")
                    if target_city_slug not in cities:
                        msg = f"Integralnosc referencyjna zerwana w {path}: link '{city_target}' wskazuje na nieistniejace miasto."
                        violations.append(
                            ValidationViolation(
                                path=path, rule="REFERENTIAL_INTEGRITY", message=msg
                            )
                        )
                        errors.append(msg)

        # 5. Completeness checks
        if len(cities) < 8:
            msg = f"Niekompletna liczba miast: znaleziono {len(cities)} z 8 wymaganych."
            violations.append(
                ValidationViolation(path="/miasta", rule="COMPLETENESS", message=msg)
            )
            errors.append(msg)

        if len(persons) < 8:
            msg = f"Niekompletna liczba koordynatorow: znaleziono {len(persons)} z 8 wymaganych."
            violations.append(
                ValidationViolation(path="/osoby", rule="COMPLETENESS", message=msg)
            )
            errors.append(msg)

        # 6. Linguistic evaluation of commodities
        if not skip_linguistic and commodities:
            try:
                ling_resp = await self.linguistic.validate_commodities(
                    list(commodities)
                )
                for ev in ling_resp.evaluations:
                    if not ev.is_singular_nominative:
                        path = f"/towary/{ev.word}"
                        msg = f"Towar '{ev.word}' nie jest w mianowniku liczby pojedynczej: {ev.reason}. Uzyj: '{ev.suggested_singular}'."
                        violations.append(
                            ValidationViolation(
                                path=path,
                                rule="SINGULAR_NOMINATIVE",
                                message=msg,
                                suggestion=ev.suggested_singular,
                            )
                        )
                        errors.append(msg)
            except Exception as e:
                logger.warning(f"Linguistic subagent check error: {e}")

        # Per-file log reporting
        violations_by_path: dict[str, list[ValidationViolation]] = {}
        for v in violations:
            violations_by_path.setdefault(v.path, []).append(v)

        for idx, f in enumerate(files):
            file_viols = violations_by_path.get(f.path, [])
            if file_viols:
                for v in file_viols:
                    logger.warning(
                        f"Validation [FAIL] [{idx + 1}/{len(files)}] for '{f.path}' ({v.rule}): {v.message}"
                    )
            else:
                logger.info(
                    f"Validation [PASS] [{idx + 1}/{len(files)}] for '{f.path}'"
                )

        if len(cities) < 8 or len(persons) < 8:
            logger.warning(
                f"Completeness check [FAIL]: cities={len(cities)}/8, persons={len(persons)}/8"
            )
        else:
            logger.info(
                f"Completeness check [PASS]: cities={len(cities)}, persons={len(persons)}, commodities={len(commodities)}"
            )

        is_valid = len(errors) == 0
        hint = None
        if not is_valid:
            hint = (
                "Zapisz powyzsze bledy jako liste zadan w TODOs.md uzywajac narzedzia write_file. "
                "Nastepnie popraw wskazane pliki uzywajac narzedzia write_file, a po ukonczeniu wszystkich "
                "poprawek wywolaj validate_all_files ponownie, aby potwierdzic spojnosc przed wysylka."
            )

        report = ValidationReport(
            valid=is_valid,
            total_files=len(files),
            cities_count=len(cities),
            persons_count=len(persons),
            commodities_count=len(commodities),
            errors=errors,
            violations=violations,
            hint=hint,
        )
        logger.info(
            f"Validation summary: valid={report.valid}, files={report.total_files}, errors={len(report.errors)}"
        )
        return report
