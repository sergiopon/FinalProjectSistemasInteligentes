"""Tests for ml/conformal.py on synthetic texts."""

from __future__ import annotations

import logging
from unittest.mock import patch

import numpy as np
import pytest
from mapie.classification import CrossConformalClassifier
from sklearn.exceptions import NotFittedError
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC
from sklearn.utils.validation import check_is_fitted

from api.domain.errors import InvalidInputError
from ml.conformal import COVERAGE_TOLERANCE, conformal_report, fit_cross_conformal

WORDS = ("malo", "regular", "bueno")
TEXTS = [f"{WORDS[i % 3]} curso numero {i}" for i in range(150)]
Y = np.arange(150) % 3
GROUPS = np.arange(150) // 3
CLEAR_TEXTS = np.asarray(["malo curso", "regular curso", "bueno curso"], dtype=object)


def new_pipeline(classifier: object | None = None) -> Pipeline:
    final = LogisticRegression(max_iter=1000) if classifier is None else classifier
    return Pipeline([("features", TfidfVectorizer()), ("classifier", final)])


class StubModel:
    """Conformal model stand-in whose predict_set returns fixed sets."""

    def __init__(self, sets: list[list[int]]) -> None:
        self.y_set = np.asarray(sets, dtype=bool)[:, :, np.newaxis]
        self.agg_scores: list[str] = []

    def predict_set(self, X: object, agg_scores: str) -> tuple[np.ndarray, np.ndarray]:
        self.agg_scores.append(agg_scores)
        return np.zeros(len(self.y_set), dtype=np.int64), self.y_set


STUB_SETS = [[1, 0, 0], [1, 1, 0], [0, 0, 0], [0, 1, 1]]


def assert_invalid(detail: str, info: pytest.ExceptionInfo[InvalidInputError]) -> None:
    assert info.value.detail == detail


@pytest.mark.parametrize("confidence_level", [0.9, 0.8])
def test_fit_cross_conformal_returns_singleton_sets_for_clear_texts(
    confidence_level: float,
) -> None:
    model = fit_cross_conformal(new_pipeline(), TEXTS, Y, GROUPS, confidence_level)
    y_pred, y_set = model.predict_set(CLEAR_TEXTS, agg_scores="mean")
    assert y_pred.tolist() == [0, 1, 2]
    assert y_set[:, :, 0].tolist() == [
        [True, False, False],
        [False, True, False],
        [False, False, True],
    ]


def test_fit_cross_conformal_leaves_input_pipeline_unfitted() -> None:
    pipeline = new_pipeline()
    fit_cross_conformal(pipeline, TEXTS, Y, GROUPS, 0.9)
    with pytest.raises(NotFittedError):
        check_is_fitted(pipeline)


def test_fit_cross_conformal_sets_lac_and_seed() -> None:
    pipeline = new_pipeline()
    with patch("ml.conformal.CrossConformalClassifier", wraps=CrossConformalClassifier) as spy:
        fit_cross_conformal(pipeline, TEXTS, Y, GROUPS, 0.9)
    assert spy.call_count == 1
    kwargs = spy.call_args.kwargs
    assert kwargs["estimator"] is pipeline
    assert kwargs["confidence_level"] == 0.9
    assert kwargs["conformity_score"] == "lac"
    assert kwargs["random_state"] == 42
    cv = kwargs["cv"]
    assert isinstance(cv, StratifiedGroupKFold)
    assert cv.n_splits == 5
    assert cv.shuffle is True
    assert cv.random_state == 42


@pytest.mark.parametrize("confidence_level", [0.0, 1.0, 1.5])
def test_fit_cross_conformal_rejects_confidence_level_out_of_range(
    confidence_level: float,
) -> None:
    with pytest.raises(InvalidInputError) as info:
        fit_cross_conformal(new_pipeline(), TEXTS, Y, GROUPS, confidence_level)
    assert_invalid("confidence_level must be in (0, 1)", info)


def test_fit_cross_conformal_rejects_length_mismatch() -> None:
    with pytest.raises(InvalidInputError) as info:
        fit_cross_conformal(new_pipeline(), TEXTS, Y[:149], GROUPS, 0.9)
    assert_invalid("texts, y and groups must have the same length", info)


def test_fit_cross_conformal_rejects_missing_class() -> None:
    with pytest.raises(InvalidInputError) as info:
        fit_cross_conformal(new_pipeline(), TEXTS, np.arange(150) % 2, GROUPS, 0.9)
    assert_invalid("y must contain the classes 0, 1 and 2", info)


def test_fit_cross_conformal_rejects_too_few_groups() -> None:
    with pytest.raises(InvalidInputError) as info:
        fit_cross_conformal(new_pipeline(), TEXTS, Y, np.arange(150) % 4, 0.9)
    assert_invalid("groups must hold at least 5 distinct values", info)


def test_fit_cross_conformal_rejects_pipeline_without_predict_proba() -> None:
    with pytest.raises(InvalidInputError) as info:
        fit_cross_conformal(new_pipeline(LinearSVC()), TEXTS, Y, GROUPS, 0.9)
    assert_invalid("pipeline must expose predict_proba", info)


def test_conformal_report_computes_set_metrics() -> None:
    stub = StubModel(STUB_SETS)
    report = conformal_report(stub, ["t0", "t1", "t2", "t3"], np.array([0, 1, 2, 0]))
    assert report == {
        "empirical_coverage": 0.5,
        "mean_set_size": 1.25,
        "singleton_rate": 0.25,
        "empty_rate": 0.25,
    }
    assert all(type(value) is float for value in report.values())
    assert stub.agg_scores == ["mean"]


def test_conformal_report_rejects_empty_input() -> None:
    with pytest.raises(InvalidInputError) as info:
        conformal_report(StubModel(STUB_SETS), [], np.array([], dtype=np.int64))
    assert_invalid("texts and y must have the same non-zero length", info)


def test_coverage_tolerance_value() -> None:
    assert COVERAGE_TOLERANCE == 0.05


def test_fit_cross_conformal_logs_counts_no_text(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        fit_cross_conformal(new_pipeline(), TEXTS, Y, GROUPS, 0.9)
    records = [record for record in caplog.records if record.name == "ml.conformal"]
    assert [record.getMessage() for record in records] == [
        "conformal_fitted rows=150 groups=50 confidence_level=0.9"
    ]
    assert not any("curso" in record.getMessage() for record in caplog.records)


def test_conformal_report_rejects_length_mismatch() -> None:
    with pytest.raises(InvalidInputError) as info:
        conformal_report(StubModel(STUB_SETS), ["t0", "t1", "t2", "t3"], np.array([0, 1, 2]))
    assert_invalid("texts and y must have the same non-zero length", info)


@pytest.mark.parametrize(
    "y", [np.array([0, 3]), np.array([0, -1]), np.array([0.0, 1.0]), np.array([[0], [1]])]
)
def test_conformal_report_rejects_out_of_range_y(y: np.ndarray) -> None:
    with pytest.raises(InvalidInputError) as info:
        conformal_report(StubModel(STUB_SETS), ["t0", "t1"], y)
    assert_invalid("y must hold only the class indices 0, 1 and 2", info)
