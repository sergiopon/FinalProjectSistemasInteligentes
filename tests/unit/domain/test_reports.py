"""Tests for api/domain/reports.py."""

from __future__ import annotations

from collections.abc import Callable
from functools import partial

import pytest

from api.domain.entities import ASPECT_ORDER, AspectGroup
from api.domain.errors import InvalidInputError
from api.domain.reports import (
    AspectCell,
    CourseReport,
    DriftReport,
    MetricsSnapshot,
    ModelInfo,
    PolarityCounts,
    PriorityEntry,
    TopicSummary,
)

CONTENT = AspectGroup.CONTENT
ASSESSMENT = AspectGroup.ASSESSMENT
VALID_TIMESTAMP = "2026-11-10T12:00:00Z"


def assert_invalid(build: Callable[[], object], detail: str) -> None:
    with pytest.raises(InvalidInputError) as info:
        build()
    assert info.value.detail == detail


def empty_cells() -> tuple[AspectCell, ...]:
    return tuple(AspectCell(group, 0, 0, 0, 0) for group in ASPECT_ORDER)


def course_report(
    aspects: tuple[AspectCell, ...], comment_count: int = 10, review_count: int = 3
) -> CourseReport:
    return CourseReport(
        "Redes", comment_count, review_count, PolarityCounts(1, 1, 1), aspects, (), (), ()
    )


def drift_report(body_sha256: str = "a" * 64, created_at: str = VALID_TIMESTAMP) -> DriftReport:
    return DriftReport(body_sha256, 10, 0.1, 0.05, 0.04, False, created_at)


def metrics_snapshot(
    request_count: int = 2, classify_count: int = 7, review_count: int = 3
) -> MetricsSnapshot:
    return MetricsSnapshot(request_count, 1.0, 2.0, classify_count, review_count, None)


def model_info(version: str) -> ModelInfo:
    return ModelInfo(
        version, VALID_TIMESTAMP, "a" * 64, "logistic_regression", "tfidf", 0.9, 0.62, 0.9
    )


def test_polarity_counts_negative() -> None:
    assert_invalid(lambda: PolarityCounts(-1, 0, 0), "count is negative")


def test_aspect_cell_negative_count() -> None:
    assert_invalid(lambda: AspectCell(CONTENT, -1, 0, 0, 0), "count is negative")
    assert_invalid(lambda: AspectCell(CONTENT, 0, -1, 0, 0), "count is negative")
    assert_invalid(lambda: AspectCell(CONTENT, 0, 0, -1, 0), "count is negative")
    assert_invalid(lambda: AspectCell(CONTENT, 0, 0, 0, -1), "count is negative")


def test_aspect_cell_sum_mismatch() -> None:
    assert_invalid(lambda: AspectCell(CONTENT, 4, 1, 1, 1), "aspect counts do not sum to mentions")


def test_aspect_cell_negative_share() -> None:
    assert AspectCell(CONTENT, 4, 1, 1, 2).negative_share == 0.25
    assert AspectCell(CONTENT, 0, 0, 0, 0).negative_share is None


def test_priority_entry_invalid() -> None:
    assert_invalid(
        lambda: PriorityEntry(0, CONTENT, 10, 4, 0.5, 0.4, 0.2, False), "rank is below 1"
    )
    assert_invalid(
        lambda: PriorityEntry(1, CONTENT, 10, 4, 1.01, 0.4, 0.2, False),
        "priority value out of range",
    )


def test_topic_summary_invalid() -> None:
    assert_invalid(
        lambda: TopicSummary(-1, 5, ("curso", "tema"), "Buen curso"), "topic is negative"
    )
    assert_invalid(
        lambda: TopicSummary(0, 0, ("curso", "tema"), "Buen curso"), "topic size is below 1"
    )


def test_course_report_aspects_order() -> None:
    swapped = list(empty_cells())
    swapped[0], swapped[1] = swapped[1], swapped[0]
    message = "aspects must be the 9 groups in order"
    assert_invalid(lambda: course_report(tuple(swapped)), message)
    assert_invalid(lambda: course_report(empty_cells()[:8]), message)
    assert course_report(empty_cells()).aspects == empty_cells()


def test_course_report_review_count() -> None:
    assert_invalid(
        lambda: course_report(empty_cells(), comment_count=10, review_count=11),
        "review_count out of range",
    )


def test_drift_report_sha() -> None:
    assert_invalid(
        lambda: drift_report(body_sha256="A" * 64), "body_sha256 is not 64 lowercase hex"
    )
    assert_invalid(
        lambda: drift_report(body_sha256="a" * 63), "body_sha256 is not 64 lowercase hex"
    )
    assert drift_report(body_sha256="a" * 64).body_sha256 == "a" * 64


def test_drift_report_created_at() -> None:
    message = "created_at is not ISO 8601 UTC"
    for bad in ("2026-11-10T12:00:00", "2026-11-10T12:00:00+00:00", "2026-02-30T00:00:00Z"):
        assert_invalid(partial(drift_report, created_at=bad), message)
    assert drift_report(created_at=VALID_TIMESTAMP).created_at == VALID_TIMESTAMP


def test_metrics_snapshot_abstention() -> None:
    assert metrics_snapshot(classify_count=7, review_count=3).abstention_rate == 0.3
    assert metrics_snapshot(classify_count=0, review_count=0).abstention_rate is None
    assert_invalid(lambda: metrics_snapshot(request_count=-1), "count is negative")


def test_model_info_version() -> None:
    for bad in ("v1", "v0001", "V001"):
        assert_invalid(partial(model_info, bad), "version does not match vNNN")
    assert model_info("v001").version == "v001"
