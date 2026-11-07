"""Tests for api/domain/decision.py."""

from __future__ import annotations

import dataclasses
import math

import pytest

from api.domain.decision import (
    CommentAnalysis,
    DecisionCosts,
    DecisionResult,
    decide,
)
from api.domain.entities import (
    AspectGroup,
    AspectSentiment,
    ClassProbabilities,
    Comment,
    ConformalSet,
    Decision,
    DecisionReason,
    Polarity,
)
from api.domain.errors import InvalidInputError

NEG, NEU, POS = Polarity.NEGATIVE, Polarity.NEUTRAL, Polarity.POSITIVE
DEFAULTS = DecisionCosts(5.0, 1.0, True)
FLAG_FALSE = DecisionCosts(5.0, 1.0, False)
ERROR_COST_DETAIL = "error_cost must be finite and > 0"
REVIEW_COST_DETAIL = "review_cost must be finite and > 0"
ASPECTS_DETAIL = "aspects must be unique and follow ASPECT_ORDER"


def _probs(a: float, b: float, c: float) -> ClassProbabilities:
    return ClassProbabilities(negative=a, neutral=b, positive=c)


def _set(*labels: Polarity) -> ConformalSet:
    return ConformalSet(labels=frozenset(labels), confidence_level=0.9)


def _check(
    probs: ClassProbabilities,
    conformal_set: ConformalSet,
    costs: DecisionCosts,
    expected: tuple[Decision, DecisionReason, Polarity],
) -> None:
    result = decide(probs, conformal_set, costs)
    assert (result.decision, result.reason, result.label) == expected


def test_decide_classifies_confident_singleton() -> None:
    _check(
        _probs(0.05, 0.10, 0.85),
        _set(POS),
        DEFAULTS,
        (Decision.CLASSIFY, DecisionReason.CONFIDENT, POS),
    )


def test_decide_reviews_when_expected_cost_exceeds_review_cost() -> None:
    _check(
        _probs(0.15, 0.25, 0.60),
        _set(POS),
        DEFAULTS,
        (Decision.REVIEW, DecisionReason.EXPECTED_COST, POS),
    )


def test_decide_classifies_at_threshold_080() -> None:
    _check(
        _probs(0.10, 0.10, 0.80),
        _set(POS),
        DEFAULTS,
        (Decision.CLASSIFY, DecisionReason.CONFIDENT, POS),
    )


def test_decide_reviews_set_not_singleton() -> None:
    _check(
        _probs(0.45, 0.40, 0.15),
        _set(NEG, NEU),
        DEFAULTS,
        (Decision.REVIEW, DecisionReason.SET_NOT_SINGLETON, NEG),
    )


def test_decide_reviews_empty_set() -> None:
    _check(
        _probs(0.30, 0.40, 0.30),
        _set(),
        DEFAULTS,
        (Decision.REVIEW, DecisionReason.EMPTY_SET, NEU),
    )


def test_decide_reviews_label_outside_set() -> None:
    _check(
        _probs(0.10, 0.82, 0.08),
        _set(NEG),
        DEFAULTS,
        (Decision.REVIEW, DecisionReason.LABEL_OUTSIDE_SET, NEU),
    )


def test_decide_classifies_multi_label_set_when_flag_false() -> None:
    _check(
        _probs(0.02, 0.90, 0.08),
        _set(NEU, POS),
        FLAG_FALSE,
        (Decision.CLASSIFY, DecisionReason.CONFIDENT, NEU),
    )


def test_decide_flag_false_falls_through_to_expected_cost() -> None:
    _check(
        _probs(0.30, 0.40, 0.30),
        _set(NEU, POS),
        FLAG_FALSE,
        (Decision.REVIEW, DecisionReason.EXPECTED_COST, NEU),
    )


def test_decide_flag_false_falls_through_to_label_outside_set() -> None:
    _check(
        _probs(0.50, 0.30, 0.20),
        _set(NEU, POS),
        FLAG_FALSE,
        (Decision.REVIEW, DecisionReason.LABEL_OUTSIDE_SET, NEG),
    )


def test_decide_empty_set_wins_with_flag_false() -> None:
    _check(
        _probs(0.30, 0.40, 0.30),
        _set(),
        FLAG_FALSE,
        (Decision.REVIEW, DecisionReason.EMPTY_SET, NEU),
    )


