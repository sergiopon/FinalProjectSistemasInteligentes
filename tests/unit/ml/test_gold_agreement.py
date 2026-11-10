"""Tests for the gold-sheet reader and the agreement statistics (spec 015)."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest

from api.domain.entities import ASPECT_ORDER
from api.domain.errors import DatasetError
from ml.gold import (
    ASPECT_COLUMNS,
    ASPECT_VALUES,
    POLARITY_VALUES,
    SHEET_COLUMNS,
    agreement,
    cohen_kappa,
    main,
    read_sheet,
)

NEG, NEU, POS = POLARITY_VALUES
POL_A = [NEG, NEG, NEU, NEU, POS, POS, POS, NEG, NEU, POS]
POL_B = [NEG, NEU, NEU, NEU, POS, POS, NEG, NEG, NEU, POS]
CONTENT_A = ["", "negative", "", "", "positive", "", "", "", "neutral", ""]
CONTENT_B = ["", "negative", "", "positive", "positive", "", "", "", "", ""]


@pytest.fixture(autouse=True)
def _restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def _sheet(polarity: list[str], content: list[str]) -> pd.DataFrame:
    n = len(polarity)
    frame = pd.DataFrame(
        {
            "gold_id": [str(i) for i in range(1, n + 1)],
            "row_key": [f"synthetic.csv:{i}" for i in range(1, n + 1)],
            "text": [f"Comentario sintético número {i}." for i in range(1, n + 1)],
            "polarity": polarity,
        }
    )
    for column in ASPECT_COLUMNS:
        frame[column] = ""
    frame["aspect_content"] = content
    return frame[list(SHEET_COLUMNS)]


def _write(frame: pd.DataFrame, path: Path, encoding: str = "utf-8") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding=encoding, lineterminator="\n")
    return path


def test_cohen_kappa_polarity_vector() -> None:
    assert cohen_kappa(POL_A, POL_B, POLARITY_VALUES) == 0.7014925373134329


def test_cohen_kappa_undefined_returns_none() -> None:
    assert cohen_kappa([""] * 5, [""] * 5, ASPECT_VALUES) is None


def test_cohen_kappa_disjoint_single_values() -> None:
    assert cohen_kappa([""] * 4, ["negative"] * 4, ASPECT_VALUES) == 0.0


def _expected() -> dict[str, object]:
    aspects: dict[str, object] = {
        group.value: {"presence_kappa": None, "label_kappa": None} for group in ASPECT_ORDER
    }
    aspects["content"] = {"presence_kappa": 0.52381, "label_kappa": 0.583333}
    return {
        "rows": 10,
        "polarity": {"kappa": 0.701493, "observed_agreement": 0.8},
        "aspects": aspects,
    }


def test_agreement_vector() -> None:
    result = agreement(_sheet(POL_A, CONTENT_A), _sheet(POL_B, CONTENT_B))
    assert result == _expected()


def test_main_agreement_writes_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _write(_sheet(POL_A, CONTENT_A), tmp_path / "gold" / "sheet_a.csv")
    _write(_sheet(POL_B, CONTENT_B), tmp_path / "gold" / "sheet_b.csv")
    assert main(["agreement"]) == 0
    written = json.loads((tmp_path / "gold" / "agreement.json").read_text(encoding="utf-8"))
    assert written == _expected()


@pytest.mark.parametrize(
    ("name", "message"),
    [
        ("sheet_a.txt", "input file must have the .csv extension"),
        ("link.csv", "input file must not be a symlink"),
        ("missing.csv", "input file not found"),
    ],
)
def test_read_sheet_rejects_unsafe_path(tmp_path: Path, name: str, message: str) -> None:
    gold_dir = tmp_path / "gold"
    _write(_sheet(POL_A, CONTENT_A), gold_dir / "sheet_a.csv")
    (gold_dir / "link.csv").symlink_to(gold_dir / "sheet_a.csv")
    (gold_dir / "sheet_a.txt").write_text("x", encoding="utf-8")
    with pytest.raises(DatasetError, match=message):
        read_sheet(gold_dir / name, gold_dir)


def test_read_sheet_rejects_header_only(tmp_path: Path) -> None:
    path = tmp_path / "gold" / "sheet_a.csv"
    _write(_sheet([], []), path)
    with pytest.raises(DatasetError, match="gold sheet has no rows"):
        read_sheet(path, path.parent)


def test_main_agreement_missing_sheet_returns_two(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "gold").mkdir()
    assert main(["agreement"]) == 2
    assert capsys.readouterr().err == "ml.gold failed: input file not found\n"


def test_read_sheet_accepts_bom(tmp_path: Path) -> None:
    polarity = [" Positive "] + POL_A[1:]
    path = _write(_sheet(polarity, CONTENT_A), tmp_path / "gold" / "sheet_a.csv", "utf-8-sig")
    assert read_sheet(path, path.parent)["polarity"][0] == "positive"


def test_read_sheet_rejects_missing_column(tmp_path: Path) -> None:
    path = _write(
        _sheet(POL_A, CONTENT_A).drop(columns="aspect_platform"), tmp_path / "g" / "a.csv"
    )
    with pytest.raises(DatasetError, match="gold sheet columns mismatch"):
        read_sheet(path, path.parent)


@pytest.mark.parametrize("value", ["", "mixed"])
def test_read_sheet_rejects_incomplete_row(tmp_path: Path, value: str) -> None:
    polarity = list(POL_A)
    polarity[2] = value
    path = _write(_sheet(polarity, CONTENT_A), tmp_path / "gold" / "sheet_a.csv")
    with pytest.raises(DatasetError, match="gold sheet incomplete: row 3"):
        read_sheet(path, path.parent)


def test_read_sheet_rejects_invalid_aspect(tmp_path: Path) -> None:
    content = list(CONTENT_A)
    content[1] = "good"
    path = _write(_sheet(POL_A, content), tmp_path / "gold" / "sheet_a.csv")
    with pytest.raises(DatasetError, match="gold sheet invalid aspect: row 2"):
        read_sheet(path, path.parent)


def _swapped(column: str) -> pd.DataFrame:
    frame = _sheet(POL_B, CONTENT_B)
    frame.loc[[0, 1], column] = frame.loc[[1, 0], column].to_numpy()
    return frame


@pytest.mark.parametrize(
    "other",
    [
        _sheet(POL_B[:9], CONTENT_B[:9]),
        _swapped("row_key"),
        _swapped("gold_id"),
    ],
)
def test_agreement_rejects_mismatched_rows(other: pd.DataFrame) -> None:
    with pytest.raises(DatasetError, match="gold sheets do not match"):
        agreement(_sheet(POL_A, CONTENT_A), other)
