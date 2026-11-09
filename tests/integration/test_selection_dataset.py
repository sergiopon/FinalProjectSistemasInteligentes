"""Integration tests of ml/selection.py and ml/evaluation.py on the real Dataset/.

Needs the embedding cache of spec 009. The full selection takes several minutes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from api.domain.entities import POLARITY_ORDER, Polarity
from ml.data import load_dataset
from ml.evaluation import evaluate, per_file_macro_f1
from ml.selection import SelectionResult, select_model
from ml.split import grouped_split, template_groups

pytestmark = pytest.mark.integration

DATASET_DIR = Path("Dataset")


@dataclass(frozen=True)
class Run:
    result: SelectionResult
    test_texts: list[str]
    test_y: np.ndarray
    test_files: list[str]


@pytest.fixture(scope="module")
def run() -> Run:
    frame = load_dataset(DATASET_DIR)
    texts = np.asarray(frame["text"].tolist(), dtype=object)
    y = np.asarray([POLARITY_ORDER.index(Polarity(value)) for value in frame["polarity"]])
    files = np.asarray(frame["source_file"].tolist(), dtype=object)
    groups = template_groups(texts.tolist())
    train_idx, test_idx = grouped_split(y, groups)
    result = select_model(texts[train_idx].tolist(), y[train_idx], groups[train_idx])
    return Run(result, texts[test_idx].tolist(), y[test_idx], files[test_idx].tolist())


def test_dataset_selection_table(run: Run) -> None:
    rows = run.result.selection
    assert len(rows) == 24
    means = [float(str(row["cv_macro_f1_mean"])) for row in rows]
    assert max(means) >= 0.50
    dummy_means = [
        mean for row, mean in zip(rows, means, strict=True) if row["classifier"] == "dummy"
    ]
    assert all(mean < 0.25 for mean in dummy_means)
    assert run.result.classifier != "linear_svm"


def test_dataset_test_metrics(run: Run) -> None:
    metrics = evaluate(run.result.pipeline, run.test_texts, run.test_y)
    assert float(str(metrics["macro_f1"])) >= 0.45
    per_file = per_file_macro_f1(run.result.pipeline, run.test_texts, run.test_y, run.test_files)
    dataset_names = {path.name for path in DATASET_DIR.glob("*.csv")}
    assert per_file
    assert set(per_file) <= dataset_names
