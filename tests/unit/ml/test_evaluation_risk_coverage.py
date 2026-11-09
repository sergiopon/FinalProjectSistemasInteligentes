"""Tests for risk_coverage in ml/evaluation.py."""

from __future__ import annotations

import numpy as np
import pytest

from api.domain.errors import InvalidInputError
from ml.evaluation import risk_coverage


def assert_points(actual: list[tuple[float, float]], expected: list[tuple[float, float]]) -> None:
    assert len(actual) == len(expected)
    for (coverage, risk), (expected_coverage, expected_risk) in zip(actual, expected, strict=True):
        assert type(coverage) is float
        assert type(risk) is float
        assert abs(coverage - expected_coverage) <= 1e-9
        assert abs(risk - expected_risk) <= 1e-9


def test_risk_coverage_orders_by_confidence() -> None:
    probabilities = np.array(
        [[0.9, 0.05, 0.05], [0.2, 0.7, 0.1], [0.4, 0.35, 0.25], [0.1, 0.3, 0.6]]
    )
    result = risk_coverage(probabilities, np.array([0, 0, 0, 2]))
    assert_points(result, [(0.25, 0.0), (0.5, 0.5), (0.75, 1 / 3), (1.0, 0.25)])


def test_risk_coverage_breaks_ties_by_row_index() -> None:
    probabilities = np.array([[0.5, 0.3, 0.2], [0.2, 0.5, 0.3]])
    result = risk_coverage(probabilities, np.array([1, 1]))
    assert_points(result, [(0.5, 1.0), (1.0, 0.5)])


@pytest.mark.parametrize("shape", [(2, 2), (0, 3), (3,)])
def test_risk_coverage_rejects_bad_shape(shape: tuple[int, ...]) -> None:
    rows = shape[0]
    with pytest.raises(InvalidInputError) as info:
        risk_coverage(np.full(shape, 0.5), np.zeros(rows, dtype=np.int64))
    assert info.value.detail == "probabilities must have shape (n, 3) with n >= 1"


def test_risk_coverage_rejects_length_mismatch() -> None:
    with pytest.raises(InvalidInputError) as info:
        risk_coverage(np.full((2, 3), 1 / 3), np.array([0, 1, 2]))
    assert info.value.detail == "probabilities and y must have the same length"
