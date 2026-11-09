"""Integration tests for ml/aspects.py and ml/topics.py on the real dataset (spec 012)."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
import pytest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from api.domain.clauses import aspect_sentiments, split_clauses
from api.domain.entities import ASPECT_ORDER, AspectScores, ClassProbabilities, ClauseAnalysis
from ml.aspects import _THRESHOLD_GRID, aspect_report, aspect_targets, fit_aspect_model
from ml.data import load_dataset
from ml.split import grouped_split, template_groups
from ml.topics import fit_topics

pytestmark = pytest.mark.integration

DATASET = Path(__file__).resolve().parents[2] / "Dataset"
COMMON_WORDS = {"de", "la", "el", "en", "que", "los"}


@pytest.fixture(scope="module")
def split() -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    frame = load_dataset(DATASET)
    groups = template_groups(frame["text"].tolist())
    labels = frame["polarity"].astype("category").cat.codes.to_numpy()
    train_idx, test_idx = grouped_split(labels, groups)
    return frame.iloc[train_idx], frame.iloc[test_idx], groups[train_idx]


def test_aspect_targets_counts_on_dataset() -> None:
    sums = aspect_targets(load_dataset(DATASET)).sum(axis=0)
    assert sums.tolist() == [361, 94, 76, 71, 66, 59, 48, 38, 35]


def test_aspect_model_macro_f1_on_test_split(
    split: tuple[pd.DataFrame, pd.DataFrame, np.ndarray],
) -> None:
    train, test, groups = split
    pipeline, thresholds = fit_aspect_model(train["text"].tolist(), aspect_targets(train), groups)
    report = aspect_report(pipeline, thresholds, test["text"].tolist(), aspect_targets(test))
    f1_values = [cast(dict[str, float], report[group.value])["f1"] for group in ASPECT_ORDER]
    assert sum(f1_values) / 9 >= 0.40
    assert all(value in _THRESHOLD_GRID for value in thresholds)


def test_clause_aspect_sentiment_on_test_split(
    split: tuple[pd.DataFrame, pd.DataFrame, np.ndarray],
) -> None:
    train, test, groups = split
    aspects, thresholds = fit_aspect_model(train["text"].tolist(), aspect_targets(train), groups)
    polarity = Pipeline(
        [
            ("features", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=2)),
            ("classifier", LogisticRegression(max_iter=1000, class_weight="balanced")),
        ]
    ).fit(train["text"].tolist(), train["polarity"].tolist())
    matched, total = 0, 0
    for _, row in test.iterrows():
        analyses = _analyze_row(str(row["text"]), polarity, aspects, thresholds)
        for sentiment in aspect_sentiments(analyses):
            label = row[f"aspect_{sentiment.group.value}"]
            if label:
                total += 1
                matched += int(sentiment.polarity.value == label)
    assert total > 0
    assert matched / total >= 0.44


def test_topics_on_train_rows(split: tuple[pd.DataFrame, pd.DataFrame, np.ndarray]) -> None:
    train, _, _ = split
    _, kmeans, terms = fit_topics(train["text"].tolist())
    assert 4 <= kmeans.n_clusters <= 10
    for topic in terms:
        assert len(set(topic)) == 5
        assert not COMMON_WORDS & set(topic)


def _analyze_row(
    text: str, polarity: Pipeline, aspects: Pipeline, thresholds: tuple[float, ...]
) -> list[ClauseAnalysis]:
    analyses = []
    for clause in split_clauses(text):
        probs = polarity.predict_proba([clause])[0]
        scores = aspects.predict_proba([clause])[0]
        present = frozenset(
            group
            for group, score, cut in zip(ASPECT_ORDER, scores, thresholds, strict=True)
            if score >= cut
        )
        analyses.append(
            ClauseAnalysis(
                text=clause,
                probabilities=ClassProbabilities(*(float(p) for p in probs)),
                aspects=AspectScores(tuple(float(s) for s in scores), present),
            )
        )
    return analyses
