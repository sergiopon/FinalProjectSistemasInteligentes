"""Train, evaluate and publish a model version: ``python -m ml.train`` (spec 014).

Runs clean, split, select, evaluate, conformal, aspects, topics, write and activate, in that
order. Every fit uses the train rows only (ARCHITECTURE.md section 3).
"""

from __future__ import annotations

import argparse
import bisect
import json
import logging
import os
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

from api.domain.entities import POLARITY_ORDER, Polarity
from api.domain.errors import AppError, ConfigError, InvalidInputError
from api.domain.safety import RedactingFilter, resolve_within
from ml.artifact import activate, write_version
from ml.aspects import aspect_report, aspect_targets, fit_aspect_model
from ml.conformal import conformal_report, fit_cross_conformal
from ml.data import dataset_files, dataset_sha256, load_dataset
from ml.evaluation import evaluate, per_file_macro_f1, risk_coverage
from ml.schemas import ReferenceStats, SplitInfo
from ml.selection import select_model
from ml.split import grouped_split, template_groups
from ml.topics import fit_topics
from ml.train_parts import PolarityResult, Rows, build_bundle, build_manifest, build_report

logger = logging.getLogger(__name__)

_DECILES: Final[tuple[int, ...]] = (10, 20, 30, 40, 50, 60, 70, 80, 90)
_SHARE_FLOOR: Final[float] = 1e-4
_TOKEN_PATTERN: Final[re.Pattern[str]] = re.compile(r"(?u)\b\w\w+\b")
_CLASS_COUNT: Final[int] = 3


def read_confidence_level(config_path: Path) -> float:
    """Read the conformal confidence level from the application config.

    Args:
        config_path: Path of ``config/app.json``.

    Returns:
        ``1 - conformal.alpha``.

    Raises:
        ConfigError: The file is unreadable or ``conformal.alpha`` is not a number in (0, 1).
    """
    try:
        config: object = json.loads(config_path.read_text(encoding="utf-8"))
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
    """Build the drift reference statistics of docs/contracts.md section 9.5.

    Args:
        train_texts: Train texts.
        test_texts: Test texts, measured against the train vocabulary.
        y_train: Class index of each train text.
        vocabulary: Terms of the topic vocabulary.

    Returns:
        Length deciles and shares, the out-of-vocabulary rate and the class shares.

    Raises:
        InvalidInputError: An input is empty or the labels do not match the texts.
    """
    if not train_texts or not test_texts or len(y_train) != len(train_texts):
        raise InvalidInputError("reference statistics need matching non-empty inputs")
    lengths = [len(text) for text in train_texts]
    edges = [int(v) for v in np.percentile(lengths, _DECILES, method="lower")]
    counts = [0] * (len(edges) + 1)
    for length in lengths:
        counts[bisect.bisect_right(edges, length)] += 1
    raw = [max(count / len(lengths), _SHARE_FLOOR) for count in counts]
    return {
        "length_edges": edges,
        "length_shares": [value / sum(raw) for value in raw],
        "reference_oov_rate": _oov_rate(test_texts, vocabulary),
        "class_shares": [float((y_train == k).sum()) / len(y_train) for k in range(_CLASS_COUNT)],
    }


def train(dataset_dir: Path, models_dir: Path, confidence_level: float) -> str:
    """Run the whole training pipeline and activate the new version.

    Args:
        dataset_dir: Directory with the three dataset CSV files.
        models_dir: Directory that receives ``vNNN`` and ``registry.json``.
        confidence_level: Target coverage of the conformal sets.

    Returns:
        The name of the version written.
    """
    frame, sha, y = _load(dataset_dir)
    groups = template_groups(frame["text"].tolist())
    train_idx, test_idx = grouped_split(y, groups)
    fit, test = _take(frame, y, groups, train_idx), _take(frame, y, groups, test_idx)
    logger.info(
        "event=train_split train_rows=%d test_rows=%d groups=%d",
        len(train_idx),
        len(test_idx),
        np.unique(groups).size,
    )
    polarity = _fit_polarity(fit, test, confidence_level)
    targets = aspect_targets(frame)
    aspect_model, thresholds = fit_aspect_model(fit.texts, targets[train_idx], fit.groups)
    aspects = aspect_report(aspect_model, thresholds, test.texts, targets[test_idx])
    topics = fit_topics(fit.texts)
    stats = reference_stats(fit.texts, test.texts, fit.y, frozenset(topics[0].vocabulary_))
    bundle = build_bundle(polarity, (aspect_model, thresholds), topics)
    split: SplitInfo = {
        "train_rows": len(train_idx),
        "test_rows": len(test_idx),
        "groups": int(np.unique(groups).size),
    }
    report = build_report(polarity, test, aspects, topics, split)
    manifest = build_manifest(polarity, sha, confidence_level)
    version = write_version(models_dir, bundle, manifest, report, stats).name
    activate(models_dir, version)
    logger.info(
        "event=train_done version=%s test_macro_f1=%.4f empirical_coverage=%.4f",
        version,
        polarity.macro_f1,
        polarity.conformal_metrics["empirical_coverage"],
    )
    return version


