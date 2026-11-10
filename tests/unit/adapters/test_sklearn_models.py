"""Tests for SklearnPolarityModel and SklearnAspectModel in api/adapters/sklearn_models.py."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from mapie.classification import CrossConformalClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import Pipeline

from api.adapters.sklearn_models import SklearnAspectModel, SklearnPolarityModel
from api.domain.entities import AspectGroup, Polarity
from api.domain.errors import InferenceError, InvalidInputError, ModelIntegrityError

TOLERANCE = 1e-6
TEXTS = (
    ["el curso fue terrible"] * 10 + ["el curso fue normal"] * 10 + ["el curso fue excelente"] * 10
)
LABELS = np.array([0] * 10 + [1] * 10 + [2] * 10)


def _polarity_pipeline() -> Pipeline:
    return Pipeline([("features", TfidfVectorizer()), ("classifier", LogisticRegression())])


@pytest.fixture(scope="module")
def polarity_fixture() -> tuple[Pipeline, CrossConformalClassifier]:
    pipeline = _polarity_pipeline().fit(TEXTS, LABELS)
    conformal = CrossConformalClassifier(
        _polarity_pipeline(),
        confidence_level=0.9,
        conformity_score="lac",
        cv=StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=42),
        random_state=42,
    )
    conformal.fit_conformalize(np.asarray(TEXTS, dtype=object), LABELS, groups=np.arange(30))
    return pipeline, conformal


@pytest.fixture
def polarity(polarity_fixture: tuple[Pipeline, CrossConformalClassifier]) -> SklearnPolarityModel:
    return SklearnPolarityModel(*polarity_fixture, 0.9)


def _close(row: Any, expected: tuple[float, float, float]) -> bool:
    values = (row.negative, row.neutral, row.positive)
    return all(abs(a - b) <= TOLERANCE for a, b in zip(values, expected, strict=True))


def test_polarity_predict_proba_returns_rows_in_order(polarity: SklearnPolarityModel) -> None:
    rows = polarity.predict_proba(["el curso fue excelente", "el curso fue terrible"])

    assert _close(rows[0], (0.111532, 0.111532, 0.776936))
    assert _close(rows[1], (0.776936, 0.111532, 0.111532))


def test_polarity_predict_proba_unknown_words_returns_uniform(
    polarity: SklearnPolarityModel,
) -> None:
    assert _close(polarity.predict_proba(["zzz qqq"])[0], (1 / 3, 1 / 3, 1 / 3))


def test_polarity_predict_proba_normalizes_whitespace(polarity: SklearnPolarityModel) -> None:
    assert polarity.predict_proba(["  el   curso fue excelente "]) == polarity.predict_proba(
        ["el curso fue excelente"]
    )


def test_polarity_predict_set_maps_labels(polarity: SklearnPolarityModel) -> None:
    sets = polarity.predict_set(["el curso fue excelente", "el curso fue terrible", "zzz qqq"])

    assert [item.labels for item in sets] == [
        frozenset({Polarity.POSITIVE}),
        frozenset({Polarity.NEGATIVE}),
        frozenset(),
    ]
    assert all(item.confidence_level == 0.9 for item in sets)


def test_polarity_rejects_empty_sequence(polarity: SklearnPolarityModel) -> None:
    with pytest.raises(InvalidInputError):
        polarity.predict_proba([])
    with pytest.raises(InvalidInputError):
        polarity.predict_set([])


def test_polarity_rejects_too_many_texts(polarity: SklearnPolarityModel) -> None:
    with pytest.raises(InvalidInputError):
        polarity.predict_proba(["el curso"] * 5001)


def test_polarity_rejects_blank_text(polarity: SklearnPolarityModel) -> None:
    with pytest.raises(InvalidInputError):
        polarity.predict_proba(["el curso", "   "])


def test_polarity_library_error_raises_inference_error(
    polarity_fixture: tuple[Pipeline, CrossConformalClassifier],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pipeline, conformal = polarity_fixture
    cause = ValueError("x")

    def broken(_: object) -> None:
        raise cause

    model = SklearnPolarityModel(pipeline, conformal, 0.9)
    monkeypatch.setattr(pipeline, "predict_proba", broken)

    with pytest.raises(InferenceError) as error:
        model.predict_proba(["el curso"])
    assert error.value.__cause__ is cause
    with pytest.raises(ModelIntegrityError):
        SklearnPolarityModel(_polarity_pipeline(), conformal, 0.9)


def test_polarity_rejects_wrong_types(
    polarity_fixture: tuple[Pipeline, CrossConformalClassifier],
) -> None:
    pipeline, conformal = polarity_fixture

    with pytest.raises(ModelIntegrityError):
        SklearnPolarityModel("x", conformal, 0.9)
    with pytest.raises(ModelIntegrityError):
        SklearnPolarityModel(pipeline, "x", 0.9)


def test_polarity_rejects_two_class_pipeline(
    polarity_fixture: tuple[Pipeline, CrossConformalClassifier],
) -> None:
    two_classes = _polarity_pipeline().fit(TEXTS[:10] + TEXTS[20:], np.array([0] * 10 + [2] * 10))

    with pytest.raises(ModelIntegrityError):
        SklearnPolarityModel(two_classes, polarity_fixture[1], 0.9)


@pytest.mark.parametrize("level", [0.0, 1.0])
def test_polarity_rejects_confidence_level_out_of_range(
    polarity_fixture: tuple[Pipeline, CrossConformalClassifier], level: float
) -> None:
    with pytest.raises(ModelIntegrityError):
        SklearnPolarityModel(*polarity_fixture, level)


ASPECT_TEXTS = [f"palabra{j} comentario" for j in range(9) for _ in range(2)]


@pytest.fixture(scope="module")
def aspect_pipeline() -> Pipeline:
    labels = np.zeros((18, 9), dtype=int)
    for row in range(18):
        labels[row, row // 2] = 1
    pipeline = Pipeline(
        [("features", TfidfVectorizer()), ("classifier", OneVsRestClassifier(LogisticRegression()))]
    )
    return pipeline.fit(ASPECT_TEXTS, labels)


def test_aspect_detect_scores_match_pipeline(aspect_pipeline: Pipeline) -> None:
    result = SklearnAspectModel(aspect_pipeline, (0.5,) * 9).detect(["palabra0 comentario"])[0]

    expected = aspect_pipeline.predict_proba(["palabra0 comentario"])[0]
    assert len(result.scores) == 9
    assert all(type(score) is float for score in result.scores)
    assert all(abs(a - b) <= 1e-12 for a, b in zip(result.scores, expected, strict=True))


def test_aspect_detect_threshold_zero_marks_all_present(aspect_pipeline: Pipeline) -> None:
    result = SklearnAspectModel(aspect_pipeline, (0.0,) * 9).detect(["palabra0 comentario"])[0]

    assert len(result.present) == 9


def test_aspect_detect_threshold_one_marks_none(aspect_pipeline: Pipeline) -> None:
    result = SklearnAspectModel(aspect_pipeline, (1.0,) * 9).detect(["palabra0 comentario"])[0]

    assert result.present == frozenset()


def test_aspect_detect_threshold_equal_score_is_present(aspect_pipeline: Pipeline) -> None:
    score = float(aspect_pipeline.predict_proba(["palabra0 comentario"])[0][0])
    model = SklearnAspectModel(aspect_pipeline, (score,) + (1.0,) * 8)

    assert model.detect(["palabra0 comentario"])[0].present == frozenset({AspectGroup.CONTENT})


def test_aspect_rejects_invalid_thresholds(aspect_pipeline: Pipeline) -> None:
    with pytest.raises(ModelIntegrityError):
        SklearnAspectModel(aspect_pipeline, (0.5,) * 8)
    with pytest.raises(ModelIntegrityError):
        SklearnAspectModel(aspect_pipeline, (1.5,) + (0.5,) * 8)


def test_aspect_detect_rejects_empty_sequence(aspect_pipeline: Pipeline) -> None:
    with pytest.raises(InvalidInputError):
        SklearnAspectModel(aspect_pipeline, (0.5,) * 9).detect([])
