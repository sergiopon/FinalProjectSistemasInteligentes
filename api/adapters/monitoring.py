"""In-memory metrics store and reference-based drift detector (SEC-03: nothing is persisted)."""

from __future__ import annotations

import bisect
import logging
import math
import re
import threading
from collections import deque
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from api.domain.entities import Decision
from api.domain.errors import InvalidInputError, ModelIntegrityError
from api.domain.reports import DriftReport, MetricsSnapshot

LATENCY_BUFFER_SIZE: int = 1000
BIN_COUNT: int = 10
EDGE_COUNT: int = 9
SHARE_FLOOR: float = 1e-4
PSI_THRESHOLD: float = 0.25
OOV_MARGIN: float = 0.10
SHARE_SUM_TOLERANCE: float = 1e-6
MAX_TEXTS: int = 5000
TOKEN_PATTERN: re.Pattern[str] = re.compile(r"(?u)\b\w\w+\b")

_P50: int = 50
_P95: int = 95
_INVALID_REFERENCE: str = "reference stats are invalid"

logger = logging.getLogger(__name__)


def utc_now_iso() -> str:
    """Return the current UTC time as YYYY-MM-DDTHH:MM:SSZ."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def nearest_rank(sorted_values: Sequence[float], percent: int) -> float:
    """Return the nearest-rank percentile of an ascending sequence.

    Args:
        sorted_values: Values sorted ascending, at least one.
        percent: Percentile in 1..100.

    Returns:
        The value at rank ceil(percent * n / 100), counted from 1.
    """
    rank = -(-percent * len(sorted_values) // 100)
    return sorted_values[rank - 1]


class InMemoryMetricsStore:
    """Thread-safe request counters and a ring buffer of the last 1000 latencies."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._latencies: deque[float] = deque(maxlen=LATENCY_BUFFER_SIZE)
        self._request_count = 0
        self._classify_count = 0
        self._review_count = 0
        self._last_drift: DriftReport | None = None

    def record(self, route: str, latency_ms: float, decisions: Sequence[Decision]) -> None:
        """Record the latency and decisions of one request.

        Args:
            route: Route that served the request.
            latency_ms: Latency in milliseconds, finite and >= 0.
            decisions: Decisions returned by the request.

        Raises:
            InvalidInputError: The latency is not finite or is negative; nothing is recorded.
        """
        if not math.isfinite(latency_ms) or latency_ms < 0.0:
            raise InvalidInputError("latency must be a finite non-negative number")
        classify = sum(1 for item in decisions if item is Decision.CLASSIFY)
        review = sum(1 for item in decisions if item is Decision.REVIEW)
        with self._lock:
            self._request_count += 1
            self._latencies.append(latency_ms)
            self._classify_count += classify
            self._review_count += review
        logger.debug(
            "metrics_recorded route=%s latency_ms=%.1f decisions=%d",
            route,
            latency_ms,
            len(decisions),
        )

    def record_drift(self, report: DriftReport) -> None:
        """Replace the last drift report.

        Args:
            report: The new drift report.
        """
        with self._lock:
            self._last_drift = report

    def snapshot(self) -> MetricsSnapshot:
        """Return the current metrics.

        Returns:
            Counters, nearest-rank p50 and p95 (None when no latency is held) and the last drift.
        """
        with self._lock:
            latencies = sorted(self._latencies)
            counts = (self._request_count, self._classify_count, self._review_count)
            last_drift = self._last_drift
        p50 = nearest_rank(latencies, _P50) if latencies else None
        p95 = nearest_rank(latencies, _P95) if latencies else None
        return MetricsSnapshot(counts[0], p50, p95, counts[1], counts[2], last_drift)


def _is_number(value: object) -> bool:
    """Whether a value is an int or float and not a bool."""
    return isinstance(value, int | float) and not isinstance(value, bool)


def _parse_edges(value: object) -> tuple[int, ...]:
    """Validate the 9 non-decreasing integer length edges."""
    if not isinstance(value, list) or len(value) != EDGE_COUNT:
        raise ModelIntegrityError(_INVALID_REFERENCE)
    if not all(isinstance(item, int) and not isinstance(item, bool) for item in value):
        raise ModelIntegrityError(_INVALID_REFERENCE)
    edges = tuple(int(item) for item in value)
    if any(later < earlier for earlier, later in zip(edges, edges[1:], strict=False)):
        raise ModelIntegrityError(_INVALID_REFERENCE)
    return edges


