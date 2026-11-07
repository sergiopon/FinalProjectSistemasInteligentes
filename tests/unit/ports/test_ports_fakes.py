"""Fakes that conform to the ports of api/ports/; mypy --strict proves the conformance."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from api.domain.entities import (
    AspectScores,
    ClassProbabilities,
    ConformalSet,
    Decision,
    Polarity,
    WordInfluence,
)
from api.domain.reports import DriftReport, MetricsSnapshot, ModelInfo
from api.ports.models import AspectModel, Explainer, ModelStore, PolarityModel
from api.ports.monitoring import DriftDetector, MetricsStore
from api.ports.text import Anonymizer, Summarizer, TopicModel


class FakeModelStore:
    def info(self) -> ModelInfo:
        return ModelInfo(
            "v001", "2026-11-10T12:00:00Z", "0" * 64, "logistic_regression", "tfidf", 0.9, 0.61, 0.9
        )

    def bundle(self) -> Mapping[str, object]:
        return {"schema_version": 1}


class FakePolarityModel:
    def predict_proba(self, texts: Sequence[str]) -> tuple[ClassProbabilities, ...]:
        return tuple(ClassProbabilities(0.2, 0.3, 0.5) for _ in texts)

    def predict_set(self, texts: Sequence[str]) -> tuple[ConformalSet, ...]:
        return tuple(ConformalSet(frozenset({Polarity.POSITIVE}), 0.9) for _ in texts)


class FakeAspectModel:
    def detect(self, texts: Sequence[str]) -> tuple[AspectScores, ...]:
        return tuple(AspectScores((0.0,) * 9, frozenset()) for _ in texts)


class FakeExplainer:
    def explain(self, text: str, top_k: int) -> tuple[WordInfluence, ...]:
        return (WordInfluence("claro", 0.1),)[:top_k]


class FakeAnonymizer:
    def mask(self, text: str) -> str:
        return text


class FakeSummarizer:
    def summarize(self, texts: Sequence[str], k: int) -> tuple[str, ...]:
        return tuple(texts[:k])


class FakeTopicModel:
    def assign(self, texts: Sequence[str]) -> tuple[int, ...]:
        return (0,) * len(texts)

    def terms(self, topic: int) -> tuple[str, ...]:
        return ("a", "b", "c", "d", "e")


class FakeDriftDetector:
    def compare(self, texts: Sequence[str], body_sha256: str, created_at: str) -> DriftReport:
        return DriftReport(body_sha256, len(texts), 0.0, 0.0, 0.0, False, created_at)


class FakeMetricsStore:
    def record(self, route: str, latency_ms: float, decisions: Sequence[Decision]) -> None:
        return None

    def record_drift(self, report: DriftReport) -> None:
        return None

    def snapshot(self) -> MetricsSnapshot:
        return MetricsSnapshot(0, None, None, 0, 0, None)


def test_model_port_fakes_conform() -> None:
    store: ModelStore = FakeModelStore()
    polarity: PolarityModel = FakePolarityModel()
    aspects: AspectModel = FakeAspectModel()
    explainer: Explainer = FakeExplainer()
    assert store.info().version == "v001"
    assert store.bundle()["schema_version"] == 1
    assert len(polarity.predict_proba(["uno", "dos"])) == 2
    assert polarity.predict_set(["uno"])[0].labels == frozenset({Polarity.POSITIVE})
    assert len(aspects.detect(["uno"])) == 1
    assert explainer.explain("muy claro", 1) == (WordInfluence("claro", 0.1),)


def test_text_port_fakes_conform() -> None:
    anonymizer: Anonymizer = FakeAnonymizer()
    summarizer: Summarizer = FakeSummarizer()
    topics: TopicModel = FakeTopicModel()
    assert anonymizer.mask("Ana") == "Ana"
    assert summarizer.summarize(["a b c", "d e f"], 1) == ("a b c",)
    assert topics.assign(["x y", "z w"]) == (0, 0)
    assert len(topics.terms(0)) == 5


def test_monitoring_port_fakes_conform() -> None:
    store: MetricsStore = FakeMetricsStore()
    detector: DriftDetector = FakeDriftDetector()
    report = detector.compare(["texto uno"], "0" * 64, "2026-11-10T12:00:00Z")
    assert report.row_count == 1
    store.record("/predict", 12.5, [Decision.CLASSIFY])
    store.record_drift(report)
    assert store.snapshot().request_count == 0
