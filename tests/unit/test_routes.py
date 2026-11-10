from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.adapters.http_schemas import ModelInfoJson
from api.main import build_app
from api.routes import Services
from tests.fixtures.fake_ports import C1_TEXT, make_services

CSV = (
    "﻿id,curso,feedback\nid,curso,feedback\n1,Redes,Ana dio buen contenido.\n2,Redes,Buen curso.\n"
).encode()
CSV_HEADERS = {"Content-Type": "text/csv; charset=utf-8"}


def client_for(services: Services, tmp_path: Path) -> TestClient:
    web = tmp_path / "web"
    web.mkdir(exist_ok=True)
    (web / "index.html").write_text("<p>synthetic</p>", encoding="utf-8")
    return TestClient(build_app(lambda: services, web))


@pytest.fixture
def services() -> Services:
    return make_services()


@pytest.fixture
def client(services: Services, tmp_path: Path) -> Iterator[TestClient]:
    with client_for(services, tmp_path) as test_client:
        yield test_client


def test_routes_health(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok", "model_version": "v001"}


def test_routes_model(client: TestClient) -> None:
    response = client.get("/model")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "v001"
    assert set(body) == set(ModelInfoJson.model_fields)


def test_routes_predict(client: TestClient) -> None:
    response = client.post("/predict", json={"text": C1_TEXT})
    body = response.json()
    assert response.status_code == 200
    assert body["text"] == C1_TEXT
    assert body["predicted"] == "neutral"
    assert body["decision"] == "review"
    assert body["reason"] == "set_not_singleton"
    assert body["conformal_set"] == ["negative", "neutral"]


def test_routes_predict_rejects(client: TestClient) -> None:
    plain = client.post(
        "/predict", content=b'{"text": "a"}', headers={"Content-Type": "text/plain"}
    )
    assert plain.status_code == 415
    json_type = {"Content-Type": "application/json"}
    for body in (b"{bad", b'{"text": "a", "x": 1}', b'{"text": "   "}'):
        response = client.post("/predict", content=body, headers=json_type)
        assert response.status_code == 422
        assert response.json()["error"] == "invalid_input"


def test_routes_predict_batch(client: TestClient) -> None:
    response = client.post("/predict-batch", content=CSV, headers=CSV_HEADERS)
    body = response.json()
    assert response.status_code == 200
    assert body["row_count"] == 2
    assert body["rows"][0]["text"] == "[PERSON] dio buen contenido."
    assert body["rows"][0]["row"] == 1
    assert body["courses"][0]["course"] == "Redes"
    assert len(body["courses"][0]["aspects"]) == 9


def test_routes_predict_batch_rejects(tmp_path: Path) -> None:
    with client_for(make_services(max_upload_bytes=64), tmp_path) as small:
        big = small.post("/predict-batch", content=CSV, headers=CSV_HEADERS)
        assert big.status_code == 413
        assert big.json()["error"] == "payload_too_large"
    with client_for(make_services(), tmp_path) as normal:
        plain = normal.post("/predict-batch", content=b"x", headers={"Content-Type": "text/plain"})
        assert plain.status_code == 415
        bad = normal.post(
            "/predict-batch", content=b"curso,texto\nRedes,hola\n", headers=CSV_HEADERS
        )
        assert bad.status_code == 422
        assert bad.json()["error"] == "invalid_csv"


def test_routes_drift(client: TestClient) -> None:
    response = client.post("/drift", content=CSV, headers=CSV_HEADERS)
    body = response.json()
    assert response.status_code == 200
    assert body["body_sha256"] == hashlib.sha256(CSV).hexdigest()
    assert body["created_at"] == "2026-11-05T12:00:00Z"
    assert body["row_count"] == 2
    assert client.get("/metrics").json()["last_drift"] is not None


def test_routes_metrics_records(client: TestClient) -> None:
    client.post("/predict", json={"text": "Buen curso."})
    client.post("/predict-batch", content=CSV, headers=CSV_HEADERS)
    client.post("/drift", content=CSV, headers=CSV_HEADERS)
    body = client.get("/metrics").json()
    assert body["request_count"] == 2
    assert body["decisions"] == {"classify": 3, "review": 0}


def test_routes_logs_hold_no_text(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        client.post("/predict", json={"text": "Ana Gómez secreto"})
    messages = [record.getMessage() for record in caplog.records]
    assert messages
    assert not any("Ana" in message or "secreto" in message for message in messages)
