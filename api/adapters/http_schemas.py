"""Pydantic request and response models of the HTTP API and the builders that fill them."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Final

from pydantic import BaseModel, ConfigDict, PlainSerializer, field_validator

from api.domain.decision import CommentAnalysis
from api.domain.entities import (
    POLARITY_ORDER,
    AspectSentiment,
    ClassProbabilities,
    Decision,
    WordInfluence,
)
from api.domain.reports import (
    AspectCell,
    CourseReport,
    DriftReport,
    MetricsSnapshot,
    ModelInfo,
    PriorityEntry,
    TopicSummary,
)

MAX_TEXT_CHARS: Final[int] = 2000
FLOAT_DECIMALS: Final[int] = 4


def round_float(value: float) -> float:
    """Round a float to FLOAT_DECIMALS decimals.

    Args:
        value: Number to round.

    Returns:
        The rounded number.
    """
    return round(value, FLOAT_DECIMALS)


Rounded = Annotated[float, PlainSerializer(round_float, return_type=float)]


class _Model(BaseModel):
    """Base of every HTTP model: immutable."""

    model_config = ConfigDict(frozen=True)


class PredictRequest(_Model):
    """Body of POST /predict."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str

    @field_validator("text", mode="after")
    @classmethod
    def _strip_and_bound(cls, text: str) -> str:
        stripped = text.strip()
        if not 1 <= len(stripped) <= MAX_TEXT_CHARS:
            raise ValueError("text length out of range")
        return stripped


class ProbabilitiesJson(_Model):
    """Polarity probabilities."""

    negative: Rounded
    neutral: Rounded
    positive: Rounded


class AspectJson(_Model):
    """Polarity expressed about one aspect group."""

    group: str
    polarity: str
    score: Rounded


class InfluenceJson(_Model):
    """Influence of one word on the predicted class."""

    word: str
    delta: Rounded


class PredictResponse(_Model):
    """Response of POST /predict."""

    model_version: str
    text: str
    predicted: str
    probabilities: ProbabilitiesJson
    conformal_set: list[str]
    confidence_level: Rounded
    decision: str
    reason: str
    aspects: list[AspectJson]
    influences: list[InfluenceJson]


class RowJson(_Model):
    """One analyzed row of a batch."""

    row: int
    course: str | None
    text: str
    predicted: str
    probabilities: ProbabilitiesJson
    conformal_set: list[str]
    decision: str
    reason: str
    aspects: list[AspectJson]


class DecisionCountsJson(_Model):
    """Comments classified and sent to review."""

    classify: int
    review: int


class PolarityCountsJson(_Model):
    """Comments per polarity."""

    negative: int
    neutral: int
    positive: int


class AspectCellJson(_Model):
    """Mentions of one aspect group split by polarity."""

    group: str
    mentions: int
    negative: int
    neutral: int
    positive: int
    negative_share: Rounded | None


class PriorityJson(_Model):
    """One row of a course priority ranking."""

    rank: int
    group: str
    mentions: int
    negative: int
    prevalence: Rounded
    smoothed_negative_share: Rounded
    score: Rounded
    low_support: bool


class TopicJson(_Model):
    """A topic of a course."""

    topic: int
    size: int
    terms: list[str]
    quote: str


class CourseReportJson(_Model):
    """Aggregated view of one course."""

    course: str
    comment_count: int
    review_count: int
    polarity_counts: PolarityCountsJson
    aspects: list[AspectCellJson]
    priorities: list[PriorityJson]
    topics: list[TopicJson]
    quotes: list[str]


class BatchResponse(_Model):
    """Response of POST /predict-batch."""

    model_version: str
    row_count: int
    decision_counts: DecisionCountsJson
    rows: list[RowJson]
    courses: list[CourseReportJson]


class DriftReportJson(_Model):
    """Response of POST /drift."""

    body_sha256: str
    row_count: int
    length_psi: Rounded
    oov_rate: Rounded
    reference_oov_rate: Rounded
    drifted: bool
    created_at: str


class LatencyJson(_Model):
    """Latency percentiles in milliseconds."""

    p50: Rounded | None
    p95: Rounded | None


class MetricsResponse(_Model):
    """Response of GET /metrics."""

    request_count: int
    latency_ms: LatencyJson
    decisions: DecisionCountsJson
    abstention_rate: Rounded | None
    last_drift: DriftReportJson | None


class ModelInfoJson(_Model):
    """Response of GET /model."""

    version: str
    created_at: str
    dataset_sha256: str
    polarity_model: str
    representation: str
    confidence_level: Rounded
    test_macro_f1: Rounded
    empirical_coverage: Rounded


class HealthResponse(_Model):
    """Response of GET /health."""

    status: str
    model_version: str


class ErrorResponse(_Model):
    """Body of every error response."""

    error: str
    message: str
    request_id: str


def _probabilities_json(probabilities: ClassProbabilities) -> ProbabilitiesJson:
    return ProbabilitiesJson(
        negative=probabilities.negative,
        neutral=probabilities.neutral,
        positive=probabilities.positive,
    )


def _aspect_json(aspect: AspectSentiment) -> AspectJson:
    return AspectJson(group=aspect.group.value, polarity=aspect.polarity.value, score=aspect.score)


def _influence_json(influence: WordInfluence) -> InfluenceJson:
    return InfluenceJson(word=influence.word, delta=influence.delta)


def _conformal_labels(analysis: CommentAnalysis) -> list[str]:
    return [item.value for item in POLARITY_ORDER if item in analysis.conformal_set.labels]


