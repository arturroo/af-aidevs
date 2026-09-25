import json
import logging
from typing import Any

from schemas import StagedOrderItem, ValidationReport

logger = logging.getLogger("services.validation")


class ValidationService:
    """Pre-Flight Quality Gate service asserting order manifest compliance against food4cities.json."""

    @staticmethod
    def validate_manifest_data(
        manifest_raw: list[dict[str, Any]] | dict[str, Any] | str,
        expected_demands: dict[str, dict[str, int]],
    ) -> ValidationReport:
        """Validates raw or parsed manifest against target municipal resource demands."""
        errors: list[str] = []
        warnings: list[str] = []

        # Parse JSON string if necessary
        parsed_orders: list[Any] = []
        if isinstance(manifest_raw, str):
            try:
                data = json.loads(manifest_raw)
                if (
                    isinstance(data, dict)
                    and "content" in data
                    and isinstance(data["content"], (str, dict, list))
                ):
                    data = (
                        json.loads(data["content"])
                        if isinstance(data["content"], str)
                        else data["content"]
                    )

                if isinstance(data, list):
                    parsed_orders = data
                elif isinstance(data, dict) and "orders" in data:
                    parsed_orders = data["orders"]
                elif isinstance(data, dict):
                    orders_list: list[Any] = []
                    for k, v in data.items():
                        if isinstance(v, dict):
                            orders_list.append({"city": k, **v})
                        elif isinstance(v, str):
                            try:
                                v_dict = json.loads(v)
                                if isinstance(v_dict, dict):
                                    orders_list.append({"city": k, **v_dict})
                            except Exception:
                                pass
                    if orders_list:
                        parsed_orders = orders_list
                    else:
                        parsed_orders = [data]
                else:
                    errors.append(
                        f"Nieprawidlowa struktura manifestu: oczekiwano listy lub obiektu z kluczem 'orders', otrzymano {type(data).__name__}"
                    )
            except Exception as e:
                # If standard json.loads failed, attempt to parse as NDJSON
                ndjson_orders: list[Any] = []
                for line in manifest_raw.splitlines():
                    line = line.strip()
                    if line:
                        try:
                            line_obj = json.loads(line)
                            if isinstance(line_obj, dict):
                                ndjson_orders.append(line_obj)
                        except Exception:
                            pass
                if ndjson_orders:
                    parsed_orders = ndjson_orders
                else:
                    errors.append(f"Blad parsowania JSON manifestu: {e}")
                    return ValidationReport(
                        valid=False,
                        orders_count=0,
                        errors=errors,
                        hint="Popraw skladnie JSON w pliku orders_manifest.json za pomoca write_file.",
                    )
        elif isinstance(manifest_raw, list):
            parsed_orders = manifest_raw
        elif isinstance(manifest_raw, dict) and "orders" in manifest_raw:
            parsed_orders = manifest_raw["orders"]
        elif isinstance(manifest_raw, dict):
            if "content" in manifest_raw and isinstance(
                manifest_raw["content"], (str, dict, list)
            ):
                try:
                    inner_data = (
                        json.loads(manifest_raw["content"])
                        if isinstance(manifest_raw["content"], str)
                        else manifest_raw["content"]
                    )
                    if isinstance(inner_data, list):
                        parsed_orders = inner_data
                    elif isinstance(inner_data, dict) and "orders" in inner_data:
                        parsed_orders = inner_data["orders"]
                    elif isinstance(inner_data, dict):
                        parsed_orders = [
                            {"city": k, **v} if isinstance(v, dict) else v
                            for k, v in inner_data.items()
                        ]
                except Exception:
                    pass
            if not parsed_orders:
                parsed_orders = [
                    {"city": k, **v} if isinstance(v, dict) else v
                    for k, v in manifest_raw.items()
                ]
        else:
            errors.append(
                f"Nieobsługiwany typ danych wejściowych manifestu: {type(manifest_raw).__name__}"
            )
            return ValidationReport(
                valid=False,
                orders_count=0,
                errors=errors,
                hint="Upewnij sie, ze orders_manifest.json jest poprawnym plikiem JSON.",
            )

        # Validate typed model conversion
        staged_items: list[StagedOrderItem] = []
        for idx, item in enumerate(parsed_orders):
            if not isinstance(item, dict):
                errors.append(
                    f"Pozycja [{idx + 1}]: Blad schematu zamowienia (oczekiwano obiektu dict, otrzymano {type(item).__name__})"
                )
                continue
            try:
                # If city not explicitly in item, check if there's key or title
                city_name = str(item.get("city", "")).strip().lower()
                staged = StagedOrderItem(
                    city=city_name,
                    title=str(
                        item.get("title", f"Dostawa dla {city_name.capitalize()}")
                    ),
                    creatorID=int(item.get("creatorID", 0)),
                    destination=str(item.get("destination", "")).strip(),
                    signature=str(item.get("signature", "")).strip(),
                    items=item.get("items", {}),
                )
                staged_items.append(staged)
            except Exception as e:
                errors.append(f"Pozycja [{idx + 1}]: Blad schematu zamowienia ({e})")

        # Cardinality Check
        expected_cities = set(expected_demands.keys())
        manifest_cities = {s.city for s in staged_items if s.city}

        if len(staged_items) != len(expected_cities):
            errors.append(
                f"Nieprawidlowa liczba zamowien: przygotowano {len(staged_items)}, a wymagane jest dokladnie {len(expected_cities)} (miasta: {sorted(expected_cities)})"
            )

        missing_cities = expected_cities - manifest_cities
        if missing_cities:
            errors.append(f"Brakujace zamowienia dla miast: {sorted(missing_cities)}")

        extra_cities = manifest_cities - expected_cities
        if extra_cities:
            errors.append(
                f"Nierozpoznane/nadmiarowe miasta w manifeście: {sorted(extra_cities)}"
            )

        # Field & Commodities Precision Checks
        for item in staged_items:
            city = item.city
            if not city:
                errors.append("Wykryto zamowienie z pusta nazwa miasta.")
                continue

            if not item.destination:
                errors.append(
                    f"{city.capitalize()}: Puste pole 'destination'. Wymagany kod docelowy z bazy SQLite."
                )

            if not item.creatorID or item.creatorID <= 0:
                errors.append(
                    f"{city.capitalize()}: Nieprawidlowy 'creatorID' ({item.creatorID}). Wymagany dodatni identyfikator tworcy z SQLite."
                )

            if not item.signature or len(item.signature) < 10:
                errors.append(
                    f"{city.capitalize()}: Puste lub nieprawidlowe pole 'signature'. Wymagany podpis SHA1 z signatureGenerator."
                )

            if city in expected_demands:
                expected_items = expected_demands[city]
                actual_items = item.items or {}

                # Check missing items
                for expected_k, expected_v in expected_items.items():
                    if expected_k not in actual_items:
                        errors.append(
                            f"{city.capitalize()}: Brak wymaganej pozycji towarowej '{expected_k}' (wymagane: {expected_v})."
                        )
                    elif actual_items[expected_k] != expected_v:
                        errors.append(
                            f"{city.capitalize()}: Niezgodna ilosc towaru '{expected_k}' - zadeklarowano {actual_items[expected_k]}, wymagane dokladnie {expected_v} (Bez brakow i bez nadmiarow)."
                        )

                # Check extra items
                for actual_k in actual_items:
                    if actual_k not in expected_items:
                        errors.append(
                            f"{city.capitalize()}: Nadmiarowy towar '{actual_k}' (ilosc: {actual_items[actual_k]}), nieobecny w zapotrzebowaniu miasta."
                        )

        is_valid = len(errors) == 0
        hint = (
            "Manifest jest w 100% poprawny. Mozesz bezpiecznie wywolac dispatch_staged_orders."
            if is_valid
            else "Wykryto niezgodnosci w manifestu. Skoryguj wskazane pola w pliku orders_manifest.json za pomoca write_file i uruchom validate_staged_orders ponownie."
        )

        logger.info(
            f"Manifest validation outcome: valid={is_valid}, errors={len(errors)}"
        )
        return ValidationReport(
            valid=is_valid,
            orders_count=len(staged_items),
            errors=errors,
            warnings=warnings,
            hint=hint,
        )
