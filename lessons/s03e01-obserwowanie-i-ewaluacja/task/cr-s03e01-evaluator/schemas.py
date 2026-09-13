from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str = Field(description="Health check status", json_schema_extra={"example": "ok"})
    service: str = Field(description="Service name", json_schema_extra={"example": "cr-s03e01-evaluator"})
    version: str = Field(description="Service version", json_schema_extra={"example": "0.1.0"})


class SensorReading(BaseModel):
    model_config = ConfigDict(strict=True)

    sensor_type: str = Field(
        description="Active sensor or combination of active sensors separated by slash, e.g. 'temperature', 'water', 'voltage/temperature'",
        json_schema_extra={"example": "temperature/voltage"},
    )
    timestamp: int = Field(
        description="Unix timestamp of the reading",
        json_schema_extra={"example": 1774064280},
    )
    temperature_K: Union[float, int] = Field(
        description="Temperature reading in Kelvin",
        json_schema_extra={"example": 612.0},
    )
    pressure_bar: Union[float, int] = Field(
        description="Pressure reading in bar",
        json_schema_extra={"example": 0.0},
    )
    water_level_meters: Union[float, int] = Field(
        description="Water level reading in meters",
        json_schema_extra={"example": 0.0},
    )
    voltage_supply_v: Union[float, int] = Field(
        description="Voltage supply reading in Volts",
        json_schema_extra={"example": 230.4},
    )
    humidity_percent: Union[float, int] = Field(
        description="Humidity reading in percent",
        json_schema_extra={"example": 0.0},
    )
    operator_notes: str = Field(
        description="Human technician note in English",
        json_schema_extra={"example": "Readings look stable and within expected range."},
    )


class OperatorNoteEvaluation(BaseModel):
    reasoning: str = Field(
        description="Concise justification analyzing whether the technician's note claims a malfunction/alarm vs normal operation",
        json_schema_extra={"example": "Operator notes state all values are within nominal parameters."},
    )
    operator_claims_anomaly: bool = Field(
        description="True if the technician explicitly claims or implies an error, failure, malfunction, or alarm. False if claiming normal/nominal status.",
        json_schema_extra={"example": False},
    )


class BatchNoteAnomalyEvaluation(BaseModel):
    anomaly_indices: List[int] = Field(
        description="List of integer indices where the technician claims or implies an anomaly, alarm, malfunction, defect, or error.",
        json_schema_extra={"example": [1936, 1956, 1975]},
    )


class RunTaskRequest(BaseModel):
    backend: Optional[str] = Field(
        default="langchain",
        description="Execution backend framework: 'langchain' or 'genai'",
        json_schema_extra={"example": "langchain"},
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Authoritative session identifier for traceability and auditing",
        json_schema_extra={"example": "s03e01_langchain_20260912_231500"},
    )


class RunTaskResponse(BaseModel):
    status: str = Field(
        description="Overall execution status: 'success' or 'error'",
        json_schema_extra={"example": "success"},
    )
    session_id: str = Field(
        description="Authoritative session identifier",
        json_schema_extra={"example": "s03e01_langchain_20260912_231500"},
    )
    task: str = Field(
        description="Course task name",
        json_schema_extra={"example": "evaluation"},
    )
    total_scanned: int = Field(
        description="Total number of sensor telemetry records processed",
        json_schema_extra={"example": 10000},
    )
    anomalies_found: int = Field(
        description="Total number of anomalous records identified for recheck",
        json_schema_extra={"example": 142},
    )
    recheck: List[str] = Field(
        description="Sorted list of file identifiers containing anomalies submitted to Centrala",
        json_schema_extra={"example": ["0001", "0042", "0105"]},
    )
    verification_response: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw verification response returned from Centrala /verify endpoint",
    )
    flag: Optional[str] = Field(
        default=None,
        description="Extracted course flag if verification succeeded",
        json_schema_extra={"example": "{FLG:...}"},
    )
    hint: Optional[str] = Field(
        default=None,
        description="Optional diagnostic or next-step message",
        json_schema_extra={"example": "Task completed successfully and logged to BigQuery."},
    )
