"""Cross-conformal prediction sets for the polarity pipeline (spec 011, ADR-002).

MAPIE 1.6.0 has no ``predict_proba``: class probabilities come from the pipeline refit by
``ml.selection``; this module only calibrates the prediction sets.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Final

import numpy as np
from mapie.classification import CrossConformalClassifier
from sklearn.pipeline import Pipeline

from api.domain.errors import InvalidInputError
from ml.schemas import SEED
from ml.split import N_SPLITS, cv_splitter

logger = logging.getLogger(__name__)

COVERAGE_TOLERANCE: Final[float] = 0.05

_CLASSES: Final[frozenset[int]] = frozenset({0, 1, 2})


def fit_cross_conformal(
    pipeline: Pipeline,
    texts: Sequence[str],
    y: np.ndarray,
    groups: np.ndarray,
    confidence_level: float,
) -> CrossConformalClassifier:
    """Calibrate conformal prediction sets on the grouped folds of the train rows.

    Args:
        pipeline: Unfitted polarity pipeline exposing ``predict_proba``; it is cloned, not fitted.
        texts: Train texts.
        y: Class index of each text, in ``POLARITY_ORDER``.
        groups: Template group of each text.
        confidence_level: Target coverage, ``1 - alpha``, strictly between 0 and 1.

    Returns:
        The fitted MAPIE cross-conformal classifier (LAC score).

    Raises:
        InvalidInputError: Confidence level out of range, lengths differ, a class is missing,
            fewer than ``N_SPLITS`` groups, or the pipeline has no ``predict_proba``.
    """
    _validate_fit_input(pipeline, texts, y, groups, confidence_level)
    model = CrossConformalClassifier(
        estimator=pipeline,
        confidence_level=confidence_level,
        conformity_score="lac",
        cv=cv_splitter(),
        random_state=SEED,
    )
    model.fit_conformalize(np.asarray(texts, dtype=object), y, groups=groups)
    logger.info(
        "conformal_fitted rows=%d groups=%d confidence_level=%s",
        len(texts),
        len(np.unique(groups)),
        confidence_level,
    )
    return model


def conformal_report(
    model: CrossConformalClassifier, texts: Sequence[str], y: np.ndarray
) -> dict[str, float]:
    """Measure the prediction sets of a fitted conformal classifier on labelled rows.

    Args:
        model: Fitted cross-conformal classifier.
        texts: Comment texts.
        y: Class index of each text, in ``POLARITY_ORDER``.

    Returns:
        ``empirical_coverage`` (share of rows whose true class is in the set),
        ``mean_set_size``, ``singleton_rate`` and ``empty_rate``, as Python floats.

    Raises:
        InvalidInputError: ``texts`` and ``y`` differ in length or are empty, or ``y`` holds a
            value outside 0, 1 and 2.
    """
    if len(texts) != len(y) or len(y) == 0:
        raise InvalidInputError("texts and y must have the same non-zero length")
    if not set(y.tolist()) <= _CLASSES:
        raise InvalidInputError("y must hold only the class indices 0, 1 and 2")
    _, y_set = model.predict_set(np.asarray(texts, dtype=object), agg_scores="mean")
    sets = np.asarray(y_set, dtype=bool)[:, :, 0]
    sizes = sets.sum(axis=1)
    return {
        "empirical_coverage": float(np.mean(sets[np.arange(len(y)), y])),
        "mean_set_size": float(np.mean(sizes)),
        "singleton_rate": float(np.mean(sizes == 1)),
        "empty_rate": float(np.mean(sizes == 0)),
    }


def _validate_fit_input(
    pipeline: Pipeline,
    texts: Sequence[str],
    y: np.ndarray,
    groups: np.ndarray,
    confidence_level: float,
) -> None:
    """Check, in order: confidence level, lengths, classes, groups, ``predict_proba``."""
    if not 0.0 < confidence_level < 1.0:
        raise InvalidInputError("confidence_level must be in (0, 1)")
    if not len(texts) == len(y) == len(groups):
        raise InvalidInputError("texts, y and groups must have the same length")
    if set(y.tolist()) != _CLASSES:
        raise InvalidInputError("y must contain the classes 0, 1 and 2")
    if len(np.unique(groups)) < N_SPLITS:
        raise InvalidInputError("groups must hold at least 5 distinct values")
    if not hasattr(pipeline, "predict_proba"):
        raise InvalidInputError("pipeline must expose predict_proba")
