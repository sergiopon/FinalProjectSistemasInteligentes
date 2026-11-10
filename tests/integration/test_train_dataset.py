"""Integration test of ml/train.py on the real Dataset/ and the embedding cache (spec 014)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ml.artifact import load_verified
from ml.conformal import COVERAGE_TOLERANCE
from ml.train import train

pytestmark = pytest.mark.integration

DATASET_SHA256 = "5e3ac133828878229457420245bd2d674fdfe985e5a13632bf97b35bdbf2f666"


def test_train_on_dataset(tmp_path: Path) -> None:
    models_dir = tmp_path / "models"
    assert train(Path("Dataset").resolve(), models_dir, 0.9) == "v001"
    manifest = json.loads((models_dir / "v001" / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((models_dir / "v001" / "report.json").read_text(encoding="utf-8"))
    assert manifest["dataset_sha256"] == DATASET_SHA256
    split = report["split"]
    assert split["train_rows"] + split["test_rows"] == 618
    assert len(set(report["test_row_keys"])) == split["test_rows"]
    assert manifest["metrics"]["empirical_coverage"] >= 0.9 - COVERAGE_TOLERANCE
    assert manifest["metrics"]["test_macro_f1"] > 0.20
    assert len(load_verified(models_dir, "v001")) == 10
