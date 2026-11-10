"""Tests for ml/aspects.py."""

from __future__ import annotations

from typing import Any, cast

import numpy as np
import pandas as pd
import pytest
from sklearn.pipeline import Pipeline

from api.domain.entities import ASPECT_ORDER
from api.domain.errors import InvalidInputError
from ml.aspects import aspect_report, aspect_targets, fit_aspect_model

KEYWORDS = (
    "contenidos",
    "parciales",
    "retroalimentación",
    "metodología",
    "diapositivas",
    "horario",
    "plataforma",
    "correos",
    "carga",
)
ROWS = 180
THRESHOLD_COUNT = 9


def make_data() -> tuple[list[str], np.ndarray, np.ndarray]:
    texts = [f"comentario sobre {KEYWORDS[i % 9]} del curso" for i in range(ROWS)]
    y = np.zeros((ROWS, 9), dtype=np.int64)
    for i in range(ROWS):
        y[i, i % 9] = 1
    groups = np.arange(ROWS) // 9
    return texts, y, groups


def make_frame() -> pd.DataFrame:
    frame = pd.DataFrame({f"aspect_{group.value}": ["", ""] for group in ASPECT_ORDER})
    frame.loc[0, "aspect_content"] = "positive"
    frame.loc[1, "aspect_platform"] = "negative"
    frame.loc[1, "aspect_workload_pace"] = "neutral"
    return frame


class StubPipeline:
    def predict_proba(self, X: Any) -> np.ndarray:
        scores = np.zeros((4, 9))
        scores[:, 0] = [0.9, 0.2, 0.6, 0.1]
        return scores


def stub() -> Pipeline:
    return cast(Pipeline, StubPipeline())


def assert_invalid(detail: str, info: pytest.ExceptionInfo[InvalidInputError]) -> None:
    assert info.value.detail == detail


def test_aspect_targets_marks_present_groups() -> None:
    targets = aspect_targets(make_frame())
    assert targets.tolist() == [[1, 0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 1, 0, 1]]
    assert targets.dtype == np.int64


def test_aspect_targets_rejects_missing_column() -> None:
    with pytest.raises(InvalidInputError) as info:
        aspect_targets(make_frame().drop(columns="aspect_platform"))
    assert_invalid("missing column aspect_platform", info)


def test_fit_aspect_model_picks_lowest_threshold_on_ties() -> None:
    texts, y, groups = make_data()
    _, thresholds = fit_aspect_model(texts, y, groups)
    assert thresholds == (0.1,) * 9


def test_fit_aspect_model_detects_keyword() -> None:
    texts, y, groups = make_data()
    pipeline, thresholds = fit_aspect_model(texts, y, groups)
    scores = pipeline.predict_proba(np.asarray(["el horario del curso", "las diapositivas"]))
    present = scores >= np.asarray(thresholds)
    assert np.flatnonzero(present[0]).tolist() == [5]
    assert np.flatnonzero(present[1]).tolist() == [4]
    assert abs(scores[0, 5] - 0.869) <= 0.001
    assert abs(scores[1, 4] - 0.717) <= 0.001


def test_fit_aspect_model_pipeline_steps() -> None:
    texts, y, groups = make_data()
    pipeline, _ = fit_aspect_model(texts, y, groups)
    assert [name for name, _ in pipeline.steps] == ["features", "classifier"]
    assert pipeline.named_steps["features"].ngram_range == (1, 2)
    estimator = pipeline.named_steps["classifier"].estimator
    assert estimator.class_weight == "balanced"
    assert estimator.max_iter == 1000


def test_fit_aspect_model_rejects_bad_shape() -> None:
    texts, y, groups = make_data()
    with pytest.raises(InvalidInputError) as info:
        fit_aspect_model(texts, y[:, :8], groups)
    assert_invalid("Y must have shape (n, 9)", info)


def test_fit_aspect_model_rejects_length_mismatch() -> None:
    texts, y, groups = make_data()
    with pytest.raises(InvalidInputError) as info:
        fit_aspect_model(texts[:-1], y, groups)
    assert_invalid("texts, Y and groups must have the same length", info)


def test_fit_aspect_model_rejects_non_binary() -> None:
    texts, y, groups = make_data()
    y[0, 0] = 2
    with pytest.raises(InvalidInputError) as info:
        fit_aspect_model(texts, y, groups)
    assert_invalid("Y must hold only 0 and 1", info)


def test_fit_aspect_model_rejects_rare_group() -> None:
    texts, y, groups = make_data()
    y[:, 6] = 0
    y[:4, 6] = 1
    with pytest.raises(InvalidInputError) as info:
        fit_aspect_model(texts, y, groups)
    assert_invalid("aspect group platform has fewer than 5 positive rows", info)


def test_fit_aspect_model_rejects_too_few_groups() -> None:
    texts, y, _ = make_data()
    with pytest.raises(InvalidInputError) as info:
        fit_aspect_model(texts, y, np.arange(ROWS) % 4)
    assert_invalid("groups must hold at least 5 distinct values", info)


def test_aspect_report_computes_per_group_metrics() -> None:
    y = np.zeros((4, 9), dtype=np.int64)
    y[:, 0] = [1, 1, 0, 0]
    report = aspect_report(stub(), (0.5,) * THRESHOLD_COUNT, ["a"] * 4, y)
    assert list(report) == [group.value for group in ASPECT_ORDER]
    assert report["content"] == {"precision": 0.5, "recall": 0.5, "f1": 0.5, "threshold": 0.5}
    assert report["assessment"] == {"precision": 0.0, "recall": 0.0, "f1": 0.0, "threshold": 0.5}


def test_aspect_report_rejects_wrong_threshold_count() -> None:
    y = np.zeros((4, 9), dtype=np.int64)
    with pytest.raises(InvalidInputError) as info:
        aspect_report(stub(), (0.5,) * 8, ["a"] * 4, y)
    assert_invalid("thresholds and Y must cover the 9 aspect groups", info)
