from typing import Literal


def compute_sync_ratio(year: int, month: int, day: int) -> float:
    """Computes decimal temporal synchronization ratio according to ACME specifications.

    Formula:
      raw = (day * 8 + month * 12 + year * 7) % 101
      syncRatio = raw / 100.0  (range 0.00 to 1.00)
    """
    raw_sync = (day * 8 + month * 12 + year * 7) % 101
    return round(raw_sync / 100.0, 2)


def get_target_internal_mode(year: int) -> Literal[1, 2, 3, 4]:
    """Resolves required hardware internalMode phase from target year.

    1: year < 2000
    2: 2000 <= year <= 2150
    3: 2151 <= year <= 2300
    4: year >= 2301
    """
    if year < 2000:
        return 1
    elif 2000 <= year <= 2150:
        return 2
    elif 2151 <= year <= 2300:
        return 3
    else:
        return 4


def parse_date_string(date_str: str) -> tuple[int, int, int]:
    """Parses standard ISO date string YYYY-MM-DD into (year, month, day)."""
    parts = date_str.strip().split("-")
    if len(parts) != 3:
        raise ValueError(f"Invalid date format: '{date_str}'. Expected 'YYYY-MM-DD'.")
    return int(parts[0]), int(parts[1]), int(parts[2])
