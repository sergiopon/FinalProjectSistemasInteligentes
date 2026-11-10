"""Tests for the registry, path and happy-path rows of api/adapters/model_store.py."""

from __future__ import annotations

import json
import logging
import shutil
import typing
from pathlib import Path

import pytest

from api.adapters.model_store import TrustedModelStore, _checked_path
from api.domain.errors import ModelIntegrityError, ModelUnavailableError
from api.domain.reports import ModelInfo
from tests.fixtures.model_bundles import write_fake_version, write_registry


@pytest.fixture
def models(tmp_path: Path) -> Path:
    directory = tmp_path / "models"
    directory.mkdir()
    return directory


@pytest.fixture
def ready(models: Path) -> Path:
    write_fake_version(models, "v001")
    write_registry(models, "v001", ["v001"])
    return models


def expect_unavailable(models: Path, detail: str) -> None:
    with pytest.raises(ModelUnavailableError) as caught:
        TrustedModelStore(models)
    assert type(caught.value) is ModelUnavailableError
    assert caught.value.detail == detail


def expect_integrity(models: Path, detail: str) -> None:
    with pytest.raises(ModelIntegrityError) as caught:
        TrustedModelStore(models)
    assert type(caught.value) is ModelIntegrityError
    assert caught.value.detail == detail


def test_trusted_model_store_loads_active_version(
    ready: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    store = TrustedModelStore(ready)
    expected = ModelInfo(
        "v001", "2026-11-10T12:00:00Z", "a" * 64, "logistic_regression", "tfidf", 0.9, 0.61, 0.9
    )
    assert store.info() == expected
    assert store.bundle()["schema_version"] == 1
    assert "event=model_loaded version=v001" in caplog.messages


def test_trusted_model_store_follows_registry_after_rollback(models: Path) -> None:
    write_fake_version(models, "v001")
    write_fake_version(models, "v002")
    write_registry(models, "v002", ["v001", "v002"])
    assert TrustedModelStore(models).info().version == "v002"
    write_registry(models, "v001", ["v001"])
    assert TrustedModelStore(models).info().version == "v001"


def test_trusted_model_store_accepts_symlinked_models_dir(ready: Path, tmp_path: Path) -> None:
    link = tmp_path / "link"
    link.symlink_to(ready)
    assert TrustedModelStore(link).info().version == "v001"


def test_trusted_model_store_bundle_is_read_only(ready: Path) -> None:
    bundle = typing.cast(dict[str, object], TrustedModelStore(ready).bundle())
    with pytest.raises(TypeError):
        bundle["schema_version"] = 2


def test_trusted_model_store_rejects_missing_models_dir(tmp_path: Path) -> None:
    expect_unavailable(tmp_path / "absent", "models directory not found")


def test_trusted_model_store_rejects_missing_registry(models: Path) -> None:
    expect_unavailable(models, "registry not found")


def test_trusted_model_store_rejects_malformed_registry(models: Path) -> None:
    (models / "registry.json").write_text("{", encoding="utf-8")
    expect_integrity(models, "invalid registry")


@pytest.mark.parametrize("active", ["../v001", "v1", "v001\n", 7])
def test_trusted_model_store_rejects_invalid_active(models: Path, active: object) -> None:
    write_fake_version(models, "v001")
    (models / "registry.json").write_text(
        json.dumps({"active": active, "history": [active]}), encoding="utf-8"
    )
    expect_integrity(models, "invalid registry")


@pytest.mark.parametrize("history", [["v002"], []])
def test_trusted_model_store_rejects_inconsistent_history(models: Path, history: list[str]) -> None:
    write_fake_version(models, "v001")
    write_registry(models, "v001", history)
    expect_integrity(models, "invalid registry")


def test_trusted_model_store_rejects_symlinked_registry(ready: Path, tmp_path: Path) -> None:
    real = tmp_path / "real.json"
    (ready / "registry.json").rename(real)
    (ready / "registry.json").symlink_to(real)
    expect_integrity(ready, "symlink rejected")


def test_trusted_model_store_rejects_missing_version_directory(models: Path) -> None:
    write_registry(models, "v001", ["v001"])
    expect_unavailable(models, "model version not found")


def test_trusted_model_store_rejects_symlinked_version(ready: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    shutil.move(ready / "v001", outside)
    (ready / "v001").symlink_to(outside, target_is_directory=True)
    expect_integrity(ready, "symlink rejected")


def test_trusted_model_store_rejects_version_that_is_a_file(models: Path) -> None:
    write_registry(models, "v001", ["v001"])
    (models / "v001").write_text("x", encoding="utf-8")
    expect_integrity(models, "not a directory")


def test_trusted_model_store_rejects_symlinked_bundle(ready: Path, tmp_path: Path) -> None:
    real = tmp_path / "real.joblib"
    (ready / "v001" / "bundle.joblib").rename(real)
    (ready / "v001" / "bundle.joblib").symlink_to(real)
    expect_integrity(ready, "symlink rejected")


def test_trusted_model_store_rejects_missing_bundle(ready: Path) -> None:
    (ready / "v001" / "bundle.joblib").unlink()
    expect_integrity(ready, "model file missing")


def test_trusted_model_store_rejects_bundle_that_is_a_directory(ready: Path) -> None:
    (ready / "v001" / "bundle.joblib").unlink()
    (ready / "v001" / "bundle.joblib").mkdir()
    expect_integrity(ready, "not a regular file")


def test_trusted_model_store_rejects_registry_that_is_not_an_object(models: Path) -> None:
    (models / "registry.json").write_text("[]", encoding="utf-8")
    expect_integrity(models, "invalid registry")


def test_trusted_model_store_rejects_registry_that_is_a_directory(models: Path) -> None:
    (models / "registry.json").mkdir()
    expect_integrity(models, "not a regular file")


def test_trusted_model_store_rejects_path_outside_models(models: Path) -> None:
    with pytest.raises(ModelIntegrityError) as caught:
        _checked_path(models, Path("../x"), True, ModelUnavailableError("missing"))
    assert caught.value.detail == "path escapes models directory"
