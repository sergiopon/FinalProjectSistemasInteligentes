"""Nine-group aspect presence model with per-group thresholds (spec 012).

A TF-IDF one-vs-rest logistic regression scores each aspect group. Each group's threshold is
chosen on grouped out-of-fold scores so that no template appears on both sides (ADR-001).
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import Pipeline

from api.domain.entities import ASPECT_ORDER
from api.domain.errors import InvalidInputError
from ml.split import cv_splitter

logger = logging.getLogger(__name__)

_THRESHOLD_GRID: Final[tuple[float, ...]] = tuple(round(0.10 + 0.05 * i, 2) for i in range(17))
_MIN_POSITIVES: Final[int] = 5
_MIN_GROUPS: Final[int] = 5
_GROUP_COUNT: Final[int] = len(ASPECT_ORDER)
_NO_GROUP_KEY: Final[int] = _GROUP_COUNT
_MATRIX_DIMS: Final[int] = 2


def aspect_targets(frame: pd.DataFrame) -> np.ndarray:
    """Build the presence matrix of the nine aspect groups.

    Args:
        frame: Clean dataset with one ``aspect_<group>`` column per group.

    Returns:
        Array of shape ``(n, 9)``, dtype ``int64``, columns in ``ASPECT_ORDER``.

    Raises:
        InvalidInputError: An ``aspect_<group>`` column is missing.
    """
    columns = []
    for group in ASPECT_ORDER:
        name = f"aspect_{group.value}"
        if name not in frame.columns:
            raise InvalidInputError(f"missing column {name}")
        columns.append((frame[name] != "").to_numpy(dtype=np.int64))
    return np.stack(columns, axis=1)


def fit_aspect_model(
    texts: Sequence[str], Y: np.ndarray, groups: np.ndarray
) -> tuple[Pipeline, tuple[float, ...]]:
    """Fit the aspect presence model and choose one threshold per group.

    Args:
        texts: Training texts.
        Y: Presence matrix of shape ``(n, 9)`` holding 0 and 1.
        groups: Template group id of each row.

    Returns:
        The pipeline fit on all rows and nine thresholds in ``ASPECT_ORDER``.

    Raises:
        InvalidInputError: The inputs are inconsistent, a group has too few positives, or
            ``groups`` holds fewer than five distinct values.
    """
    _validate_fit(texts, Y, groups)
    template = _template()
    scores = _out_of_fold_scores(template, texts, Y, groups)
    thresholds = tuple(_best_threshold(Y[:, j], scores[:, j]) for j in range(_GROUP_COUNT))
    pipeline = clone(template).fit(np.asarray(texts, dtype=object), Y)
    logger.info("aspect_model_fitted rows=%d thresholds=%s", len(texts), thresholds)
    return pipeline, thresholds


def aspect_report(
    pipeline: Pipeline, thresholds: tuple[float, ...], texts: Sequence[str], Y: np.ndarray
) -> dict[str, object]:
    """Compute precision, recall and F1 of each aspect group.

    Args:
        pipeline: Fitted aspect pipeline.
        thresholds: One threshold per group in ``ASPECT_ORDER``.
        texts: Evaluation texts.
        Y: Presence matrix of shape ``(len(texts), 9)``.

    Returns:
        Mapping from group value to ``precision``, ``recall``, ``f1`` and ``threshold``.

    Raises:
        InvalidInputError: The thresholds or ``Y`` do not cover the nine groups.
    """
    if len(thresholds) != _GROUP_COUNT or Y.shape != (len(texts), _GROUP_COUNT):
        raise InvalidInputError("thresholds and Y must cover the 9 aspect groups")
    scores = pipeline.predict_proba(np.asarray(texts, dtype=object))
    report: dict[str, object] = {}
    for j, group in enumerate(ASPECT_ORDER):
        predicted = scores[:, j] >= thresholds[j]
        report[group.value] = {
            "precision": float(precision_score(Y[:, j], predicted, zero_division=0)),
            "recall": float(recall_score(Y[:, j], predicted, zero_division=0)),
            "f1": float(f1_score(Y[:, j], predicted, zero_division=0)),
            "threshold": float(thresholds[j]),
        }
    return report


def _template() -> Pipeline:
    """Return an unfitted aspect pipeline."""
    return Pipeline(
        [
            ("features", TfidfVectorizer(ngram_range=(1, 2))),
            (
                "classifier",
                OneVsRestClassifier(LogisticRegression(class_weight="balanced", max_iter=1000)),
            ),
        ]
    )


def _validate_fit(texts: Sequence[str], Y: np.ndarray, groups: np.ndarray) -> None:
    """Check the inputs of ``fit_aspect_model`` in the order of the spec."""
    if Y.ndim != _MATRIX_DIMS or Y.shape[1] != _GROUP_COUNT:
        raise InvalidInputError("Y must have shape (n, 9)")
    if not len(texts) == Y.shape[0] == len(groups):
        raise InvalidInputError("texts, Y and groups must have the same length")
    if not np.isin(Y, (0, 1)).all():
        raise InvalidInputError("Y must hold only 0 and 1")
    for j, group in enumerate(ASPECT_ORDER):
        if int(Y[:, j].sum()) < _MIN_POSITIVES:
            raise InvalidInputError(f"aspect group {group.value} has fewer than 5 positive rows")
    if len(np.unique(groups)) < _MIN_GROUPS:
        raise InvalidInputError("groups must hold at least 5 distinct values")


def _stratification_key(Y: np.ndarray) -> np.ndarray:
    """Pick, per row, its rarest present group; rows without any group get ``_NO_GROUP_KEY``."""
    totals = Y.sum(axis=0).astype(np.float64)
    ranked = np.where(Y == 1, totals, np.inf)
    key = np.argmin(ranked, axis=1)
    return np.where(Y.sum(axis=1) == 0, _NO_GROUP_KEY, key).astype(np.int64)


def _out_of_fold_scores(
    template: Pipeline, texts: Sequence[str], Y: np.ndarray, groups: np.ndarray
) -> np.ndarray:
    """Score every row with a model that did not see its template group."""
    rows = np.asarray(texts, dtype=object)
    scores = np.zeros(Y.shape, dtype=np.float64)
    for fit_rows, held_rows in cv_splitter().split(rows, _stratification_key(Y), groups):
        model = clone(template).fit(rows[fit_rows], Y[fit_rows])
        scores[held_rows] = model.predict_proba(rows[held_rows])
    return scores


def _best_threshold(truth: np.ndarray, scores: np.ndarray) -> float:
    """Return the grid value with the highest F1; ties go to the lowest value."""
    f1_values = [
        f1_score(truth, scores >= threshold, zero_division=0) for threshold in _THRESHOLD_GRID
    ]
    return float(_THRESHOLD_GRID[int(np.argmax(f1_values))])
