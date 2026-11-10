"""Integration test of ml.train on the real dataset (spec 014)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ml.artifact import load_verified
from ml.conformal import COVERAGE_TOLERANCE
from ml.train import train

pytestmark = pytest.mark.integration

DATASET_SHA = "5e3ac133828878229457420245bd2d674fdfe985e5a13632bf97b35bdbf2f666"
DUMMY_MACRO_F1 = 0.20
CONFIDENCE_LEVEL = 0.9
ALL_ROWS = 618


def test_train_on_dataset(tmp_path: Path) -> None:
    models = tmp_path / "models"
    assert train(Path("Dataset").resolve(), models, CONFIDENCE_LEVEL) == "v001"
    manifest = json.loads((models / "v001" / "manifest.json").read_text(encoding="utf-8"))
    report = json.loads((models / "v001" / "report.json").read_text(encoding="utf-8"))
    assert manifest["dataset_sha256"] == DATASET_SHA
    assert report["split"]["train_rows"] + report["split"]["test_rows"] == ALL_ROWS
    assert len(set(report["test_row_keys"])) == report["split"]["test_rows"]
    assert manifest["metrics"]["empirical_coverage"] >= CONFIDENCE_LEVEL - COVERAGE_TOLERANCE
    assert manifest["metrics"]["test_macro_f1"] > DUMMY_MACRO_F1
    assert len(load_verified(models, "v001")) == 10
