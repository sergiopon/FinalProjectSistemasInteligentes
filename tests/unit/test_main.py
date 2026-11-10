from __future__ import annotations

import ast
import logging
import re
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.domain.errors import (
    AppError,
    CsvFormatError,
    InferenceError,
    InvalidInputError,
    ModelIntegrityError,
    ModelUnavailableError,
    NotFoundError,
    PayloadTooLargeError,
    UnsafePathError,
    UnsupportedMediaTypeError,
)
from api.main import (
    CLIENT_ERRORS,
    SECURITY_HEADERS,
    _float_tuple,
    _read_reference,
    _terms_tuple,
    _vocabulary,
    build_app,
)
from api.routes import Services
from tests.fixtures.fake_ports import RaisingPolarityModel, make_services

MAIN_PATH = Path(__file__).resolve().parents[2] / "api" / "main.py"
PREDICT_BODY = {"text": "Buen curso."}


def client_for(services: Services, tmp_path: Path) -> TestClient:
    web = tmp_path / "web"
    web.mkdir(exist_ok=True)
    (web / "index.html").write_text("<p>synthetic</p>", encoding="utf-8")
    return TestClient(build_app(lambda: services, web))


def raising_client(error: Exception, tmp_path: Path) -> Iterator[TestClient]:
    with client_for(make_services(RaisingPolarityModel(error)), tmp_path) as client:
        yield client


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with client_for(make_services(), tmp_path) as test_client:
        yield test_client


def test_main_umask_and_offline_first() -> None:
    body = ast.parse(MAIN_PATH.read_text(encoding="utf-8")).body
    assert isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
    assert isinstance(body[1], ast.ImportFrom) and body[1].module == "__future__"
    assert isinstance(body[2], ast.Import) and body[2].names[0].name == "os"
    assert ast.unparse(body[3]) == "os.umask(63)"  # 0o077
    assert ast.unparse(body[4]) == "os.environ['HF_HUB_OFFLINE'] = '1'"
    assert ast.unparse(body[5]) == "os.environ['TRANSFORMERS_OFFLINE'] = '1'"


def test_main_offline_env_set() -> None:
    import os

    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"


def test_main_request_id_header(client: TestClient) -> None:
    first = client.get("/health", headers={"X-Request-ID": "abc"}).headers["X-Request-ID"]
    second = client.get("/health", headers={"X-Request-ID": "abc"}).headers["X-Request-ID"]
    assert re.fullmatch(r"[0-9a-f]{32}", first)
    assert re.fullmatch(r"[0-9a-f]{32}", second)
    assert len({"abc", first, second}) == 3


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (InvalidInputError("x"), 422, "invalid_input"),
        (CsvFormatError("x"), 422, "invalid_csv"),
        (PayloadTooLargeError("x"), 413, "payload_too_large"),
        (UnsupportedMediaTypeError("x"), 415, "unsupported_media_type"),
        (NotFoundError("x"), 404, "not_found"),
        (ModelUnavailableError("x"), 503, "model_unavailable"),
        (InferenceError("x"), 500, "internal_error"),
        (UnsafePathError("x"), 500, "internal_error"),
    ],
)
def test_main_app_error_mapping(error: AppError, status: int, code: str, tmp_path: Path) -> None:
    for client in raising_client(error, tmp_path):
        response = client.post("/predict", json=PREDICT_BODY)
        assert response.status_code == status
        assert response.json() == {
            "error": code,
            "message": CLIENT_ERRORS[code][1],
            "request_id": response.headers["X-Request-ID"],
        }


def test_main_unhandled_error_generic(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    error = RuntimeError("Ana Gómez ana@uni.edu.co")
    for client in raising_client(error, tmp_path):
        with caplog.at_level(logging.INFO):
            response = client.post("/predict", json=PREDICT_BODY)
    assert response.status_code == 500
    assert response.json() == {
        "error": "internal_error",
        "message": "Internal error.",
        "request_id": response.headers["X-Request-ID"],
    }
    for forbidden in ("Ana", "Traceback", "RuntimeError"):
        assert forbidden not in response.text
    errors = [r for r in caplog.records if r.levelno == logging.ERROR and r.name == "api.main"]
    assert len(errors) == 1
    assert errors[0].getMessage().startswith("unhandled_error request_id=")


def test_main_not_found_and_method(client: TestClient) -> None:
    missing = client.get("/nope")
    assert missing.status_code == 404
    assert missing.json()["error"] == "not_found"
    wrong = client.delete("/predict")
    assert wrong.status_code == 405
    assert wrong.json()["error"] == "method_not_allowed"
    assert wrong.json()["message"] == "Method not allowed."


def test_main_static_index(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert response.text == "<p>synthetic</p>"


def test_main_security_headers(tmp_path: Path, client: TestClient) -> None:
    responses = [client.get("/"), client.get("/health"), client.get("/nope")]
    for error_client in raising_client(RuntimeError("boom"), tmp_path):
        responses.append(error_client.post("/predict", json=PREDICT_BODY))
    assert responses[-1].status_code == 500
    for response in responses:
        for name, value in SECURITY_HEADERS.items():
            assert response.headers[name] == value
    for path in ("/docs", "/openapi.json"):
        response = client.get(path)
        assert response.status_code == 404
        assert response.json()["error"] == "not_found"


def test_main_static_missing_dir(tmp_path: Path) -> None:
    app = build_app(lambda: make_services(), tmp_path / "absent")
    with TestClient(app) as client:
        response = client.get("/")
    assert response.status_code == 500
    assert response.json()["error"] == "internal_error"


def test_main_startup_failure(tmp_path: Path) -> None:
    def failing() -> Services:
        raise ModelIntegrityError("hash mismatch")

    with pytest.raises(ModelIntegrityError), TestClient(build_app(failing, tmp_path)):
        pass


def test_main_float_tuple() -> None:
    assert _float_tuple((0.5, 0.25), "aspect_thresholds") == (0.5, 0.25)
    for bad in ([0.5], (0.5, "x")):
        with pytest.raises(ModelIntegrityError) as raised:
            _float_tuple(bad, "aspect_thresholds")
        assert raised.value.detail == "bundle key aspect_thresholds has an invalid type"


def test_main_terms_tuple() -> None:
    assert _terms_tuple((("a", "b"),)) == (("a", "b"),)
    with pytest.raises(ModelIntegrityError):
        _terms_tuple((("a", 1),))


def test_main_vocabulary() -> None:
    assert _vocabulary(SimpleNamespace(vocabulary_={"curso": 0})) == frozenset({"curso"})
    with pytest.raises(ModelIntegrityError):
        _vocabulary(object())


def test_main_read_reference(tmp_path: Path) -> None:
    folder = tmp_path / "v001"
    folder.mkdir()
    target = folder / "reference_stats.json"
    target.write_text('{"length_edges": []}', encoding="utf-8")
    assert _read_reference(tmp_path, "v001") == {"length_edges": []}
    for content, detail in (
        ("[1]", "reference stats are not an object"),
        ("{bad", "reference stats unreadable"),
    ):
        target.write_text(content, encoding="utf-8")
        with pytest.raises(ModelIntegrityError) as raised:
            _read_reference(tmp_path, "v001")
        assert raised.value.detail == detail
    target.unlink()
    with pytest.raises(ModelIntegrityError) as missing:
        _read_reference(tmp_path, "v001")
    assert missing.value.detail == "reference stats unreadable"
