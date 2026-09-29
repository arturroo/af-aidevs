import os

from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Runtime configuration for CHRONOS-P1 Cockpit Actuator."""

    AIDEVS_API_KEY: str = Field(
        default_factory=lambda: os.getenv("AIDEVS_API_KEY") or ""
    )
    AIDEVS_TIMETRAVEL_PREVIEW_URL: str = Field(
        default_factory=lambda: (
            os.getenv("AIDEVS_TIMETRAVEL_PREVIEW_URL")
            or "https://hub.ag3nts.org/timetravel_preview"
        )
    )
    AIDEVS_TIMETRAVEL_BACKEND_URL: str = Field(
        default_factory=lambda: (
            os.getenv("AIDEVS_TIMETRAVEL_BACKEND_URL")
            or "https://hub.ag3nts.org/timetravel_backend"
        )
    )
    AIDEVS_API_VERIFY: str = Field(
        default_factory=lambda: (
            os.getenv("AIDEVS_API_VERIFY")
            or os.getenv("AIDEVS_VERIFY")
            or "https://hub.ag3nts.org/verify"
        )
    )
    HEADLESS: bool = Field(
        default_factory=lambda: (
            (os.getenv("HEADLESS") or "true").lower() in ("true", "1", "yes")
        )
    )


settings = Settings()
