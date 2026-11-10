"""In-memory fake ports that record their calls; shared by the application and API tests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from api.adapters.monitoring import InMemoryMetricsStore
from api.adapters.settings import LimitSettings
from api.application.analyze import AnalyzeBatch, AnalyzeComment
from api.application.course_report import BuildCourseReport
from api.domain.decision import DecisionCosts
from api.domain.entities import (
    ASPECT_ORDER,
    AspectGroup,
    AspectScores,
    ClassProbabilities,
    ConformalSet,
    Polarity,
    WordInfluence,
)
from api.domain.errors import InvalidInputError
from api.domain.reports import DriftReport, ModelInfo
from api.ports.models import PolarityModel
from api.routes import Services

DEFAULT_PROBABILITIES: tuple[float, float, float] = (0.1, 0.1, 0.8)
DEFAULT_SET: frozenset[Polarity] = frozenset({Polarity.POSITIVE})


def _drop_last[T](items: tuple[T, ...], short_by: int) -> tuple[T, ...]:
    return items[: len(items) - short_by]


class FakePolarityModel:
    def __init__(
        self,
        probabilities: Mapping[str, tuple[float, float, float]],
        sets: Mapping[str, frozenset[Polarity]],
        confidence_level: float = 0.9,
        short_by: int = 0,
    ) -> None:
        self._probabilities = probabilities
        self._sets = sets
        self._confidence_level = confidence_level
        self._short_by = short_by
        self.proba_calls: list[tuple[str, ...]] = []
        self.set_calls: list[tuple[str, ...]] = []

    def predict_proba(self, texts: Sequence[str]) -> tuple[ClassProbabilities, ...]:
        self.proba_calls.append(tuple(texts))
        results = tuple(
            ClassProbabilities(*self._probabilities.get(text, DEFAULT_PROBABILITIES))
            for text in texts
        )
        return _drop_last(results, self._short_by)

    def predict_set(self, texts: Sequence[str]) -> tuple[ConformalSet, ...]:
        self.set_calls.append(tuple(texts))
        results = tuple(
            ConformalSet(self._sets.get(text, DEFAULT_SET), self._confidence_level)
            for text in texts
        )
        return _drop_last(results, self._short_by)


class FakeAspectModel:
    def __init__(
        self,
        scores: Mapping[str, Mapping[AspectGroup, float]],
        threshold: float = 0.5,
        short_by: int = 0,
    ) -> None:
        self._scores = scores
        self._threshold = threshold
        self._short_by = short_by
        self.detect_calls: list[tuple[str, ...]] = []

    def _detect_one(self, text: str) -> AspectScores:
        found = self._scores.get(text, {})
        values = tuple(found.get(group, 0.0) for group in ASPECT_ORDER)
        present = frozenset(group for group, score in found.items() if score >= self._threshold)
        return AspectScores(values, present)

    def detect(self, texts: Sequence[str]) -> tuple[AspectScores, ...]:
        self.detect_calls.append(tuple(texts))
        results = tuple(self._detect_one(text) for text in texts)
        return _drop_last(results, self._short_by)


class FakeExplainer:
    def __init__(self, influences: tuple[WordInfluence, ...]) -> None:
        self._influences = influences
        self.calls: list[tuple[str, int]] = []

    def explain(self, text: str, top_k: int) -> tuple[WordInfluence, ...]:
        self.calls.append((text, top_k))
        return self._influences[:top_k]


class FakeAnonymizer:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def mask(self, text: str) -> str:
        self.calls.append(text)
        return text.replace("Ana", "[PERSON]")


class FakeSummarizer:
    def __init__(self, empty: bool = False) -> None:
        self._empty = empty
        self.calls: list[tuple[tuple[str, ...], int]] = []

    def summarize(self, texts: Sequence[str], k: int) -> tuple[str, ...]:
        self.calls.append((tuple(texts), k))
        if self._empty:
            return ()
        return tuple(dict.fromkeys(texts))[:k]


class FakeTopicModel:
    def __init__(
        self,
        topic_by_text: Mapping[str, int],
        terms_by_topic: Mapping[int, tuple[str, ...]],
        short_by: int = 0,
    ) -> None:
        self._topic_by_text = topic_by_text
        self._terms_by_topic = terms_by_topic
        self._short_by = short_by
        self.assign_calls: list[tuple[str, ...]] = []

    def assign(self, texts: Sequence[str]) -> tuple[int, ...]:
        self.assign_calls.append(tuple(texts))
        results = tuple(self._topic_by_text.get(text, 0) for text in texts)
        return _drop_last(results, self._short_by)

    def terms(self, topic: int) -> tuple[str, ...]:
        if topic not in self._terms_by_topic:
            raise InvalidInputError("unknown topic")
        return self._terms_by_topic[topic]


class FakeDriftDetector:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], str, str]] = []

    def compare(self, texts: Sequence[str], body_sha256: str, created_at: str) -> DriftReport:
        self.calls.append((tuple(texts), body_sha256, created_at))
        return DriftReport(body_sha256, len(texts), 0.0, 0.0, 0.0, False, created_at)


class RaisingPolarityModel:
    def __init__(self, error: Exception) -> None:
        self._error = error

    def predict_proba(self, texts: Sequence[str]) -> tuple[ClassProbabilities, ...]:
        raise self._error

    def predict_set(self, texts: Sequence[str]) -> tuple[ConformalSet, ...]:
        raise self._error


C1_TEXT = "El contenido fue claro, pero los parciales fueron difíciles."
FIXED_CLOCK = "2026-11-05T12:00:00Z"


def make_services(
    polarity: PolarityModel | None = None, max_upload_bytes: int = 2097152
) -> Services:
    model = polarity or FakePolarityModel(
        {C1_TEXT: (0.31, 0.52, 0.17)},
        {C1_TEXT: frozenset({Polarity.NEGATIVE, Polarity.NEUTRAL})},
    )
    costs = DecisionCosts(5.0, 1.0, True)
    aspects = FakeAspectModel({})
    anonymizer = FakeAnonymizer()
    topics = FakeTopicModel({}, {0: ("curso", "clase", "tema", "contenido", "horario")})
    return Services(
        model_info=ModelInfo(
            "v001", FIXED_CLOCK, "0" * 64, "logistic_regression", "tfidf", 0.9, 0.61, 0.9
        ),
        analyze_comment=AnalyzeComment(model, aspects, FakeExplainer(()), costs),
        analyze_batch=AnalyzeBatch(model, aspects, anonymizer, costs),
        course_report=BuildCourseReport(anonymizer, FakeSummarizer(), topics),
        drift=FakeDriftDetector(),
        metrics=InMemoryMetricsStore(),
        limits=LimitSettings(
            max_text_chars=2000, max_upload_bytes=max_upload_bytes, max_upload_rows=5000
        ),
        clock=lambda: FIXED_CLOCK,
    )
