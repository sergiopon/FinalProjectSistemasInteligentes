"""Dataset file checks, hashing and cleaning of the course-evaluation CSV files (spec 007)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from collections.abc import Mapping, Sequence
from pathlib import Path
from types import MappingProxyType
from typing import Final

import pandas as pd

from api.domain.entities import ASPECT_ORDER, AspectGroup, Polarity
from api.domain.errors import DatasetError
from ml.schemas import ASPECT_LABEL_TO_GROUP, CLEAN_COLUMNS, POLARITY_RAW_MAP, RAW_COLUMNS

logger = logging.getLogger(__name__)

MAX_INPUT_BYTES: Final[int] = 2_097_152

_CSV_SUFFIX: Final[str] = ".csv"
_HEADER_ID: Final[str] = "id"
_WHITESPACE_RUN: Final[re.Pattern[str]] = re.compile(r"\s+")
_POLARITY_NOISE: Final[re.Pattern[str]] = re.compile(r"[\[\]'\" ]")
_ASPECT_SENTIMENT: Final[Mapping[str, Polarity]] = MappingProxyType(
    {
        "negativo": Polarity.NEGATIVE,
        "neutral": Polarity.NEUTRAL,
        "positivo": Polarity.POSITIVE,
    }
)
_PARSE_ERRORS: Final = (UnicodeDecodeError, pd.errors.ParserError, pd.errors.EmptyDataError)


def validate_input_file(path: Path, base: Path) -> Path:
    """Check that an input CSV file is safe to read (SEC-11).

    Args:
        path: File to check.
        base: Directory the file must resolve inside.

    Returns:
        The resolved path of the file.

    Raises:
        DatasetError: The file has another extension, is a symlink, is missing, lies outside
            ``base``, is not a regular file or exceeds ``MAX_INPUT_BYTES``; or ``base`` is missing.
    """
    if path.suffix.lower() != _CSV_SUFFIX:
        raise DatasetError("input file must have the .csv extension")
    if path.is_symlink():
        raise DatasetError("input file must not be a symlink")
    resolved = _resolve_strict(path, "input file not found")
    root = _resolve_strict(base, "input base directory not found")
    if not resolved.is_relative_to(root):
        raise DatasetError("input file is outside its base directory")
    if not resolved.is_file():
        raise DatasetError("input file must be a regular file")
    if resolved.stat().st_size > MAX_INPUT_BYTES:
        raise DatasetError(f"input file exceeds {MAX_INPUT_BYTES} bytes")
    return resolved


def dataset_files(dataset_dir: Path) -> tuple[Path, ...]:
    """List the validated CSV files at the top level of the dataset directory.

    Args:
        dataset_dir: Directory holding the course CSV files.

    Returns:
        The resolved CSV paths, sorted by file name.

    Raises:
        DatasetError: The directory is missing, holds no CSV file, or a file fails its checks.
    """
    try:
        entries = sorted(dataset_dir.iterdir(), key=lambda entry: entry.name)
    except OSError as error:
        raise DatasetError("dataset directory not found") from error
    csv_entries = [entry for entry in entries if entry.suffix.lower() == _CSV_SUFFIX]
    if not csv_entries:
        raise DatasetError("no CSV files in dataset directory")
    return tuple(validate_input_file(entry, dataset_dir) for entry in csv_entries)


def dataset_sha256(files: Sequence[Path]) -> str:
    """Hash the dataset: for each file sorted by name, its name, a line feed and its bytes.

    Args:
        files: Dataset files, usually the output of ``dataset_files``.

    Returns:
        The lowercase hexadecimal SHA-256 digest.
    """
    digest = hashlib.sha256()
    for file in sorted(files, key=lambda path: path.name):
        digest.update(file.name.encode("utf-8") + b"\n")
        digest.update(file.read_bytes())
    return digest.hexdigest()


def normalize_text(text: str) -> str:
    """Apply Unicode NFC, collapse every whitespace run to one space and strip.

    Case, punctuation, accents and intensifiers are kept.

    Args:
        text: Raw comment text.

    Returns:
        The normalized text.
    """
    composed = unicodedata.normalize("NFC", text)
    return _WHITESPACE_RUN.sub(" ", composed).strip()


def normalize_polarity(raw: str) -> Polarity:
    """Map one raw polarity spelling of the dataset to its class.

    Args:
        raw: Value of the ``polaridad_basica`` column.

    Returns:
        The polarity class.

    Raises:
        DatasetError: The value is not a known spelling.
    """
    key = _POLARITY_NOISE.sub("", raw.lower())
    polarity = POLARITY_RAW_MAP.get(key)
    if polarity is None:
        raise DatasetError("unknown polarity label")
    return polarity


def parse_aspects(raw: str) -> dict[AspectGroup, Polarity]:
    """Parse the JSON aspect list of one row into one polarity per aspect group.

    A group seen with conflicting sentiments in the same row becomes neutral.

    Args:
        raw: Value of the ``aspectos`` column.

    Returns:
        A new dict holding only the groups present, keys in ``ASPECT_ORDER``.

    Raises:
        DatasetError: The value is not a JSON list of known label and sentiment entries.
    """
    try:
        entries = json.loads(raw)
    except json.JSONDecodeError as error:
        raise DatasetError("aspect list is not valid JSON") from error
    if not isinstance(entries, list):
        raise DatasetError("aspect list must be a JSON list")
    seen: dict[AspectGroup, set[Polarity]] = {}
    for entry in entries:
        group, sentiment = _parse_aspect_entry(entry)
        seen.setdefault(group, set()).add(sentiment)
    return {group: _merge_sentiments(seen[group]) for group in ASPECT_ORDER if group in seen}


def load_dataset(dataset_dir: Path) -> pd.DataFrame:
    """Read, validate and clean every CSV file of the dataset directory.

    Args:
        dataset_dir: Directory holding the course CSV files.

    Returns:
        A new frame with the columns ``CLEAN_COLUMNS``, rows in file order.

    Raises:
        DatasetError: A file fails its checks, cannot be parsed or holds an invalid value, or
            no data row remains.
    """
    files = dataset_files(dataset_dir)
    rows: list[dict[str, object]] = []
    for path in files:
        rows.extend(_clean_file(path))
    if not rows:
        raise DatasetError("dataset has no rows")
    frame = pd.DataFrame(rows, columns=list(CLEAN_COLUMNS))
    frame["source_id"] = frame["source_id"].astype("int64")
    logger.info("dataset_loaded files=%d rows=%d", len(files), len(frame))
    return frame


def _resolve_strict(path: Path, detail: str) -> Path:
    """Resolve a path that must exist, mapping resolution failures to a DatasetError."""
    try:
        return path.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise DatasetError(detail) from error


def _parse_aspect_entry(entry: object) -> tuple[AspectGroup, Polarity]:
    """Map one aspect entry of the JSON list to its group and sentiment."""
    if not isinstance(entry, dict):
        raise DatasetError("aspect entry is malformed")
    label = entry.get("aspecto")
    sentiment = entry.get("sentimiento")
    if not isinstance(label, str) or not isinstance(sentiment, str):
        raise DatasetError("aspect entry is malformed")
    group = ASPECT_LABEL_TO_GROUP.get(label)
    if group is None:
        raise DatasetError("unknown aspect label")
    polarity = _ASPECT_SENTIMENT.get(sentiment)
    if polarity is None:
        raise DatasetError("unknown aspect sentiment")
    return group, polarity


def _merge_sentiments(sentiments: set[Polarity]) -> Polarity:
    """Return the single sentiment of a group, or neutral when they conflict."""
    if len(sentiments) == 1:
        return next(iter(sentiments))
    return Polarity.NEUTRAL


def _read_raw_file(path: Path) -> pd.DataFrame:
    """Parse one CSV file as strings, check its header and drop repeated header rows."""
    try:
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except _PARSE_ERRORS as error:
        raise DatasetError("dataset file is not a parseable CSV") from error
    if list(frame.columns) != list(RAW_COLUMNS):
        raise DatasetError("dataset columns do not match")
    return frame[frame["id"] != _HEADER_ID]


def _clean_file(path: Path) -> list[dict[str, object]]:
    """Clean every data row of one CSV file, numbering rows from 1 in file order."""
    records: list[dict[str, str]] = _read_raw_file(path).to_dict("records")
    return [_clean_row(path.name, number, record) for number, record in enumerate(records, start=1)]


def _parse_source_id(raw: str) -> int:
    """Convert the raw ``id`` value to an integer."""
    try:
        return int(raw)
    except ValueError as error:
        raise DatasetError("dataset id is not an integer") from error


def _clean_row(file_name: str, number: int, record: dict[str, str]) -> dict[str, object]:
    """Build one row of the clean frame from one raw CSV record."""
    source_id = _parse_source_id(record["id"])
    text = normalize_text(record["feedback"])
    if not text:
        raise DatasetError("dataset text is empty")
    polarity = normalize_polarity(record["polaridad_basica"])
    aspects = parse_aspects(record["aspectos"])
    row: dict[str, object] = {
        "row_key": f"{file_name}:{number}",
        "source_file": file_name,
        "source_id": source_id,
        "course": record["curso"],
        "semester": record["semestre"],
        "text": text,
        "polarity": polarity.value,
    }
    for group in ASPECT_ORDER:
        row[f"aspect_{group.value}"] = aspects[group].value if group in aspects else ""
    return row
