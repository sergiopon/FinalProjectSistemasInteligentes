"""Train, evaluate, write and activate a model version: ``python -m ml.train`` (spec 014)."""

from __future__ import annotations

import argparse
import bisect
import json
import logging
import os
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import f1_score
from sklearn.pipeline import Pipeline

from api.domain.entities import ASPECT_ORDER, POLARITY_ORDER, Polarity
from api.domain.errors import AppError, ConfigError, InvalidInputError
from api.domain.safety import RedactingFilter, resolve_within
from ml.artifact import activate, write_version
from ml.aspects import aspect_report, aspect_targets, fit_aspect_model
from ml.conformal import conformal_report, fit_cross_conformal
from ml.data import dataset_files, dataset_sha256, load_dataset
from ml.evaluation import evaluate, per_file_macro_f1, risk_coverage
from ml.representations import EMBEDDING_MODEL_NAME, EMBEDDING_REVISION
from ml.schemas import BUNDLE_SCHEMA_VERSION, SEED, Manifest, ReferenceStats, Report
from ml.selection import SelectionResult, select_model
from ml.split import grouped_split, template_groups
from ml.topics import fit_topics

logger = logging.getLogger(__name__)

_DECILES: Final[tuple[int, ...]] = (10, 20, 30, 40, 50, 60, 70, 80, 90)
_SHARE_FLOOR: Final[float] = 1e-4
_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?u)\b\w\w+\b")


@dataclass(frozen=True)
class _Part:
    """Rows of one side of the split."""

    texts: list[str]
    y: np.ndarray
    groups: np.ndarray
    files: list[str]
    keys: list[str]
    idx: np.ndarray


@dataclass(frozen=True)
class _Polarity:
    """Polarity model with the evidence measured on the test rows."""

    selection: SelectionResult
    conformal: object
    test: dict[str, object]
    per_file: dict[str, float]
    conformal_metrics: dict[str, float]
    curve: list[tuple[float, float]]
    macro_f1: float


def read_confidence_level(config_path: Path) -> float:
    """Return ``1 - conformal.alpha`` from the config file; raise ``ConfigError`` if invalid."""
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigError("config file unreadable") from error
    conformal = config.get("conformal") if isinstance(config, dict) else None
    alpha = conformal.get("alpha") if isinstance(conformal, dict) else None
    if isinstance(alpha, bool) or not isinstance(alpha, int | float) or not 0 < alpha < 1:
        raise ConfigError("conformal.alpha must be a number in (0, 1)")
    return 1.0 - float(alpha)


def reference_stats(
    train_texts: Sequence[str],
    test_texts: Sequence[str],
    y_train: np.ndarray,
    vocabulary: frozenset[str],
) -> ReferenceStats:
    """Build the drift statistics of ``docs/contracts.md`` section 9.5."""
    if not train_texts or not test_texts or len(y_train) != len(train_texts):
        raise InvalidInputError("reference statistics need matching non-empty inputs")
    lengths = [len(text) for text in train_texts]
    edges = [int(v) for v in np.percentile(lengths, _DECILES, method="lower")]
    counts = [0] * (len(edges) + 1)
    for length in lengths:
        counts[bisect.bisect_right(edges, length)] += 1
    raw = [max(count / len(lengths), _SHARE_FLOOR) for count in counts]
    tokens = [t for text in test_texts for t in _TOKEN_PATTERN.findall(text.lower())]
    unknown = sum(1 for token in tokens if token not in vocabulary)
    return {
        "length_edges": edges,
        "length_shares": [value / sum(raw) for value in raw],
        "reference_oov_rate": unknown / len(tokens) if tokens else 0.0,
        "class_shares": [float(np.sum(y_train == k)) / len(y_train) for k in range(3)],
    }


