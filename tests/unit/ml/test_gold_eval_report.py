"""Tests for the gold-evaluation report, writer and command line (spec 029)."""

from __future__ import annotations

import json
import stat
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import numpy as np
import pandas as pd
import pytest
from mapie.classification import CrossConformalClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.multiclass import OneVsRestClassifier
from sklearn.pipeline import Pipeline

from api.domain.entities import ASPECT_ORDER
from api.domain.errors import DatasetError, ModelUnavailableError
from ml import gold_eval
from ml.gold_eval import ASPECT_COLUMNS, GOLD_COLUMNS, evaluate_gold, main, write_report

TEXTS = [
    "El curso fue pésimo y muy confuso",
    "Los materiales eran malos y desordenados",
    "No me gustó nada la plataforma",
    "Muy mala comunicación con el docente",
    "El curso cumple con lo esperado",
    "Los materiales son regulares sin más",
    "La plataforma funciona de forma normal",
    "El horario es el habitual del programa",
    "Excelente curso y muy claro",
    "Los materiales fueron muy útiles",
    "Me encantó la plataforma",
    "Gran comunicación con el docente",
]
CLASS_OF_TEXT = [0] * 4 + [1] * 4 + [2] * 4
KEYS = [f"f.csv:{i}" for i in range(1, 6)]
CONFORMAL = {
    "empirical_coverage": 0.9,
    "mean_set_size": 1.2,
    "singleton_rate": 0.8,
    "empty_rate": 0.0,
}


def _stub_pipeline(monkeypatch: pytest.MonkeyPatch, column0: Sequence[float]) -> Pipeline:
    """Aspect pipeline whose score for group 0 is fixed per row and 0.0 elsewhere."""

    def predict_proba(X: Any) -> Any:
        scores = np.zeros((len(X), 9))
        scores[:, 0] = np.resize(np.asarray(column0), len(X))
        return scores

    pipeline = Pipeline(steps=[("model", LogisticRegression())])
    monkeypatch.setattr(pipeline, "predict_proba", predict_proba)
    return pipeline


def _sheet(polarity: list[str], content: list[str] | None = None) -> pd.DataFrame:
    frame = pd.DataFrame({"row_key": KEYS, "polarity": polarity})
    for column in ASPECT_COLUMNS:
        frame[column] = ""
    if content is not None:
        frame["aspect_content"] = content
    return frame[list(GOLD_COLUMNS)]


def _real_aspect_pipeline() -> Pipeline:
    rng = np.random.default_rng(42)
    indicators = rng.integers(0, 2, size=(12, 9))
    indicators[:2] = 0
    indicators[2:4] = 1
    pipeline = Pipeline(
        [("tfidf", TfidfVectorizer()), ("model", OneVsRestClassifier(LogisticRegression()))]
    )
    return pipeline.fit(TEXTS, indicators)


def _bundle(aspect_pipeline: Any, thresholds: float) -> dict[str, object]:
    polarity = Pipeline(
        [("tfidf", TfidfVectorizer()), ("model", LogisticRegression(random_state=42))]
    ).fit(TEXTS, CLASS_OF_TEXT)
    return {
        "polarity_pipeline": polarity,
        "aspect_pipeline": aspect_pipeline,
        "conformal_classifier": CrossConformalClassifier(estimator=LogisticRegression()),
        "aspect_thresholds": tuple([thresholds] * 9),
    }


def _setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sheets: tuple[pd.DataFrame, pd.DataFrame] | None = None,
    bundle: dict[str, object] | None = None,
    dataset_polarity: Sequence[str] = ("negative", "neutral", "neutral", "positive", "neutral"),
) -> tuple[Path, Path, Path]:
    pol_a = ["negative", "neutral", "positive", "positive", "neutral"]
    pol_b = ["negative", "positive", "positive", "positive", "positive"]
    sheet_a, sheet_b = sheets or (_sheet(pol_a), _sheet(pol_b))
    gold = tmp_path / "gold"
    gold.mkdir()
    sheet_a.to_csv(gold / "sheet_a.csv", index=False)
    sheet_b.to_csv(gold / "sheet_b.csv", index=False)
    models = tmp_path / "models"
    (models / "v001").mkdir(parents=True)
    (models / "registry.json").write_text('{"active": "v001", "history": ["v001"]}')
    (models / "v001" / "report.json").write_text('{"test_row_keys": ["f.csv:1", "f.csv:2"]}')
    frame = pd.DataFrame({"row_key": KEYS, "text": TEXTS[:5], "polarity": list(dataset_polarity)})
    loaded = bundle or _bundle(_real_aspect_pipeline(), 0.5)
    monkeypatch.setattr(gold_eval, "load_dataset", lambda _dir: frame)
    monkeypatch.setattr(gold_eval, "load_verified", lambda _dir, _version: loaded)
    monkeypatch.setattr(gold_eval, "conformal_report", lambda _model, _texts, _y: dict(CONFORMAL))
    return gold, tmp_path / "Dataset", models


