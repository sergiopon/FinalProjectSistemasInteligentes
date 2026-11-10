"""Template groups and the grouped splitter shared by every cross-validation in ml (spec 008).

The dataset has no author column and its texts come from shared templates, so near-identical
comments are grouped and kept on the same side of every split (ADR-001).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_distances
from sklearn.model_selection import StratifiedGroupKFold

from api.domain.errors import InvalidInputError
from ml.schemas import SEED

logger = logging.getLogger(__name__)

N_SPLITS: Final[int] = 5
TEMPLATE_DISTANCE_THRESHOLD: Final[float] = 0.7
MIN_GROUP_TEXTS: Final[int] = 2


def template_groups(texts: Sequence[str]) -> np.ndarray:
    """Assign a template group id to each text.

    Texts are compared by character 3-5 gram TF-IDF and clustered by average linkage on the
    cosine distance, cut at ``TEMPLATE_DISTANCE_THRESHOLD``.

    Args:
        texts: Cleaned comment texts.

    Returns:
        One group label per text, dtype ``int64``.

    Raises:
        InvalidInputError: Fewer than ``MIN_GROUP_TEXTS`` texts, or a blank text.
    """
    _validate_texts(texts)
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
    distances = cosine_distances(vectorizer.fit_transform(list(texts)))
    clustering = AgglomerativeClustering(
        n_clusters=None,
        metric="precomputed",
        linkage="average",
        distance_threshold=TEMPLATE_DISTANCE_THRESHOLD,
    )
    labels = np.asarray(clustering.fit_predict(distances), dtype=np.int64)
    _, sizes = np.unique(labels, return_counts=True)
    logger.info(
        "template_groups rows=%d groups=%d largest=%d", len(labels), len(sizes), int(sizes.max())
    )
    return labels


def cv_splitter() -> StratifiedGroupKFold:
    """Return a new grouped, stratified 5-fold splitter with the project seed.

    Returns:
        An unused ``StratifiedGroupKFold``; callers pass ``X``, ``y`` and ``groups`` to ``split``.
    """
    return StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED)


def grouped_split(y: np.ndarray, groups: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Split rows 80/20 so that no group appears on both sides (first fold of ``cv_splitter``).

    Args:
        y: Class index of each row.
        groups: Group id of each row.

    Returns:
        ``(train_idx, test_idx)``: positional indices, ascending, dtype ``int64``.

    Raises:
        InvalidInputError: ``y`` or ``groups`` is not 1-D, their lengths differ, or ``groups``
            holds fewer than ``N_SPLITS`` distinct values.
    """
    _validate_split_input(y, groups)
    train_idx, test_idx = next(cv_splitter().split(np.zeros((len(y), 1)), y, groups))
    train = np.asarray(train_idx, dtype=np.int64)
    test = np.asarray(test_idx, dtype=np.int64)
    logger.info("grouped_split train=%d test=%d", len(train), len(test))
    return train, test


def _validate_texts(texts: Sequence[str]) -> None:
    """Check the input of ``template_groups``; the count rule comes before the blank rule."""
    if len(texts) < MIN_GROUP_TEXTS:
        raise InvalidInputError("template_groups needs at least 2 texts")
    if any(not text.strip() for text in texts):
        raise InvalidInputError("template_groups texts must not be blank")


def _validate_split_input(y: np.ndarray, groups: np.ndarray) -> None:
    """Check the input of ``grouped_split`` in the order shape, length, group count."""
    if y.ndim != 1 or groups.ndim != 1:
        raise InvalidInputError("y and groups must be 1-D arrays")
    if len(y) != len(groups):
        raise InvalidInputError("y and groups must have the same length")
    if len(np.unique(groups)) < N_SPLITS:
        raise InvalidInputError("groups must hold at least 5 distinct values")
