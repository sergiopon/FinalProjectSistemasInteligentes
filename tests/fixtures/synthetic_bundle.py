"""Small, valid artifact inputs for the tests of ml/artifact.py (spec 013)."""

from __future__ import annotations

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from api.domain.entities import ASPECT_ORDER
from ml.schemas import BUNDLE_SCHEMA_VERSION, Manifest, ReferenceStats, Report

_WORDS = ("malo", "regular", "bueno")
_FILE = "feedback_curso_universitario.csv"
_REVISION = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"


def make_bundle() -> dict[str, object]:
    """Return a bundle with a real, tiny polarity pipeline and stub parts."""
    texts = [f"{_WORDS[i % 3]} curso {i % 5}" for i in range(30)]
    y = [i % 3 for i in range(30)]
    pipeline = Pipeline(
        [("features", TfidfVectorizer()), ("classifier", LogisticRegression(max_iter=1000))]
    ).fit(texts, y)
    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "class_order": ("negative", "neutral", "positive"),
        "aspect_order": tuple(group.value for group in ASPECT_ORDER),
        "polarity_pipeline": pipeline,
        "conformal_classifier": "stub",
        "aspect_pipeline": "stub",
        "aspect_thresholds": (0.5,) * 9,
        "topic_vectorizer": "stub",
        "topic_kmeans": "stub",
        "topic_terms": (("alfa", "beta", "gamma", "delta", "epsilon"),),
    }


def make_manifest() -> Manifest:
    """Return a manifest as ml.train builds it, before write_version completes it."""
    return {
        "version": "v000",
        "created_at": "",
        "bundle_sha256": "f" * 64,
        "dataset_sha256": "0" * 64,
        "python_version": "",
        "library_versions": {},
        "embedding": {
            "model_name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            "revision": _REVISION,
        },
        "polarity_model": "logistic_regression",
        "representation": "tfidf",
        "best_params": {"classifier__C": 1.0},
        "confidence_level": 0.9,
        "seed": 42,
        "metrics": {"test_macro_f1": 0.61, "empirical_coverage": 0.9},
        "smoke": {"texts": [], "probabilities": []},
    }


def make_report() -> Report:
    """Return a report whose strings are all short labels."""
    group_scores: dict[str, object] = {
        group.value: {"precision": 0.5, "recall": 0.5, "f1": 0.5, "threshold": 0.4}
        for group in ASPECT_ORDER
    }
    return {
        "selection": [
            {
                "representation": "tfidf",
                "classifier": "logistic_regression",
                "best_params": {"classifier__C": 1.0},
                "cv_macro_f1_mean": 0.6,
                "cv_macro_f1_std": 0.02,
            }
        ],
        "test": {"macro_f1": 0.61},
        "per_file_macro_f1": {_FILE: 0.6},
        "conformal": {"empirical_coverage": 0.9},
        "risk_coverage": [(0.5, 0.1), (1.0, 0.3)],
        "aspects": group_scores,
        "topics": [{"topic": 0, "size": 10, "terms": ["carga", "ritmo"]}],
        "split": {"train_rows": 494, "test_rows": 124, "groups": 100},
        "test_row_keys": [f"{_FILE}:1"],
    }


def make_reference() -> ReferenceStats:
    """Return reference statistics that satisfy the schema."""
    return {
        "length_edges": [40, 60, 80, 100, 120, 140, 160, 180, 200],
        "length_shares": [0.1] * 10,
        "reference_oov_rate": 0.05,
        "class_shares": [0.33, 0.42, 0.25],
    }
