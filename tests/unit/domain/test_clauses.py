"""Tests for api/domain/clauses.py."""

from __future__ import annotations

import time

import pytest

from api.domain.clauses import _STRIP_CHARS, aspect_sentiments, split_clauses
from api.domain.entities import (
    ASPECT_ORDER,
    AspectGroup,
    AspectScores,
    AspectSentiment,
    ClassProbabilities,
    ClauseAnalysis,
    Polarity,
)
from api.domain.errors import InvalidInputError

TOP_POSITIVE = ClassProbabilities(0.1, 0.1, 0.8)
TOP_NEGATIVE = ClassProbabilities(0.7, 0.2, 0.1)


def make_clause(
    text: str,
    probabilities: ClassProbabilities,
    scores: dict[AspectGroup, float],
    present: set[AspectGroup],
) -> ClauseAnalysis:
    values = tuple(scores.get(group, 0.0) for group in ASPECT_ORDER)
    return ClauseAnalysis(text, probabilities, AspectScores(values, frozenset(present)))


def test_split_clauses_contract_vector() -> None:
    text = "El contenido fue claro, pero los parciales fueron difíciles. Sin embargo, buen horario."
    assert split_clauses(text) == (
        "El contenido fue claro",
        "los parciales fueron difíciles",
        "buen horario",
    )


def test_split_clauses_falls_back_when_all_pieces_short() -> None:
    assert split_clauses("Ok.") == ("Ok.",)


def test_split_clauses_strips_whitespace() -> None:
    assert split_clauses("  Bueno  ") == ("Bueno",)


def test_split_clauses_strips_unicode_whitespace() -> None:
    assert split_clauses("Bien.\xa0\xa0\xa0") == ("Bien",)
    assert all(char in _STRIP_CHARS for char in map(chr, range(0x3100)) if char.isspace())


def test_split_clauses_long_punctuation_run_is_linear() -> None:
    started = time.perf_counter()
    split_clauses("." * 100000 + "x")
    assert time.perf_counter() - started < 1.0


def test_split_clauses_keeps_decimal_number() -> None:
    assert split_clauses("Nota 3.5 pero injusta.") == ("Nota 3.5", "injusta")


def test_split_clauses_ellipsis_and_uppercase_connector() -> None:
    assert split_clauses("Bien... PERO lento!") == ("Bien", "lento")


def test_split_clauses_ignores_connector_inside_word() -> None:
    assert split_clauses("Me dolió el peroné, pero sigo.") == ("Me dolió el peroné", "sigo")


def test_split_clauses_aunque_and_no_obstante() -> None:
    text = "Clases buenas aunque largas; el material, no obstante, es pobre"
    assert split_clauses(text) == ("Clases buenas", "largas", "el material", "es pobre")


def test_split_clauses_mientras_que() -> None:
    text = "La plataforma falla mientras que el profesor ayuda."
    assert split_clauses(text) == ("La plataforma falla", "el profesor ayuda")


def test_split_clauses_double_space_is_not_connector() -> None:
    assert split_clauses("Sin  embargo bien") == ("Sin  embargo bien",)


def test_split_clauses_only_connector() -> None:
    assert split_clauses("pero") == ("pero",)


def test_split_clauses_drops_short_sentences() -> None:
    assert split_clauses("Sí. No. Tal vez.") == ("Tal vez",)


def test_split_clauses_keeps_inverted_marks() -> None:
    assert split_clauses("¿Qué? ¡Nada!") == ("¿Qué", "¡Nada")


@pytest.mark.parametrize("text", ["", "   "])
def test_split_clauses_rejects_empty_text(text: str) -> None:
    with pytest.raises(InvalidInputError) as info:
        split_clauses(text)
    assert info.value.detail == "text must not be empty"


def test_aspect_sentiments_contract_vector() -> None:
    content, assessment = AspectGroup.CONTENT, AspectGroup.ASSESSMENT
    clauses = (
        make_clause("clause zero", TOP_POSITIVE, {content: 0.9}, {content}),
        make_clause(
            "clause one", TOP_NEGATIVE, {content: 0.6, assessment: 0.8}, {content, assessment}
        ),
    )
    assert aspect_sentiments(clauses) == (
        AspectSentiment(content, Polarity.POSITIVE, 0.9, 0),
        AspectSentiment(assessment, Polarity.NEGATIVE, 0.8, 1),
    )


def test_aspect_sentiments_order_and_tie() -> None:
    content, platform = AspectGroup.CONTENT, AspectGroup.PLATFORM
    workload = AspectGroup.WORKLOAD_PACE
    clauses = (
        make_clause(
            "clause zero", TOP_POSITIVE, {platform: 0.7, workload: 0.4}, {platform, workload}
        ),
        make_clause("clause one", TOP_NEGATIVE, {platform: 0.7, content: 0.3}, {platform, content}),
    )
    assert aspect_sentiments(clauses) == (
        AspectSentiment(content, Polarity.NEGATIVE, 0.3, 1),
        AspectSentiment(platform, Polarity.POSITIVE, 0.7, 0),
        AspectSentiment(workload, Polarity.POSITIVE, 0.4, 0),
    )


def test_aspect_sentiments_ignores_groups_not_present() -> None:
    materials = AspectGroup.MATERIALS
    clauses = (make_clause("clause zero", TOP_POSITIVE, {materials: 0.95}, set()),)
    assert aspect_sentiments(clauses) == ()


def test_aspect_sentiments_empty_input() -> None:
    assert aspect_sentiments(()) == ()
