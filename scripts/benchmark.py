"""Measure p50 and p95 latency of the prediction routes through the in-process app."""

from __future__ import annotations

import csv
import importlib
import io
import json
import math
import sys
import time
from collections.abc import Sequence
from http import HTTPStatus

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.domain.errors import AppError, InferenceError, InvalidInputError

PREDICT_RUNS: int = 100
BATCH_RUNS: int = 20
BATCH_ROWS: int = 100
WARMUP_RUNS: int = 3
BATCH_COURSE: str = "Curso de prueba"
MAX_BATCH_ROWS: int = 5000
MAX_PERCENT: int = 100
SAMPLE_COMMENTS: tuple[str, ...] = (
    "El contenido del curso fue claro y ordenado.",
    "Los parciales fueron muy difíciles para el tiempo disponible.",
    "La plataforma se cayó varias veces durante las entregas.",
    "El profesor respondió los correos a tiempo.",
    "La carga de trabajo fue alta pero el material ayudó.",
)


def percentile(values: Sequence[float], percent: float) -> float:
    """Return the nearest-rank percentile of the values."""
    if not values:
        raise InvalidInputError("no latencies")
    if percent <= 0 or percent > MAX_PERCENT:
        raise InvalidInputError("percent out of range")
    return sorted(values)[math.ceil(percent / MAX_PERCENT * len(values)) - 1]


def batch_body(rows: int) -> bytes:
    """Build a synthetic CSV body of the given number of rows."""
    if rows < 1 or rows > MAX_BATCH_ROWS:
        raise InvalidInputError("rows out of range")
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(("feedback", "curso"))
    for index in range(rows):
        writer.writerow((SAMPLE_COMMENTS[index % len(SAMPLE_COMMENTS)], BATCH_COURSE))
    return buffer.getvalue().encode("utf-8")


def measure(
    client: TestClient, path: str, body: bytes, content_type: str, runs: int
) -> tuple[float, ...]:
    """Post the body `runs` times and return each latency in milliseconds."""
    if runs < 1:
        raise InvalidInputError("runs out of range")
    latencies: list[float] = []
    for _ in range(runs):
        before = time.perf_counter()
        response = client.post(path, content=body, headers={"Content-Type": content_type})
        latencies.append((time.perf_counter() - before) * 1000.0)
        if response.status_code != HTTPStatus.OK:
            raise InferenceError(f"benchmark request failed status={response.status_code}")
    return tuple(latencies)


def summarize(latencies: Sequence[float]) -> dict[str, float | int]:
    """Return the run count and the p50 and p95 latency in milliseconds."""
    return {
        "runs": len(latencies),
        "p50_ms": round(percentile(latencies, 50), 2),
        "p95_ms": round(percentile(latencies, 95), 2),
    }


def run_benchmark(client: TestClient) -> dict[str, object]:
    """Warm up and measure both prediction routes."""
    health = client.get("/health")
    if health.status_code != HTTPStatus.OK:
        raise InferenceError(f"benchmark request failed status={health.status_code}")
    predict_body = json.dumps({"text": SAMPLE_COMMENTS[0]}).encode()
    batch = batch_body(BATCH_ROWS)
    measure(client, "/predict", predict_body, "application/json", WARMUP_RUNS)
    measure(client, "/predict-batch", batch, "text/csv", WARMUP_RUNS)
    return {
        "model_version": health.json()["model_version"],
        "predict": summarize(
            measure(client, "/predict", predict_body, "application/json", PREDICT_RUNS)
        ),
        "predict_batch": {
            **summarize(measure(client, "/predict-batch", batch, "text/csv", BATCH_RUNS)),
            "rows": BATCH_ROWS,
        },
    }


def load_app() -> FastAPI:
    """Import and return the application, building it only when called."""
    app: FastAPI = importlib.import_module("api.main").app
    return app


def main() -> int:
    """Run the benchmark and print the result as JSON on the last stdout line."""
    try:
        with TestClient(load_app()) as client:
            result = run_benchmark(client)
    except AppError as error:
        print(f"benchmark failed: {error.code}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
