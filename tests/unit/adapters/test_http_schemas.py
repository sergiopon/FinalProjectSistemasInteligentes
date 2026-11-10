"""Tests for api/adapters/http_schemas.py."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from api.adapters.http_schemas import (
    PredictRequest,
    PriorityJson,
    ProbabilitiesJson,
    batch_response,
    drift_report_json,
    metrics_response,
    model_info_json,
    predict_response,
)
from api.domain.decision import CommentAnalysis, DecisionResult
from api.domain.entities import (
    ASPECT_ORDER,
    AspectGroup,
    AspectSentiment,
    ClassProbabilities,
    Comment,
    ConformalSet,
    Decision,
    DecisionReason,
    Polarity,
    WordInfluence,
)
from api.domain.reports import (
    AspectCell,
    CourseReport,
    DriftReport,
    MetricsSnapshot,
    ModelInfo,
    PolarityCounts,
)

TEXT = "El contenido fue claro, pero los parciales fueron difíciles."
SHA = "a" * 64
NOW = "2026-11-10T12:00:00Z"


def review_analysis() -> CommentAnalysis:
    return CommentAnalysis(
        comment=Comment(TEXT),
        probabilities=ClassProbabilities(0.31, 0.52, 0.17),
        conformal_set=ConformalSet(frozenset({Polarity.NEGATIVE, Polarity.NEUTRAL}), 0.9),
        decision=DecisionResult(
            Decision.REVIEW, DecisionReason.SET_NOT_SINGLETON, Polarity.NEUTRAL
        ),
        aspects=(
            AspectSentiment(AspectGroup.CONTENT, Polarity.POSITIVE, 0.91, 0),
            AspectSentiment(AspectGroup.ASSESSMENT, Polarity.NEGATIVE, 0.77, 1),
        ),
        influences=(WordInfluence("difíciles", 0.14), WordInfluence("claro", -0.09)),
    )


def classify_analysis() -> CommentAnalysis:
    return CommentAnalysis(
        comment=Comment("Muy buen curso", "Bases de datos"),
        probabilities=ClassProbabilities(0.05, 0.05, 0.9),
        conformal_set=ConformalSet(frozenset({Polarity.POSITIVE}), 0.9),
        decision=DecisionResult(Decision.CLASSIFY, DecisionReason.CONFIDENT, Polarity.POSITIVE),
        aspects=(),
        influences=(),
    )


def course_report() -> CourseReport:
    cells = tuple(AspectCell(group, 0, 0, 0, 0) for group in ASPECT_ORDER)
    return CourseReport("Bases de datos", 2, 1, PolarityCounts(0, 1, 1), cells, (), (), ())


def test_predict_request_strips_text() -> None:
    assert PredictRequest.model_validate_json('{"text": "  hola  "}').text == "hola"


@pytest.mark.parametrize(
    "body",
    [
        '{"text": "   "}',
        '{"text": 123}',
        '{"text": null}',
        "{}",
        '{"text": "x", "extra": 1}',
        json.dumps({"text": "a" * 2001}),
    ],
)
def test_predict_request_rejects_invalid(body: str) -> None:
    with pytest.raises(ValidationError):
        PredictRequest.model_validate_json(body)


def test_predict_request_accepts_2000_after_strip() -> None:
    body = json.dumps({"text": "  " + "a" * 2000 + "  "})
    assert len(PredictRequest.model_validate_json(body).text) == 2000


def test_predict_response_matches_contract_example() -> None:
    expected = {
        "model_version": "v001",
        "text": TEXT,
        "predicted": "neutral",
        "probabilities": {"negative": 0.31, "neutral": 0.52, "positive": 0.17},
        "conformal_set": ["negative", "neutral"],
        "confidence_level": 0.9,
        "decision": "review",
        "reason": "set_not_singleton",
        "aspects": [
            {"group": "content", "polarity": "positive", "score": 0.91},
            {"group": "assessment", "polarity": "negative", "score": 0.77},
        ],
        "influences": [{"word": "difíciles", "delta": 0.14}, {"word": "claro", "delta": -0.09}],
    }
    assert predict_response(review_analysis(), "v001").model_dump(mode="json") == expected


def test_rounding_four_decimals() -> None:
    values = ProbabilitiesJson(negative=0.333333333, neutral=0.333333333, positive=0.333333334)
    assert values.model_dump() == {"negative": 0.3333, "neutral": 0.3333, "positive": 0.3333}
    priority = PriorityJson(
        rank=1,
        group="content",
        mentions=4,
        negative=1,
        prevalence=0.4,
        smoothed_negative_share=0.2619,
        score=0.104761904,
        low_support=False,
    )
    assert priority.model_dump()["score"] == 0.1048
    report = batch_response([], [course_report()], "v001").model_dump_json()
    assert '"negative_share":null' in report


def test_batch_response_numbers_rows_and_counts() -> None:
    result = batch_response(
        [classify_analysis(), review_analysis()], [course_report()], "v001"
    ).model_dump(mode="json")
    assert result["row_count"] == 2
    assert [row["row"] for row in result["rows"]] == [1, 2]
    assert result["decision_counts"] == {"classify": 1, "review": 1}
    assert result["rows"][0]["course"] == "Bases de datos"
    assert result["rows"][1]["course"] is None
    assert result["courses"][0]["course"] == "Bases de datos"


def test_metrics_response_shape() -> None:
    snapshot = MetricsSnapshot(10, 12.5, 40.1, 7, 3, None)
    assert metrics_response(snapshot).model_dump(mode="json") == {
        "request_count": 10,
        "latency_ms": {"p50": 12.5, "p95": 40.1},
        "decisions": {"classify": 7, "review": 3},
        "abstention_rate": 0.3,
        "last_drift": None,
    }


def test_model_info_and_drift_json_fields() -> None:
    info = ModelInfo("v001", NOW, SHA, "logistic_regression", "tfidf", 0.9, 0.61, 0.9)
    assert list(model_info_json(info).model_dump()) == list(vars_of(info))
    drift = DriftReport(SHA, 5, 0.1, 0.2, 0.2, False, NOW)
    assert list(drift_report_json(drift).model_dump()) == list(vars_of(drift))
    with_drift = metrics_response(MetricsSnapshot(1, None, None, 0, 0, drift))
    assert with_drift.last_drift == drift_report_json(drift)


def vars_of(entity: ModelInfo | DriftReport) -> tuple[str, ...]:
    return tuple(entity.__dataclass_fields__)
