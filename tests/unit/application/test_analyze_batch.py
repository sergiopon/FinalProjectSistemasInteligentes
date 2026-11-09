from __future__ import annotations

import pytest

from api.application.analyze import AnalyzeBatch
from api.domain.decision import DecisionCosts, DecisionResult
from api.domain.entities import (
    AspectGroup,
    AspectSentiment,
    Comment,
    Decision,
    DecisionReason,
    Polarity,
)
from api.domain.errors import InferenceError, InvalidInputError
from tests.fixtures.fake_ports import FakeAnonymizer, FakeAspectModel, FakePolarityModel

COSTS = DecisionCosts(5.0, 1.0, True)
B0 = Comment("Ana dio buen contenido.", "Redes")
B1 = Comment("Los parciales fueron difíciles; el horario fue malo.", "Redes")
CLAUSE_0 = "Ana dio buen contenido"
CLAUSE_1A = "Los parciales fueron difíciles"
CLAUSE_1B = "el horario fue malo"


def polarity_model() -> FakePolarityModel:
    return FakePolarityModel(
        {B1.text: (0.60, 0.30, 0.10), CLAUSE_1A: (0.80, 0.15, 0.05), CLAUSE_1B: (0.70, 0.20, 0.10)},
        {B1.text: frozenset({Polarity.NEGATIVE})},
    )


def aspect_model(short_by: int = 0) -> FakeAspectModel:
    return FakeAspectModel(
        {
            CLAUSE_0: {AspectGroup.CONTENT: 0.9},
            CLAUSE_1A: {AspectGroup.ASSESSMENT: 0.8},
            CLAUSE_1B: {AspectGroup.ORGANIZATION_SCHEDULE: 0.7},
        },
        short_by=short_by,
    )


def use_case(
    polarity: FakePolarityModel | None = None,
    aspects: FakeAspectModel | None = None,
    anonymizer: FakeAnonymizer | None = None,
) -> AnalyzeBatch:
    return AnalyzeBatch(
        polarity or polarity_model(),
        aspects or aspect_model(),
        anonymizer or FakeAnonymizer(),
        COSTS,
    )


def test_analyze_batch_masks_text() -> None:
    anonymizer = FakeAnonymizer()
    result = use_case(anonymizer=anonymizer).execute((B0, B1))
    assert result[0].comment == Comment("[PERSON] dio buen contenido.", "Redes")
    assert result[1].comment.text == B1.text
    assert anonymizer.calls == [B0.text, B1.text]


def test_analyze_batch_decisions() -> None:
    result = use_case().execute((B0, B1))
    assert result[0].decision == DecisionResult(
        Decision.CLASSIFY, DecisionReason.CONFIDENT, Polarity.POSITIVE
    )
    assert result[1].decision == DecisionResult(
        Decision.REVIEW, DecisionReason.EXPECTED_COST, Polarity.NEGATIVE
    )


def test_analyze_batch_aspects() -> None:
    result = use_case().execute((B0, B1))
    assert result[0].aspects == (AspectSentiment(AspectGroup.CONTENT, Polarity.POSITIVE, 0.9, 0),)
    assert result[1].aspects == (
        AspectSentiment(AspectGroup.ASSESSMENT, Polarity.NEGATIVE, 0.8, 0),
        AspectSentiment(AspectGroup.ORGANIZATION_SCHEDULE, Polarity.NEGATIVE, 0.7, 1),
    )


def test_analyze_batch_one_call_per_port() -> None:
    polarity = polarity_model()
    aspects = aspect_model()
    use_case(polarity, aspects).execute((B0, B1))
    assert polarity.proba_calls == [(B0.text, B1.text), (CLAUSE_0, CLAUSE_1A, CLAUSE_1B)]
    assert polarity.set_calls == [(B0.text, B1.text)]
    assert aspects.detect_calls == [(CLAUSE_0, CLAUSE_1A, CLAUSE_1B)]


def test_analyze_batch_no_influences() -> None:
    assert all(item.influences == () for item in use_case().execute((B0, B1)))


def test_analyze_batch_rejects_empty() -> None:
    polarity = polarity_model()
    with pytest.raises(InvalidInputError) as error:
        use_case(polarity).execute(())
    assert error.value.detail == "batch must hold between 1 and 5000 comments"
    assert polarity.proba_calls == []


def test_analyze_batch_rejects_over_limit() -> None:
    comment = Comment("Buen curso.")
    with pytest.raises(InvalidInputError):
        use_case().execute([comment] * 5001)
    assert len(use_case().execute([comment] * 5000)) == 5000


def test_analyze_batch_chunks_clauses() -> None:
    polarity = polarity_model()
    aspects = aspect_model()
    result = use_case(polarity, aspects).execute(
        [Comment("Uno bueno; dos bueno; tres bueno.")] * 2500
    )
    assert [len(call) for call in polarity.proba_calls] == [2500, 5000, 2500]
    assert [len(call) for call in aspects.detect_calls] == [5000, 2500]
    assert len(result) == 2500


def test_analyze_batch_short_aspect_result() -> None:
    with pytest.raises(InferenceError) as error:
        use_case(aspects=aspect_model(short_by=1)).execute((B0, B1))
    assert error.value.detail == "AspectModel.detect returned 2 results for 3 texts"
