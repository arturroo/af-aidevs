import io
import json
import zipfile
import pytest
from fastapi.testclient import TestClient

from main import app
from schemas import SensorReading
from services.sensor_service import SensorService


def test_health_endpoints():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "cr-s03e01-evaluator"

    root_resp = client.get("/")
    assert root_resp.status_code == 200
    assert root_resp.json()["task"] == "evaluation"
    assert root_resp.json()["status"] == "ready"


def test_sensor_physical_validation():
    # 1. Nominal temperature reading
    reading_ok = SensorReading(
        sensor_type="temperature",
        timestamp=1774064280,
        temperature_K=600.0,
        pressure_bar=0.0,
        water_level_meters=0.0,
        voltage_supply_v=0.0,
        humidity_percent=0.0,
        operator_notes="Readings look stable and nominal.",
    )
    is_anomaly, reason = SensorService.audit_single_record(reading_ok)
    assert not is_anomaly
    assert reason == "OK"

    # 2. Temperature reading out of bounds (950K > 873K)
    reading_too_hot = SensorReading(
        sensor_type="temperature",
        timestamp=1774064280,
        temperature_K=950.0,
        pressure_bar=0.0,
        water_level_meters=0.0,
        voltage_supply_v=0.0,
        humidity_percent=0.0,
        operator_notes="High temperature detected.",
    )
    is_anomaly, reason = SensorService.audit_single_record(reading_too_hot)
    assert is_anomaly
    assert "out of bounds" in reason

    # 3. Ghost reading on inactive voltage channel
    reading_ghost = SensorReading(
        sensor_type="temperature",
        timestamp=1774064280,
        temperature_K=650.0,
        pressure_bar=0.0,
        water_level_meters=0.0,
        voltage_supply_v=230.0,  # inactive channel returning voltage!
        humidity_percent=0.0,
        operator_notes="Everything fine.",
    )
    is_anomaly, reason = SensorService.audit_single_record(reading_ghost)
    assert is_anomaly
    assert "ghost reading" in reason

    # 4. Multi-sensor active combination (temperature/voltage)
    reading_multi = SensorReading(
        sensor_type="temperature/voltage",
        timestamp=1774064280,
        temperature_K=700.0,
        pressure_bar=0.0,
        water_level_meters=0.0,
        voltage_supply_v=230.5,
        humidity_percent=0.0,
        operator_notes="Dual check completed.",
    )
    is_anomaly, reason = SensorService.audit_single_record(reading_multi)
    assert not is_anomaly


def test_process_zip_archive_in_memory():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        record_1 = {
            "sensor_type": "temperature",
            "timestamp": 1774064280,
            "temperature_K": 600.0,
            "pressure_bar": 0.0,
            "water_level_meters": 0.0,
            "voltage_supply_v": 0.0,
            "humidity_percent": 0.0,
            "operator_notes": "Readings look stable.",
        }
        record_2 = {
            "sensor_type": "pressure",
            "timestamp": 1774064281,
            "temperature_K": 0.0,
            "pressure_bar": 200.0,  # out of bounds [60, 160]
            "water_level_meters": 0.0,
            "voltage_supply_v": 0.0,
            "humidity_percent": 0.0,
            "operator_notes": "Pressure high.",
        }
        record_3 = {
            "sensor_type": "water",
            "timestamp": 1774064282,
            "temperature_K": 100.0,  # ghost reading
            "pressure_bar": 0.0,
            "water_level_meters": 10.0,
            "voltage_supply_v": 0.0,
            "humidity_percent": 0.0,
            "operator_notes": "Readings look stable.",
        }

        zf.writestr("0001.json", json.dumps(record_1))
        zf.writestr("0002.json", json.dumps(record_2))
        zf.writestr("0003.json", json.dumps(record_3))

    zip_bytes = buffer.getvalue()
    total_scanned, physical_anomalies, note_to_clean, clean_records = SensorService.process_zip_archive(zip_bytes)

    assert total_scanned == 3
    assert sorted(physical_anomalies) == ["0002", "0003"]
    assert "Readings look stable." in note_to_clean
    assert note_to_clean["Readings look stable."] == ["0001"]
    assert len(clean_records) == 1
