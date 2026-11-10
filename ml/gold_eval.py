"""Evaluation of the active bundle on the agreed gold rows (spec 029)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final, cast

import numpy as np
import pandas as pd
from mapie.classification import CrossConformalClassifier
from sklearn.metrics import f1_score, precision_score, recall_score
from sklearn.pipeline import Pipeline

from api.domain.entities import ASPECT_ORDER, POLARITY_ORDER, AspectGroup
from api.domain.errors import (
    AppError,
    DatasetError,
    InvalidInputError,
    ModelUnavailableError,
)
from api.domain.safety import resolve_within
from ml.artifact import load_verified
from ml.conformal import conformal_report
from ml.data import load_dataset, validate_input_file
from ml.evaluation import evaluate

logger = logging.getLogger(__name__)

GOLD_SHEETS: Final[tuple[str, str]] = ("sheet_a.csv", "sheet_b.csv")
REPORT_NAME: Final[str] = "gold_eval.json"
REPORTS_DIR: Final[Path] = Path("reports")
ASPECT_COLUMNS: Final[tuple[str, ...]] = tuple(f"aspect_{group.value}" for group in ASPECT_ORDER)
GOLD_COLUMNS: Final[tuple[str, ...]] = ("row_key", "polarity", *ASPECT_COLUMNS)
POLARITY_VALUES: Final[frozenset[str]] = frozenset(p.value for p in POLARITY_ORDER)
ASPECT_VALUES: Final[frozenset[str]] = POLARITY_VALUES | {""}

_PARSE_ERRORS: Final = (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError)
_VERSION_PATTERN: Final[re.Pattern[str]] = re.compile(r"^v\d{3}$")
_LABEL_COLUMNS: Final[tuple[str, ...]] = GOLD_COLUMNS[1:]
_CLASS_INDEX: Final[dict[str, int]] = {p.value: i for i, p in enumerate(POLARITY_ORDER)}


def read_gold_sheet(path: Path, gold_dir: Path) -> pd.DataFrame:
    """Read and normalize one annotator sheet (SEC-11).

    Args:
        path: Sheet file.
        gold_dir: Directory the sheet must resolve inside.

    Returns:
        A new frame with the columns ``GOLD_COLUMNS``; labels stripped and lower-cased.

    Raises:
        DatasetError: The file fails SEC-11, cannot be parsed, lacks a column, repeats a
            ``row_key`` or holds an invalid polarity or aspect value.
    """
    resolved = validate_input_file(path, gold_dir)
    try:
        raw = pd.read_csv(resolved, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except _PARSE_ERRORS as error:
        raise DatasetError("gold sheet cannot be parsed") from error
    if not set(GOLD_COLUMNS) <= set(raw.columns):
        raise DatasetError("gold sheet missing columns")
    sheet = raw[list(GOLD_COLUMNS)].copy()
    sheet["row_key"] = sheet["row_key"].str.strip()
    for column in _LABEL_COLUMNS:
        sheet[column] = sheet[column].str.strip().str.lower()
    if sheet["row_key"].duplicated().any():
        raise DatasetError("gold sheet has duplicate row keys")
    if not sheet["polarity"].isin(POLARITY_VALUES).all():
        raise DatasetError("gold sheet has an invalid polarity value")
    if not sheet[list(ASPECT_COLUMNS)].isin(ASPECT_VALUES).to_numpy().all():
        raise DatasetError("gold sheet has an invalid aspect value")
    return sheet


def agreed_polarity(sheet_a: pd.DataFrame, sheet_b: pd.DataFrame) -> pd.DataFrame:
    """Keep the rows with the same polarity in both sheets; the key sets MUST be equal."""
    merged = _merge_column(sheet_a, sheet_b, "polarity")
    agreed = merged[merged["polarity_a"] == merged["polarity_b"]]
    return agreed.rename(columns={"polarity_a": "polarity"})[["row_key", "polarity"]].reset_index(
        drop=True
    )


def agreed_presence(
    sheet_a: pd.DataFrame, sheet_b: pd.DataFrame, group: AspectGroup
) -> pd.DataFrame:
    """Keep the rows where both sheets agree on presence: ``row_key`` and ``present`` (bool)."""
    merged = _merge_column(sheet_a, sheet_b, f"aspect_{group.value}")
    present_a = (merged.iloc[:, 1] != "").to_numpy()
    present_b = (merged.iloc[:, 2] != "").to_numpy()
    agreed = pd.DataFrame({"row_key": merged["row_key"], "present": present_a})
    return agreed[present_a == present_b].reset_index(drop=True)


def presence_metrics(gold: Sequence[bool], predicted: Sequence[bool]) -> dict[str, float | int]:
    """Precision, recall and F1 of the positive class; unequal lengths are rejected."""
    if len(gold) != len(predicted):
        raise InvalidInputError("gold and predicted lengths differ")
    y_true = np.asarray(gold, dtype=int)
    y_pred = np.asarray(predicted, dtype=int)
    if len(gold) == 0:
        return {"agreed_rows": 0, "gold_present": 0, "precision": 0.0, "recall": 0.0, "f1": 0.0}
    return {
        "agreed_rows": len(gold),
        "gold_present": int(y_true.sum()),
        "precision": float(precision_score(y_true, y_pred, zero_division=0.0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0.0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0.0)),
    }


def active_version(models_dir: Path) -> str:
    """Return the active version name from ``registry.json`` or raise ``ModelUnavailableError``."""
    registry = _read_json(resolve_within(models_dir, Path("registry.json")), "registry not found")
    active = registry.get("active")
    if not isinstance(active, str) or not _VERSION_PATTERN.fullmatch(active):
        raise ModelUnavailableError("registry has no active version")
    return active


def evaluate_gold(gold_dir: Path, dataset_dir: Path, models_dir: Path) -> dict[str, object]:
    """Evaluate the active bundle against the rows where both annotators agree.

    Returns:
        The report of ``reports/gold_eval.json``: counts and metrics only.

    Raises:
        DatasetError: A sheet or the row keys are invalid, or no polarity agreement exists.
        ModelUnavailableError: The registry, report or bundle objects are unusable.
    """
    version = active_version(models_dir)
    polarity_pipeline, aspect_pipeline, conformal, thresholds = _narrow_bundle(
        load_verified(models_dir, version)
    )
    test_keys = set(_test_row_keys(models_dir, version))
    sheet_a, sheet_b = (read_gold_sheet(gold_dir / name, gold_dir) for name in GOLD_SHEETS)
    lookup = load_dataset(dataset_dir).set_index("row_key")
    if not set(sheet_a["row_key"]) | set(sheet_b["row_key"]) <= set(lookup.index):
        raise DatasetError("gold row key not in dataset")
    agreed = agreed_polarity(sheet_a, sheet_b)
    polarity = _polarity_block(polarity_pipeline, conformal, agreed, lookup, test_keys)
    aspects = _aspect_blocks(aspect_pipeline, thresholds, (sheet_a, sheet_b), lookup)
    return {
        "model_version": version,
        "gold_rows": len(sheet_a),
        "polarity": polarity,
        "aspects": aspects,
        "aspect_macro_f1": float(np.mean([block["f1"] for block in aspects.values()])),
    }


def write_report(reports_dir: Path, report: Mapping[str, object]) -> Path:
    """Write the report as JSON with owner-only permissions (SEC-04, SEC-12)."""
    reports_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = resolve_within(reports_dir, Path(REPORT_NAME))
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.chmod(target, 0o600)
    return target


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gold evaluation command line.

    Returns:
        0 on success, 2 for an expected error, 1 for an unexpected one.
    """
    os.umask(0o077)
    parser = argparse.ArgumentParser(prog="ml.gold_eval")
    parser.add_argument("--gold", default="gold")
    parser.add_argument("--dataset", default="Dataset")
    parser.add_argument("--models", default="models")
    args = parser.parse_args(argv)
    try:
        report = evaluate_gold(Path(args.gold), Path(args.dataset), Path(args.models))
        target = write_report(REPORTS_DIR, report)
        polarity = cast("dict[str, int]", report["polarity"])
        logger.info(
            "gold_eval_done version=%s agreed_rows=%d",
            report["model_version"],
            polarity["agreed_rows"],
        )
        print(target)
    except AppError as error:
        logger.error("gold_eval_failed code=%s", error.code)
        return 2
    except Exception:
        logger.exception("gold_eval_crashed")
        return 1
    return 0


