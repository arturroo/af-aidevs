from schemas import (
    CandidateEntities,
    CentralaEnvelope,
    CentralaTransmitPayload,
    ObjectFinding,
    RunTaskRequest,
    SecretClues,
)


def test_centrala_envelope_serialization():
    payload = CentralaTransmitPayload(
        action="transmit",
        cityName="Opalino",
        cityArea="14.85",
        warehousesCount=12,
        phoneNumber="555-0192",
    )
    env = CentralaEnvelope(
        apikey="test-key",
        task="radiomonitoring",
        answer=payload,
    )
    dumped = env.model_dump()
    assert dumped["apikey"] == "test-key"
    assert dumped["task"] == "radiomonitoring"
    assert dumped["answer"]["action"] == "transmit"
    assert dumped["answer"]["cityName"] == "Opalino"
    assert dumped["answer"]["cityArea"] == "14.85"


def test_object_finding_contract():
    finding = ObjectFinding(
        source_file="/decoded/packet_001.txt",
        mime_type="text/plain",
        summary_sentences=[
            "Interception of radio signal from Domatowo outpost.",
            "Mentions safe haven coordinates and 12 food warehouses.",
            "Contact number for Syjon outpost is 555-0192.",
        ],
        schema_or_structure={"sections": ["Section 1"]},
        candidate_entities=CandidateEntities(
            city_names=["Opalino", "Syjon"],
            city_area="14.85",
            warehouses_count=12,
            phone_numbers=["555-0192"],
        ),
        secret_clues=SecretClues(
            telegraphist_mentions=True,
            morse_detected=True,
            raw_clue="··−· ·−·· ·− −−· ·−",
            extracted_key="FLAGA",
        ),
        confidence=0.98,
        reasoning="High confidence transcript",
    )
    json_str = finding.model_dump_json()
    reloaded = ObjectFinding.model_validate_json(json_str)
    assert reloaded.source_file == "/decoded/packet_001.txt"
    assert reloaded.candidate_entities.warehouses_count == 12
    assert reloaded.secret_clues.extracted_key == "FLAGA"


def test_run_task_request_defaults():
    req = RunTaskRequest()
    assert req.backend == "langchain"
    assert req.model is None
    assert req.thinking_level is None
