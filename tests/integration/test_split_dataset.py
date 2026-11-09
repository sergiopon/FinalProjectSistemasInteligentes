"""Integration tests of ml/split.py on the real Dataset/ (SEC-09 exception)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from api.domain.entities import POLARITY_ORDER, Polarity
from ml.data import load_dataset
from ml.split import cv_splitter, grouped_split, template_groups

pytestmark = pytest.mark.integration


def dataset_inputs() -> tuple[list[str], np.ndarray, np.ndarray]:
    frame = load_dataset(Path("Dataset"))
    texts: list[str] = frame["text"].tolist()
    y = np.asarray([POLARITY_ORDER.index(Polarity(value)) for value in frame["polarity"]])
    return texts, y, template_groups(texts)


def test_dataset_template_groups() -> None:
    _, _, groups = dataset_inputs()
    assert len(np.unique(groups)) == 380
    assert int(np.bincount(groups).max()) == 8


def test_dataset_grouped_split() -> None:
    _, y, groups = dataset_inputs()
    train_idx, test_idx = grouped_split(y, groups)
    assert len(train_idx) == 494
    assert len(test_idx) == 124
    train_groups = set(groups[train_idx].tolist())
    test_groups = set(groups[test_idx].tolist())
    assert len(train_groups) == 306
    assert len(test_groups) == 74
    assert train_groups.isdisjoint(test_groups)
    assert np.bincount(y[test_idx], minlength=3).tolist() == [41, 52, 31]


def test_dataset_cv_folds() -> None:
    texts, y, groups = dataset_inputs()
    folds = list(cv_splitter().split(np.asarray(texts, dtype=object), y, groups))
    assert [len(test_idx) for _, test_idx in folds] == [124, 124, 124, 124, 122]
    train_idx, test_idx = grouped_split(y, groups)
    assert np.array_equal(folds[0][0], train_idx)
    assert np.array_equal(folds[0][1], test_idx)