def _parse_shares(value: object) -> tuple[float, ...]:
    """Validate the 10 bin shares, each in (0, 1], summing to 1."""
    if not isinstance(value, list) or len(value) != BIN_COUNT:
        raise ModelIntegrityError(_INVALID_REFERENCE)
    if not all(_is_number(item) for item in value):
        raise ModelIntegrityError(_INVALID_REFERENCE)
    shares = tuple(float(item) for item in value)
    if not all(0.0 < share <= 1.0 for share in shares):
        raise ModelIntegrityError(_INVALID_REFERENCE)
    if abs(sum(shares) - 1.0) > SHARE_SUM_TOLERANCE:
        raise ModelIntegrityError(_INVALID_REFERENCE)
    return shares


def _parse_oov_rate(value: object) -> float:
    """Validate the reference out-of-vocabulary rate, in [0, 1]."""
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ModelIntegrityError(_INVALID_REFERENCE)
    rate = float(value)
    if not 0.0 <= rate <= 1.0:
        raise ModelIntegrityError(_INVALID_REFERENCE)
    return rate


class ReferenceDriftDetector:
    """Compares a batch with the training reference by length PSI and out-of-vocabulary rate."""

    def __init__(self, reference: Mapping[str, object], vocabulary: frozenset[str]) -> None:
        """Validate the reference statistics.

        Args:
            reference: Mapping read from reference_stats.json.
            vocabulary: Training vocabulary, lowercase tokens.

        Raises:
            ModelIntegrityError: A key is missing or a value is invalid.
        """
        self._edges = _parse_edges(reference.get("length_edges"))
        self._shares = _parse_shares(reference.get("length_shares"))
        self._reference_oov_rate = _parse_oov_rate(reference.get("reference_oov_rate"))
        self._vocabulary = vocabulary

    def compare(self, texts: Sequence[str], body_sha256: str, created_at: str) -> DriftReport:
        """Compare a batch with the training reference.

        Args:
            texts: Texts of the batch, 1 to 5000.
            body_sha256: SHA-256 of the uploaded body, 64 lowercase hex characters.
            created_at: UTC timestamp ending in Z.

        Returns:
            The drift report; drifted when the PSI exceeds 0.25 or the OOV rate exceeds the
            reference rate by more than 0.10.

        Raises:
            InvalidInputError: Wrong number of texts, or a malformed hash or timestamp.
        """
        if not 1 <= len(texts) <= MAX_TEXTS:
            raise InvalidInputError("texts must hold 1 to 5000 items")
        length_psi = self._length_psi(texts)
        oov_rate = self._oov_rate(texts)
        reference_oov_rate = self._reference_oov_rate
        drifted = length_psi > PSI_THRESHOLD or oov_rate > reference_oov_rate + OOV_MARGIN
        report = DriftReport(
            body_sha256=body_sha256,
            row_count=len(texts),
            length_psi=length_psi,
            oov_rate=oov_rate,
            reference_oov_rate=reference_oov_rate,
            drifted=drifted,
            created_at=created_at,
        )
        logger.info(
            "drift_compared rows=%d length_psi=%.6f oov_rate=%.6f drifted=%s",
            len(texts),
            length_psi,
            oov_rate,
            drifted,
        )
        return report

    def _length_psi(self, texts: Sequence[str]) -> float:
        """Return the population stability index of the text lengths over 10 bins."""
        counts = [0] * BIN_COUNT
        for text in texts:
            counts[bisect.bisect_right(self._edges, len(text))] += 1
        total = len(texts)
        psi = 0.0
        for count, expected in zip(counts, self._shares, strict=True):
            actual = max(count / total, SHARE_FLOOR)
            psi += (actual - expected) * math.log(actual / expected)
        return psi

    def _oov_rate(self, texts: Sequence[str]) -> float:
        """Return the share of tokens that are not in the training vocabulary."""
        tokens = [token for text in texts for token in TOKEN_PATTERN.findall(text.lower())]
        if not tokens:
            return 0.0
        unknown = sum(1 for token in tokens if token not in self._vocabulary)
        return unknown / len(tokens)
