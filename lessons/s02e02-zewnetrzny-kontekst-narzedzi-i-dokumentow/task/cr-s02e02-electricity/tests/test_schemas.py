import pytest
from af_aidevs.schemas.common import AgentResponseEnvelope
from af_aidevs.schemas.vision import GridCircuitSolverData, VisionInspectRequest
from schemas import RotatePayload, SolverResult


def test_schema_serialization():
    """Verify that Generic AgentResponseEnvelope serializes and validates correctly."""
    data = GridCircuitSolverData(
        rotations=[[0, 1, 0], [2, 0, 3], [0, 0, 1]],
        confidence=0.98,
        tile_confidence=[[1.0, 1.0, 1.0], [1.0, 1.0, 0.95], [1.0, 1.0, 1.0]],
    )
    envelope = AgentResponseEnvelope[GridCircuitSolverData](
        status="success",
        reasoning="Test reasoning for audit trail",
        data=data,
    )

    json_dict = envelope.model_dump()
    assert json_dict["status"] == "success"
    assert json_dict["data"]["rotations"][1][0] == 2
    assert json_dict["data"]["confidence"] == 0.98

    # Test roundtrip
    restored = AgentResponseEnvelope[GridCircuitSolverData].model_validate(json_dict)
    assert restored.data.rotations == data.rotations


def test_rotate_payload():
    """Verify course API rotation payload format."""
    payload = RotatePayload(
        apikey="secret-key",
        task="electricity",
        answer={"rotate": "2x3"},
    )
    dumped = payload.model_dump()
    assert dumped["apikey"] == "secret-key"
    assert dumped["answer"]["rotate"] == "2x3"