def test_decide_classifies_when_cost_equals_review_cost() -> None:
    _check(
        _probs(0.20, 0.30, 0.50),
        _set(POS),
        DecisionCosts(2.0, 1.0, True),
        (Decision.CLASSIFY, DecisionReason.CONFIDENT, POS),
    )


def test_decide_reviews_just_above_review_cost() -> None:
    _check(
        _probs(0.21, 0.30, 0.49),
        _set(POS),
        DecisionCosts(2.0, 1.0, True),
        (Decision.REVIEW, DecisionReason.EXPECTED_COST, POS),
    )


def test_decide_reviews_just_below_threshold_080() -> None:
    _check(
        _probs(0.10, 0.1001, 0.7999),
        _set(POS),
        DEFAULTS,
        (Decision.REVIEW, DecisionReason.EXPECTED_COST, POS),
    )


def test_decide_tie_uses_first_polarity() -> None:
    _check(
        _probs(0.40, 0.40, 0.20),
        _set(NEG),
        DEFAULTS,
        (Decision.REVIEW, DecisionReason.EXPECTED_COST, NEG),
    )


def test_decide_three_label_set_flag_false() -> None:
    _check(
        _probs(0.80, 0.10, 0.10),
        _set(NEG, NEU, POS),
        FLAG_FALSE,
        (Decision.CLASSIFY, DecisionReason.CONFIDENT, NEG),
    )


@pytest.mark.parametrize("error_cost", [0.0, -1.0, math.inf, math.nan])
def test_decision_costs_rejects_invalid_error_cost(error_cost: float) -> None:
    with pytest.raises(InvalidInputError) as info:
        DecisionCosts(error_cost, 1.0, True)
    assert info.value.detail == ERROR_COST_DETAIL


@pytest.mark.parametrize("review_cost", [0.0, -0.5, math.inf, math.nan])
def test_decision_costs_rejects_invalid_review_cost(review_cost: float) -> None:
    with pytest.raises(InvalidInputError) as info:
        DecisionCosts(5.0, review_cost, True)
    assert info.value.detail == REVIEW_COST_DETAIL


def test_decision_costs_checks_error_cost_first() -> None:
    with pytest.raises(InvalidInputError) as info:
        DecisionCosts(0.0, 0.0, True)
    assert info.value.detail == ERROR_COST_DETAIL


def test_decision_costs_accepts_defaults() -> None:
    costs = DecisionCosts(5.0, 1.0, True)
    assert (costs.error_cost, costs.review_cost, costs.review_if_set_not_singleton) == (
        5.0,
        1.0,
        True,
    )


def test_decision_result_is_frozen() -> None:
    result = DecisionResult(Decision.CLASSIFY, DecisionReason.CONFIDENT, POS)
    field_name = "decision"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(result, field_name, Decision.REVIEW)


def _analysis(aspects: tuple[AspectSentiment, ...]) -> CommentAnalysis:
    return CommentAnalysis(
        comment=Comment("Buen curso."),
        probabilities=_probs(0.05, 0.10, 0.85),
        conformal_set=_set(POS),
        decision=DecisionResult(Decision.CLASSIFY, DecisionReason.CONFIDENT, POS),
        aspects=aspects,
        influences=(),
    )


def _aspect(group: AspectGroup, polarity: Polarity, score: float) -> AspectSentiment:
    return AspectSentiment(group, polarity, score, 0)


def test_comment_analysis_accepts_ordered_aspects() -> None:
    analysis = _analysis(
        (
            _aspect(AspectGroup.CONTENT, POS, 0.9),
            _aspect(AspectGroup.PLATFORM, NEG, 0.8),
        )
    )
    assert len(analysis.aspects) == 2


def test_comment_analysis_rejects_repeated_group() -> None:
    with pytest.raises(InvalidInputError) as info:
        _analysis(
            (
                _aspect(AspectGroup.CONTENT, POS, 0.9),
                _aspect(AspectGroup.CONTENT, NEG, 0.8),
            )
        )
    assert info.value.detail == ASPECTS_DETAIL


def test_comment_analysis_rejects_out_of_order() -> None:
    with pytest.raises(InvalidInputError) as info:
        _analysis(
            (
                _aspect(AspectGroup.PLATFORM, NEG, 0.8),
                _aspect(AspectGroup.CONTENT, POS, 0.9),
            )
        )
    assert info.value.detail == ASPECTS_DETAIL


def test_comment_analysis_accepts_empty_aspects() -> None:
    assert _analysis(()).aspects == ()
