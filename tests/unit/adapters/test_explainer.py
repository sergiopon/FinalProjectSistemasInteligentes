"""Tests for OcclusionExplainer in api/adapters/explainer.py."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import pytest

from api.adapters.explainer import OcclusionExplainer
from api.domain.entities import ClassProbabilities, ConformalSet, WordInfluence
from api.domain.errors import InferenceError, InvalidInputError


def _probs(negative: float, neutral: float, positive: float) -> ClassProbabilities:
    return ClassProbabilities(negative=negative, neutral=neutral, positive=positive)


class StubModel:
    def __init__(self, table: Mapping[str, ClassProbabilities]) -> None:
        self.table = table
        self.calls: list[list[str]] = []

    def predict_proba(self, texts: Sequence[str]) -> tuple[ClassProbabilities, ...]:
        self.calls.append(list(texts))
        return tuple(self.table[text] for text in texts)

    def predict_set(self, texts: Sequence[str]) -> tuple[ConformalSet, ...]:
        raise NotImplementedError


class FailingModel:
    def predict_proba(self, texts: Sequence[str]) -> tuple[ClassProbabilities, ...]:
        raise InferenceError("x")

    def predict_set(self, texts: Sequence[str]) -> tuple[ConformalSet, ...]:
        raise NotImplementedError


TEXT = "Buen curso, mal horario"
TABLE = {
    TEXT: _probs(0.25, 0.25, 0.5),
    "curso, mal horario": _probs(0.125, 0.125, 0.75),
    "Buen , mal horario": _probs(0.25, 0.25, 0.5),
    "Buen curso, horario": _probs(0.0625, 0.0625, 0.875),
    "Buen curso, mal": _probs(0.375, 0.375, 0.25),
}


def test_explainer_ranks_by_absolute_delta() -> None:
    model = StubModel(TABLE)

    result = OcclusionExplainer(model).explain(TEXT, 3)

    assert result == (
        WordInfluence("mal", -0.375),
        WordInfluence("buen", -0.25),
        WordInfluence("horario", 0.25),
    )
    assert model.calls == [
        [
            TEXT,
            "curso, mal horario",
            "Buen , mal horario",
            "Buen curso, horario",
            "Buen curso, mal",
        ]
    ]


def test_explainer_top_k_larger_than_words() -> None:
    result = OcclusionExplainer(StubModel(TABLE)).explain(TEXT, 20)

    assert len(result) == 4
    assert result[-1] == WordInfluence("curso", 0.0)


def test_explainer_repeated_word_counted_once() -> None:
    table = {
        "muy muy bueno": _probs(0.25, 0.25, 0.5),
        "bueno": _probs(0.5, 0.25, 0.25),
        "muy muy": _probs(0.25, 0.25, 0.5),
    }

    result = OcclusionExplainer(StubModel(table)).explain("muy muy bueno", 5)

    assert result == (WordInfluence("muy", 0.25), WordInfluence("bueno", 0.0))


def test_explainer_single_word_returns_empty() -> None:
    model = StubModel({})

    assert OcclusionExplainer(model).explain("Excelente", 5) == ()
    assert model.calls == []


@pytest.mark.parametrize("top_k", [0, 21])
def test_explainer_rejects_top_k_out_of_range(top_k: int) -> None:
    with pytest.raises(InvalidInputError):
        OcclusionExplainer(StubModel(TABLE)).explain(TEXT, top_k)


def test_explainer_rejects_blank_text() -> None:
    with pytest.raises(InvalidInputError):
        OcclusionExplainer(StubModel(TABLE)).explain("  ", 3)


def test_explainer_propagates_inference_error() -> None:
    with pytest.raises(InferenceError):
        OcclusionExplainer(FailingModel()).explain(TEXT, 3)
