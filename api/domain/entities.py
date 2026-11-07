"""Domain entities and enums exchanged between layers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from api.domain.errors import InvalidInputError


class Polarity(StrEnum):
    """Sentiment class of a comment, in class-index order."""

    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    POSITIVE = "positive"


class Decision(StrEnum):
    """Outcome of the decision agent."""

    CLASSIFY = "classify"
    REVIEW = "review"


class DecisionReason(StrEnum):
    """Rule that produced a decision."""

    CONFIDENT = "confident"
    EMPTY_SET = "empty_set"
    SET_NOT_SINGLETON = "set_not_singleton"
    LABEL_OUTSIDE_SET = "label_outside_set"
    EXPECTED_COST = "expected_cost"


class AspectGroup(StrEnum):
    """Aspect group of a course evaluation, in canonical order."""

    CONTENT = "content"
    ASSESSMENT = "assessment"
    FEEDBACK = "feedback"
    METHODOLOGY_CLARITY = "methodology_clarity"
    MATERIALS = "materials"
    ORGANIZATION_SCHEDULE = "organization_schedule"
    PLATFORM = "platform"
    COMMUNICATION_CLIMATE = "communication_climate"
    WORKLOAD_PACE = "workload_pace"


POLARITY_ORDER: Final[tuple[Polarity, ...]] = tuple(Polarity)
ASPECT_ORDER: Final[tuple[AspectGroup, ...]] = tuple(AspectGroup)
PROBABILITY_SUM_TOLERANCE: Final[float] = 1e-6


@dataclass(frozen=True, slots=True)
class Comment:
    """A student comment, optionally tied to a course.

    Attributes:
        text: Comment text, not blank.
        course: Course name, or None when unknown; not blank when given.
    """

    text: str
    course: str | None = None

    def __post_init__(self) -> None:
        """Reject a blank text or a blank course."""
        if self.text.strip() == "":
            raise InvalidInputError("comment text is blank")
        if self.course is not None and self.course.strip() == "":
            raise InvalidInputError("course is blank")


@dataclass(frozen=True, slots=True)
class ClassProbabilities:
    """Probability of each polarity class.

    Attributes:
        negative: Probability of the negative class.
        neutral: Probability of the neutral class.
        positive: Probability of the positive class.
    """

    negative: float
    neutral: float
    positive: float

    def __post_init__(self) -> None:
        """Reject values outside the unit range or a sum that is not 1."""
        if not all(0.0 <= value <= 1.0 for value in (self.negative, self.neutral, self.positive)):
            raise InvalidInputError("probability out of range")
        total = self.negative + self.neutral + self.positive
        if abs(total - 1.0) > PROBABILITY_SUM_TOLERANCE:
            raise InvalidInputError("probabilities do not sum to 1")

    def of(self, polarity: Polarity) -> float:
        """Return the probability of the given polarity."""
        if polarity is Polarity.NEGATIVE:
            return self.negative
        if polarity is Polarity.NEUTRAL:
            return self.neutral
        return self.positive

    def top(self) -> Polarity:
        """Return the most probable polarity; a tie goes to the first in POLARITY_ORDER."""
        return max(POLARITY_ORDER, key=self.of)


@dataclass(frozen=True, slots=True)
class ConformalSet:
    """Conformal prediction set of a comment.

    Attributes:
        labels: Polarities kept in the set; empty means the model cannot decide.
        confidence_level: Coverage the set was calibrated for, strictly between 0 and 1.
    """

    labels: frozenset[Polarity]
    confidence_level: float

    def __post_init__(self) -> None:
        """Reject a confidence level outside the open interval (0, 1)."""
        if not 0.0 < self.confidence_level < 1.0:
            raise InvalidInputError("confidence_level out of range")

    @property
    def is_singleton(self) -> bool:
        """Whether the set holds exactly one label."""
        return len(self.labels) == 1


@dataclass(frozen=True, slots=True)
class AspectScores:
    """Presence score of every aspect group for one text.

    Attributes:
        scores: One score per group, in ASPECT_ORDER.
        present: Groups whose score reached their threshold.
    """

    scores: tuple[float, ...]
    present: frozenset[AspectGroup]

    def __post_init__(self) -> None:
        """Reject a wrong number of scores or a score outside the unit range."""
        if len(self.scores) != len(ASPECT_ORDER):
            raise InvalidInputError("aspect scores must have 9 values")
        if not all(0.0 <= score <= 1.0 for score in self.scores):
            raise InvalidInputError("aspect score out of range")

    def score(self, group: AspectGroup) -> float:
        """Return the score of the given group."""
        return self.scores[ASPECT_ORDER.index(group)]


@dataclass(frozen=True, slots=True)
class AspectSentiment:
    """Polarity expressed about one aspect group in one clause.

    Attributes:
        group: Aspect group mentioned.
        polarity: Polarity of the clause.
        score: Presence score of the group, in the unit range.
        clause_index: Zero-based position of the clause in the comment.
    """

    group: AspectGroup
    polarity: Polarity
    score: float
    clause_index: int

    def __post_init__(self) -> None:
        """Reject a score outside the unit range or a negative clause index."""
        if not 0.0 <= self.score <= 1.0:
            raise InvalidInputError("aspect score out of range")
        if self.clause_index < 0:
            raise InvalidInputError("clause_index is negative")


@dataclass(frozen=True, slots=True)
class ClauseAnalysis:
    """Model output for one clause of a comment.

    Attributes:
        text: Clause text, not blank.
        probabilities: Polarity probabilities of the clause.
        aspects: Aspect scores of the clause.
    """

    text: str
    probabilities: ClassProbabilities
    aspects: AspectScores

    def __post_init__(self) -> None:
        """Reject a blank clause text."""
        if self.text.strip() == "":
            raise InvalidInputError("clause text is blank")


@dataclass(frozen=True, slots=True)
class WordInfluence:
    """Change in the predicted class probability caused by one word.

    Attributes:
        word: The word, not blank.
        delta: Probability change, between -1 and 1.
    """

    word: str
    delta: float

    def __post_init__(self) -> None:
        """Reject a blank word or a delta outside -1 and 1."""
        if self.word.strip() == "":
            raise InvalidInputError("word is blank")
        if not -1.0 <= self.delta <= 1.0:
            raise InvalidInputError("delta out of range")
