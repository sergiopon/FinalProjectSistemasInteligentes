"""Tests for the loading, activation and rollback side of ml/artifact.py (spec 013)."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import shutil
from pathlib import Path

import joblib
import pytest

from api.domain.errors import AppError, ModelIntegrityError, ModelUnavailableError
from ml import registry
from ml.artifact import activate, load_verified, rollback, write_version
from ml.registry import dump_json
from tests.fixtures.synthetic_bundle import (
    make_bundle,
    make_manifest,
    make_reference,
    make_report,
)

REGISTRY_TEXT = '{\n  "active": "v001",\n  "history": [\n    "v001"\n  ]\n}\n'


def make_version(models: Path) -> Path:
    return write_version(models, make_bundle(), make_manifest(), make_report(), make_reference())


def read_json(path: Path) -> dict[str, object]:
    loaded: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def edit_manifest(vdir: Path, **changes: object) -> None:
    path = vdir / "manifest.json"
    manifest = read_json(path)
    manifest.update(changes)
    path.write_text(json.dumps(manifest), encoding="utf-8")


def assert_detail(info: pytest.ExceptionInfo[ModelIntegrityError], detail: str) -> None:
    assert info.value.detail == detail


def rehash(vdir: Path) -> None:
    sha = hashlib.sha256((vdir / "bundle.joblib").read_bytes()).hexdigest()
    edit_manifest(vdir, bundle_sha256=sha)


def test_load_verified_returns_bundle(tmp_path: Path) -> None:
    make_version(tmp_path)
    bundle = load_verified(tmp_path, "v001")
    assert len(bundle) == 10
    assert bundle["schema_version"] == 1


def test_load_verified_rejects_tampered_bundle(tmp_path: Path) -> None:
    vdir = make_version(tmp_path)
    with (vdir / "bundle.joblib").open("ab") as handle:
        handle.write(b"\x00")
    with pytest.raises(ModelIntegrityError) as info:
        load_verified(tmp_path, "v001")
    assert_detail(info, "bundle hash mismatch")


def test_load_verified_rejects_library_mismatch(tmp_path: Path) -> None:
    vdir = make_version(tmp_path)
    libraries = dict(read_json(vdir / "manifest.json"))["library_versions"]
    assert isinstance(libraries, dict)
    edit_manifest(vdir, library_versions={**libraries, "scikit-learn": "0.0.0"})
    with pytest.raises(ModelIntegrityError) as info:
        load_verified(tmp_path, "v001")
    assert_detail(info, "library version mismatch: scikit-learn")
    libraries.pop("mapie")
    edit_manifest(vdir, library_versions=libraries)
    with pytest.raises(ModelIntegrityError) as info:
        load_verified(tmp_path, "v001")
    assert_detail(info, "library version mismatch: mapie")


def test_load_verified_rejects_symlinked_version(tmp_path: Path) -> None:
    make_version(tmp_path)
    (tmp_path / "v002").symlink_to(tmp_path / "v001")
    with pytest.raises(ModelIntegrityError) as info:
        load_verified(tmp_path, "v002")
    assert_detail(info, "symlink rejected")


def test_load_verified_rejects_symlinked_bundle(tmp_path: Path) -> None:
    vdir = make_version(tmp_path)
    copy = tmp_path / "copy.joblib"
    shutil.copy(vdir / "bundle.joblib", copy)
    (vdir / "bundle.joblib").unlink()
    (vdir / "bundle.joblib").symlink_to(copy)
    with pytest.raises(ModelIntegrityError) as info:
        load_verified(tmp_path, "v001")
    assert_detail(info, "symlink rejected")


@pytest.mark.parametrize("name", ["../v001", "v1", "v0001"])
def test_load_verified_rejects_bad_names(tmp_path: Path, name: str) -> None:
    make_version(tmp_path)
    with pytest.raises(ModelIntegrityError) as info:
        load_verified(tmp_path, name)
    assert_detail(info, "invalid version name")


def test_load_verified_rejects_missing_manifest(tmp_path: Path) -> None:
    vdir = make_version(tmp_path)
    (vdir / "manifest.json").unlink()
    with pytest.raises(ModelIntegrityError) as info:
        load_verified(tmp_path, "v001")
    assert_detail(info, "version files are missing")


@pytest.mark.parametrize("content", [b"{", b"\xff\xfe", b"[1]"])
def test_load_verified_rejects_invalid_manifest(tmp_path: Path, content: bytes) -> None:
    vdir = make_version(tmp_path)
    (vdir / "manifest.json").write_bytes(content)
    with pytest.raises(ModelIntegrityError) as info:
        load_verified(tmp_path, "v001")
    assert_detail(info, "manifest.json is invalid")


def test_load_verified_rejects_bundle_schema(tmp_path: Path) -> None:
    vdir = make_version(tmp_path)
    joblib.dump([1, 2], vdir / "bundle.joblib")
    rehash(vdir)
    with pytest.raises(ModelIntegrityError) as info:
        load_verified(tmp_path, "v001")
    assert_detail(info, "bundle schema is invalid")
    (vdir / "bundle.joblib").write_bytes(b"not joblib")
    rehash(vdir)
    with pytest.raises(ModelIntegrityError) as info:
        load_verified(tmp_path, "v001")
    assert_detail(info, "bundle failed to load")


def test_load_verified_rejects_manifest_version(tmp_path: Path) -> None:
    vdir = make_version(tmp_path)
    edit_manifest(vdir, version="v009")
    with pytest.raises(ModelIntegrityError) as info:
        load_verified(tmp_path, "v001")
    assert_detail(info, "manifest version mismatch")


def test_load_verified_rejects_library_not_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_version(tmp_path)
    real = importlib.metadata.version

    def fake(name: str) -> str:
        if name == "mapie":
            raise importlib.metadata.PackageNotFoundError(name)
        return real(name)

    monkeypatch.setattr(importlib.metadata, "version", fake)
    with pytest.raises(ModelIntegrityError) as info:
        load_verified(tmp_path, "v001")
    assert_detail(info, "library version mismatch: mapie")


def test_activate_rejects_partial_version(tmp_path: Path) -> None:
    (tmp_path / "v002").mkdir()
    with pytest.raises(ModelIntegrityError) as info:
        activate(tmp_path, "v002")
    assert_detail(info, "version files are missing")


def test_activate_and_rollback_stack(tmp_path: Path) -> None:
    make_version(tmp_path)
    make_version(tmp_path)
    activate(tmp_path, "v001")
    assert read_json(tmp_path / "registry.json") == {"active": "v001", "history": ["v001"]}
    activate(tmp_path, "v002")
    assert read_json(tmp_path / "registry.json") == {
        "active": "v002",
        "history": ["v001", "v002"],
    }
    assert rollback(tmp_path) == "v001"
    assert read_json(tmp_path / "registry.json") == {"active": "v001", "history": ["v001"]}
    with pytest.raises(ModelUnavailableError) as info:
        rollback(tmp_path)
    assert info.value.detail == "no previous version to roll back to"


def test_registry_text_format(tmp_path: Path) -> None:
    make_version(tmp_path)
    activate(tmp_path, "v001")
    assert (tmp_path / "registry.json").read_text(encoding="utf-8") == REGISTRY_TEXT


def test_activate_same_version_keeps_history(tmp_path: Path) -> None:
    make_version(tmp_path)
    activate(tmp_path, "v001")
    activate(tmp_path, "v001")
    assert read_json(tmp_path / "registry.json")["history"] == ["v001"]


def test_activate_rejects_unverified_version(tmp_path: Path) -> None:
    make_version(tmp_path)
    vdir = make_version(tmp_path)
    activate(tmp_path, "v001")
    with (vdir / "bundle.joblib").open("ab") as handle:
        handle.write(b"\x00")
    with pytest.raises(ModelIntegrityError) as info:
        activate(tmp_path, "v002")
    assert_detail(info, "bundle hash mismatch")
    assert (tmp_path / "registry.json").read_text(encoding="utf-8") == REGISTRY_TEXT


def test_registry_file_is_private_and_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_version(tmp_path)
    make_version(tmp_path)
    activate(tmp_path, "v001")
    assert (tmp_path / "registry.json").stat().st_mode & 0o777 == 0o600
    assert not list(tmp_path.glob(".registry-*.tmp"))

    def fail(source: object, target: object) -> None:
        raise OSError("disk")

    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError, match="disk"):
        activate(tmp_path, "v002")
    assert not list(tmp_path.glob(".registry-*.tmp"))


def test_rollback_rejects_missing_registry(tmp_path: Path) -> None:
    with pytest.raises(ModelUnavailableError) as info:
        rollback(tmp_path)
    assert info.value.detail == "registry.json is missing"


@pytest.mark.parametrize(
    "text",
    [
        '{"active": "v002", "history": ["v001"]}',
        "{",
        '{"active": "v001", "history": ["v001", 3]}',
        '{"active": "x1", "history": ["x1"]}',
    ],
)
def test_registry_rejects_invalid_content(tmp_path: Path, text: str) -> None:
    (tmp_path / "registry.json").write_text(text, encoding="utf-8")
    with pytest.raises(AppError) as info:
        registry.read_registry(tmp_path)
    assert info.value.detail == "registry.json is invalid"


def test_registry_rejects_symlink(tmp_path: Path) -> None:
    (tmp_path / "real.json").write_text(REGISTRY_TEXT, encoding="utf-8")
    (tmp_path / "registry.json").symlink_to(tmp_path / "real.json")
    with pytest.raises(AppError) as info:
        registry.read_registry(tmp_path)
    assert info.value.detail == "symlink rejected"


def test_dump_json_vector() -> None:
    assert dump_json({"b": 1, "a": "é"}) == '{\n  "a": "é",\n  "b": 1\n}\n'
