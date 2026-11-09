"""Test-split metrics of a fitted polarity pipeline (spec 010)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

import numpy as np
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_recall_fscore_support,
)
from sklearn.pipeline import Pipeline

from api.domain.entities import POLARITY_ORDER
from api.domain.errors import InvalidInputError

_LABELS: Final[list[int]] = [0, 1, 2]


def evaluate(pipeline: Pipeline, texts: Sequence[str], y: np.ndarray) -> dict[str, object]:
    """Measure a fitted pipeline on labelled rows.

    Args:
        pipeline: Fitted polarity pipeline.
        texts: Comment texts.
        y: Class index of each text, in ``POLARITY_ORDER``.

    Returns:
        Accuracy, macro precision, recall and F1, per-class metrics keyed by polarity value, and
        the confusion matrix (rows true class, columns predicted class). Values are Python
        ``float`` or ``int``; a class absent from ``y`` and the predictions scores 0.0.

    Raises:
        InvalidInputError: ``texts`` and ``y`` differ in length or are empty, or ``y`` holds a
            value outside 0, 1 and 2.
    """
    _validate_labels(texts, y)
    predicted = pipeline.predict(np.asarray(texts, dtype=object))
    precision, recall, f1, support = precision_recall_fscore_support(
        y, predicted, labels=_LABELS, zero_division=0
    )
    per_class = {
        polarity.value: {
            "precision": float(precision[index]),
            "recall": float(recall[index]),
            "f1": float(f1[index]),
            "support": int(support[index]),
        }
        for index, polarity in enumerate(POLARITY_ORDER)
    }
    matrix = confusion_matrix(y, predicted, labels=_LABELS)
    return {
        "accuracy": float(accuracy_score(y, predicted)),
        "macro_precision": float(np.mean(precision)),
        "macro_recall": float(np.mean(recall)),
        "macro_f1": float(np.mean(f1)),
        "per_class": per_class,
        "confusion_matrix": [[int(count) for count in row] for row in matrix],
    }


def per_file_macro_f1(
    pipeline: Pipeline, texts: Sequence[str], y: np.ndarray, source_files: Sequence[str]
) -> dict[str, float]:
    """Macro-F1 of a fitted pipeline on the rows of each source file.

    Args:
        pipeline: Fitted polarity pipeline.
        texts: Comment texts.
        y: Class index of each text, in ``POLARITY_ORDER``.
        source_files: Source file name of each text.

    Returns:
        Macro-F1 per file name, keys sorted ascending.

    Raises:
        InvalidInputError: ``texts`` and ``y`` differ in length or are empty, ``y`` holds a value
            outside 0, 1 and 2, or ``source_files`` differs in length from ``y``.
    """
    _validate_labels(texts, y)
    if len(source_files) != len(y):
        raise InvalidInputError("source_files must have the same length as y")
    predicted = np.asarray(pipeline.predict(np.asarray(texts, dtype=object)))
    files = np.asarray(source_files, dtype=object)
    return {
        name: float(
            f1_score(
                y[files == name],
                predicted[files == name],
                labels=_LABELS,
                average="macro",
                zero_division=0,
            )
        )
        for name in sorted(set(source_files))
    }


def _validate_labels(texts: Sequence[str], y: np.ndarray) -> None:
    """Check that texts and labels match in length and that labels are class indices."""
    if len(texts) != len(y) or len(y) == 0:
        raise InvalidInputError("texts and y must have the same non-zero length")
    if not set(y.tolist()) <= set(_LABELS):
        raise InvalidInputError("y must hold only the class indices 0, 1 and 2")