def train(dataset_dir: Path, models_dir: Path, confidence_level: float) -> str:
    """Train on the dataset, write a new version, activate it and return its name."""
    frame = load_dataset(dataset_dir)
    sha = dataset_sha256(dataset_files(dataset_dir))
    y = np.array([POLARITY_ORDER.index(Polarity(v)) for v in frame["polarity"]], dtype=np.int64)
    logger.info("event=train_dataset rows=%d dataset_sha256=%s", len(frame), sha)
    groups = template_groups(frame["text"].tolist())
    train_idx, test_idx = grouped_split(y, groups)
    n_groups = int(np.unique(groups).size)
    logger.info(
        "event=train_split train_rows=%d test_rows=%d groups=%d",
        len(train_idx),
        len(test_idx),
        n_groups,
    )
    fit, held = _part(frame, y, groups, train_idx), _part(frame, y, groups, test_idx)
    polarity = _polarity(fit, held, confidence_level)
    aspect_pipeline, thresholds, aspects = _aspects(frame, fit, held)
    vectorizer, kmeans, terms = fit_topics(fit.texts)
    bundle = _bundle(polarity, (aspect_pipeline, thresholds), (vectorizer, kmeans, terms))
    topics = _topics_report(kmeans, terms)
    report = _report(polarity, aspects, topics, (fit, held), n_groups)
    reference = reference_stats(fit.texts, held.texts, fit.y, frozenset(vectorizer.vocabulary_))
    version = write_version(
        models_dir, bundle, _manifest(sha, polarity, confidence_level), report, reference
    ).name
    activate(models_dir, version)
    logger.info(
        "event=train_done version=%s test_macro_f1=%.4f empirical_coverage=%.4f",
        version,
        polarity.macro_f1,
        polarity.conformal_metrics["empirical_coverage"],
    )
    return version


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line; return 0 on success, 2 for an expected error, 1 otherwise."""
    os.umask(0o077)
    _configure_logging()
    args = _parser().parse_args(argv)
    try:
        dataset_dir, models_dir, config_path = (
            resolve_within(Path.cwd(), Path(value))
            for value in (args.dataset, args.models, args.config)
        )
        version = train(dataset_dir, models_dir, read_confidence_level(config_path))
        print(f"trained={version}")
    except AppError as error:
        print(f"error={error.code}", file=sys.stderr)
        return 2
    except Exception:
        logger.exception("event=train_failed code=unexpected")
        print("error=internal_error", file=sys.stderr)
        return 1
    return 0


def _part(frame: pd.DataFrame, y: np.ndarray, groups: np.ndarray, idx: np.ndarray) -> _Part:
    """Take the rows at ``idx`` from the dataset frame and the label arrays."""
    rows = frame.iloc[idx]
    return _Part(
        rows["text"].tolist(),
        y[idx],
        groups[idx],
        rows["source_file"].tolist(),
        rows["row_key"].tolist(),
        idx,
    )


def _polarity(fit: _Part, held: _Part, confidence_level: float) -> _Polarity:
    """Select the polarity model on the train rows and measure it on the test rows."""
    selection = select_model(fit.texts, fit.y, fit.groups)
    pipeline: Pipeline = selection.pipeline
    test = evaluate(pipeline, held.texts, held.y)
    per_file = per_file_macro_f1(pipeline, held.texts, held.y, held.files)
    macro_f1 = float(f1_score(held.y, pipeline.predict(held.texts), average="macro"))
    conformal = fit_cross_conformal(pipeline, fit.texts, fit.y, fit.groups, confidence_level)
    metrics = conformal_report(conformal, held.texts, held.y)
    curve = risk_coverage(pipeline.predict_proba(held.texts), held.y)
    logger.info(
        "event=train_selected representation=%s classifier=%s",
        selection.representation,
        selection.classifier,
    )
    return _Polarity(selection, conformal, test, per_file, metrics, curve, macro_f1)


def _aspects(
    frame: pd.DataFrame, fit: _Part, held: _Part
) -> tuple[Pipeline, tuple[float, ...], dict[str, object]]:
    """Fit the aspect model on the train rows and report it on the test rows."""
    targets = aspect_targets(frame)
    pipeline, thresholds = fit_aspect_model(fit.texts, targets[fit.idx], fit.groups)
    return pipeline, thresholds, aspect_report(pipeline, thresholds, held.texts, targets[held.idx])


def _topics_report(kmeans: KMeans, terms: tuple[tuple[str, ...], ...]) -> list[dict[str, object]]:
    """Describe each topic by its size on the train rows and its top terms."""
    return [
        {"topic": t, "size": int((kmeans.labels_ == t).sum()), "terms": list(terms[t])}
        for t in range(len(terms))
    ]


def _bundle(
    polarity: _Polarity,
    aspect_model: tuple[Pipeline, tuple[float, ...]],
    topic_model: tuple[TfidfVectorizer, KMeans, tuple[tuple[str, ...], ...]],
) -> dict[str, object]:
    """Assemble the 10-key bundle of ``docs/contracts.md`` section 9.1."""
    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "class_order": tuple(p.value for p in POLARITY_ORDER),
        "aspect_order": tuple(g.value for g in ASPECT_ORDER),
        "polarity_pipeline": polarity.selection.pipeline,
        "conformal_classifier": polarity.conformal,
        "aspect_pipeline": aspect_model[0],
        "aspect_thresholds": aspect_model[1],
        "topic_vectorizer": topic_model[0],
        "topic_kmeans": topic_model[1],
        "topic_terms": topic_model[2],
    }


def _report(
    polarity: _Polarity,
    aspects: dict[str, object],
    topics: list[dict[str, object]],
    parts: tuple[_Part, _Part],
    n_groups: int,
) -> Report:
    """Assemble the 9-key report of ``docs/contracts.md`` section 9.4."""
    fit, held = parts
    return {
        "selection": list(polarity.selection.selection),
        "test": polarity.test,
        "per_file_macro_f1": polarity.per_file,
        "conformal": polarity.conformal_metrics,
        "risk_coverage": list(polarity.curve),
        "aspects": aspects,
        "topics": topics,
        "split": {"train_rows": len(fit.idx), "test_rows": len(held.idx), "groups": n_groups},
        "test_row_keys": held.keys,
    }


def _manifest(sha: str, polarity: _Polarity, confidence_level: float) -> Manifest:
    """Build the manifest; ``write_version`` replaces the six placeholder keys."""
    selection = polarity.selection
    return {
        "version": "",
        "created_at": "",
        "bundle_sha256": "",
        "dataset_sha256": sha,
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


def _configure_logging() -> None:
    """Send log records to stdout with contact data masked."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("level=%(levelname)s logger=%(name)s %(message)s"))
    handler.addFilter(RedactingFilter())
    logging.basicConfig(handlers=[handler], level=logging.INFO, force=True)


def _parser() -> argparse.ArgumentParser:
    """Build the command line parser."""
    parser = argparse.ArgumentParser(prog="ml.train")
    parser.add_argument("--dataset", default="Dataset")
    parser.add_argument("--models", default="models")
    parser.add_argument("--config", default="config/app.json")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
