"""Use cases that analyze one comment or a batch of comments."""

from __future__ import annotations

from collections.abc import Sequence

from api.domain.clauses import aspect_sentiments, split_clauses
from api.domain.decision import CommentAnalysis, DecisionCosts, decide
from api.domain.entities import (
    AspectScores,
    AspectSentiment,
    ClassProbabilities,
    ClauseAnalysis,
    Comment,
    ConformalSet,
)
from api.domain.errors import InferenceError, InvalidInputError
from api.ports.models import AspectModel, Explainer, PolarityModel
from api.ports.text import Anonymizer

MAX_PORT_TEXTS: int = 5000
MIN_INFLUENCE_COUNT: int = 1
MAX_INFLUENCE_COUNT: int = 20


def _checked[T](results: tuple[T, ...], expected: int, port: str) -> tuple[T, ...]:
    """Return the port results when there is one per text.

    Args:
        results: Results returned by the port.
        expected: Number of texts sent to the port.
        port: Port method name used in the error detail.

    Returns:
        The same results.

    Raises:
        InferenceError: The number of results differs from the number of texts.
    """
    if len(results) != expected:
        raise InferenceError(f"{port} returned {len(results)} results for {expected} texts")
    return results


def _chunks(texts: Sequence[str]) -> tuple[Sequence[str], ...]:
    """Split texts into consecutive slices of at most MAX_PORT_TEXTS items, in order."""
    return tuple(
        texts[start : start + MAX_PORT_TEXTS] for start in range(0, len(texts), MAX_PORT_TEXTS)
    )


def _clause_sentiments(
    polarity: PolarityModel, aspects: AspectModel, clause_groups: Sequence[tuple[str, ...]]
) -> tuple[tuple[AspectSentiment, ...], ...]:
    """Return the aspect sentiments of each group of clauses, in order.

    Args:
        polarity: Polarity model applied to every clause.
        aspects: Aspect model applied to every clause.
        clause_groups: Clauses of each comment.

    Returns:
        One tuple of aspect sentiments per group.

    Raises:
        InferenceError: A port returns a wrong number of results or fails.
    """
    flat = tuple(clause for group in clause_groups for clause in group)
    probabilities: list[ClassProbabilities] = []
    scores: list[AspectScores] = []
    for piece in _chunks(flat):
        probabilities.extend(
            _checked(polarity.predict_proba(piece), len(piece), "PolarityModel.predict_proba")
        )
        scores.extend(_checked(aspects.detect(piece), len(piece), "AspectModel.detect"))
    result: list[tuple[AspectSentiment, ...]] = []
    start = 0
    for group in clause_groups:
        analyses = tuple(
            ClauseAnalysis(text, probabilities[start + index], scores[start + index])
            for index, text in enumerate(group)
        )
        result.append(aspect_sentiments(analyses))
        start += len(group)
    return tuple(result)


class AnalyzeComment:
    """Analyzes the caller's own comment, with word influences (POST /predict)."""

    def __init__(
        self,
        polarity: PolarityModel,
        aspects: AspectModel,
        explainer: Explainer,
        costs: DecisionCosts,
        influence_count: int = 5,
    ) -> None:
        """Store the dependencies.

        Args:
            polarity: Polarity model.
            aspects: Aspect model.
            explainer: Word influence explainer.
            costs: Decision costs.
            influence_count: Number of word influences returned, 1 to 20.

        Raises:
            InvalidInputError: influence_count is outside 1..20.
        """
        if not MIN_INFLUENCE_COUNT <= influence_count <= MAX_INFLUENCE_COUNT:
            raise InvalidInputError("influence_count must be between 1 and 20")
        self._polarity = polarity
        self._aspects = aspects
        self._explainer = explainer
        self._costs = costs
        self._influence_count = influence_count

    def execute(self, comment: Comment) -> CommentAnalysis:
        """Analyze one comment.

        Args:
            comment: The comment; its text is returned unmasked (SEC-02).

        Returns:
            The full analysis of the comment.

        Raises:
            InferenceError: A port returns a wrong number of results or fails.
        """
        texts = (comment.text,)
        probabilities = _checked(
            self._polarity.predict_proba(texts), 1, "PolarityModel.predict_proba"
        )[0]
        conformal_set: ConformalSet = _checked(
            self._polarity.predict_set(texts), 1, "PolarityModel.predict_set"
        )[0]
        decision = decide(probabilities, conformal_set, self._costs)
        clauses = split_clauses(comment.text)
        sentiments = _clause_sentiments(self._polarity, self._aspects, (clauses,))[0]
        influences = self._explainer.explain(comment.text, self._influence_count)
        return CommentAnalysis(
            comment, probabilities, conformal_set, decision, sentiments, influences
        )


class AnalyzeBatch:
    """Analyzes a batch of comments and masks their text (POST /predict-batch)."""

    def __init__(
        self,
        polarity: PolarityModel,
        aspects: AspectModel,
        anonymizer: Anonymizer,
        costs: DecisionCosts,
    ) -> None:
        """Store the dependencies.

        Args:
            polarity: Polarity model.
            aspects: Aspect model.
            anonymizer: Masks personal data in the returned texts.
            costs: Decision costs.
        """
        self._polarity = polarity
        self._aspects = aspects
        self._anonymizer = anonymizer
        self._costs = costs

    def execute(self, comments: Sequence[Comment]) -> tuple[CommentAnalysis, ...]:
        """Analyze a batch of comments.

        Args:
            comments: 1 to 5000 comments.

        Returns:
            One analysis per comment, in input order, with the text masked and no influences.

        Raises:
            InvalidInputError: The batch is empty or holds more than 5000 comments.
            InferenceError: A port returns a wrong number of results or fails.
            AnonymizerUnavailableError: The anonymizer fails.
        """
        if not 1 <= len(comments) <= MAX_PORT_TEXTS:
            raise InvalidInputError("batch must hold between 1 and 5000 comments")
        texts = tuple(comment.text for comment in comments)
        count = len(texts)
        probabilities = _checked(
            self._polarity.predict_proba(texts), count, "PolarityModel.predict_proba"
        )
        sets = _checked(self._polarity.predict_set(texts), count, "PolarityModel.predict_set")
        decisions = [decide(p, s, self._costs) for p, s in zip(probabilities, sets, strict=True)]
        groups = tuple(split_clauses(text) for text in texts)
        sentiments = _clause_sentiments(self._polarity, self._aspects, groups)
        masked = [Comment(self._anonymizer.mask(c.text), c.course) for c in comments]
        return tuple(
            CommentAnalysis(masked[i], probabilities[i], sets[i], decisions[i], sentiments[i], ())
            for i in range(count)
        )
