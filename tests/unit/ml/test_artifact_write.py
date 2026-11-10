"""Tests for the writing side of ml/artifact.py (spec 013)."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import numpy as np
import pytest
from sklearn.pipeline import Pipeline

from api.domain.errors import InvalidInputError
from ml import artifact
from ml.artifact import SMOKE_TEXTS, main, next_version, write_version
from ml.schemas import Report
from tests.fixtures.synthetic_bundle import (
    make_bundle,
    make_manifest,
    make_reference,
    make_report,
)


@pytest.fixture
def umask_restored() -> Iterator[None]:
    previous = os.umask(0o022)
    yield
    os.umask(previous)


def assert_invalid(detail: str, info: pytest.ExceptionInfo[InvalidInputError]) -> None:
    assert info.value.detail == detail


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_next_version_starts_at_v001(tmp_path: Path) -> None:
    assert next_version(tmp_path) == "v001"


def test_next_version_skips_non_version_names(tmp_path: Path) -> None:
    for name in ("v001", "v002", "v010", "notes", "v1"):
        (tmp_path / name).mkdir()
    (tmp_path / "v011").write_text("x")
    assert next_version(tmp_path) == "v012"


def test_next_version_rejects_v999(tmp_path: Path) -> None:
    (tmp_path / "v999").mkdir()
    with pytest.raises(InvalidInputError) as info:
        next_version(tmp_path)
    assert_invalid("version limit v999 reached", info)


def test_next_version_after_v998(tmp_path: Path) -> None:
    (tmp_path / "v998").mkdir()
    assert next_version(tmp_path) == "v999"


@pytest.mark.usefixtures("umask_restored")
def test_write_version_creates_files_with_private_modes(tmp_path: Path) -> None:
    models = tmp_path / "models"
    vdir = write_version(models, make_bundle(), make_manifest(), make_report(), make_reference())
    assert vdir == models.resolve() / "v001"
    assert mode(models) == 0o700
    assert mode(vdir) == 0o700
    for name in ("bundle.joblib", "manifest.json", "report.json", "reference_stats.json"):
        assert mode(vdir / name) == 0o600


def test_write_version_completes_manifest(tmp_path: Path) -> None:
    vdir = write_version(tmp_path, make_bundle(), make_manifest(), make_report(), make_reference())
    manifest = json.loads((vdir / "manifest.json").read_text(encoding="utf-8"))
    assert (
        manifest["bundle_sha256"]
        == hashlib.sha256((vdir / "bundle.joblib").read_bytes()).hexdigest()
    )
    assert manifest["version"] == "v001"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", manifest["created_at"])
    assert len(manifest["library_versions"]) == 9
    assert manifest["library_versions"]["scikit-learn"] == "1.9.1"
    assert manifest["smoke"]["texts"] == list(SMOKE_TEXTS)
    for row in manifest["smoke"]["probabilities"]:
        assert abs(sum(row) - 1.0) <= 1e-9
    assert manifest["dataset_sha256"] == "0" * 64


def test_write_version_rejects_comment_text_in_report(tmp_path: Path) -> None:
    report = make_report()
    report["test_row_keys"] = ["El curso fue muy bueno y claro"]
    with pytest.raises(InvalidInputError) as info:
        write_version(tmp_path, make_bundle(), make_manifest(), report, make_reference())
    assert_invalid("report.json must not contain comment text", info)
    assert not (tmp_path / "v001").exists()


def test_write_version_rejects_report_keys(tmp_path: Path) -> None:
    report = dict(make_report())
    del report["topics"]
    typed = cast(Report, report)
    with pytest.raises(InvalidInputError) as info:
        write_version(tmp_path, make_bundle(), make_manifest(), typed, make_reference())
    assert_invalid("report.json keys do not match the schema", info)


def test_write_version_rejects_reference_shape(tmp_path: Path) -> None:
    reference = make_reference()
    reference["length_shares"] = [0.1] * 9
    with pytest.raises(InvalidInputError) as info:
        write_version(tmp_path, make_bundle(), make_manifest(), make_report(), reference)
    assert_invalid("reference_stats.json does not match the schema", info)


def test_write_version_rejects_bundle_keys(tmp_path: Path) -> None:
    bundle = make_bundle()
    del bundle["topic_kmeans"]
    with pytest.raises(InvalidInputError) as info:
        write_version(tmp_path, bundle, make_manifest(), make_report(), make_reference())
    assert_invalid("bundle keys do not match the schema", info)


def test_write_version_rejects_short_revision(tmp_path: Path) -> None:
    manifest = make_manifest()
    manifest["embedding"]["revision"] = "abc"
    without = make_manifest()
    cast(dict[str, object], without["embedding"]).pop("revision")
    for bad in (manifest, without):
        with pytest.raises(InvalidInputError) as info:
            write_version(tmp_path, make_bundle(), bad, make_report(), make_reference())
        assert_invalid("embedding revision must be a 40-character commit hash", info)


def test_write_version_rejects_bad_dataset_hash(tmp_path: Path) -> None:
    manifest = make_manifest()
    manifest["dataset_sha256"] = "G" * 64
    with pytest.raises(InvalidInputError) as info:
        write_version(tmp_path, make_bundle(), manifest, make_report(), make_reference())
    assert_invalid("dataset_sha256 must be 64 lowercase hex characters", info)


def test_write_version_rejects_incomplete_metrics(tmp_path: Path) -> None:
    missing = make_manifest()
    cast(dict[str, object], missing["metrics"]).pop("test_macro_f1")
    integer = make_manifest()
    cast(dict[str, object], integer["metrics"])["empirical_coverage"] = 1
    for bad in (missing, integer):
        with pytest.raises(InvalidInputError) as info:
            write_version(tmp_path, make_bundle(), bad, make_report(), make_reference())
        assert_invalid("manifest metrics are incomplete", info)


def test_write_version_rejects_bad_smoke_shape(tmp_path: Path) -> None:
    bundle = make_bundle()
    pipeline = cast(Pipeline, bundle["polarity_pipeline"])
    pipeline.fit(["malo curso", "bueno curso"] * 5, [0, 1] * 5)
    with pytest.raises(InvalidInputError) as info:
        write_version(tmp_path, bundle, make_manifest(), make_report(), make_reference())
    assert_invalid("smoke probabilities must have shape (3, 3)", info)


def test_write_version_propagates_numpy_int(tmp_path: Path) -> None:
    manifest = make_manifest()
    cast(dict[str, object], manifest)["seed"] = np.int64(42)
    with pytest.raises(TypeError):
        write_version(tmp_path, make_bundle(), manifest, make_report(), make_reference())


def prepare_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    models = tmp_path / "models"
    write_version(models, make_bundle(), make_manifest(), make_report(), make_reference())
    return models


def test_main_commands_and_exit_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    prepare_models(tmp_path, monkeypatch)
    assert main(["activate", "v001"]) == 0
    assert capsys.readouterr().out.strip() == "active=v001"
    assert main(["verify", "v001"]) == 0
    assert capsys.readouterr().out.strip() == "verified=v001"
    assert main(["rollback"]) == 2
    assert capsys.readouterr().err.strip() == "error=model_unavailable"
    for bad in ("../x", "src"):
        assert main(["--models", bad, "rollback"]) == 2
        assert capsys.readouterr().err.strip() == "error=internal_error"


def rewrite_manifest(models: Path, change: dict[str, object]) -> None:
    path = models / "v001" / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest.update(change)
    path.write_text(json.dumps(manifest), encoding="utf-8")


def test_main_verify_detects_smoke_drift(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    models = prepare_models(tmp_path, monkeypatch)
    smoke = json.loads((models / "v001" / "manifest.json").read_text(encoding="utf-8"))["smoke"]
    drifted = {
        **smoke,
        "probabilities": [
            [smoke["probabilities"][0][0] + 0.01, *smoke["probabilities"][0][1:]],
            *smoke["probabilities"][1:],
        ],
    }
    other_texts = {**smoke, "texts": ["otro", "texto", "mas"]}
    changes: list[object] = [drifted, other_texts, []]
    for change in changes:
        rewrite_manifest(models, {"smoke": change})
        assert main(["verify", "v001"]) == 2


@pytest.mark.usefixtures("umask_restored")
def test_main_sets_umask(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["rollback"]) == 2
    assert os.umask(0o022) == 0o077


def test_main_unexpected_error_returns_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    prepare_models(tmp_path, monkeypatch)

    def boom(models_dir: Path, version: str) -> dict[str, object]:
        raise RuntimeError("boom")

    monkeypatch.setattr(artifact, "load_verified", boom)
    assert main(["verify", "v001"]) == 1
    assert capsys.readouterr().err.strip() == "error=internal_error"
    assert "artifact_command_failed" in caplog.text
