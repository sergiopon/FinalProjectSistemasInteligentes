"""Dataclasses and artifact builders used by ml.train (spec 014)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline

from api.domain.entities import ASPECT_ORDER, POLARITY_ORDER
from ml.representations import EMBEDDING_MODEL_NAME, EMBEDDING_REVISION
from ml.schemas import BUNDLE_SCHEMA_VERSION, SEED, Manifest, Report, SplitInfo
from ml.selection import SelectionResult

Topics = tuple[TfidfVectorizer, KMeans, tuple[tuple[str, ...], ...]]


@dataclass(frozen=True)
class Rows:
    """The rows of one side of the split."""

    texts: list[str]
    y: np.ndarray
    groups: np.ndarray
    files: list[str]
    keys: list[str]


@dataclass(frozen=True)
class PolarityResult:
    """Everything the polarity stage produces."""

    selection: SelectionResult
    conformal: object
    conformal_metrics: dict[str, float]
    curve: list[tuple[float, float]]
    test: dict[str, object]
    per_file: dict[str, float]
    macro_f1: float


def build_bundle(
    polarity: PolarityResult,
    aspects: tuple[Pipeline, tuple[float, ...]],
    topics: Topics,
) -> dict[str, object]:
    """Assemble the bundle of docs/contracts.md section 9.1."""
    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "class_order": tuple(p.value for p in POLARITY_ORDER),
        "aspect_order": tuple(g.value for g in ASPECT_ORDER),
        "polarity_pipeline": polarity.selection.pipeline,
        "conformal_classifier": polarity.conformal,
        "aspect_pipeline": aspects[0],
        "aspect_thresholds": aspects[1],
        "topic_vectorizer": topics[0],
        "topic_kmeans": topics[1],
        "topic_terms": topics[2],
    }


def build_report(
    polarity: PolarityResult,
    test: Rows,
    aspects: dict[str, object],
    topics: Topics,
    split: SplitInfo,
) -> Report:
    """Assemble the report of docs/contracts.md section 9.4."""
    terms = topics[2]
    return {
        "selection": list(polarity.selection.selection),
        "test": polarity.test,
        "per_file_macro_f1": polarity.per_file,
        "conformal": polarity.conformal_metrics,
        "risk_coverage": list(polarity.curve),
        "aspects": aspects,
        "topics": [
            {"topic": t, "size": int((topics[1].labels_ == t).sum()), "terms": list(terms[t])}
            for t in range(len(terms))
        ],
        "split": split,
        "test_row_keys": list(test.keys),
    }


def build_manifest(polarity: PolarityResult, dataset_sha: str, confidence_level: float) -> Manifest:
    """Assemble the manifest; ``write_version`` fills the six keys left empty here."""
    selection = polarity.selection
    return {
        "version": "",
        "created_at": "",
        "bundle_sha256": "",
        "dataset_sha256": dataset_sha,
        "python_version": "",
        "library_versions": {},
        "embedding": {"model_name": EMBEDDING_MODEL_NAME, "revision": EMBEDDING_REVISION},
        "polarity_model": selection.classifier,
        "representation": selection.representation,
        "best_params": selection.best_params,
        "confidence_level": confidence_level,
        "seed": SEED,
        "metrics": {
            "test_macro_f1": polarity.macro_f1,
            "empirical_coverage": polarity.conformal_metrics["empirical_coverage"],
        },
        "smoke": {"texts": [], "probabilities": []},
    }