def main(argv: Sequence[str] | None = None) -> int:
    """Run the training command line.

    Args:
        argv: Arguments without the program name; defaults to ``sys.argv``.

    Returns:
        0 on success, 2 for an expected error, 1 for an unexpected one.
    """
    os.umask(0o077)
    _configure_logging()
    args = _parser().parse_args(argv)
    try:
        base = Path.cwd()
        dataset, models, config = (
            resolve_within(base, Path(value)) for value in (args.dataset, args.models, args.config)
        )
        version = train(dataset, models, read_confidence_level(config))
    except AppError as error:
        print(f"error={error.code}", file=sys.stderr)
        return 2
    except Exception:
        logger.exception("event=train_failed code=unexpected")
        print("error=internal_error", file=sys.stderr)
        return 1
    print(f"trained={version}")
    return 0


def _oov_rate(texts: Sequence[str], vocabulary: frozenset[str]) -> float:
    """Return the share of tokens of ``texts`` that are not in the vocabulary."""
    tokens = [token for text in texts for token in _TOKEN_PATTERN.findall(text.lower())]
    if not tokens:
        return 0.0
    return sum(token not in vocabulary for token in tokens) / len(tokens)


def _load(dataset_dir: Path) -> tuple[pd.DataFrame, str, np.ndarray]:
    """Load the clean dataset, its hash and the class index of each row."""
    frame = load_dataset(dataset_dir)
    sha = dataset_sha256(dataset_files(dataset_dir))
    y = np.array([POLARITY_ORDER.index(Polarity(v)) for v in frame["polarity"]], dtype=np.int64)
    logger.info("event=train_dataset rows=%d dataset_sha256=%s", len(frame), sha)
    return frame, sha, y


def _take(frame: pd.DataFrame, y: np.ndarray, groups: np.ndarray, idx: np.ndarray) -> Rows:
    """Select the rows at the given positions."""
    rows = frame.iloc[idx]
    return Rows(
        rows["text"].tolist(),
        y[idx],
        groups[idx],
        rows["source_file"].tolist(),
        rows["row_key"].tolist(),
    )


def _fit_polarity(fit: Rows, test: Rows, confidence_level: float) -> PolarityResult:
    """Select the polarity model on the train rows and measure it on the test rows."""
    selection = select_model(fit.texts, fit.y, fit.groups)
    pipeline = selection.pipeline
    test_metrics = evaluate(pipeline, test.texts, test.y)
    per_file = per_file_macro_f1(pipeline, test.texts, test.y, test.files)
    macro_f1 = float(f1_score(test.y, pipeline.predict(test.texts), average="macro"))
    conformal = fit_cross_conformal(pipeline, fit.texts, fit.y, fit.groups, confidence_level)
    conformal_metrics = conformal_report(conformal, test.texts, test.y)
    curve = risk_coverage(pipeline.predict_proba(test.texts), test.y)
    logger.info(
        "event=train_selected representation=%s classifier=%s",
        selection.representation,
        selection.classifier,
    )
    return PolarityResult(
        selection, conformal, conformal_metrics, curve, test_metrics, per_file, macro_f1
    )


def _configure_logging() -> None:
    """Send logs to stdout in the project format, with comment text redacted."""
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
