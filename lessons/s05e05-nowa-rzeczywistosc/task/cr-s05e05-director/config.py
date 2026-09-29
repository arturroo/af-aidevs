import os
from typing import Literal, cast

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Runtime configuration for CHRONOS-P1 Temporal Flight Director."""

    AIDEVS_API_KEY: str = Field(
        default_factory=lambda: os.getenv("AIDEVS_API_KEY") or ""
    )
    AIDEVS_API_VERIFY: str = Field(
        default_factory=lambda: (
            os.getenv("AIDEVS_API_VERIFY")
            or os.getenv("AIDEVS_VERIFY")
            or "https://hub.ag3nts.org/verify"
        )
    )
    COCKPIT_SERVICE_URL: str = Field(
        default_factory=lambda: (
            os.getenv("COCKPIT_SERVICE_URL") or "http://localhost:8081"
        ).strip()
    )
    GEMINI_MODEL: str = Field(
        default_factory=lambda: os.getenv("GEMINI_MODEL") or "gemini-3.5-flash-lite"
    )
    THINKING_LEVEL: Literal["low", "medium", "high"] = Field(
        default_factory=lambda: cast(
            Literal["low", "medium", "high"],
            os.getenv("THINKING_LEVEL") or "low",
        )
    )
    GOOGLE_CLOUD_PROJECT: str = Field(
        default_factory=lambda: os.getenv("GOOGLE_CLOUD_PROJECT") or "af-aidevs"
    )
    GOOGLE_CLOUD_LOCATION: str = Field(
        default_factory=lambda: os.getenv("GOOGLE_CLOUD_LOCATION") or "global"
    )
    BIGQUERY_DATASET: str = Field(
        default_factory=lambda: os.getenv("BIGQUERY_DATASET") or "s05e05"
    )
    BIGQUERY_TABLE: str = Field(
        default_factory=lambda: os.getenv("BIGQUERY_TABLE") or "audit"
    )


settings = Settings()
