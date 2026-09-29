from typing import Literal

from pydantic import BaseModel, Field


class CockpitControlsRequest(BaseModel):
    """Command payload to configure physical cockpit controls."""

    session_id: str | None = Field(
        default=None,
        description="Session identifier for audit tracking.",
        examples=["session-20260929-001"],
    )
    pta: bool = Field(
        description="Past transit port switch (True = engaged/connected).",
        examples=[False, True],
    )
    ptb: bool = Field(
        description="Future transit port switch (True = engaged/connected).",
        examples=[True, False],
    )
    pwr: int = Field(
        ge=0,
        le=100,
        description="Radiation shield potentiometer setting (0 - 100).",
        examples=[91, 28, 19],
    )
    mode: Literal["standby", "active"] = Field(
        description="Device operational mode toggle.",
        examples=["active", "standby"],
    )


class CockpitControlsResponse(BaseModel):
    """Response confirming applied cockpit switch positions."""

    success: bool = Field(
        description="Whether controls were applied successfully.",
        examples=[True],
    )
    current_pta: bool = Field(
        description="Current state of PT-A switch.",
        examples=[False],
    )
    current_ptb: bool = Field(
        description="Current state of PT-B switch.",
        examples=[True],
    )
    current_pwr: int = Field(
        description="Current setting of PWR potentiometer.",
        examples=[91],
    )
    current_mode: Literal["standby", "active"] = Field(
        description="Current operational mode.",
        examples=["active"],
    )
    flux_density: int = Field(
        description="Reported core flux density percentage.",
        examples=[100],
    )
    message: str | None = Field(
        default=None,
        description="Optional status or diagnostics message.",
    )


class CockpitTelemetryResponse(BaseModel):
    """Real-time hardware status reported by cockpit instrumentation."""

    flux_density: int = Field(
        description="Current core flux density percentage.",
        examples=[100],
    )
    sync_ratio_display: int = Field(
        description="Reported synchronization ratio percentage on gauge.",
        examples=[82],
    )
    current_imode: int = Field(
        description="Active internalMode oscillation phase (1 to 4).",
        examples=[3],
    )
    battery_status: str = Field(
        description="Battery charge indicator ratio string.",
        examples=["1/3", "3/3"],
    )
    orb_state: str = Field(
        description="Visual state of the central temporal ignition orb.",
        examples=["ready", "danger", "idle"],
    )
    condition_text: str = Field(
        description="Device status banner text from footer.",
        examples=["STAN: DOSKONAŁY // TRYB AKTYWNY"],
    )
    mode: Literal["standby", "active"] = Field(
        description="Active operational state.",
        examples=["active"],
    )
    pta: bool = Field(
        description="State of PT-A port switch.",
        examples=[False],
    )
    ptb: bool = Field(
        description="State of PT-B port switch.",
        examples=[True],
    )
    pwr: int = Field(
        description="Current PWR potentiometer setting.",
        examples=[91],
    )


class ActivateJumpRequest(BaseModel):
    """Command requesting ignition when internalMode reaches the target phase."""

    session_id: str | None = Field(
        default=None,
        description="Session identifier for audit tracking.",
        examples=["session-20260929-001"],
    )
    target_imode: Literal[1, 2, 3, 4] = Field(
        description="Target internalMode phase required for detonation.",
        examples=[3, 2],
    )
    timeout_seconds: float = Field(
        default=25.0,
        ge=5.0,
        le=60.0,
        description="Maximum seconds to wait for phase alignment before timing out.",
        examples=[25.0],
    )


class ActivateJumpResponse(BaseModel):
    """Outcome of temporal ignition trigger."""

    success: bool = Field(
        description="Whether temporal jump or tunnel initiated successfully.",
        examples=[True],
    )
    jump_code: int | None = Field(
        default=None,
        description="Verification response code returned by Central (e.g. 13 for success).",
        examples=[13],
    )
    battery_status: str | None = Field(
        default=None,
        description="Updated battery charge status following displacement.",
        examples=["3/3", "2/3"],
    )
    flag: str | None = Field(
        default=None,
        description="Final mission completion flag if captured.",
        examples=["{FLG:...}"],
    )
    message: str = Field(
        description="Human-readable result summary.",
        examples=["Jump completed successfully. Battery replenished."],
    )