def _merge_column(sheet_a: pd.DataFrame, sheet_b: pd.DataFrame, column: str) -> pd.DataFrame:
    """Join one label column of both sheets on ``row_key``, sorted by key."""
    if set(sheet_a["row_key"]) != set(sheet_b["row_key"]):
        raise DatasetError("gold sheets have different row keys")
    merged = sheet_a[["row_key", column]].merge(
        sheet_b[["row_key", column]], on="row_key", suffixes=("_a", "_b")
    )
    return merged.sort_values("row_key").reset_index(drop=True)


def _read_json(path: Path, missing_detail: str) -> dict[str, object]:
    """Read a JSON object, or raise ``ModelUnavailableError`` with ``missing_detail``."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ModelUnavailableError(missing_detail) from error
    if not isinstance(data, dict):
        raise ModelUnavailableError(missing_detail)
    return data


def _test_row_keys(models_dir: Path, version: str) -> list[str]:
    """Read the held-out ``row_key`` list of a version's report."""
    report = _read_json(
        resolve_within(models_dir, Path(version) / "report.json"), "report not found"
    )
    keys = report.get("test_row_keys")
    if not isinstance(keys, list):
        raise ModelUnavailableError("report not found")
    return [str(key) for key in keys]


def _narrow_bundle(
    bundle: Mapping[str, object],
) -> tuple[Pipeline, Pipeline, CrossConformalClassifier, tuple[float, ...]]:
    """Check the type of each bundle object that the evaluation uses."""
    polarity = bundle["polarity_pipeline"]
    aspect = bundle["aspect_pipeline"]
    conformal = bundle["conformal_classifier"]
    thresholds = bundle["aspect_thresholds"]
    if (
        not isinstance(polarity, Pipeline)
        or not isinstance(aspect, Pipeline)
        or not isinstance(conformal, CrossConformalClassifier)
        or not isinstance(thresholds, tuple | list)
        or len(thresholds) != len(ASPECT_ORDER)
        or not all(isinstance(value, float) for value in thresholds)
    ):
        raise ModelUnavailableError("bundle object has an unexpected type")
    return polarity, aspect, conformal, tuple(float(value) for value in thresholds)


