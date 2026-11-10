"""Tests for ml/topics.py."""

from __future__ import annotations

import pytest

from api.domain.errors import InvalidInputError
from ml.topics import fit_topics

THEMES = (
    ("alfa", "beta", "gamma", "delta", "epsilon"),
    ("rojo", "verde", "azul", "negro", "blanco"),
    ("lunes", "martes", "jueves", "viernes", "sabado"),
    ("perro", "gato", "raton", "conejo", "caballo"),
    ("mesa", "silla", "lampara", "puerta", "ventana"),
    ("pera", "manzana", "uva", "mango", "fresa"),
)


def make_texts() -> list[str]:
    return [
        f"curso {w[i % 5]} {w[(i + 1) % 5]} {w[(i + 2) % 5]}" for w in THEMES for i in range(10)
    ]


def assert_invalid(detail: str, info: pytest.ExceptionInfo[InvalidInputError]) -> None:
    assert info.value.detail == detail


def test_fit_topics_selects_k_by_silhouette() -> None:
    texts = make_texts()
    vectorizer, kmeans, _ = fit_topics(texts)
    assert kmeans.n_clusters == 6
    labels = kmeans.predict(vectorizer.transform(texts))
    assert sorted(labels.tolist().count(t) for t in range(6)) == [10] * 6


def test_fit_topics_drops_frequent_words() -> None:
    vectorizer, _, _ = fit_topics(make_texts())
    assert "curso" not in vectorizer.vocabulary_
    assert len(vectorizer.vocabulary_) == 30


def test_fit_topics_terms_are_alphabetical_on_ties() -> None:
    _, _, terms = fit_topics(make_texts())
    assert {tuple(sorted(theme)) for theme in THEMES} == set(terms)
    assert ("azul", "blanco", "negro", "rojo", "verde") in terms
    assert ("alfa", "beta", "delta", "epsilon", "gamma") in terms


def test_fit_topics_assign_matches_terms() -> None:
    vectorizer, kmeans, terms = fit_topics(make_texts())
    topic = int(kmeans.predict(vectorizer.transform(["rojo verde azul"]))[0])
    assert terms[topic] == ("azul", "blanco", "negro", "rojo", "verde")


def test_fit_topics_rejects_too_few_texts() -> None:
    with pytest.raises(InvalidInputError) as info:
        fit_topics(make_texts()[:49])
    assert_invalid("fit_topics needs at least 50 texts", info)


def test_fit_topics_rejects_empty_vocabulary() -> None:
    with pytest.raises(InvalidInputError) as info:
        fit_topics(["curso uno"] * 50)
    assert_invalid("topic vocabulary has fewer than 5 terms", info)
