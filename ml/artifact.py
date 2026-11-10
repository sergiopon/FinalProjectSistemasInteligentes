"""Write, verify, activate and roll back model versions (spec 013, ADR-003).

``joblib.load`` runs code from the file it reads, so a version is loaded only after its hash and
the library versions it was built with have been checked (SEC-14).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final, cast

import joblib
import numpy as np
from sklearn.pipeline import Pipeline

from api.domain.errors import AppError, InvalidInputError, ModelIntegrityError, UnsafePathError
from api.domain.safety import resolve_within
from ml.artifact_checks import (
    BUNDLE_KEYS,
    check_bundle,
    check_manifest,
    check_reference,
    check_report,
)
from ml.artifact_verify import (
    check_libraries,
    checked_file,
    complete_manifest,
    read_manifest,
    read_smoke,
)
from ml.registry import VERSION_PATTERN, dump_json, pop_version, push_version
from ml.schemas import BUNDLE_SCHEMA_VERSION, Manifest, ReferenceStats, Report

logger = logging.getLogger(__name__)

SMOKE_TEXTS: Final[tuple[str, str, str]] = (
    "El curso fue excelente y las clases muy claras.",
    "Los parciales fueron injustos y la retroalimentación llegó tarde.",
    "El contenido estuvo bien, aunque el horario fue incómodo.",
)
_LOAD_ERRORS: Final = (OSError, EOFError, KeyError, ValueError, ImportError, AttributeError)
_SMOKE_TOLERANCE: Final[float] = 1e-9
_SMOKE_SHAPE: Final[tuple[int, int]] = (3, 3)
_MAX_VERSION: Final[int] = 999


def next_version(models_dir: Path) -> str:
    """Return the next free version name.

    Args:
        models_dir: Directory that holds the versions.

    Returns:
        ``v001`` when no version exists, else the highest number plus one.

    Raises:
        InvalidInputError: The highest version is ``v999``.
    """
    numbers = [
        int(entry.name[1:])
        for entry in (models_dir.iterdir() if models_dir.exists() else ())
        if VERSION_PATTERN.fullmatch(entry.name)
    ]
    highest = max(numbers, default=0)
    if highest >= _MAX_VERSION:
        raise InvalidInputError("version limit v999 reached")
    return f"v{highest + 1:03d}"


def write_version(
    models_dir: Path,
    bundle: dict[str, object],
    manifest: Manifest,
    report: Report,
    reference: ReferenceStats,
) -> Path:
    """Write a new immutable version directory.

    Args:
        models_dir: Directory that holds the versions; created when absent.
        bundle: Bundle dictionary of docs/contracts.md section 9.1.
        manifest: Manifest built by the caller; this function completes six keys.
        report: Report of docs/contracts.md section 9.4.
        reference: Drift reference statistics.

    Returns:
        The directory of the new version.

    Raises:
        InvalidInputError: An input does not match its schema.
    """
    check_bundle(bundle)
    check_manifest(manifest)
    check_report(report)
    check_reference(reference)
    smoke = _smoke_rows(bundle)
    models_dir.mkdir(mode=0o700, exist_ok=True)
    version = next_version(models_dir)
    vdir = resolve_within(models_dir, Path(version))
    vdir.mkdir(mode=0o700)
    bundle_path = resolve_within(vdir, Path("bundle.joblib"))
    _write_bundle(bundle_path, bundle)
    sha = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
    _write_file(resolve_within(vdir, Path("report.json")), dump_json(report).encode("utf-8"))
    _write_file(
        resolve_within(vdir, Path("reference_stats.json")), dump_json(reference).encode("utf-8")
    )
    completed = complete_manifest(
        manifest, version, sha, {"texts": list(SMOKE_TEXTS), "probabilities": smoke}
    )
    _write_file(resolve_within(vdir, Path("manifest.json")), dump_json(completed).encode("utf-8"))
    logger.info("version_written version=%s bundle_sha256=%s", version, sha)
    return vdir


def load_verified(models_dir: Path, version: str) -> dict[str, object]:
    """Load a version after the SEC-14 checks.

    Args:
        models_dir: Directory that holds the versions.
        version: Version name such as ``v001``.

    Returns:
        The bundle dictionary.

    Raises:
        ModelIntegrityError: A file is missing or a symlink, the hash or a library version
            differs, or the bundle does not load or match the schema.
    """
    if not VERSION_PATTERN.fullmatch(version):
        raise ModelIntegrityError("invalid version name")
    manifest_path = checked_file(models_dir, version, "manifest.json")
    bundle_path = checked_file(models_dir, version, "bundle.joblib")
    manifest = read_manifest(manifest_path, version)
    raw = bundle_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != manifest["bundle_sha256"]:
        raise ModelIntegrityError("bundle hash mismatch")
    check_libraries(manifest)
    bundle = _load_bundle(raw)
    logger.info("version_loaded version=%s", version)
    return bundle


def activate(models_dir: Path, version: str) -> None:
    """Verify a version and make it the active one.

    Args:
        models_dir: Directory that holds the versions.
        version: Version name such as ``v001``.

    Raises:
        ModelIntegrityError: The version fails ``load_verified``.
    """
    load_verified(models_dir, version)
    if push_version(models_dir, version):
        logger.info("version_activated version=%s", version)


def rollback(models_dir: Path) -> str:
    """Make the previous version the active one.

    Args:
        models_dir: Directory that holds the versions.

    Returns:
        The version that is active after the rollback.

    Raises:
        ModelUnavailableError: There is no previous version.
    """
    active = pop_version(models_dir)
    logger.info("version_rolled_back active=%s", active)
    return active


def main(argv: Sequence[str] | None = None) -> int:
    """Run the artifact command line: activate, rollback or verify.

    Args:
        argv: Arguments without the program name; defaults to ``sys.argv``.

    Returns:
        0 on success, 2 for an expected error, 1 for an unexpected one.
    """
    os.umask(0o077)
    args = _parser().parse_args(argv)
    try:
        print(_run(args))
    except AppError as error:
        print(f"error={error.code}", file=sys.stderr)
        return 2
    except Exception:
        logger.exception("artifact_command_failed")
        print("error=internal_error", file=sys.stderr)
        return 1
    return 0


def _run(args: argparse.Namespace) -> str:
    """Run the chosen command and return the line to print."""
    models_dir = _models_path(args.models)
    if args.command == "activate":
        activate(models_dir, args.version)
        return f"active={args.version}"
    if args.command == "rollback":
        return f"active={rollback(models_dir)}"
    _verify(models_dir, args.version)
    return f"verified={args.version}"


def _smoke_rows(bundle: dict[str, object]) -> list[list[float]]:
    """Return the polarity probabilities of the smoke texts."""
    pipeline = cast("Pipeline", bundle["polarity_pipeline"])
    rows = np.asarray(pipeline.predict_proba(list(SMOKE_TEXTS)))
    if rows.shape != _SMOKE_SHAPE:
        raise InvalidInputError("smoke probabilities must have shape (3, 3)")
    return cast("list[list[float]]", rows.tolist())


def _write_bundle(path: Path, bundle: dict[str, object]) -> None:
    """Create the bundle file exclusively and dump the bundle into it."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        joblib.dump(bundle, handle)


