"""Model store that loads a joblib bundle only after verifying its origin and versions."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import logging
import re
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Final

import joblib

from api.domain.entities import ASPECT_ORDER, POLARITY_ORDER
from api.domain.errors import (
    InvalidInputError,
    ModelIntegrityError,
    ModelUnavailableError,
    UnsafePathError,
)
from api.domain.reports import ModelInfo
from api.domain.safety import resolve_within
from ml.schemas import BUNDLE_SCHEMA_VERSION

VERSION_PATTERN: Final[re.Pattern[str]] = re.compile(r"v\d{3}")
SHA256_PATTERN: Final[re.Pattern[str]] = re.compile(r"[0-9a-f]{64}")
REGISTRY_FILE: Final = "registry.json"
MANIFEST_FILE: Final = "manifest.json"
BUNDLE_FILE: Final = "bundle.joblib"
CHECKED_LIBRARIES: Final[tuple[str, ...]] = ("scikit-learn", "numpy", "joblib", "mapie")
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
INVALID_MANIFEST: Final = "invalid manifest"

logger = logging.getLogger(__name__)


def _checked_path(
    root: Path, relative: Path, directory: bool, missing: ModelUnavailableError
) -> Path:
    """Resolve relative under root, refusing symlinks, escapes and the wrong kind of entry."""
    if (root / relative).is_symlink():
        raise ModelIntegrityError("symlink rejected")
    try:
        target = resolve_within(root, relative)
    except UnsafePathError as error:
        raise ModelIntegrityError("path escapes models directory") from error
    if not target.exists():
        raise missing
    if directory and not target.is_dir():
        raise ModelIntegrityError("not a directory")
    if not directory and not target.is_file():
        raise ModelIntegrityError("not a regular file")
    return target


def _read_object(path: Path, label: str) -> dict[str, object]:
    """Read a JSON file whose top level is an object."""
    try:
        document: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ModelIntegrityError(f"invalid {label}") from error
    if not isinstance(document, dict):
        raise ModelIntegrityError(f"invalid {label}")
    return document


def _active_version(root: Path) -> str:
    """Return the active version named by registry.json."""
    path = _checked_path(
        root, Path(REGISTRY_FILE), False, ModelUnavailableError("registry not found")
    )
    registry = _read_object(path, "registry")
    active = registry.get("active")
    history = registry.get("history")
    if (
        not isinstance(active, str)
        or VERSION_PATTERN.fullmatch(active) is None
        or not isinstance(history, list)
        or not history
        or not all(isinstance(item, str) for item in history)
        or history[-1] != active
    ):
        raise ModelIntegrityError("invalid registry")
    return active


def _field[T](source: Mapping[str, object], key: str, kind: type[T]) -> T:
    """Return source[key] when it is an instance of kind."""
    value = source.get(key)
    if not isinstance(value, kind):
        raise ModelIntegrityError(INVALID_MANIFEST)
    return value


def _model_info(manifest: Mapping[str, object], version: str) -> ModelInfo:
    """Build the ModelInfo of a manifest."""
    metrics: Mapping[str, object] = _field(manifest, "metrics", dict)
    try:
        return ModelInfo(
            version=version,
            created_at=_field(manifest, "created_at", str),
            dataset_sha256=_field(manifest, "dataset_sha256", str),
            polarity_model=_field(manifest, "polarity_model", str),
            representation=_field(manifest, "representation", str),
            confidence_level=_field(manifest, "confidence_level", float),
            test_macro_f1=_field(metrics, "test_macro_f1", float),
            empirical_coverage=_field(metrics, "empirical_coverage", float),
        )
    except InvalidInputError as error:
        raise ModelIntegrityError(INVALID_MANIFEST) from error


def _read_manifest(path: Path, version: str) -> dict[str, object]:
    """Read a manifest and check its version and hash fields."""
    manifest = _read_object(path, "manifest")
    if manifest.get("version") != version:
        raise ModelIntegrityError("manifest version mismatch")
    if SHA256_PATTERN.fullmatch(_field(manifest, "bundle_sha256", str)) is None:
        raise ModelIntegrityError(INVALID_MANIFEST)
    return manifest


def _check_libraries(manifest: Mapping[str, object]) -> None:
    """Require the recorded versions of the checked libraries to equal the installed ones."""
    recorded = _field(manifest, "library_versions", dict)
    for name in CHECKED_LIBRARIES:
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as error:
            raise ModelIntegrityError(f"library not installed: {name}") from error
        if recorded.get(name) != installed:
            raise ModelIntegrityError(f"library version mismatch: {name}")


def _check_hash(path: Path, expected: str) -> None:
    """Require the SHA-256 of the file to equal expected."""
    with path.open("rb") as file:
        if hashlib.file_digest(file, "sha256").hexdigest() != expected:
            raise ModelIntegrityError("bundle hash mismatch")


def _load_bundle(path: Path) -> Mapping[str, object]:
    """Load the bundle and check its shape; call only after the hash matched."""
    try:
        loaded: object = joblib.load(path)
    except (OSError, EOFError, KeyError, ValueError, ImportError, AttributeError) as error:
        raise ModelIntegrityError("bundle failed to load") from error
    if not isinstance(loaded, dict) or set(loaded) != BUNDLE_KEYS:
        raise ModelIntegrityError("bundle keys mismatch")
    if loaded["schema_version"] != BUNDLE_SCHEMA_VERSION:
        raise ModelIntegrityError("bundle schema mismatch")
    if loaded["class_order"] != tuple(item.value for item in POLARITY_ORDER):
        raise ModelIntegrityError("bundle class order mismatch")
    if loaded["aspect_order"] != tuple(group.value for group in ASPECT_ORDER):
        raise ModelIntegrityError("bundle aspect order mismatch")
    return MappingProxyType(loaded)


class TrustedModelStore:
    """Active model bundle, verified on every construction."""

    def __init__(self, models_dir: Path) -> None:
        """Verify and load the active version listed in registry.json.

        Args:
            models_dir: Directory that holds registry.json and the vNNN folders.

        Raises:
            ModelUnavailableError: If the directory, registry or active version is absent.
            ModelIntegrityError: If any check on the registry, manifest, libraries, hash or
                bundle fails.
        """
        try:
            root = models_dir.resolve(strict=True)
        except OSError as error:
            raise ModelUnavailableError("models directory not found") from error
        version = _active_version(root)
        _checked_path(root, Path(version), True, ModelUnavailableError("model version not found"))
        missing = ModelIntegrityError("model file missing")
        manifest_path = _checked_path(root, Path(version) / MANIFEST_FILE, False, missing)
        bundle_path = _checked_path(root, Path(version) / BUNDLE_FILE, False, missing)
        manifest = _read_manifest(manifest_path, version)
        self._info = _model_info(manifest, version)
        _check_libraries(manifest)
        _check_hash(bundle_path, _field(manifest, "bundle_sha256", str))
        self._bundle = _load_bundle(bundle_path)
        logger.info("event=model_loaded version=%s", version)

    def info(self) -> ModelInfo:
        """Return the metadata of the active model."""
        return self._info

    def bundle(self) -> Mapping[str, object]:
        """Return the verified, read-only bundle."""
        return self._bundle
