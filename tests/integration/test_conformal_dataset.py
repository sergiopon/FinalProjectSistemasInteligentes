"""Integration tests of ml/conformal.py and risk_coverage on the real Dataset/.

No embedding cache is needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest

from api.domain.entities import POLARITY_ORDER, Polarity
from ml.conformal import COVERAGE_TOLERANCE, conformal_report, fit_cross_conformal
from ml.data import load_dataset
from ml.evaluation import risk_coverage
from ml.selection import build_pipeline
from ml.split import grouped_split, template_groups

pytestmark = pytest.mark.integration


@dataclass(frozen=True)
class Split:
    train_texts: list[str]
    train_y: np.ndarray
    train_groups: np.ndarray
    test_texts: list[str]
    test_y: np.ndarray


@pytest.fixture(scope="module")
def split() -> Split:
    frame = load_dataset(Path("Dataset"))
    texts = np.asarray(frame["text"].tolist(), dtype=object)
    y = np.asarray([POLARITY_ORDER.index(Polarity(value)) for value in frame["polarity"]])
    groups = template_groups(texts.tolist())
    train_idx, test_idx = grouped_split(y, groups)
    return Split(
        texts[train_idx].tolist(),
        y[train_idx],
        groups[train_idx],
        texts[test_idx].tolist(),
        y[test_idx],
    )


def test_conformal_coverage_on_test_split_within_tolerance(split: Split) -> None:
    pipeline = build_pipeline("tfidf", "logistic_regression")
    model = fit_cross_conformal(pipeline, split.train_texts, split.train_y, split.train_groups, 0.9)
    report = conformal_report(model, split.test_texts, split.test_y)
    assert len(split.test_texts) == 124
    assert report["empirical_coverage"] >= 0.9 - COVERAGE_TOLERANCE
    assert 0.0 <= report["mean_set_size"] <= 3.0


def test_risk_coverage_on_test_split(split: Split) -> None:
    pipeline = build_pipeline("tfidf", "logistic_regression")
    pipeline.fit(np.asarray(split.train_texts, dtype=object), split.train_y)
    test_texts = np.asarray(split.test_texts, dtype=object)
    points = risk_coverage(pipeline.predict_proba(test_texts), split.test_y)
    accuracy = float(np.mean(pipeline.predict(test_texts) == split.test_y))
    assert len(points) == 124
    assert points[-1][0] == 1.0
    assert abs(points[-1][1] - (1 - accuracy)) <= 1e-9
