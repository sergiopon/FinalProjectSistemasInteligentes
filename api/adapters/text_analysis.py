"""Summarizer and topic model adapters over the vectorizer and KMeans stored in the bundle."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final, cast

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer

from api.domain.errors import InferenceError, InvalidInputError, ModelIntegrityError

SENTENCE_SPLIT: Final[re.Pattern[str]] = re.compile(r"[.!?]+(?=\s|$)")
MAX_TEXTS: Final = 5000
MIN_K: Final = 1
MAX_K: Final = 10
TERMS_PER_TOPIC: Final = 5


def _check_texts(texts: Sequence[str]) -> None:
    if not MIN_K <= len(texts) <= MAX_TEXTS:
        raise InvalidInputError("texts must hold 1 to 5000 items")
    if any(text.strip() == "" for text in texts):
        raise InvalidInputError("texts must be non-empty after strip")


def _check_vectorizer(vectorizer: object) -> None:
    if not isinstance(vectorizer, TfidfVectorizer) or not hasattr(vectorizer, "vocabulary_"):
        raise ModelIntegrityError("topic vectorizer is invalid")


def _split_sentences(texts: Sequence[str]) -> tuple[str, ...]:
    """Split texts into stripped sentences, keeping the first occurrence of each."""
    sentences: dict[str, None] = {}
    for text in texts:
        for piece in SENTENCE_SPLIT.split(text):
            sentence = piece.strip()
            if sentence:
                sentences.setdefault(sentence)
    return tuple(sentences)


def _centroid_cosines(vectorizer: object, sentences: Sequence[str]) -> tuple[float, ...]:
    """Cosine of each sentence vector with the mean vector, 0.0 when either norm is 0."""
    try:
        matrix = cast("TfidfVectorizer", vectorizer).transform(list(sentences))
        centroid = np.asarray(matrix.mean(axis=0)).ravel()
        dots = np.asarray(matrix @ centroid).ravel()
        norms = np.sqrt(np.asarray(matrix.multiply(matrix).sum(axis=1)).ravel())
    except (ValueError, AttributeError) as error:
        raise InferenceError("summarizer failed") from error
    denominators = norms * float(np.linalg.norm(centroid))
    return tuple(
        float(dot / den) if den > 0.0 else 0.0 for dot, den in zip(dots, denominators, strict=True)
    )


def _check_terms(terms: tuple[tuple[str, ...], ...], n_clusters: int) -> None:
    valid = len(terms) == n_clusters and all(
        len(topic) == TERMS_PER_TOPIC and all(term != "" for term in topic) for topic in terms
    )
    if not valid:
        raise ModelIntegrityError("topic terms are invalid")


class CentroidSummarizer:
    """Picks the sentences closest to the centroid of all sentences.

    Args:
        vectorizer: Fitted TfidfVectorizer of the bundle.

    Raises:
        ModelIntegrityError: If the vectorizer is not a fitted TfidfVectorizer.
    """

    def __init__(self, vectorizer: object) -> None:
        _check_vectorizer(vectorizer)
        self._vectorizer = vectorizer

    def summarize(self, texts: Sequence[str], k: int) -> tuple[str, ...]:
        """Return up to k representative sentences, most representative first.

        Args:
            texts: 1 to 5000 non-blank texts.
            k: Number of sentences, 1 to 10.

        Returns:
            Distinct sentences taken from the texts; empty when no sentence remains.

        Raises:
            InvalidInputError: If texts or k are out of range.
            InferenceError: If the vectorizer fails.
        """
        _check_texts(texts)
        if not MIN_K <= k <= MAX_K:
            raise InvalidInputError("k must be between 1 and 10")
        sentences = _split_sentences(texts)
        if not sentences:
            return ()
        cosines = _centroid_cosines(self._vectorizer, sentences)
        order = sorted(range(len(sentences)), key=lambda index: (-cosines[index], index))
        return tuple(sentences[index] for index in order[:k])


class KMeansTopicModel:
    """Assigns texts to the topics of the trained KMeans and names them with stored terms.

    Args:
        vectorizer: Fitted TfidfVectorizer of the bundle.
        kmeans: Fitted KMeans of the bundle.
        terms: One tuple of 5 non-empty terms per cluster.

    Raises:
        ModelIntegrityError: If the vectorizer, kmeans or terms are invalid.
    """

    def __init__(
        self, vectorizer: object, kmeans: object, terms: tuple[tuple[str, ...], ...]
    ) -> None:
        _check_vectorizer(vectorizer)
        if not isinstance(kmeans, KMeans) or not hasattr(kmeans, "cluster_centers_"):
            raise ModelIntegrityError("topic kmeans is invalid")
        _check_terms(terms, kmeans.n_clusters)
        self._vectorizer = cast("TfidfVectorizer", vectorizer)
        self._kmeans = kmeans
        self._terms = terms

    def assign(self, texts: Sequence[str]) -> tuple[int, ...]:
        """Return the topic id of each text.

        Args:
            texts: 1 to 5000 non-blank texts.

        Returns:
            One topic id per text, same order.

        Raises:
            InvalidInputError: If texts are out of range.
            InferenceError: If the model fails.
        """
        _check_texts(texts)
        try:
            labels = self._kmeans.predict(self._vectorizer.transform(list(texts)))
        except ValueError as error:
            raise InferenceError("topic assignment failed") from error
        return tuple(int(label) for label in labels)

    def terms(self, topic: int) -> tuple[str, ...]:
        """Return the 5 terms of a topic.

        Args:
            topic: Trained topic id.

        Returns:
            The terms describing the topic.

        Raises:
            InvalidInputError: If topic is not a trained topic id.
        """
        if not 0 <= topic < len(self._terms):
            raise InvalidInputError("unknown topic id")
        return self._terms[topic]
