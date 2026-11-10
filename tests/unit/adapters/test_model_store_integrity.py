"""Tests for the manifest, library, hash and bundle-shape rows of api/adapters/model_store.py."""

from __future__ import annotations

import json
from importlib.metadata import PackageNotFoundError
from pathlib import Path

import pytest

from api.adapters.model_store import TrustedModelStore
from api.domain.entities import ASPECT_ORDER
from api.domain.errors import ModelIntegrityError
from tests.fixtures.model_bundles import (
    fake_bundle,
    replace_bundle_bytes,
    write_fake_version,
    write_registry,
)


@pytest.fixture
def models(tmp_path: Path) -> Path:
    directory = tmp_path / "models"
    directory.mkdir()
    write_registry(directory, "v001", ["v001"])
    return directory


def expect_integrity(models: Path, detail: str) -> None:
    with pytest.raises(ModelIntegrityError) as caught:
        TrustedModelStore(models)
    assert type(caught.value) is ModelIntegrityError
    assert caught.value.detail == detail


def edit_manifest(models: Path, change: dict[str, object], drop: tuple[str, ...] = ()) -> None:
    path = models / "v001" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.update(change)
    for key in drop:
        del manifest[key]
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_trusted_model_store_rejects_manifest_version_mismatch(models: Path) -> None:
    write_fake_version(models, "v001")
    edit_manifest(models, {"version": "v002"})
    expect_integrity(models, "manifest version mismatch")


def test_trusted_model_store_rejects_uppercase_hash(models: Path) -> None:
    write_fake_version(models, "v001")
    edit_manifest(models, {"bundle_sha256": "A" * 64})
    expect_integrity(models, "invalid manifest")


def test_trusted_model_store_rejects_manifest_without_metrics(models: Path) -> None:
    write_fake_version(models, "v001")
    edit_manifest(models, {}, drop=("metrics",))
    expect_integrity(models, "invalid manifest")


def test_trusted_model_store_rejects_string_confidence_level(models: Path) -> None:
    write_fake_version(models, "v001")
    edit_manifest(models, {"confidence_level": "0.9"})
    expect_integrity(models, "invalid manifest")


def test_trusted_model_store_rejects_wrong_field_type(models: Path) -> None:
    write_fake_version(models, "v001")
    edit_manifest(models, {"created_at": 5})
    expect_integrity(models, "invalid manifest")


def test_trusted_model_store_rejects_wrong_library_version(models: Path) -> None:
    write_fake_version(models, "v001")
    path = models / "v001" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    edit_manifest(models, {"library_versions": {**manifest["library_versions"], "numpy": "0.0.0"}})
    expect_integrity(models, "library version mismatch: numpy")


def test_trusted_model_store_rejects_missing_library_version(models: Path) -> None:
    write_fake_version(models, "v001")
    path = models / "v001" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    del manifest["library_versions"]["mapie"]
    edit_manifest(models, {"library_versions": manifest["library_versions"]})
    expect_integrity(models, "library version mismatch: mapie")


def test_trusted_model_store_rejects_library_versions_that_are_not_a_dict(models: Path) -> None:
    write_fake_version(models, "v001")
    edit_manifest(models, {"library_versions": []})
    expect_integrity(models, "invalid manifest")


def test_trusted_model_store_rejects_uninstalled_library(
    models: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_fake_version(models, "v001")

    def missing(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr("api.adapters.model_store.importlib.metadata.version", missing)
    expect_integrity(models, "library not installed: scikit-learn")


def test_trusted_model_store_rejects_hash_mismatch_without_loading(
    models: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    version_dir = write_fake_version(models, "v001")
    with (version_dir / "bundle.joblib").open("ab") as file:
        file.write(b"\0")
    calls: list[object] = []
    monkeypatch.setattr(
        "api.adapters.model_store.joblib.load", lambda *args, **kwargs: calls.append(args)
    )
    expect_integrity(models, "bundle hash mismatch")
    assert calls == []


def test_trusted_model_store_verifies_on_every_load(models: Path) -> None:
    version_dir = write_fake_version(models, "v001")
    TrustedModelStore(models)
    with (version_dir / "bundle.joblib").open("ab") as file:
        file.write(b"\0")
    expect_integrity(models, "bundle hash mismatch")


@pytest.mark.parametrize("content", [b"not a joblib file at all", b""])
def test_trusted_model_store_rejects_unloadable_bundle(models: Path, content: bytes) -> None:
    version_dir = write_fake_version(models, "v001")
    replace_bundle_bytes(version_dir, content)
    expect_integrity(models, "bundle failed to load")


def test_trusted_model_store_rejects_bundle_without_topic_terms(models: Path) -> None:
    bundle = fake_bundle()
    del bundle["topic_terms"]
    write_fake_version(models, "v001", bundle)
    expect_integrity(models, "bundle keys mismatch")


def test_trusted_model_store_rejects_bundle_that_is_a_list(models: Path) -> None:
    write_fake_version(models, "v001", [1, 2])
    expect_integrity(models, "bundle keys mismatch")


@pytest.mark.parametrize(
    ("key", "value", "detail"),
    [
        ("schema_version", 2, "bundle schema mismatch"),
        ("class_order", ("positive", "neutral", "negative"), "bundle class order mismatch"),
        (
            "aspect_order",
            tuple(group.value for group in reversed(ASPECT_ORDER)),
            "bundle aspect order mismatch",
        ),
    ],
)
def test_trusted_model_store_rejects_bundle_header(
    models: Path, key: str, value: object, detail: str
) -> None:
    write_fake_version(models, "v001", {**fake_bundle(), key: value})
    expect_integrity(models, detail)


def test_trusted_model_store_rejects_non_hex_hash_type(models: Path) -> None:
    write_fake_version(models, "v001")
    edit_manifest(models, {"bundle_sha256": 5})
    expect_integrity(models, "invalid manifest")
