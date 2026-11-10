"""Reading and verifying a stored model version before it is trusted (spec 013, SEC-14)."""

from __future__ import annotations

import importlib.metadata
import json
import platform
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, cast

from api.domain.errors import ModelIntegrityError
from api.domain.safety import resolve_within
from ml.artifact_checks import SHA256
from ml.schemas import Manifest, SmokeCheck

RECORDED_LIBRARIES: Final[tuple[str, ...]] = (
    "scikit-learn",
    "numpy",
    "joblib",
    "mapie",
    "scipy",
    "pandas",
    "sentence-transformers",
    "torch",
    "spacy",
)
CHECKED_LIBRARIES: Final[tuple[str, ...]] = ("scikit-learn", "numpy", "joblib", "mapie")


def checked_file(models_dir: Path, version: str, name: str) -> Path:
    """Return a regular file of a version, refusing symlinks and missing files."""
    if (models_dir / version).is_symlink() or (models_dir / version / name).is_symlink():
        raise ModelIntegrityError("symlink rejected")
    path = resolve_within(models_dir, Path(version) / name)
    if not (models_dir / version).is_dir() or not path.is_file():
        raise ModelIntegrityError("version files are missing")
    return path


def read_manifest(path: Path, version: str) -> dict[str, object]:
    """Parse a manifest and check its shape and version."""
    try:
        manifest: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise ModelIntegrityError("manifest.json is invalid") from error
    if not isinstance(manifest, dict):
        raise ModelIntegrityError("manifest.json is invalid")
    sha = manifest.get("bundle_sha256")
    if not isinstance(sha, str) or not SHA256.fullmatch(sha):
        raise ModelIntegrityError("manifest.json is invalid")
    if not isinstance(manifest.get("library_versions"), dict):
        raise ModelIntegrityError("manifest.json is invalid")
    if manifest.get("version") != version:
        raise ModelIntegrityError("manifest version mismatch")
    return manifest


def check_libraries(manifest: Mapping[str, object]) -> None:
    """Require the installed version of each checked library to match the manifest."""
    recorded = cast("Mapping[str, object]", manifest["library_versions"])
    for name in CHECKED_LIBRARIES:
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError as error:
            raise ModelIntegrityError(f"library version mismatch: {name}") from error
        if recorded.get(name) != installed:
            raise ModelIntegrityError(f"library version mismatch: {name}")


def read_smoke(models_dir: Path, version: str) -> tuple[list[str], list[list[float]]]:
    """Read the smoke texts and probabilities recorded in a manifest."""
    path = resolve_within(models_dir, Path(version) / "manifest.json")
    smoke = read_manifest(path, version).get("smoke")
    try:
        texts = cast("list[str]", cast("dict[str, object]", smoke)["texts"])
        rows = cast("list[list[float]]", cast("dict[str, object]", smoke)["probabilities"])
    except (KeyError, TypeError) as error:
        raise ModelIntegrityError("manifest.json is invalid") from error
    return texts, rows


def complete_manifest(manifest: Manifest, version: str, sha: str, smoke: SmokeCheck) -> Manifest:
    """Return a copy of the manifest with the six keys that depend on the written files."""
    completed = cast("Manifest", dict(manifest))
    completed["version"] = version
    completed["created_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    completed["bundle_sha256"] = sha
    completed["python_version"] = platform.python_version()
    completed["library_versions"] = {
        name: importlib.metadata.version(name) for name in RECORDED_LIBRARIES
    }
    completed["smoke"] = smoke
    return completed
