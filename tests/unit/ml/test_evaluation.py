"""Tests for evaluate and per_file_macro_f1 in ml/evaluation.py."""

from __future__ import annotations

import json
import warnings

import numpy as np
import pytest

from api.domain.errors import InvalidInputError
from ml.evaluation import evaluate, per_file_macro_f1

T6 = [f"t{i}" for i in range(6)]
Y6 = np.array([0, 0, 1, 1, 2, 2])
EMPTY_Y = np.array([], dtype=np.int64)


class Stub:
    """Pipeline stand-in whose predict returns fixed labels."""

    def __init__(self, predictions: np.ndarray) -> None:
        self.predictions = predictions

    def predict(self, X: object) -> np.ndarray:
        return self.predictions


STUB = Stub(np.array([0, 1, 1, 1, 2, 0]))


def close(actual: object, expected: float) -> bool:
    return isinstance(actual, float) and abs(actual - expected) <= 1e-9


def test_evaluate_vector() -> None:
    metrics = evaluate(STUB, T6, Y6)
    assert close(metrics["accuracy"], 0.6666666666666666)
    assert close(metrics["macro_precision"], 0.7222222222222222)
    assert close(metrics["macro_recall"], 0.6666666666666666)
    assert close(metrics["macro_f1"], 0.6555555555555556)
    per_class = metrics["per_class"]
    assert isinstance(per_class, dict)
    names = ["negative", "neutral", "positive"]
    assert list(per_class) == names
    expected = {
        "precision": [0.5, 0.6666666666666666, 1.0],
        "recall": [0.5, 1.0, 0.5],
        "f1": [0.5, 0.8, 0.6666666666666666],
    }
    for metric, values in expected.items():
        assert all(
            close(per_class[name][metric], value) for name, value in zip(names, values, strict=True)
        )
    assert [per_class[name]["support"] for name in names] == [2, 2, 2]
    assert all(type(per_class[name]["support"]) is int for name in names)
    assert metrics["confusion_matrix"] == [[1, 1, 0], [0, 2, 0], [1, 0, 1]]
    json.dumps(metrics)


def test_evaluate_absent_class() -> None:
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        metrics = evaluate(Stub(np.array([0, 0])), ["t0", "t1"], np.array([0, 0]))
    assert close(metrics["macro_f1"], 0.3333333333333333)
    per_class = metrics["per_class"]
    assert isinstance(per_class, dict)
    assert per_class["positive"]["f1"] == 0.0
    assert metrics["confusion_matrix"] == [[2, 0, 0], [0, 0, 0], [0, 0, 0]]


@pytest.mark.parametrize(("texts", "y"), [(T6, Y6[:5]), ([], EMPTY_Y)])
def test_evaluate_rejects_length(texts: list[str], y: np.ndarray) -> None:
    with pytest.raises(InvalidInputError) as info:
        evaluate(STUB, texts, y)
    assert info.value.detail == "texts and y must have the same non-zero length"


def test_evaluate_rejects_class_values() -> None:
    with pytest.raises(InvalidInputError) as info:
        evaluate(STUB, ["t0", "t1"], np.array([0, 3]))
    assert info.value.detail == "y must hold only the class indices 0, 1 and 2"


def test_per_file_macro_f1_vector() -> None:
    result = per_file_macro_f1(STUB, T6, Y6, ["a.csv"] * 3 + ["b.csv"] * 3)
    assert list(result) == ["a.csv", "b.csv"]
    assert close(result["a.csv"], 0.4444444444444444)
    assert close(result["b.csv"], 0.5555555555555555)


def test_per_file_macro_f1_rejects_source_file_count() -> None:
    with pytest.raises(InvalidInputError) as info:
        per_file_macro_f1(STUB, T6, Y6, ["a.csv"] * 5)
    assert info.value.detail == "source_files must have the same length as y"


@pytest.mark.parametrize(("texts", "y"), [(T6, Y6[:5]), ([], EMPTY_Y)])
def test_per_file_macro_f1_rejects_length(texts: list[str], y: np.ndarray) -> None:
    with pytest.raises(InvalidInputError) as info:
        per_file_macro_f1(STUB, texts, y, ["a.csv"] * len(y))
    assert info.value.detail == "texts and y must have the same non-zero length"


def test_per_file_macro_f1_rejects_class_values() -> None:
    with pytest.raises(InvalidInputError) as info:
        per_file_macro_f1(STUB, ["t0", "t1"], np.array([0, 3]), ["a.csv", "a.csv"])
    assert info.value.detail == "y must hold only the class indices 0, 1 and 2"