def _polarity_block(
    pipeline: Pipeline,
    conformal: CrossConformalClassifier,
    agreed: pd.DataFrame,
    lookup: pd.DataFrame,
    test_keys: set[str],
) -> dict[str, object]:
    """Polarity metrics, conformal coverage and dataset-label accuracy on agreed rows."""
    if agreed.empty:
        raise DatasetError("no agreed gold rows")
    keys = agreed["row_key"].tolist()
    texts = lookup.loc[keys, "text"].tolist()
    gold = agreed["polarity"].tolist()
    y = np.array([_CLASS_INDEX[label] for label in gold], dtype=np.int64)
    dataset_labels = [str(label) for label in lookup.loc[keys, "polarity"]]
    return {
        "agreed_rows": len(keys),
        "test_rows": sum(key in test_keys for key in keys),
        "dataset_label_accuracy": float(np.mean(np.array(dataset_labels) == np.array(gold))),
        "metrics": evaluate(pipeline, texts, y),
        "conformal": conformal_report(conformal, texts, y),
    }


def _aspect_blocks(
    pipeline: Pipeline,
    thresholds: tuple[float, ...],
    sheets: tuple[pd.DataFrame, pd.DataFrame],
    lookup: pd.DataFrame,
) -> dict[str, dict[str, float | int]]:
    """Per-group presence metrics from one ``predict_proba`` call over all sheet rows."""
    keys = sorted(sheets[0]["row_key"])
    texts = np.asarray(lookup.loc[keys, "text"].tolist(), dtype=object)
    scores = np.asarray(pipeline.predict_proba(texts))
    blocks: dict[str, dict[str, float | int]] = {}
    for j, group in enumerate(ASPECT_ORDER):
        agreed = agreed_presence(sheets[0], sheets[1], group)
        present = pd.Series(scores[:, j] >= thresholds[j], index=keys)
        predicted = present.loc[agreed["row_key"]].tolist()
        metrics = presence_metrics(agreed["present"].tolist(), predicted)
        blocks[group.value] = {**metrics, "threshold": thresholds[j]}
    return blocks


if __name__ == "__main__":
    raise SystemExit(main())
