"""Ports for monitoring: drift detection and metrics."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from api.domain.entities import Decision
from api.domain.reports import DriftReport, MetricsSnapshot


class DriftDetector(Protocol):
    """Compares an upload with the training reference."""

    def compare(self, texts: Sequence[str], body_sha256: str, created_at: str) -> DriftReport:
        """Compare an upload with the training reference.

        Preconditions:
            `texts` holds 1 to 5000 items and every item is non-empty after `strip()`. `body_sha256`
            is 64 lowercase hex characters. `created_at` is ISO 8601 UTC ending in `Z`.

        Postconditions:
            A `DriftReport` for `texts` computed as in docs/contracts.md §4.5.

        Raises:
            `InvalidInputError`: an argument violates a precondition.
        """
        ...


class MetricsStore(Protocol):
    """Keeps request latency, decision counts and the last drift report."""

    def record(self, route: str, latency_ms: float, decisions: Sequence[Decision]) -> None:
        """Record the latency and decisions of one request.

        Preconditions:
            `route` is `"/predict"` or `"/predict-batch"`. `latency_ms` is finite and >= 0.0.

        Postconditions:
            Latency and decisions stored. Thread-safe. The buffer keeps the last 1000 latencies.

        Raises:
            No exception.
        """
        ...

    def record_drift(self, report: DriftReport) -> None:
        """Replace the last drift report.

        Preconditions:
            `report` is a valid `DriftReport`.

        Postconditions:
            `report` replaces the last drift report. Thread-safe.

        Raises:
            No exception.
        """
        ...

    def snapshot(self) -> MetricsSnapshot:
        """Return the current metrics.

        Preconditions:
            None.

        Postconditions:
            Percentiles by nearest rank over the latency buffer. `p50_ms` and `p95_ms` are `None`
            when it is empty.

        Raises:
            No exception.
        """
        ...
