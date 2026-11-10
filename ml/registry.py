"""Registry of model versions, models/registry.json (spec 013, docs/contracts.md section 9.3)."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Final, cast

from api.domain.errors import ModelIntegrityError, ModelUnavailableError
from api.domain.safety import resolve_within
from ml.schemas import Registry

VERSION_PATTERN: Final[re.Pattern[str]] = re.compile(r"v[0-9]{3}")
_REGISTRY_KEYS: Final[frozenset[str]] = frozenset({"active", "history"})
_MIN_HISTORY_TO_ROLL_BACK: Final[int] = 2


def dump_json(value: object) -> str:
    """Serialize a value the way every JSON file of the artifact is written.

    Args:
        value: JSON-encodable value.

    Returns:
        Indented, key-sorted text with a trailing newline.
    """
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def read_registry(models_dir: Path) -> Registry | None:
    """Read and validate the registry.

    Args:
        models_dir: Directory that holds the versions.

    Returns:
        The registry, or None when the file is absent.

    Raises:
        ModelIntegrityError: The file is a symlink or its content is invalid.
    """
    path = _registry_path(models_dir)
    if not path.exists():
        return None
    try:
        raw: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ModelIntegrityError("registry.json is invalid") from error
    return _validate_registry(raw)


def push_version(models_dir: Path, version: str) -> bool:
    """Append a version to the history and make it active.

    Args:
        models_dir: Directory that holds the versions.
        version: Version name, already verified by the caller.

    Returns:
        False, without writing, when the history already ends with the version.
    """
    registry = read_registry(models_dir)
    history = [] if registry is None else list(registry["history"])
    if history and history[-1] == version:
        return False
    history.append(version)
    _write_registry(models_dir, {"active": version, "history": history})
    return True


def pop_version(models_dir: Path) -> str:
    """Remove the active version and activate the previous one.

    Args:
        models_dir: Directory that holds the versions.

    Returns:
        The version that is active after the rollback.

    Raises:
        ModelUnavailableError: The registry is missing or holds a single version.
    """
    registry = read_registry(models_dir)
    if registry is None:
        raise ModelUnavailableError("registry.json is missing")
    if len(registry["history"]) < _MIN_HISTORY_TO_ROLL_BACK:
        raise ModelUnavailableError("no previous version to roll back to")
    history = list(registry["history"][:-1])
    _write_registry(models_dir, {"active": history[-1], "history": history})
    return history[-1]


def _registry_path(models_dir: Path) -> Path:
    """Return the registry path, refusing a symlink."""
    path = resolve_within(models_dir, Path("registry.json"))
    if (models_dir / "registry.json").is_symlink():
        raise ModelIntegrityError("symlink rejected")
    return path


def _validate_registry(raw: object) -> Registry:
    """Check the structure of a parsed registry."""
    if not isinstance(raw, dict) or set(raw) != _REGISTRY_KEYS:
        raise ModelIntegrityError("registry.json is invalid")
    history = raw["history"]
    valid = (
        isinstance(history, list)
        and bool(history)
        and all(isinstance(v, str) and VERSION_PATTERN.fullmatch(v) for v in history)
        and raw["active"] == history[-1]
    )
    if not valid:
        raise ModelIntegrityError("registry.json is invalid")
    return cast("Registry", raw)


def _write_registry(models_dir: Path, registry: Registry) -> None:
    """Write the registry atomically."""
    _atomic_write(_registry_path(models_dir), dump_json(registry))


def _atomic_write(path: Path, text: str) -> None:
    """Write text to a temporary file in the same directory, then replace the target."""
    descriptor, name = tempfile.mkstemp(dir=path.parent, prefix=".registry-", suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, path)
    except OSError:
        Path(name).unlink(missing_ok=True)
        raise
