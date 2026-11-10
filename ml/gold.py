"""Gold-set sampling and inter-annotator agreement: ``python -m ml.gold`` (spec 015)."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd
from sklearn.metrics import cohen_kappa_score
from sklearn.model_selection import train_test_split

from api.domain.entities import ASPECT_ORDER, POLARITY_ORDER
from api.domain.errors import AppError, DatasetError
from api.domain.safety import RedactingFilter, resolve_within
from ml.data import load_dataset, validate_input_file
from ml.schemas import SEED

logger: logging.Logger = logging.getLogger(__name__)

DATASET_DIR: Final[Path] = Path("Dataset")
GOLD_DIR: Final[Path] = Path("gold")
SHEET_FILES: Final[tuple[str, str]] = ("sheet_a.csv", "sheet_b.csv")
AGREEMENT_FILE: Final[str] = "agreement.json"
DEFAULT_SAMPLE_SIZE: Final[int] = 100
MIN_SAMPLE_SIZE: Final[int] = 10
MAX_SAMPLE_SIZE: Final[int] = 200
ASPECT_COLUMNS: Final[tuple[str, ...]] = tuple(f"aspect_{group.value}" for group in ASPECT_ORDER)
SHEET_COLUMNS: Final[tuple[str, ...]] = ("gold_id", "row_key", "text", "polarity", *ASPECT_COLUMNS)
POLARITY_VALUES: Final[tuple[str, ...]] = tuple(p.value for p in POLARITY_ORDER)
ASPECT_VALUES: Final[tuple[str, ...]] = ("", *POLARITY_VALUES)
PRESENCE_VALUES: Final[tuple[str, str]] = ("absent", "present")

_PARSE_ERRORS: Final = (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError)
_LABEL_COLUMNS: Final[list[str]] = ["polarity", *ASPECT_COLUMNS]


def sample_sheet(frame: pd.DataFrame, n: int) -> pd.DataFrame:
    """Draw a polarity-stratified sample and build a blank annotation sheet.

    The dataset label never appears in the sheet.

    Args:
        frame: Clean frame; only ``row_key``, ``text`` and ``polarity`` are used.
        n: Number of comments to sample.

    Returns:
        A new frame with the columns ``SHEET_COLUMNS`` and ``n`` rows.

    Raises:
        DatasetError: ``n`` is out of range or the sample cannot be stratified.
    """
    if n < MIN_SAMPLE_SIZE or n > MAX_SAMPLE_SIZE:
        raise DatasetError("sample size out of range")
    try:
        positions, _ = train_test_split(
            np.arange(len(frame)),
            train_size=n,
            stratify=frame["polarity"].to_numpy(),
            random_state=SEED,
        )
    except ValueError as error:
        raise DatasetError("cannot stratify sample") from error
    chosen = frame.iloc[positions]
    sheet = pd.DataFrame(
        {
            "gold_id": [str(i) for i in range(1, n + 1)],
            "row_key": chosen["row_key"].to_numpy(),
            "text": chosen["text"].to_numpy(),
        }
    )
    for column in SHEET_COLUMNS[3:]:
        sheet[column] = ""
    return sheet[list(SHEET_COLUMNS)]


def write_sheets(sheet: pd.DataFrame, gold_dir: Path) -> tuple[Path, Path]:
    """Write the same blank sheet twice, once per annotator, never overwriting a file.

    Args:
        sheet: Sheet from ``sample_sheet``.
        gold_dir: Directory that receives the sheets; created when missing.

    Returns:
        The paths of the two sheets.

    Raises:
        DatasetError: A sheet already exists; nothing is written.
    """
    gold_dir.mkdir(exist_ok=True)
    first, second = (resolve_within(gold_dir, Path(name)) for name in SHEET_FILES)
    if first.exists() or second.exists():
        raise DatasetError("gold sheets already exist")
    for target in (first, second):
        sheet.to_csv(target, index=False, encoding="utf-8", mode="x", lineterminator="\n")
    return first, second


def read_sheet(path: Path, gold_dir: Path) -> pd.DataFrame:
    """Read and validate one filled annotation sheet (SEC-11).

    Args:
        path: Sheet file.
        gold_dir: Directory the sheet must lie inside.

    Returns:
        A new frame with ``polarity`` and aspect cells stripped and lowercased.

    Raises:
        DatasetError: The file fails the input checks, is unreadable, has other columns, has an
            incomplete or invalid cell, or has no rows.
    """
    resolved = validate_input_file(path, gold_dir)
    try:
        raw = pd.read_csv(resolved, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except _PARSE_ERRORS as error:
        raise DatasetError("gold sheet unreadable") from error
    if list(raw.columns) != list(SHEET_COLUMNS):
        raise DatasetError("gold sheet columns mismatch")
    frame = _normalize_sheet(raw)
    _check_sheet_values(frame)
    if len(frame) == 0:
        raise DatasetError("gold sheet has no rows")
    return frame


def cohen_kappa(first: Sequence[str], second: Sequence[str], labels: Sequence[str]) -> float | None:
    """Return Cohen's kappa of two raters, or None when it is undefined.

    Args:
        first: Labels of the first rater.
        second: Labels of the second rater.
        labels: Every label that may occur.

    Returns:
        The kappa, or None when both raters used one same single value.
    """
    if len(set(first) | set(second)) == 1:
        return None
    return float(cohen_kappa_score(list(first), list(second), labels=list(labels)))


def agreement(sheet_a: pd.DataFrame, sheet_b: pd.DataFrame) -> dict[str, object]:
    """Measure the agreement of two annotators on polarity and on each aspect group.

    Args:
        sheet_a: Sheet of annotator A, from ``read_sheet``.
        sheet_b: Sheet of annotator B, from ``read_sheet``.

    Returns:
        Row count, polarity kappa and observed agreement, and per group the presence and label
        kappa; every float is rounded to 6 decimals.

    Raises:
        DatasetError: The sheets differ in length, ``gold_id`` or ``row_key``.
    """
    same_keys = all(list(sheet_a[c]) == list(sheet_b[c]) for c in ("gold_id", "row_key"))
    if len(sheet_a) != len(sheet_b) or not same_keys:
        raise DatasetError("gold sheets do not match")
    polarity_a, polarity_b = list(sheet_a["polarity"]), list(sheet_b["polarity"])
    equal = sum(a == b for a, b in zip(polarity_a, polarity_b, strict=True))
    return {
        "rows": len(sheet_a),
        "polarity": {
            "kappa": _rounded(cohen_kappa(polarity_a, polarity_b, POLARITY_VALUES)),
            "observed_agreement": round(equal / len(sheet_a), 6),
        },
        "aspects": {
            group.value: _aspect_agreement(sheet_a, sheet_b, f"aspect_{group.value}")
            for group in ASPECT_ORDER
        },
    }


def main(argv: Sequence[str] | None = None) -> int:
    """Run ``sample`` or ``agreement``; return 0, 2 for an expected error or 1 for any other."""
    os.umask(0o077)
    _configure_logging()
    args = _parser().parse_args(argv)
    try:
        if args.command == "sample":
            _run_sample(args.n)
        else:
            _run_agreement()
    except AppError as error:
        logger.error("event=gold_failed code=%s detail=%s", error.code, error.detail)
        print(f"ml.gold failed: {error.detail}", file=sys.stderr)
        return 2
    except Exception:
        logger.exception("event=gold_failed code=unexpected")
        print("ml.gold failed: unexpected error, see the log.", file=sys.stderr)
        return 1
    return 0


def _rounded(value: float | None) -> float | None:
    """Round a kappa to 6 decimals; None stays None."""
    return None if value is None else round(value, 6)


def _aspect_agreement(
    sheet_a: pd.DataFrame, sheet_b: pd.DataFrame, column: str
) -> dict[str, float | None]:
    """Presence and label kappa of the aspect group held in ``column``."""
    first, second = list(sheet_a[column]), list(sheet_b[column])
    presence = [["present" if cell else "absent" for cell in cells] for cells in (first, second)]
    return {
        "presence_kappa": _rounded(cohen_kappa(presence[0], presence[1], PRESENCE_VALUES)),
        "label_kappa": _rounded(cohen_kappa(first, second, ASPECT_VALUES)),
    }


def _normalize_sheet(frame: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with the label columns stripped and lowercased."""
    normalized = frame.copy()
    for column in _LABEL_COLUMNS:
        normalized[column] = normalized[column].str.strip().str.lower()
    return normalized


