from __future__ import annotations

import json
from collections import Counter

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from api.domain.errors import InferenceError, InvalidInputError
from scripts import benchmark
from scripts.benchmark import batch_body, measure, percentile, run_benchmark, summarize

EXPECTED_BODY = (
    b"feedback,curso\n"
    b"El contenido del curso fue claro y ordenado.,Curso de prueba\n"
    b"Los parciales fueron muy dif\xc3\xadciles para el tiempo disponible.,Curso de prueba\n"
)


class Stub:
    def __init__(self, health_status: int = 200, predict_status: int = 200) -> None:
        self.calls: Counter[str] = Counter()
        self.content_types: dict[str, set[str]] = {}
        self.app = self._build(health_status, predict_status)

    def _record(self, request: Request) -> None:
        path = request.url.path
        self.calls[path] += 1
        self.content_types.setdefault(path, set()).add(request.headers["content-type"])

    def _build(self, health_status: int, predict_status: int) -> FastAPI:
        app = FastAPI()

        @app.get("/health")
        def health() -> JSONResponse:
            return JSONResponse(
                {"status": "ok", "model_version": "v009"}, status_code=health_status
            )

        @app.post("/predict")
        async def predict(request: Request) -> JSONResponse:
            self._record(request)
            return JSONResponse({}, status_code=predict_status)

        @app.post("/predict-batch")
        async def predict_batch(request: Request) -> JSONResponse:
            self._record(request)
            return JSONResponse({})

        return app


def test_percentile_nearest_rank() -> None:
    twenty = tuple(float(i) for i in range(1, 21))
    assert percentile(twenty, 50) == 10.0
    assert percentile(twenty, 95) == 19.0
    assert percentile((3.0, 1.0, 2.0), 50) == 2.0
    assert percentile((3.0, 1.0, 2.0), 95) == 3.0
    assert percentile((7.5,), 50) == 7.5
    assert percentile((7.5,), 95) == 7.5


def test_percentile_rejects_empty() -> None:
    with pytest.raises(InvalidInputError):
        percentile((), 50)


@pytest.mark.parametrize("percent", [0, 101])
def test_percentile_rejects_out_of_range(percent: float) -> None:
    with pytest.raises(InvalidInputError):
        percentile((1.0,), percent)


def test_batch_body_vector() -> None:
    assert batch_body(2) == EXPECTED_BODY


def test_batch_body_wraps_comments() -> None:
    lines = batch_body(6).decode("utf-8").splitlines()
    assert len(lines) == 7
    assert lines[6] == lines[1]


def test_batch_body_rejects_row_limits() -> None:
    for rows in (0, 5001):
        with pytest.raises(InvalidInputError):
            batch_body(rows)
    assert len(batch_body(5000).decode("utf-8").splitlines()) == 5001


def test_measure_one_latency_per_run() -> None:
    stub = Stub()
    with TestClient(stub.app) as client:
        latencies = measure(client, "/predict", b"{}", "application/json", 4)
    assert len(latencies) == 4
    assert all(isinstance(value, float) and value >= 0.0 for value in latencies)
    assert stub.calls["/predict"] == 4


def test_measure_rejects_zero_runs() -> None:
    with TestClient(Stub().app) as client, pytest.raises(InvalidInputError):
        measure(client, "/predict", b"{}", "application/json", 0)


def test_measure_rejects_non_200() -> None:
    with TestClient(Stub(predict_status=503).app) as client, pytest.raises(InferenceError):
        measure(client, "/predict", b"{}", "application/json", 1)


def test_summarize_vector() -> None:
    assert summarize((1.0, 2.0, 10.006)) == {"runs": 3, "p50_ms": 2.0, "p95_ms": 10.01}


def test_run_benchmark_shape_and_counts() -> None:
    stub = Stub()
    with TestClient(stub.app) as client:
        result = run_benchmark(client)
    assert result["model_version"] == "v009"
    predict = result["predict"]
    batch = result["predict_batch"]
    assert isinstance(predict, dict)
    assert isinstance(batch, dict)
    assert predict["runs"] == 100
    assert batch["runs"] == 20
    assert batch["rows"] == 100
    assert stub.calls["/predict"] == 103
    assert stub.calls["/predict-batch"] == 23
    assert stub.content_types["/predict"] == {"application/json"}
    assert stub.content_types["/predict-batch"] == {"text/csv"}


def test_main_prints_json_last_line(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(benchmark, "load_app", lambda: Stub().app)
    assert benchmark.main() == 0
    last = capsys.readouterr().out.strip().splitlines()[-1]
    assert json.loads(last)["model_version"] == "v009"


def test_main_returns_2_on_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(benchmark, "load_app", lambda: Stub(health_status=503).app)
    assert benchmark.main() == 2
    assert capsys.readouterr().err == "benchmark failed: internal_error\n"
