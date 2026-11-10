from __future__ import annotations

import logging
import threading

import pytest

from api.adapters.monitoring import InMemoryMetricsStore, nearest_rank
from api.domain.entities import Decision
from api.domain.errors import InvalidInputError
from api.domain.reports import DriftReport, MetricsSnapshot

SHA = "a" * 64
NOW = "2026-11-10T12:00:00Z"
TOLERANCE = 1e-6


def drift_report(row_count: int) -> DriftReport:
    return DriftReport(SHA, row_count, 0.1, 0.2, 0.2, False, NOW)


def test_nearest_rank_vectors() -> None:
    values = [float(item) for item in range(1, 21)]
    assert nearest_rank(values, 50) == 10.0
    assert nearest_rank(values, 95) == 19.0
    assert nearest_rank([10.0, 20.0, 30.0], 50) == 20.0
    assert nearest_rank([10.0, 20.0, 30.0], 95) == 30.0
    assert nearest_rank([7.0], 50) == 7.0
    assert nearest_rank([7.0], 95) == 7.0


def test_metrics_snapshot_empty() -> None:
    snapshot = InMemoryMetricsStore().snapshot()
    assert snapshot == MetricsSnapshot(0, None, None, 0, 0, None)
    assert snapshot.abstention_rate is None


def test_metrics_counts_decisions() -> None:
    store = InMemoryMetricsStore()
    store.record("/predict-batch", 12.5, [Decision.CLASSIFY] * 7 + [Decision.REVIEW] * 3)
    snapshot = store.snapshot()
    assert snapshot.classify_count == 7
    assert snapshot.review_count == 3
    assert snapshot.abstention_rate is not None
    assert abs(snapshot.abstention_rate - 0.3) <= TOLERANCE
    assert snapshot.request_count == 1
    assert snapshot.p50_ms == 12.5
    assert snapshot.p95_ms == 12.5


def test_metrics_buffer_keeps_last_1000() -> None:
    store = InMemoryMetricsStore()
    for value in range(1, 1002):
        store.record("/predict", float(value), [])
    snapshot = store.snapshot()
    assert snapshot.request_count == 1001
    assert snapshot.p50_ms == 501.0
    assert snapshot.p95_ms == 951.0


@pytest.mark.parametrize("latency", [-1.0, float("nan"), float("inf")])
def test_metrics_rejects_invalid_latency(latency: float) -> None:
    store = InMemoryMetricsStore()
    store.record("/predict", 4.0, [Decision.CLASSIFY])
    before = store.snapshot()
    with pytest.raises(InvalidInputError) as error:
        store.record("/predict", latency, [Decision.REVIEW])
    assert error.value.detail == "latency must be a finite non-negative number"
    assert store.snapshot() == before


def test_metrics_record_is_thread_safe() -> None:
    store = InMemoryMetricsStore()

    def work() -> None:
        for _ in range(1000):
            store.record("/predict", 1.0, [Decision.CLASSIFY])

    threads = [threading.Thread(target=work) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    snapshot = store.snapshot()
    assert snapshot.request_count == 8000
    assert snapshot.classify_count == 8000


def test_metrics_record_drift_replaces_last() -> None:
    store = InMemoryMetricsStore()
    first = drift_report(1)
    second = drift_report(2)
    store.record_drift(first)
    store.record_drift(second)
    assert store.snapshot().last_drift is second


def test_metrics_logs_without_text(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG, logger="api.adapters.monitoring")
    InMemoryMetricsStore().record("/predict", 3.0, [Decision.REVIEW])
    assert "metrics_recorded route=/predict latency_ms=3.0 decisions=1" in caplog.messages