def predict_response(analysis: CommentAnalysis, model_version: str) -> PredictResponse:
    """Build the response of POST /predict.

    Args:
        analysis: Analysis of one comment.
        model_version: Version of the active model bundle.

    Returns:
        The response model.
    """
    return PredictResponse(
        model_version=model_version,
        text=analysis.comment.text,
        predicted=analysis.decision.label.value,
        probabilities=_probabilities_json(analysis.probabilities),
        conformal_set=_conformal_labels(analysis),
        confidence_level=analysis.conformal_set.confidence_level,
        decision=analysis.decision.decision.value,
        reason=analysis.decision.reason.value,
        aspects=[_aspect_json(item) for item in analysis.aspects],
        influences=[_influence_json(item) for item in analysis.influences],
    )


def _row_json(position: int, analysis: CommentAnalysis) -> RowJson:
    return RowJson(
        row=position,
        course=analysis.comment.course,
        text=analysis.comment.text,
        predicted=analysis.decision.label.value,
        probabilities=_probabilities_json(analysis.probabilities),
        conformal_set=_conformal_labels(analysis),
        decision=analysis.decision.decision.value,
        reason=analysis.decision.reason.value,
        aspects=[_aspect_json(item) for item in analysis.aspects],
    )


def _aspect_cell_json(cell: AspectCell) -> AspectCellJson:
    return AspectCellJson(
        group=cell.group.value,
        mentions=cell.mentions,
        negative=cell.negative,
        neutral=cell.neutral,
        positive=cell.positive,
        negative_share=cell.negative_share,
    )


def _priority_json(entry: PriorityEntry) -> PriorityJson:
    return PriorityJson(
        rank=entry.rank,
        group=entry.group.value,
        mentions=entry.mentions,
        negative=entry.negative,
        prevalence=entry.prevalence,
        smoothed_negative_share=entry.smoothed_negative_share,
        score=entry.score,
        low_support=entry.low_support,
    )


def _topic_json(topic: TopicSummary) -> TopicJson:
    return TopicJson(topic=topic.topic, size=topic.size, terms=list(topic.terms), quote=topic.quote)


def course_report_json(report: CourseReport) -> CourseReportJson:
    """Convert a course report to its HTTP model.

    Args:
        report: Aggregated view of one course.

    Returns:
        The HTTP model.
    """
    counts = report.polarity_counts
    return CourseReportJson(
        course=report.course,
        comment_count=report.comment_count,
        review_count=report.review_count,
        polarity_counts=PolarityCountsJson(
            negative=counts.negative, neutral=counts.neutral, positive=counts.positive
        ),
        aspects=[_aspect_cell_json(cell) for cell in report.aspects],
        priorities=[_priority_json(entry) for entry in report.priorities],
        topics=[_topic_json(topic) for topic in report.topics],
        quotes=list(report.quotes),
    )


def batch_response(
    analyses: Sequence[CommentAnalysis], reports: Sequence[CourseReport], model_version: str
) -> BatchResponse:
    """Build the response of POST /predict-batch.

    Args:
        analyses: One analysis per data row, in file order.
        reports: One report per course.
        model_version: Version of the active model bundle.

    Returns:
        The response model; rows are numbered from 1.
    """
    classified = sum(1 for item in analyses if item.decision.decision is Decision.CLASSIFY)
    reviewed = sum(1 for item in analyses if item.decision.decision is Decision.REVIEW)
    return BatchResponse(
        model_version=model_version,
        row_count=len(analyses),
        decision_counts=DecisionCountsJson(classify=classified, review=reviewed),
        rows=[_row_json(position, item) for position, item in enumerate(analyses, start=1)],
        courses=[course_report_json(report) for report in reports],
    )


def drift_report_json(report: DriftReport) -> DriftReportJson:
    """Convert a drift report to its HTTP model.

    Args:
        report: Result of a drift check.

    Returns:
        The HTTP model.
    """
    return DriftReportJson(
        body_sha256=report.body_sha256,
        row_count=report.row_count,
        length_psi=report.length_psi,
        oov_rate=report.oov_rate,
        reference_oov_rate=report.reference_oov_rate,
        drifted=report.drifted,
        created_at=report.created_at,
    )


def metrics_response(snapshot: MetricsSnapshot) -> MetricsResponse:
    """Build the response of GET /metrics.

    Args:
        snapshot: Service metrics at one moment.

    Returns:
        The response model.
    """
    drift = snapshot.last_drift
    return MetricsResponse(
        request_count=snapshot.request_count,
        latency_ms=LatencyJson(p50=snapshot.p50_ms, p95=snapshot.p95_ms),
        decisions=DecisionCountsJson(
            classify=snapshot.classify_count, review=snapshot.review_count
        ),
        abstention_rate=snapshot.abstention_rate,
        last_drift=None if drift is None else drift_report_json(drift),
    )


def model_info_json(info: ModelInfo) -> ModelInfoJson:
    """Convert model metadata to its HTTP model.

    Args:
        info: Metadata of the active model bundle.

    Returns:
        The HTTP model.
    """
    return ModelInfoJson(
        version=info.version,
        created_at=info.created_at,
        dataset_sha256=info.dataset_sha256,
        polarity_model=info.polarity_model,
        representation=info.representation,
        confidence_level=info.confidence_level,
        test_macro_f1=info.test_macro_f1,
        empirical_coverage=info.empirical_coverage,
    )
