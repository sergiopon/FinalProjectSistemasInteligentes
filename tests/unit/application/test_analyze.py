from __future__ import annotations

import pytest

from api.application.analyze import AnalyzeComment
from api.domain.decision import DecisionCosts, DecisionResult
from api.domain.entities import (
    AspectGroup,
    AspectSentiment,
    ClassProbabilities,
    Comment,
    Decision,
    DecisionReason,
    Polarity,
    WordInfluence,
)
from api.domain.errors import InferenceError, InvalidInputError
from tests.fixtures.fake_ports import FakeAspectModel, FakeExplainer, FakePolarityModel

COSTS = DecisionCosts(5.0, 1.0, True)
C1 = Comment("El contenido fue claro, pero los parciales fueron difíciles.")
CLAUSE_A = "El contenido fue claro"
CLAUSE_B = "los parciales fueron difíciles"
INFLUENCES = (WordInfluence("difíciles", 0.14), WordInfluence("claro", -0.09))


def polarity_model(short_by: int = 0) -> FakePolarityModel:
    return FakePolarityModel(
        {C1.text: (0.31, 0.52, 0.17), CLAUSE_A: (0.05, 0.10, 0.85), CLAUSE_B: (0.80, 0.15, 0.05)},
        {C1.text: frozenset({Polarity.NEGATIVE, Polarity.NEUTRAL})},
        short_by=short_by,
    )


def aspect_model() -> FakeAspectModel:
    return FakeAspectModel(
        {CLAUSE_A: {AspectGroup.CONTENT: 0.91}, CLAUSE_B: {AspectGroup.ASSESSMENT: 0.77}}
    )


def use_case(
    polarity: FakePolarityModel | None = None,
    aspects: FakeAspectModel | None = None,
    explainer: FakeExplainer | None = None,
    influence_count: int = 5,
) -> AnalyzeComment:
    return AnalyzeComment(
        polarity or polarity_model(),
        aspects or aspect_model(),
        explainer or FakeExplainer(INFLUENCES),
        COSTS,
        influence_count,
    )


def test_analyze_comment_returns_decision() -> None:
    result = use_case().execute(C1)
    assert result.decision == DecisionResult(
        Decision.REVIEW, DecisionReason.SET_NOT_SINGLETON, Polarity.NEUTRAL
    )
    assert result.probabilities == ClassProbabilities(0.31, 0.52, 0.17)
    assert result.conformal_set.labels == frozenset({Polarity.NEGATIVE, Polarity.NEUTRAL})


def test_analyze_comment_aspects_from_clauses() -> None:
    assert use_case().execute(C1).aspects == (
        AspectSentiment(AspectGroup.CONTENT, Polarity.POSITIVE, 0.91, 0),
        AspectSentiment(AspectGroup.ASSESSMENT, Polarity.NEGATIVE, 0.77, 1),
    )


def test_analyze_comment_port_calls() -> None:
    polarity = polarity_model()
    aspects = aspect_model()
    explainer = FakeExplainer(INFLUENCES)
    use_case(polarity, aspects, explainer).execute(C1)
    assert polarity.proba_calls == [(C1.text,), (CLAUSE_A, CLAUSE_B)]
    assert polarity.set_calls == [(C1.text,)]
    assert aspects.detect_calls == [(CLAUSE_A, CLAUSE_B)]
    assert explainer.calls == [(C1.text, 5)]


def test_analyze_comment_returns_unmasked_text() -> None:
    comment = Comment("Ana explicó bien.", "Redes")
    result = use_case().execute(comment)
    assert result.comment is comment
    assert result.comment.text == "Ana explicó bien."


def test_analyze_comment_influences_limited() -> None:
    explainer = FakeExplainer(INFLUENCES)
    result = use_case(explainer=explainer, influence_count=1).execute(C1)
    assert result.influences == (WordInfluence("difíciles", 0.14),)
    assert explainer.calls == [(C1.text, 1)]


def test_analyze_comment_rejects_influence_count() -> None:
    for count in (0, 21):
        with pytest.raises(InvalidInputError) as error:
            use_case(influence_count=count)
        assert error.value.detail == "influence_count must be between 1 and 20"
    use_case(influence_count=20)
    use_case(influence_count=1)


def test_analyze_comment_short_port_result() -> None:
    with pytest.raises(InferenceError) as error:
        use_case(polarity_model(short_by=1)).execute(C1)
    assert error.value.detail == "PolarityModel.predict_proba returned 0 results for 1 texts"


def test_analyze_comment_confident_default() -> None:
    result = use_case().execute(Comment("Buen curso."))
    assert result.decision == DecisionResult(
        Decision.CLASSIFY, DecisionReason.CONFIDENT, Polarity.POSITIVE
    )
    assert result.aspects == ()
