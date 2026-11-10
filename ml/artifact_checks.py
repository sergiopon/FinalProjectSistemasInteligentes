"""Schema checks for the inputs of ml.artifact.write_version (spec 013)."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Final, cast

from api.domain.errors import InvalidInputError
from ml.schemas import BUNDLE_SCHEMA_VERSION, Manifest, ReferenceStats, Report

BUNDLE_KEYS: Final[frozenset[str]] = frozenset(
    {
        "schema_version",
        "class_order",
        "aspect_order",
        "polarity_pipeline",
        "conformal_classifier",
        "aspect_pipeline",
        "aspect_thresholds",
        "topic_vectorizer",
        "topic_kmeans",
        "topic_terms",
    }
)
_REPORT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "selection",
        "test",
        "per_file_macro_f1",
        "conformal",
        "risk_coverage",
        "aspects",
        "topics",
        "split",
        "test_row_keys",
    }
)
_REFERENCE_KEYS: Final[frozenset[str]] = frozenset(
    {"length_edges", "length_shares", "reference_oov_rate", "class_shares"}
)
_MAX_REPORT_WORDS: Final[int] = 3
_MAX_REPORT_CHARS: Final[int] = 80
_SHARE_TOLERANCE: Final[float] = 1e-6
_EDGE_COUNT: Final[int] = 9
_LENGTH_SHARE_COUNT: Final[int] = 10
_CLASS_SHARE_COUNT: Final[int] = 3
_SHA256 = re.compile(r"[0-9a-f]{64}")
_REVISION = re.compile(r"[0-9a-f]{40}")
SHA256 = _SHA256


def check_bundle(bundle: dict[str, object]) -> None:
    """Check the key set and schema version of a bundle."""
    if set(bundle) != BUNDLE_KEYS or bundle["schema_version"] != BUNDLE_SCHEMA_VERSION:
        raise InvalidInputError("bundle keys do not match the schema")


def check_manifest(manifest: Manifest) -> None:
    """Check the dataset hash, the embedding revision and the metrics of a manifest."""
    dataset = manifest["dataset_sha256"]
    if not isinstance(dataset, str) or not _SHA256.fullmatch(dataset):
        raise InvalidInputError("dataset_sha256 must be 64 lowercase hex characters")
    revision = cast("Mapping[str, object]", manifest["embedding"]).get("revision")
    if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
        raise InvalidInputError("embedding revision must be a 40-character commit hash")
    metrics = cast("Mapping[str, object]", manifest["metrics"])
    for name in ("test_macro_f1", "empirical_coverage"):
        value = metrics.get(name)
        if not isinstance(value, float) or not 0.0 <= value <= 1.0:
            raise InvalidInputError("manifest metrics are incomplete")


def check_report(report: Report) -> None:
    """Check the key set of a report and that it holds no comment text."""
    if set(report) != _REPORT_KEYS:
        raise InvalidInputError("report.json keys do not match the schema")
    if _has_comment_text(report):
        raise InvalidInputError("report.json must not contain comment text")


def _has_comment_text(value: object) -> bool:
    """Return True when a string in the value is long enough to be a comment."""
    if isinstance(value, str):
        return len(value.split()) > _MAX_REPORT_WORDS or len(value) > _MAX_REPORT_CHARS
    if isinstance(value, Mapping):
        return any(_has_comment_text(k) or _has_comment_text(v) for k, v in value.items())
    if isinstance(value, list | tuple):
        return any(_has_comment_text(item) for item in value)
    return False


def check_reference(reference: ReferenceStats) -> None:
    """Check the drift reference statistics against their schema."""
    raw = cast("Mapping[str, object]", reference)
    valid = (
        set(raw) == _REFERENCE_KEYS
        and _is_edges(raw["length_edges"])
        and _is_shares(raw["length_shares"], _LENGTH_SHARE_COUNT)
        and _is_shares(raw["class_shares"], _CLASS_SHARE_COUNT)
        and _is_unit_float(raw["reference_oov_rate"])
    )
    if not valid:
        raise InvalidInputError("reference_stats.json does not match the schema")


def _is_unit_float(value: object) -> bool:
    """Return True for a float in [0, 1]."""
    return isinstance(value, float) and 0.0 <= value <= 1.0


def _is_edges(value: object) -> bool:
    """Return True for nine non-decreasing ints."""
    return (
        isinstance(value, list)
        and len(value) == _EDGE_COUNT
        and all(type(item) is int for item in value)
        and all(a <= b for a, b in zip(value, value[1:], strict=False))
    )


def _is_shares(value: object, count: int) -> bool:
    """Return True for ``count`` floats that sum to 1."""
    return (
        isinstance(value, list)
        and len(value) == count
        and all(isinstance(item, float) for item in value)
        and math.isclose(sum(value), 1.0, abs_tol=_SHARE_TOLERANCE)
    )
