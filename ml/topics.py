"""KMeans topic model over course comments (spec 012)."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import silhouette_score

from api.domain.errors import InvalidInputError
from ml.schemas import SEED

logger = logging.getLogger(__name__)

_MIN_TEXTS: Final[int] = 50
_K_RANGE: Final[tuple[int, ...]] = (4, 5, 6, 7, 8, 9, 10)
_TERMS_PER_TOPIC: Final[int] = 5
_MIN_TERMS: Final[int] = 5
_MIN_CLUSTERS: Final[int] = 2


def fit_topics(
    texts: Sequence[str],
) -> tuple[TfidfVectorizer, KMeans, tuple[tuple[str, ...], ...]]:
    """Cluster comments into topics, choosing the cluster count by silhouette.

    Args:
        texts: Training texts, at least 50.

    Returns:
        The fitted vectorizer, the fitted KMeans and the top terms of each topic.

    Raises:
        InvalidInputError: Fewer than 50 texts or fewer than 5 vocabulary terms.
    """
    if len(texts) < _MIN_TEXTS:
        raise InvalidInputError("fit_topics needs at least 50 texts")
    vectorizer = TfidfVectorizer(min_df=5, max_df=0.2)
    matrix = _vectorize(vectorizer, texts)
    kmeans, silhouette = _best_kmeans(matrix)
    terms = _top_terms(kmeans, vectorizer.get_feature_names_out())
    logger.info(
        "topics_fitted rows=%d k=%d silhouette=%.4f", len(texts), kmeans.n_clusters, silhouette
    )
    return vectorizer, kmeans, terms


def _vectorize(vectorizer: TfidfVectorizer, texts: Sequence[str]) -> object:
    """Fit the vectorizer, mapping an empty vocabulary to the contract error."""
    try:
        matrix = vectorizer.fit_transform(list(texts))
    except ValueError as error:
        raise InvalidInputError("topic vocabulary has fewer than 5 terms") from error
    if len(vectorizer.vocabulary_) < _MIN_TERMS:
        raise InvalidInputError("topic vocabulary has fewer than 5 terms")
    return matrix


def _best_kmeans(matrix: object) -> tuple[KMeans, float]:
    """Fit KMeans for each candidate k and keep the best silhouette; ties go to the smaller k."""
    best: tuple[KMeans, float] | None = None
    for k in _K_RANGE:
        model = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(matrix)
        labels = model.labels_
        score = (
            float(silhouette_score(matrix, labels))
            if len(set(labels.tolist())) >= _MIN_CLUSTERS
            else -1.0
        )
        if best is None or score > best[1]:
            best = (model, score)
    if best is None:
        raise InvalidInputError("topic vocabulary has fewer than 5 terms")
    return best


def _top_terms(kmeans: KMeans, features: np.ndarray) -> tuple[tuple[str, ...], ...]:
    """Return the highest-weight terms of each cluster center."""
    return tuple(
        tuple(str(features[i]) for i in np.argsort(-center, kind="stable")[:_TERMS_PER_TOPIC])
        for center in kmeans.cluster_centers_
    )