def _check_sheet_values(frame: pd.DataFrame) -> None:
    """Check ``polarity`` over all rows first, then the aspect cells row by row."""
    for number, value in enumerate(frame["polarity"], start=1):
        if value not in POLARITY_VALUES:
            raise DatasetError(f"gold sheet incomplete: row {number}")
    cells = frame[list(ASPECT_COLUMNS)].to_numpy()
    for number, row in enumerate(cells, start=1):
        if any(cell not in ASPECT_VALUES for cell in row):
            raise DatasetError(f"gold sheet invalid aspect: row {number}")


def _run_sample(n: int) -> None:
    """Sample the dataset and write the two blank sheets."""
    sheet = sample_sheet(load_dataset(DATASET_DIR), n)
    write_sheets(sheet, resolve_within(Path.cwd(), GOLD_DIR))
    logger.info("event=gold_sample rows=%d", len(sheet))


def _run_agreement() -> None:
    """Read both filled sheets and write ``agreement.json``."""
    gold_dir = resolve_within(Path.cwd(), GOLD_DIR)
    sheet_a, sheet_b = (read_sheet(gold_dir / name, gold_dir) for name in SHEET_FILES)
    result = agreement(sheet_a, sheet_b)
    target = resolve_within(gold_dir, Path(AGREEMENT_FILE))
    target.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    logger.info("event=gold_agreement rows=%d", len(sheet_a))


def _configure_logging() -> None:
    """Send log records to stdout with contact data masked."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("level=%(levelname)s logger=%(name)s %(message)s"))
    handler.addFilter(RedactingFilter())
    logging.basicConfig(handlers=[handler], level=logging.INFO, force=True)


def _parser() -> argparse.ArgumentParser:
    """Build the command line parser."""
    parser = argparse.ArgumentParser(prog="ml.gold")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("sample").add_argument("--n", type=int, default=DEFAULT_SAMPLE_SIZE)
    commands.add_parser("agreement")
    return parser


if __name__ == "__main__":
    raise SystemExit(main())