def _write_file(path: Path, data: bytes) -> None:
    """Create a file exclusively with mode 0600 and write the bytes."""
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)


def _verify(models_dir: Path, version: str) -> None:
    """Recompute the smoke probabilities and compare them with the manifest."""
    bundle = load_verified(models_dir, version)
    texts, expected = read_smoke(models_dir, version)
    if texts != list(SMOKE_TEXTS):
        raise ModelIntegrityError("smoke texts mismatch")
    actual = np.asarray(cast("Pipeline", bundle["polarity_pipeline"]).predict_proba(texts))
    expected_array = np.asarray(expected, dtype=np.float64)
    if actual.shape != expected_array.shape or not np.allclose(
        actual, expected_array, rtol=0.0, atol=_SMOKE_TOLERANCE
    ):
        raise ModelIntegrityError("smoke probabilities mismatch")


def _models_path(raw: str) -> Path:
    """Resolve ``--models``, which must be ``<cwd>/models`` or inside it."""
    base = Path.cwd().resolve()
    path = resolve_within(base, Path(raw))
    models = base / "models"
    if path != models and not path.is_relative_to(models):
        raise UnsafePathError("path escapes base")
    return path


def _parser() -> argparse.ArgumentParser:
    """Build the command line parser."""
    parser = argparse.ArgumentParser(prog="ml.artifact")
    parser.add_argument("--models", default="models")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("rollback")
    for name in ("activate", "verify"):
        commands.add_parser(name).add_argument("version")
    return parser


def _load_bundle(raw: bytes) -> dict[str, object]:
    """Load the hashed bytes and check the bundle schema."""
    try:
        bundle = joblib.load(io.BytesIO(raw))
    except _LOAD_ERRORS as error:
        raise ModelIntegrityError("bundle failed to load") from error
    valid = (
        isinstance(bundle, dict)
        and set(bundle) == BUNDLE_KEYS
        and bundle["schema_version"] == BUNDLE_SCHEMA_VERSION
    )
    if not valid:
        raise ModelIntegrityError("bundle schema is invalid")
    return cast("dict[str, object]", bundle)
