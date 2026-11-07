"""Domain entities of course reports, drift checks, metrics and model metadata."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Final

from api.domain.entities import ASPECT_ORDER, AspectGroup
from api.domain.errors import InvalidInputError

SHA256_PATTERN: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{64}")
UTC_TIMESTAMP_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z"
)
VERSION_PATTERN: Final[re.Pattern[str]] = re.compile(r"v[0-9]{3}")


@dataclass(frozen=True, slots=True)
class PolarityCounts:
    """Number of comments per polarity.

    Attributes:
        negative: Negative comments.
        neutral: Neutral comments.
        positive: Positive comments.
    """

    negative: int
    neutral: int
    positive: int

    def __post_init__(self) -> None:
        """Reject a negative count."""
        if min(self.negative, self.neutral, self.positive) < 0:
            raise InvalidInputError("count is negative")


@dataclass(frozen=True, slots=True)
class AspectCell:
    """Mentions of one aspect group split by polarity.

    Attributes:
        group: Aspect group.
        mentions: Total mentions.
        negative: Negative mentions.
        neutral: Neutral mentions.
        positive: Positive mentions.
    """

    group: AspectGroup
    mentions: int
    negative: int
    neutral: int
    positive: int

    def __post_init__(self) -> None:
        """Reject a negative count or polarity counts that do not add up to the mentions."""
        counts = (self.mentions, self.negative, self.neutral, self.positive)
        if min(counts) < 0:
            raise InvalidInputError("count is negative")
        if self.negative + self.neutral + self.positive != self.mentions:
            raise InvalidInputError("aspect counts do not sum to mentions")

    @property
    def negative_share(self) -> float | None:
        """Share of negative mentions, or None when there are no mentions."""
        if self.mentions == 0:
            return None
        return self.negative / self.mentions


@dataclass(frozen=True, slots=True)
class PriorityEntry:
    """One row of the priority ranking of a course.

    Attributes:
        rank: Position in the ranking, starting at 1.
        group: Aspect group ranked.
        mentions: Total mentions of the group.
        negative: Negative mentions of the group.
        prevalence: Share of comments that mention the group, in the unit range.
        smoothed_negative_share: Smoothed share of negative mentions, in the unit range.
        score: Priority score, in the unit range.
        low_support: True when there are too few mentions to trust the row.
    """

    rank: int
    group: AspectGroup
    mentions: int
    negative: int
    prevalence: float
    smoothed_negative_share: float
    score: float
    low_support: bool

    def __post_init__(self) -> None:
        """Reject a rank below 1 or a float outside the unit range."""
        if self.rank < 1:
            raise InvalidInputError("rank is below 1")
        values = (self.prevalence, self.smoothed_negative_share, self.score)
        if not all(0.0 <= value <= 1.0 for value in values):
            raise InvalidInputError("priority value out of range")


@dataclass(frozen=True, slots=True)
class TopicSummary:
    """A topic found in a course's comments.

    Attributes:
        topic: Topic id, zero or more.
        size: Comments assigned to the topic, at least 1.
        terms: Terms that describe the topic.
        quote: Anonymized representative sentence.
    """

    topic: int
    size: int
    terms: tuple[str, ...]
    quote: str

    def __post_init__(self) -> None:
        """Reject a negative topic id or a size below 1."""
        if self.topic < 0:
            raise InvalidInputError("topic is negative")
        if self.size < 1:
            raise InvalidInputError("topic size is below 1")


@dataclass(frozen=True, slots=True)
class CourseReport:
    """Aggregated view of one course.

    Attributes:
        course: Course name.
        comment_count: Comments analyzed.
        review_count: Comments sent to human review.
        polarity_counts: Comments per polarity.
        aspects: One cell per aspect group, in ASPECT_ORDER.
        priorities: Priority ranking.
        topics: Topics found.
        quotes: Anonymized representative quotes.
    """

    course: str
    comment_count: int
    review_count: int
    polarity_counts: PolarityCounts
    aspects: tuple[AspectCell, ...]
    priorities: tuple[PriorityEntry, ...]
    topics: tuple[TopicSummary, ...]
    quotes: tuple[str, ...]

    def __post_init__(self) -> None:
        """Reject aspect cells that are not the 9 groups in order or a bad review count."""
        if tuple(cell.group for cell in self.aspects) != ASPECT_ORDER:
            raise InvalidInputError("aspects must be the 9 groups in order")
        if not 0 <= self.review_count <= self.comment_count:
            raise InvalidInputError("review_count out of range")


@dataclass(frozen=True, slots=True)
class DriftReport:
    """Result of comparing an uploaded batch with the training reference.

    Attributes:
        body_sha256: SHA-256 of the uploaded body, 64 lowercase hex characters.
        row_count: Rows compared.
        length_psi: Population stability index of the text lengths.
        oov_rate: Out-of-vocabulary rate of the batch.
        reference_oov_rate: Out-of-vocabulary rate of the training reference.
        drifted: True when the batch moved away from the reference.
        created_at: UTC timestamp such as 2026-11-10T12:00:00Z.
    """

    body_sha256: str
    row_count: int
    length_psi: float
    oov_rate: float
    reference_oov_rate: float
    drifted: bool
    created_at: str

    def __post_init__(self) -> None:
        """Reject a malformed hash or timestamp."""
        if SHA256_PATTERN.fullmatch(self.body_sha256) is None:
            raise InvalidInputError("body_sha256 is not 64 lowercase hex")
        if UTC_TIMESTAMP_PATTERN.fullmatch(self.created_at) is None:
            raise InvalidInputError("created_at is not ISO 8601 UTC")
        try:
            datetime.fromisoformat(self.created_at)
        except ValueError:
            raise InvalidInputError("created_at is not ISO 8601 UTC") from None


@dataclass(frozen=True, slots=True)
class MetricsSnapshot:
    """Service metrics at one moment.

    Attributes:
        request_count: Requests recorded.
        p50_ms: Median latency in milliseconds, or None without data.
        p95_ms: 95th percentile latency in milliseconds, or None without data.
        classify_count: Comments classified automatically.
        review_count: Comments sent to human review.
        last_drift: Last drift report, or None.
    """

    request_count: int
    p50_ms: float | None
    p95_ms: float | None
    classify_count: int
    review_count: int
    last_drift: DriftReport | None

    def __post_init__(self) -> None:
        """Reject a negative count."""
        if min(self.request_count, self.classify_count, self.review_count) < 0:
            raise InvalidInputError("count is negative")

    @property
    def abstention_rate(self) -> float | None:
        """Share of comments sent to review, or None when nothing was decided."""
        decided = self.classify_count + self.review_count
        if decided == 0:
            return None
        return self.review_count / decided


@dataclass(frozen=True, slots=True)
class ModelInfo:
    """Metadata of the active model bundle.

    Attributes:
        version: Bundle version such as v001.
        created_at: UTC creation timestamp.
        dataset_sha256: SHA-256 of the training dataset.
        polarity_model: Name of the selected polarity model.
        representation: Name of the text representation.
        confidence_level: Conformal coverage target.
        test_macro_f1: Macro-F1 on the held-out test split.
        empirical_coverage: Conformal coverage measured on the test split.
    """

    version: str
    created_at: str
    dataset_sha256: str
    polarity_model: str
    representation: str
    confidence_level: float
    test_macro_f1: float
    empirical_coverage: float

    def __post_init__(self) -> None:
        """Reject a version that does not match vNNN."""
        if VERSION_PATTERN.fullmatch(self.version) is None:
            raise InvalidInputError("version does not match vNNN")
