"""Decision agent: classify a comment or send it to human review."""

from __future__ import annotations

import math
from dataclasses import dataclass

from api.domain.entities import (
    ASPECT_ORDER,
    AspectSentiment,
    ClassProbabilities,
    Comment,
    ConformalSet,
    Decision,
    DecisionReason,
    Polarity,
    WordInfluence,
)
from api.domain.errors import InvalidInputError

_COST_TOLERANCE: float = 1e-12


@dataclass(frozen=True, slots=True)
class DecisionCosts:
    """Costs that drive the decision rules.

    Attributes:
        error_cost: Cost of a wrong automatic label, finite and above 0.
        review_cost: Cost of sending a comment to review, finite and above 0.
        review_if_set_not_singleton: Whether a conformal set with several labels forces review.
    """

    error_cost: float
    review_cost: float
    review_if_set_not_singleton: bool

    def __post_init__(self) -> None:
        """Reject a cost that is not finite or not above 0, checking error_cost first."""
        if not math.isfinite(self.error_cost) or self.error_cost <= 0.0:
            raise InvalidInputError("error_cost must be finite and > 0")
        if not math.isfinite(self.review_cost) or self.review_cost <= 0.0:
            raise InvalidInputError("review_cost must be finite and > 0")


@dataclass(frozen=True, slots=True)
class DecisionResult:
    """Outcome of the decision agent for one comment.

    Attributes:
        decision: Whether to classify automatically or send to review.
        reason: Rule that produced the decision.
        label: Most probable polarity, also when the decision is review.
    """

    decision: Decision
    reason: DecisionReason
    label: Polarity


@dataclass(frozen=True, slots=True)
class CommentAnalysis:
    """Full analysis of one comment.

    Attributes:
        comment: The analyzed comment.
        probabilities: Polarity probabilities of the whole text.
        conformal_set: Conformal set of the whole text.
        decision: Outcome of the decision agent.
        aspects: Aspect sentiments, one per group at most, in ASPECT_ORDER.
        influences: Word influences on the predicted class.
    """

    comment: Comment
    probabilities: ClassProbabilities
    conformal_set: ConformalSet
    decision: DecisionResult
    aspects: tuple[AspectSentiment, ...]
    influences: tuple[WordInfluence, ...]

    def __post_init__(self) -> None:
        """Reject aspects with a repeated group or out of ASPECT_ORDER."""
        positions = [ASPECT_ORDER.index(item.group) for item in self.aspects]
        if any(later <= earlier for earlier, later in zip(positions, positions[1:], strict=False)):
            raise InvalidInputError("aspects must be unique and follow ASPECT_ORDER")


def decide(
    probabilities: ClassProbabilities, conformal_set: ConformalSet, costs: DecisionCosts
) -> DecisionResult:
    """Decide whether a comment is classified automatically or reviewed.

    The first rule that matches wins:

    1. Empty conformal set: review, EMPTY_SET.
    2. More than one label and review_if_set_not_singleton: review, SET_NOT_SINGLETON.
    3. Top label outside the set: review, LABEL_OUTSIDE_SET.
    4. Expected error cost above review_cost plus a tolerance: review, EXPECTED_COST.
    5. Otherwise: classify, CONFIDENT.

    Args:
        probabilities: Polarity probabilities of the comment.
        conformal_set: Conformal set of the comment; its confidence level is not read.
        costs: Validated decision costs.

    Returns:
        The decision, the rule that produced it and the top label (a tie goes to the first
        polarity in POLARITY_ORDER), which is set also when the decision is review.
    """
    label = probabilities.top()
    labels = conformal_set.labels
    if len(labels) == 0:
        return DecisionResult(Decision.REVIEW, DecisionReason.EMPTY_SET, label)
    if len(labels) > 1 and costs.review_if_set_not_singleton:
        return DecisionResult(Decision.REVIEW, DecisionReason.SET_NOT_SINGLETON, label)
    if label not in labels:
        return DecisionResult(Decision.REVIEW, DecisionReason.LABEL_OUTSIDE_SET, label)
    expected_cost = (1.0 - probabilities.of(label)) * costs.error_cost
    if expected_cost > costs.review_cost + _COST_TOLERANCE:
        return DecisionResult(Decision.REVIEW, DecisionReason.EXPECTED_COST, label)
    return DecisionResult(Decision.CLASSIFY, DecisionReason.CONFIDENT, label)
