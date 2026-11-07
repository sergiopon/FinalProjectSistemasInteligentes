"""Tests for api/domain/entities.py."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable

import pytest

from api.domain.entities import (
    ASPECT_ORDER,
    POLARITY_ORDER,
    AspectGroup,
    AspectScores,
    AspectSentiment,
    ClassProbabilities,
    ClauseAnalysis,
    Comment,
    ConformalSet,
    Polarity,
    WordInfluence,
)
from api.domain.errors import AppError, InvalidInputError

ZERO_SCORES = (0.0,) * 9


def assert_invalid(build: Callable[[], object], detail: str) -> None:
    with pytest.raises(InvalidInputError) as info:
        build()
    assert info.value.detail == detail


def baseline_probabilities() -> ClassProbabilities:
    return ClassProbabilities(0.2, 0.3, 0.5)


def baseline_aspects() -> AspectScores:
    return AspectScores(ZERO_SCORES, frozenset())


def test_comment_valid() -> None:
    comment = Comment("Buen curso", "Bases de datos")
    assert comment.text == "Buen curso"
    assert comment.course == "Bases de datos"


def test_comment_blank_text() -> None:
    assert_invalid(lambda: Comment("   "), "comment text is blank")


def test_comment_blank_course() -> None:
    assert_invalid(lambda: Comment("Buen curso", " "), "course is blank")


def test_comment_frozen() -> None:
    comment = Comment("Buen curso")
    field_name = "text"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(comment, field_name, "x")


def test_class_probabilities_out_of_range() -> None:
    assert_invalid(lambda: ClassProbabilities(1.2, -0.1, -0.1), "probability out of range")
    assert_invalid(lambda: ClassProbabilities(float("nan"), 0.5, 0.5), "probability out of range")


def test_class_probabilities_bad_sum() -> None:
    assert_invalid(lambda: ClassProbabilities(0.2, 0.3, 0.51), "probabilities do not sum to 1")


def test_class_probabilities_sum_tolerance() -> None:
    assert ClassProbabilities(0.2, 0.3, 0.5000005).positive == 0.5000005
    assert ClassProbabilities(0.1, 0.2, 0.7).positive == 0.7


def test_class_probabilities_of() -> None:
    assert ClassProbabilities(0.1, 0.2, 0.7).of(Polarity.NEUTRAL) == 0.2


def test_class_probabilities_top() -> None:
    assert ClassProbabilities(0.1, 0.2, 0.7).top() == Polarity.POSITIVE
    assert ClassProbabilities(0.4, 0.4, 0.2).top() == Polarity.NEGATIVE
    assert ClassProbabilities(0.2, 0.4, 0.4).top() == Polarity.NEUTRAL


def test_conformal_set_singleton() -> None:
    assert ConformalSet(frozenset({Polarity.POSITIVE}), 0.9).is_singleton is True
    assert ConformalSet(frozenset(), 0.9).is_singleton is False
    assert ConformalSet(frozenset({Polarity.NEGATIVE, Polarity.NEUTRAL}), 0.9).is_singleton is False


def test_conformal_set_confidence_bounds() -> None:
    labels = frozenset({Polarity.POSITIVE})
    assert_invalid(lambda: ConformalSet(labels, 0.0), "confidence_level out of range")
    assert_invalid(lambda: ConformalSet(labels, 1.0), "confidence_level out of range")
    assert ConformalSet(labels, 0.9).confidence_level == 0.9


def test_aspect_scores_present_not_cross_checked() -> None:
    scores = AspectScores(ZERO_SCORES, frozenset({AspectGroup.CONTENT}))
    assert scores.present == frozenset({AspectGroup.CONTENT})


def test_conformal_set_empty() -> None:
    assert ConformalSet(frozenset(), 0.9).labels == frozenset()


def test_aspect_scores_length() -> None:
    assert_invalid(
        lambda: AspectScores((0.0,) * 8, frozenset()), "aspect scores must have 9 values"
    )


def test_aspect_scores_range() -> None:
    assert_invalid(
        lambda: AspectScores((0.0,) * 8 + (1.5,), frozenset()), "aspect score out of range"
    )


def test_aspect_scores_score() -> None:
    scores = AspectScores((0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8), frozenset())
    assert scores.score(AspectGroup.MATERIALS) == 0.4


def test_aspect_sentiment_invalid() -> None:
    group, polarity = AspectGroup.CONTENT, Polarity.POSITIVE
    assert_invalid(lambda: AspectSentiment(group, polarity, 1.1, 0), "aspect score out of range")
    assert_invalid(lambda: AspectSentiment(group, polarity, 0.5, -1), "clause_index is negative")


def test_clause_analysis_blank_text() -> None:
    assert_invalid(
        lambda: ClauseAnalysis("", baseline_probabilities(), baseline_aspects()),
        "clause text is blank",
    )


def test_word_influence_invalid() -> None:
    assert_invalid(lambda: WordInfluence(" ", 0.1), "word is blank")
    assert_invalid(lambda: WordInfluence("curso", -1.5), "delta out of range")
    assert WordInfluence("curso", 1.0).delta == 1.0


def test_enums_order() -> None:
    assert tuple(str(polarity) for polarity in POLARITY_ORDER) == (
        "negative",
        "neutral",
        "positive",
    )
    assert len(ASPECT_ORDER) == 9
    assert ASPECT_ORDER[0] == "content"
    assert ASPECT_ORDER[-1] == "workload_pace"
    assert str(Polarity.POSITIVE) == "positive"


def test_entities_error_hierarchy() -> None:
    error = InvalidInputError("x")
    assert isinstance(error, AppError)
    assert error.code == "invalid_input"
    assert error.detail == "x"
    assert str(error) == "x"