def _content_aspects(rows: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    polarity = ["negative"] * 5
    return _sheet(polarity, rows), _sheet(polarity, rows)


def _aspects(report: dict[str, object]) -> dict[str, dict[str, Any]]:
    return cast("dict[str, dict[str, Any]]", report["aspects"])


def _polarity(report: dict[str, object]) -> dict[str, Any]:
    return cast("dict[str, Any]", report["polarity"])


def test_evaluate_gold_report_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = evaluate_gold(*_setup(tmp_path, monkeypatch))
    assert {"model_version", "gold_rows", "polarity", "aspects", "aspect_macro_f1"} <= set(report)
    assert report["model_version"] == "v001"
    assert report["gold_rows"] == 5
    assert list(_aspects(report)) == [group.value for group in ASPECT_ORDER]
    polarity = _polarity(report)
    assert polarity["agreed_rows"] == 3
    assert polarity["conformal"] == CONFORMAL
    assert set(polarity["metrics"]) >= {"accuracy", "macro_f1", "confusion_matrix"}


def test_evaluate_gold_dataset_label_accuracy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report = evaluate_gold(*_setup(tmp_path, monkeypatch))
    polarity = _polarity(report)
    assert polarity["dataset_label_accuracy"] == pytest.approx(0.666667, abs=1e-6)


def test_evaluate_gold_counts_test_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = evaluate_gold(*_setup(tmp_path, monkeypatch))
    polarity = _polarity(report)
    assert polarity["test_rows"] == 1


@pytest.mark.parametrize(("returned", "expected_present"), [(0.55, True), (0.5499, False)])
def test_evaluate_gold_threshold_is_inclusive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, returned: float, expected_present: bool
) -> None:
    rows = ["positive"] * 5
    bundle = _bundle(_stub_pipeline(monkeypatch, [returned]), 0.55)
    report = evaluate_gold(*_setup(tmp_path, monkeypatch, _content_aspects(rows), bundle))
    content = _aspects(report)["content"]
    assert content["threshold"] == 0.55
    assert content["recall"] == (1.0 if expected_present else 0.0)


def test_evaluate_gold_macro_f1_vector(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rows = ["positive"] * 3 + ["", ""]
    bundle = _bundle(_stub_pipeline(monkeypatch, [0.9, 0.1, 0.1, 0.1, 0.9]), 0.5)
    report = evaluate_gold(*_setup(tmp_path, monkeypatch, _content_aspects(rows), bundle))
    aspects = _aspects(report)
    assert aspects["content"]["precision"] == pytest.approx(0.5, abs=1e-6)
    assert aspects["content"]["recall"] == pytest.approx(0.333333, abs=1e-6)
    assert aspects["content"]["f1"] == pytest.approx(0.4, abs=1e-6)
    assert [block["f1"] for name, block in aspects.items() if name != "content"] == [0.0] * 8
    assert report["aspect_macro_f1"] == pytest.approx(0.044444, abs=1e-6)


def test_evaluate_gold_rejects_unknown_row_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sheet_a = _sheet(["negative"] * 5)
    sheet_b = _sheet(["negative"] * 5)
    sheet_a.loc[4, "row_key"] = sheet_b.loc[4, "row_key"] = "f.csv:7"
    with pytest.raises(DatasetError, match="gold row key not in dataset"):
        evaluate_gold(*_setup(tmp_path, monkeypatch, (sheet_a, sheet_b)))


def test_evaluate_gold_rejects_no_agreement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sheets = (_sheet(["negative"] * 5), _sheet(["positive"] * 5))
    with pytest.raises(DatasetError, match="no agreed gold rows"):
        evaluate_gold(*_setup(tmp_path, monkeypatch, sheets))


def test_evaluate_gold_rejects_wrong_bundle_type(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _bundle(_real_aspect_pipeline(), 0.5)
    bundle["polarity_pipeline"] = "x"
    with pytest.raises(ModelUnavailableError, match="unexpected type"):
        evaluate_gold(*_setup(tmp_path, monkeypatch, bundle=bundle))


def test_evaluate_gold_rejects_wrong_thresholds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = _bundle(_real_aspect_pipeline(), 0.5)
    bundle["aspect_thresholds"] = (0.5,) * 8
    with pytest.raises(ModelUnavailableError, match="unexpected type"):
        evaluate_gold(*_setup(tmp_path, monkeypatch, bundle=bundle))


def test_evaluate_gold_rejects_missing_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gold, dataset, models = _setup(tmp_path, monkeypatch)
    (models / "v001" / "report.json").unlink()
    with pytest.raises(ModelUnavailableError, match="report not found"):
        evaluate_gold(gold, dataset, models)


def test_write_report_permissions_and_name(tmp_path: Path) -> None:
    target = write_report(tmp_path / "reports", {"b": 1, "a": 2})
    assert target.parts[-2:] == ("reports", "gold_eval.json")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stat.S_IMODE(target.parent.stat().st_mode) == 0o700
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 2, "b": 1}


def test_write_report_has_no_comment_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    report = evaluate_gold(*_setup(tmp_path, monkeypatch))
    content = write_report(tmp_path / "reports", report).read_text(encoding="utf-8")
    assert not [text for text in TEXTS if text in content]
    assert not [key for key in KEYS if key in content]
    assert '"text"' not in content
    assert "text" not in content


def test_main_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, _, models = _setup(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    assert main([]) == 0
    assert (tmp_path / "reports" / "gold_eval.json").is_file()
    (models / "registry.json").unlink()
    assert main([]) == 2

    def crash(*_args: object) -> dict[str, object]:
        raise RuntimeError("boom")

    monkeypatch.setattr(gold_eval, "evaluate_gold", crash)
    assert main([]) == 1
