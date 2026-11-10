"""Tests for the gold-evaluation sheet reader, agreement and metric functions (spec 029)."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from api.domain.entities import AspectGroup
from api.domain.errors import DatasetError, InvalidInputError, ModelUnavailableError
from ml.gold_eval import (
    ASPECT_COLUMNS,
    GOLD_COLUMNS,
    active_version,
    agreed_polarity,
    agreed_presence,
    presence_metrics,
    read_gold_sheet,
)


def _frame(polarity: list[str], content: list[str] | None = None) -> pd.DataFrame:
    n = len(polarity)
    frame = pd.DataFrame({"row_key": [f"f.csv:{i}" for i in range(1, n + 1)], "polarity": polarity})
    for column in ASPECT_COLUMNS:
        frame[column] = ""
    if content is not None:
        frame["aspect_content"] = content
    return frame[list(GOLD_COLUMNS)]


def _write(frame: pd.DataFrame, path: Path, encoding: str = "utf-8") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding=encoding, lineterminator="\n")
    return path


def test_read_gold_sheet_normalizes_values(tmp_path: Path) -> None:
    frame = _frame([" Negative "], ["POSITIVE"])
    frame["row_key"] = " f.csv:1 "
    frame["notes"] = "x"
    path = _write(frame, tmp_path / "gold" / "sheet_a.csv", encoding="utf-8-sig")
    sheet = read_gold_sheet(path, tmp_path / "gold")
    assert list(sheet.columns) == list(GOLD_COLUMNS)
    assert len(sheet.columns) == 11
    assert sheet.loc[0, "row_key"] == "f.csv:1"
    assert sheet.loc[0, "polarity"] == "negative"
    assert sheet.loc[0, "aspect_content"] == "positive"
    assert sheet.loc[0, "aspect_assessment"] == ""


def test_read_gold_sheet_rejects_missing_column(tmp_path: Path) -> None:
    frame = _frame(["negative"]).drop(columns=["aspect_platform"])
    path = _write(frame, tmp_path / "gold" / "sheet_a.csv")
    with pytest.raises(DatasetError, match="gold sheet missing columns"):
        read_gold_sheet(path, tmp_path / "gold")


def test_read_gold_sheet_rejects_duplicate_keys(tmp_path: Path) -> None:
    frame = _frame(["negative", "positive"])
    frame["row_key"] = "f.csv:1"
    path = _write(frame, tmp_path / "gold" / "sheet_a.csv")
    with pytest.raises(DatasetError, match="duplicate row keys"):
        read_gold_sheet(path, tmp_path / "gold")


@pytest.mark.parametrize("value", ["mixed", ""])
def test_read_gold_sheet_rejects_invalid_polarity(tmp_path: Path, value: str) -> None:
    path = _write(_frame([value]), tmp_path / "gold" / "sheet_a.csv")
    with pytest.raises(DatasetError, match="invalid polarity value"):
        read_gold_sheet(path, tmp_path / "gold")


def test_read_gold_sheet_rejects_invalid_aspect(tmp_path: Path) -> None:
    path = _write(_frame(["negative"], ["yes"]), tmp_path / "gold" / "sheet_a.csv")
    with pytest.raises(DatasetError, match="invalid aspect value"):
        read_gold_sheet(path, tmp_path / "gold")


def test_read_gold_sheet_rejects_symlink(tmp_path: Path) -> None:
    real = _write(_frame(["negative"]), tmp_path / "gold" / "real.csv")
    link = tmp_path / "gold" / "sheet_a.csv"
    link.symlink_to(real)
    with pytest.raises(DatasetError):
        read_gold_sheet(link, tmp_path / "gold")


def test_read_gold_sheet_rejects_wrong_extension(tmp_path: Path) -> None:
    path = _write(_frame(["negative"]), tmp_path / "gold" / "sheet_a.txt")
    with pytest.raises(DatasetError):
        read_gold_sheet(path, tmp_path / "gold")


def test_read_gold_sheet_rejects_unparsable_file(tmp_path: Path) -> None:
    path = tmp_path / "gold" / "sheet_a.csv"
    path.parent.mkdir()
    path.write_bytes(b"")
    with pytest.raises(DatasetError, match="cannot be parsed"):
        read_gold_sheet(path, tmp_path / "gold")


def test_agreed_polarity_keeps_matching_rows() -> None:
    sheet_a = _frame(["negative", "neutral", "positive", "positive"])
    sheet_b = _frame(["negative", "positive", "positive", "positive"])
    agreed = agreed_polarity(sheet_a, sheet_b)
    assert agreed["row_key"].tolist() == ["f.csv:1", "f.csv:3", "f.csv:4"]
    assert agreed["polarity"].tolist() == ["negative", "positive", "positive"]


def test_agreed_polarity_rejects_different_keys() -> None:
    sheet_a = _frame(["negative"] * 4)
    sheet_b = _frame(["negative"] * 4)
    sheet_b.loc[3, "row_key"] = "f.csv:9"
    with pytest.raises(DatasetError, match="different row keys"):
        agreed_polarity(sheet_a, sheet_b)


def test_agreed_presence_keeps_matching_rows() -> None:
    sheet_a = _frame(["negative"] * 5, ["negative", "", "positive", "", "neutral"])
    sheet_b = _frame(["negative"] * 5, ["positive", "", "", "", "neutral"])
    agreed = agreed_presence(sheet_a, sheet_b, AspectGroup.CONTENT)
    assert agreed["row_key"].tolist() == ["f.csv:1", "f.csv:2", "f.csv:4", "f.csv:5"]
    assert agreed["present"].tolist() == [True, False, False, True]
    assert agreed["present"].dtype == bool


def test_presence_metrics_vector() -> None:
    metrics = presence_metrics([True, True, True, False, False], [True, False, False, False, True])
    assert metrics["agreed_rows"] == 5
    assert metrics["gold_present"] == 3
    assert metrics["precision"] == pytest.approx(0.5, abs=1e-6)
    assert metrics["recall"] == pytest.approx(0.333333, abs=1e-6)
    assert metrics["f1"] == pytest.approx(0.4, abs=1e-6)


def test_presence_metrics_no_positives() -> None:
    metrics = presence_metrics([False, False], [False, False])
    assert (metrics["precision"], metrics["recall"], metrics["f1"]) == (0.0, 0.0, 0.0)


def test_presence_metrics_no_rows() -> None:
    assert presence_metrics([], [])["f1"] == 0.0


def test_presence_metrics_rejects_length_mismatch() -> None:
    with pytest.raises(InvalidInputError, match="lengths differ"):
        presence_metrics([True, False], [True, False, True])


def test_active_version_reads_registry(tmp_path: Path) -> None:
    (tmp_path / "registry.json").write_text(
        json.dumps({"active": "v002", "history": ["v001", "v002"]}), encoding="utf-8"
    )
    assert active_version(tmp_path) == "v002"


def test_active_version_rejects_missing_or_invalid(tmp_path: Path) -> None:
    with pytest.raises(ModelUnavailableError, match="registry not found"):
        active_version(tmp_path)
    (tmp_path / "registry.json").write_text('{"active": "2"}', encoding="utf-8")
    with pytest.raises(ModelUnavailableError, match="registry has no active version"):
        active_version(tmp_path)
