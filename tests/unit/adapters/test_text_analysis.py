"""Tests for CentroidSummarizer and KMeansTopicModel in api/adapters/text_analysis.py."""

from __future__ import annotations

import pytest
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from api.adapters.text_analysis import CentroidSummarizer, KMeansTopicModel
from api.domain.errors import InvalidInputError, ModelIntegrityError

CORPUS = [
    "el profesor explica claro",
    "el profesor explica bien",
    "los parciales fueron difíciles",
    "los parciales fueron largos",
    "el horario fue cómodo",
    "el horario fue tarde",
]
TERMS = (
    ("parciales", "fueron", "difíciles", "largos", "evaluación"),
    ("horario", "fue", "cómodo", "tarde", "tiempo"),
    ("profesor", "explica", "claro", "bien", "clase"),
)


@pytest.fixture(scope="module")
def vectorizer() -> TfidfVectorizer:
    return TfidfVectorizer().fit(CORPUS)


@pytest.fixture(scope="module")
def kmeans(vectorizer: TfidfVectorizer) -> KMeans:
    return KMeans(n_clusters=3, n_init=10, random_state=42).fit(vectorizer.transform(CORPUS))


def test_summarizer_ranks_by_centroid_cosine(vectorizer: TfidfVectorizer) -> None:
    texts = [
        "El profesor explica claro. Los parciales fueron difíciles!",
        "El profesor explica claro y bien. El horario fue cómodo.",
    ]
    result = CentroidSummarizer(vectorizer).summarize(texts, 3)
    assert result == (
        "El profesor explica claro",
        "El profesor explica claro y bien",
        "El horario fue cómodo",
    )


def test_summarizer_unknown_words_keep_order(vectorizer: TfidfVectorizer) -> None:
    assert CentroidSummarizer(vectorizer).summarize(["zzz qqq. www."], 2) == ("zzz qqq", "www")


def test_summarizer_drops_duplicates(vectorizer: TfidfVectorizer) -> None:
    texts = ["El horario fue cómodo", "El horario fue cómodo... ¿Por qué?"]
    result = CentroidSummarizer(vectorizer).summarize(texts, 5)
    assert result == ("El horario fue cómodo", "¿Por qué")


def test_summarizer_punctuation_only_returns_empty(vectorizer: TfidfVectorizer) -> None:
    assert CentroidSummarizer(vectorizer).summarize(["!!!"], 1) == ()


@pytest.mark.parametrize("k", [0, 11])
def test_summarizer_rejects_k_out_of_range(vectorizer: TfidfVectorizer, k: int) -> None:
    with pytest.raises(InvalidInputError):
        CentroidSummarizer(vectorizer).summarize(["a b"], k)


@pytest.mark.parametrize("texts", [[], ["a b"] * 5001, ["ok", "  "]])
def test_summarizer_rejects_invalid_texts(vectorizer: TfidfVectorizer, texts: list[str]) -> None:
    with pytest.raises(InvalidInputError):
        CentroidSummarizer(vectorizer).summarize(texts, 1)


@pytest.mark.parametrize("bad", [TfidfVectorizer(), "x"])
def test_summarizer_rejects_unfitted_vectorizer(bad: object) -> None:
    with pytest.raises(ModelIntegrityError) as info:
        CentroidSummarizer(bad)
    assert info.value.detail == "topic vectorizer is invalid"


def test_topics_assign_matches_training_labels(vectorizer: TfidfVectorizer, kmeans: KMeans) -> None:
    model = KMeansTopicModel(vectorizer, kmeans, TERMS)
    result = model.assign(["el profesor explica", "el horario fue cómodo"])
    expected = tuple(int(v) for v in kmeans.predict(vectorizer.transform(CORPUS))[[0, 4]])
    assert result == expected
    assert all(type(value) is int for value in result)


def test_topics_terms_returns_tuple(vectorizer: TfidfVectorizer, kmeans: KMeans) -> None:
    model = KMeansTopicModel(vectorizer, kmeans, TERMS)
    assert model.terms(0) == TERMS[0]
    for topic in (3, -1):
        with pytest.raises(InvalidInputError) as info:
            model.terms(topic)
        assert info.value.detail == "unknown topic id"


@pytest.mark.parametrize(
    "terms",
    [TERMS + (TERMS[2],), TERMS[:2] + (TERMS[2][:4],)],
)
def test_topics_rejects_invalid_terms(
    vectorizer: TfidfVectorizer, kmeans: KMeans, terms: tuple[tuple[str, ...], ...]
) -> None:
    with pytest.raises(ModelIntegrityError) as info:
        KMeansTopicModel(vectorizer, kmeans, terms)
    assert info.value.detail == "topic terms are invalid"


def test_topics_rejects_empty_term(vectorizer: TfidfVectorizer, kmeans: KMeans) -> None:
    terms = (TERMS[0], TERMS[1], ("a", "", "c", "d", "e"))
    with pytest.raises(ModelIntegrityError):
        KMeansTopicModel(vectorizer, kmeans, terms)


def test_topics_rejects_invalid_kmeans(vectorizer: TfidfVectorizer) -> None:
    with pytest.raises(ModelIntegrityError) as info:
        KMeansTopicModel(vectorizer, "x", TERMS)
    assert info.value.detail == "topic kmeans is invalid"


def test_topics_assign_rejects_empty_sequence(vectorizer: TfidfVectorizer, kmeans: KMeans) -> None:
    with pytest.raises(InvalidInputError):
        KMeansTopicModel(vectorizer, kmeans, TERMS).assign([])
