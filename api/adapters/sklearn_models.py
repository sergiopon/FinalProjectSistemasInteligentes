"""Polarity and aspect model adapters over the pipelines stored in the verified bundle."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import numpy as np
from mapie.classification import CrossConformalClassifier
from sklearn.pipeline import Pipeline

from api.domain.entities import (
    ASPECT_ORDER,
    POLARITY_ORDER,
    AspectScores,
    ClassProbabilities,
    ConformalSet,
)
from api.domain.errors import InferenceError, InvalidInputError, ModelIntegrityError
from ml.data import normalize_text

MAX_TEXTS: Final[int] = 5000
CLASS_COUNT: Final[int] = 3
ASPECT_COUNT: Final[int] = 9
LIBRARY_ERRORS: Final = (ValueError, TypeError, AttributeError)


def validate_texts(texts: Sequence[str]) -> list[str]:
    """Check the batch size and blank texts, then normalize every text.

    Args:
        texts: Raw comment texts.

    Returns:
        The normalized texts, in input order.

    Raises:
        InvalidInputError: The batch is empty, too large, or holds a blank text.
    """
    if not 1 <= len(texts) <= MAX_TEXTS:
        raise InvalidInputError("texts must hold 1 to 5000 items")
    if any(text.strip() == "" for text in texts):
        raise InvalidInputError("texts must be non-empty after strip")
    return [normalize_text(text) for text in texts]


def _probability_matrix(
    pipeline: Pipeline, normalized: list[str], width: int, failure: str, invalid: str
) -> np.ndarray:
    """Run `predict_proba` and check that the result is finite with the expected shape."""
    try:
        matrix = np.asarray(pipeline.predict_proba(normalized), dtype=float)
    except LIBRARY_ERRORS as error:
        raise InferenceError(failure) from error
    if matrix.shape != (len(normalized), width) or not np.isfinite(matrix).all():
        raise InferenceError(invalid)
    return matrix


class SklearnPolarityModel:
    """Polarity probabilities and conformal sets from the refit pipeline and the conformal model."""

    def __init__(self, pipeline: object, conformal: object, confidence_level: float) -> None:
        """Validate the bundle objects and keep them.

        Args:
            pipeline: Fitted `Pipeline` that produces polarity probabilities.
            conformal: Fitted `CrossConformalClassifier` that produces the sets.
            confidence_level: Coverage of the conformal sets, strictly between 0 and 1.

        Raises:
            ModelIntegrityError: A type, the class order or the confidence level is invalid.
        """
        if not isinstance(pipeline, Pipeline):
            raise ModelIntegrityError("polarity pipeline has an unexpected type")
        if not isinstance(conformal, CrossConformalClassifier):
            raise ModelIntegrityError("conformal classifier has an unexpected type")
        try:
            classes = [int(label) for label in pipeline.classes_]
        except AttributeError as error:
            raise ModelIntegrityError("polarity classes differ from POLARITY_ORDER") from error
        if classes != list(range(CLASS_COUNT)):
            raise ModelIntegrityError("polarity classes differ from POLARITY_ORDER")
        if not 0.0 < confidence_level < 1.0:
            raise ModelIntegrityError("confidence level out of range")
        self._pipeline = pipeline
        self._conformal = conformal
        self._confidence_level = confidence_level

    def predict_proba(self, texts: Sequence[str]) -> tuple[ClassProbabilities, ...]:
        """Return class probabilities for each text.

        Args:
            texts: 1 to 5000 comment texts, none blank.

        Returns:
            One `ClassProbabilities` per text, in input order.

        Raises:
            InvalidInputError: The batch is empty, too large, or holds a blank text.
            InferenceError: The pipeline fails or returns invalid probabilities.
        """
        matrix = _probability_matrix(
            self._pipeline,
            validate_texts(texts),
            CLASS_COUNT,
            "polarity inference failed",
            "polarity model returned invalid probabilities",
        )
        return tuple(
            ClassProbabilities(
                negative=float(row[0]), neutral=float(row[1]), positive=float(row[2])
            )
            for row in matrix
        )

    def predict_set(self, texts: Sequence[str]) -> tuple[ConformalSet, ...]:
        """Return the conformal set for each text.

        Args:
            texts: 1 to 5000 comment texts, none blank.

        Returns:
            One `ConformalSet` per text, in input order.

        Raises:
            InvalidInputError: The batch is empty, too large, or holds a blank text.
            InferenceError: The conformal model fails or returns an unexpected shape.
        """
        normalized = validate_texts(texts)
        try:
            _, y_set = self._conformal.predict_set(
                np.asarray(normalized, dtype=object), agg_scores="mean"
            )
        except LIBRARY_ERRORS as error:
            raise InferenceError("conformal inference failed") from error
        if y_set.shape != (len(normalized), CLASS_COUNT, 1):
            raise InferenceError("conformal model returned an unexpected shape")
        return tuple(
            ConformalSet(
                labels=frozenset(POLARITY_ORDER[j] for j in range(CLASS_COUNT) if y_set[i, j, 0]),
                confidence_level=self._confidence_level,
            )
            for i in range(len(normalized))
        )


class SklearnAspectModel:
    """Aspect presence scores from the multi-label pipeline and per-group thresholds."""

    def __init__(self, pipeline: object, thresholds: tuple[float, ...]) -> None:
        """Validate the bundle objects and keep them.

        Args:
            pipeline: Fitted `Pipeline` that produces one score per aspect group.
            thresholds: One threshold per group, each in `[0.0, 1.0]`.

        Raises:
            ModelIntegrityError: The pipeline type or the thresholds are invalid.
        """
        if not isinstance(pipeline, Pipeline):
            raise ModelIntegrityError("aspect pipeline has an unexpected type")
        if len(thresholds) != ASPECT_COUNT or not all(0.0 <= t <= 1.0 for t in thresholds):
            raise ModelIntegrityError("aspect thresholds are invalid")
        self._pipeline = pipeline
        self._thresholds = thresholds

    def detect(self, texts: Sequence[str]) -> tuple[AspectScores, ...]:
        """Return aspect scores and the groups at or above their threshold for each text.

        Args:
            texts: 1 to 5000 comment texts, none blank.

        Returns:
            One `AspectScores` per text, in input order.

        Raises:
            InvalidInputError: The batch is empty, too large, or holds a blank text.
            InferenceError: The pipeline fails or returns invalid scores.
        """
        matrix = _probability_matrix(
            self._pipeline,
            validate_texts(texts),
            ASPECT_COUNT,
            "aspect inference failed",
            "aspect model returned invalid scores",
        )
        results = []
        for row in matrix:
            scores = tuple(float(value) for value in row)
            present = frozenset(
                ASPECT_ORDER[j] for j in range(ASPECT_COUNT) if scores[j] >= self._thresholds[j]
            )
            results.append(AspectScores(scores, present))
        return tuple(results)
