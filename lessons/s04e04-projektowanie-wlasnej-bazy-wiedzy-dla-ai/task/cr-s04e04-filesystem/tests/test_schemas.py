"""Unit tests for contract-first schemas."""

from schemas import (
    CityDemandExtract,
    CommodityValidationBatchResponse,
    CoordinatorExtract,
    RawExtractionResult,
    RunTaskRequest,
    RunTaskResponse,
    TaskStats,
    TransactionExtract,
    WordEvaluation,
)


def test_city_demand_extract_schema():
    city = CityDemandExtract(
        city_name="opalino",
        demands={"chleb": 45, "woda": 120, "mlotek": 6},
    )
    assert city.city_name == "opalino"
    assert city.demands["chleb"] == 45


def test_coordinator_extract_schema():
    coord = CoordinatorExtract(
        person_name="Iga_Kapecka",
        city_name="opalino",
    )
    assert coord.person_name == "Iga_Kapecka"
    assert coord.city_name == "opalino"


def test_transaction_extract_schema():
    tx = TransactionExtract(
        seller_city="domatowo",
        commodity="chleb",
        buyer_city="opalino",
    )
    assert tx.seller_city == "domatowo"
    assert tx.commodity == "chleb"


def test_raw_extraction_result():
    res = RawExtractionResult(
        cities=[CityDemandExtract(city_name="opalino", demands={"chleb": 45})],
        coordinators=[
            CoordinatorExtract(person_name="Iga_Kapecka", city_name="opalino")
        ],
        transactions=[
            TransactionExtract(
                seller_city="domatowo", commodity="chleb", buyer_city="opalino"
            )
        ],
    )
    assert len(res.cities) == 1
    assert len(res.coordinators) == 1
    assert len(res.transactions) == 1


def test_word_evaluation_schema():
    eval_item = WordEvaluation(
        word="wiertarki",
        is_singular_nominative=False,
        suggested_singular="wiertarka",
        reason="Liczba mnoga",
    )
    assert not eval_item.is_singular_nominative
    assert eval_item.suggested_singular == "wiertarka"

    batch = CommodityValidationBatchResponse(evaluations=[eval_item])
    assert len(batch.evaluations) == 1


def test_run_task_models():
    req = RunTaskRequest(backend="langchain", session_id="s1")
    assert req.backend == "langchain"

    resp = RunTaskResponse(
        status="success",
        backend="langchain",
        flag="{FLG:TEST_FLAG}",
        stats=TaskStats(
            cities_count=8,
            persons_count=8,
            commodities_count=13,
            files_uploaded=29,
        ),
        audit_logged=True,
    )
    assert resp.status == "success"
    assert resp.flag == "{FLG:TEST_FLAG}"
    assert resp.stats.files_uploaded == 29
