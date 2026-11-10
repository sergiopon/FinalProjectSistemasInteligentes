"""Tests for the wiring of train() in ml/train.py with stubbed stages (spec 014)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd
import pytest

from api.domain.entities import ASPECT_ORDER
from ml import train as train_module
from ml.representations import EMBEDDING_REVISION
from tests.fixtures.synthetic_bundle import make_bundle

TEXTS = [f"{('malo', 'regular', 'bueno')[i % 3]} curso {i}" for i in range(12)]


def make_frame() -> pd.DataFrame:
    data: dict[str, Any] = {
        "row_key": [f"f{i % 2}.csv:{i + 1}" for i in range(12)],
        "source_file": [f"f{i % 2}.csv" for i in range(12)],
        "text": TEXTS,
        "polarity": [("negative", "neutral", "positive")[i % 3] for i in range(12)],
    }
    data.update({f"aspect_{group.value}": [""] * 12 for group in ASPECT_ORDER})
    return pd.DataFrame(data)


TERMS = (
    ("curso", "bueno", "malo", "regular", "clase"),
    ("tema", "uno", "dos", "tres", "cuatro"),
)


def make_selection() -> SimpleNamespace:
    entry = {
        "representation": "tfidf",
        "classifier": "logistic_regression",
        "best_params": {"classifier__C": 1.0},
        "cv_macro_f1_mean": 0.6,
        "cv_macro_f1_std": 0.05,
    }
    return SimpleNamespace(
        pipeline=make_bundle()["polarity_pipeline"],
        representation="tfidf",
        classifier="logistic_regression",
        best_params={"classifier__C": 1.0},
        cv_macro_f1_mean=0.6,
        cv_macro_f1_std=0.05,
        selection=(entry,),
    )


def recorder(seen: dict[str, list[tuple[Any, ...]]], name: str, result: Any) -> Any:
    def run(*args: Any) -> Any:
        seen.setdefault(name, []).append(args)
        return result

    return run


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[tuple[Any, ...]]]:
    seen: dict[str, list[tuple[Any, ...]]] = {}
    group_report = {"precision": 0.5, "recall": 0.5, "f1": 0.5, "threshold": 0.5}
    conformal = {
        "empirical_coverage": 0.9,
        "mean_set_size": 2.0,
        "singleton_rate": 0.1,
        "empty_rate": 0.0,
    }
    topic_model = (
        SimpleNamespace(vocabulary_={"curso": 0, "bueno": 1}),
        SimpleNamespace(labels_=np.array([0, 0, 0, 0, 0, 1, 1, 1, 1])),
        TERMS,
    )
    results: dict[str, Any] = {
        "load_dataset": make_frame(),
        "dataset_files": (Path("a.csv"),),
        "dataset_sha256": "0" * 64,
        "template_groups": np.arange(12) % 6,
        "grouped_split": (np.arange(9), np.arange(9, 12)),
        "select_model": make_selection(),
        "evaluate": {"accuracy": 0.5},
        "per_file_macro_f1": {"f0.csv": 0.5, "f1.csv": 0.4},
        "fit_cross_conformal": "stub",
        "conformal_report": conformal,
        "risk_coverage": [(0.5, 0.0), (1.0, 0.25)],
        "aspect_targets": np.zeros((12, 9), dtype=np.int64),
        "fit_aspect_model": ("stub", (0.5,) * 9),
        "aspect_report": {group.value: group_report for group in ASPECT_ORDER},
        "fit_topics": topic_model,
    }
    for name, result in results.items():
        monkeypatch.setattr(train_module, name, recorder(seen, name, result))
    return seen


def run_train(tmp_path: Path) -> Path:
    models = tmp_path / "models"
    assert train_module.train(tmp_path / "Dataset", models, 0.9) == "v001"
    return models / "v001"


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def test_train_writes_and_activates_v001(
    tmp_path: Path, calls: dict[str, list[tuple[Any, ...]]]
) -> None:
    run_train(tmp_path)
    assert read(tmp_path / "models" / "registry.json") == {"active": "v001", "history": ["v001"]}


def test_train_fits_on_train_rows_only(
    tmp_path: Path, calls: dict[str, list[tuple[Any, ...]]]
) -> None:
    run_train(tmp_path)
    for name in ("select_model", "fit_aspect_model", "fit_topics"):
        assert list(calls[name][0][0]) == TEXTS[:9]
    assert list(calls["fit_cross_conformal"][0][1]) == TEXTS[:9]
    assert calls["fit_cross_conformal"][0][4] == 0.9


def test_train_manifest_fields(tmp_path: Path, calls: dict[str, list[tuple[Any, ...]]]) -> None:
    manifest = read(run_train(tmp_path) / "manifest.json")
    assert manifest["dataset_sha256"] == "0" * 64
    assert manifest["polarity_model"] == "logistic_regression"
    assert manifest["representation"] == "tfidf"
    assert manifest["best_params"] == {"classifier__C": 1.0}
    assert manifest["confidence_level"] == 0.9
    assert manifest["seed"] == 42
    assert manifest["metrics"]["empirical_coverage"] == 0.9
    assert 0.0 <= manifest["metrics"]["test_macro_f1"] <= 1.0
    assert manifest["embedding"]["revision"] == EMBEDDING_REVISION


def test_train_report_fields(tmp_path: Path, calls: dict[str, list[tuple[Any, ...]]]) -> None:
    report = read(run_train(tmp_path) / "report.json")
    assert report["split"] == {"train_rows": 9, "test_rows": 3, "groups": 6}
    assert report["test_row_keys"] == ["f1.csv:10", "f0.csv:11", "f1.csv:12"]
    assert [(t["topic"], t["size"]) for t in report["topics"]] == [(0, 5), (1, 4)]
    assert report["risk_coverage"] == [[0.5, 0.0], [1.0, 0.25]]
    assert list(calls["per_file_macro_f1"][0][3]) == ["f1.csv", "f0.csv", "f1.csv"]


def test_train_reference_stats_file(
    tmp_path: Path, calls: dict[str, list[tuple[Any, ...]]]
) -> None:
    stats = read(run_train(tmp_path) / "reference_stats.json")
    assert stats["class_shares"] == pytest.approx([1 / 3] * 3, abs=1e-12)
    assert stats["reference_oov_rate"] == 0.5


def test_train_logs_hold_no_text(
    tmp_path: Path, calls: dict[str, list[tuple[Any, ...]]], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    run_train(tmp_path)
    assert caplog.messages
    assert not any("curso" in message or "f0.csv" in message for message in caplog.messages)
