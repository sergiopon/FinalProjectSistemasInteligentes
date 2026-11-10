"""Tests for train() of ml/train.py with every stage stubbed except write and activate."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from api.domain.entities import ASPECT_ORDER
from ml import train as train_module
from ml.representations import EMBEDDING_REVISION
from ml.train import train
from tests.fixtures.synthetic_bundle import make_bundle

WORDS = ("malo", "regular", "bueno")
LABELS = ("negative", "neutral", "positive")
GROUP_METRICS = {"precision": 0.5, "recall": 0.5, "f1": 0.5, "threshold": 0.5}
ENTRY = {
    "representation": "tfidf",
    "classifier": "logistic_regression",
    "best_params": {"classifier__C": 1.0},
    "cv_macro_f1_mean": 0.6,
    "cv_macro_f1_std": 0.05,
}


def make_frame() -> pd.DataFrame:
    rows = {
        "row_key": [f"f{i % 2}.csv:{i + 1}" for i in range(12)],
        "source_file": [f"f{i % 2}.csv" for i in range(12)],
        "text": [f"{WORDS[i % 3]} curso {i}" for i in range(12)],
        "polarity": [LABELS[i % 3] for i in range(12)],
    }
    rows.update({f"aspect_{group.value}": [""] * 12 for group in ASPECT_ORDER})
    return pd.DataFrame(rows)


Calls = dict[str, list[tuple[object, ...]]]
EXPECTED_TEXTS = [f"{WORDS[i % 3]} curso {i}" for i in range(9)]


def make_stub(monkeypatch: pytest.MonkeyPatch, record: Calls) -> Callable[[str, object], None]:
    def stub(name: str, result: object) -> None:
        def run(*args: object) -> object:
            record.setdefault(name, []).append(args)
            return result

        monkeypatch.setattr(train_module, name, run)

    return stub


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> Calls:
    record: Calls = {}
    stub = make_stub(monkeypatch, record)
    selection = SimpleNamespace(
        pipeline=make_bundle()["polarity_pipeline"],
        representation="tfidf",
        classifier="logistic_regression",
        best_params={"classifier__C": 1.0},
        cv_macro_f1_mean=0.6,
        cv_macro_f1_std=0.05,
        selection=(ENTRY,),
    )
    topics = (
        SimpleNamespace(vocabulary_={"curso": 0, "bueno": 1}),
        SimpleNamespace(labels_=np.array([0, 0, 0, 0, 0, 1, 1, 1, 1])),
        (("curso", "bueno", "malo", "regular", "clase"), ("tema", "uno", "dos", "tres", "cuatro")),
    )
    metrics = {
        "empirical_coverage": 0.9,
        "mean_set_size": 2.0,
        "singleton_rate": 0.1,
        "empty_rate": 0.0,
    }
    stub("load_dataset", make_frame())
    stub("dataset_files", (Path("a.csv"),))
    stub("dataset_sha256", "0" * 64)
    stub("template_groups", np.arange(12) % 6)
    stub("grouped_split", (np.arange(9), np.arange(9, 12)))
    stub("select_model", selection)
    stub("evaluate", {"accuracy": 0.5})
    stub("per_file_macro_f1", {"f0.csv": 0.5, "f1.csv": 0.4})
    stub("fit_cross_conformal", "stub")
    stub("conformal_report", metrics)
    stub("risk_coverage", [(0.5, 0.0), (1.0, 0.25)])
    stub("aspect_targets", np.zeros((12, 9), dtype=np.int64))
    stub("fit_aspect_model", ("stub", (0.5,) * 9))
    stub("aspect_report", {group.value: GROUP_METRICS for group in ASPECT_ORDER})
    stub("fit_topics", topics)
    return record


def as_texts(value: object) -> list[str]:
    assert isinstance(value, list)
    return [str(item) for item in value]


def read(models: Path, name: str) -> dict[str, object]:
    loaded: dict[str, object] = json.loads((models / "v001" / name).read_text(encoding="utf-8"))
    return loaded


def test_train_writes_and_activates_v001(tmp_path: Path, calls: Calls) -> None:
    models = tmp_path / "models"
    assert train(tmp_path, models, 0.9) == "v001"
    registry = json.loads((models / "registry.json").read_text(encoding="utf-8"))
    assert registry == {"active": "v001", "history": ["v001"]}


def test_train_fits_on_train_rows_only(tmp_path: Path, calls: Calls) -> None:
    train(tmp_path, tmp_path / "models", 0.9)
    positions = {
        "select_model": 0,
        "fit_cross_conformal": 1,
        "fit_aspect_model": 0,
        "fit_topics": 0,
    }
    for name, position in positions.items():
        assert list(as_texts(calls[name][0][position])) == EXPECTED_TEXTS
    assert calls["fit_cross_conformal"][0][4] == 0.9


def test_train_manifest_fields(tmp_path: Path, calls: Calls) -> None:
    train(tmp_path, tmp_path / "models", 0.9)
    manifest = read(tmp_path / "models", "manifest.json")
    assert manifest["dataset_sha256"] == "0" * 64
    assert manifest["polarity_model"] == "logistic_regression"
    assert manifest["representation"] == "tfidf"
    assert manifest["best_params"] == {"classifier__C": 1.0}
    assert manifest["confidence_level"] == 0.9
    assert manifest["seed"] == 42
    metrics = manifest["metrics"]
    assert isinstance(metrics, dict)
    assert metrics["empirical_coverage"] == 0.9
    assert 0.0 <= metrics["test_macro_f1"] <= 1.0
    embedding = manifest["embedding"]
    assert isinstance(embedding, dict)
    assert embedding["revision"] == EMBEDDING_REVISION


def test_train_report_fields(tmp_path: Path, calls: Calls) -> None:
    train(tmp_path, tmp_path / "models", 0.9)
    report = read(tmp_path / "models", "report.json")
    assert report["split"] == {"train_rows": 9, "test_rows": 3, "groups": 6}
    assert report["test_row_keys"] == ["f1.csv:10", "f0.csv:11", "f1.csv:12"]
    topics = report["topics"]
    assert isinstance(topics, list)
    assert [(t["topic"], t["size"]) for t in topics] == [(0, 5), (1, 4)]
    assert report["risk_coverage"] == [[0.5, 0.0], [1.0, 0.25]]
    assert list(as_texts(calls["per_file_macro_f1"][0][3])) == ["f1.csv", "f0.csv", "f1.csv"]


def test_train_reference_stats_file(tmp_path: Path, calls: Calls) -> None:
    train(tmp_path, tmp_path / "models", 0.9)
    stats = read(tmp_path / "models", "reference_stats.json")
    assert stats["class_shares"] == pytest.approx([1 / 3] * 3, abs=1e-12)
    assert stats["reference_oov_rate"] == 0.5


def test_train_logs_hold_no_text(
    tmp_path: Path, calls: Calls, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        train(tmp_path, tmp_path / "models", 0.9)
    assert "curso" not in caplog.text
    assert "f0.csv" not in caplog.text
