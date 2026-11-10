"""Tests for the gold-set sampling and the ``ml.gold`` command line (spec 015)."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest

from api.domain.errors import DatasetError
from ml import gold
from ml.gold import (
    POLARITY_VALUES,
    SHEET_COLUMNS,
    SHEET_FILES,
    main,
    sample_sheet,
    write_sheets,
)


def _f30() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "row_key": [f"synthetic.csv:{i}" for i in range(1, 31)],
            "text": [f"Comentario sintético número {i}." for i in range(1, 31)],
            "polarity": [POLARITY_VALUES[i % 3] for i in range(30)],
        }
    )


@pytest.fixture(autouse=True)
def _restore_root_logger() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def test_sample_sheet_is_stratified_and_deterministic() -> None:
    frame = _f30()
    sheet = sample_sheet(frame, 12)
    assert len(sheet) == 12
    assert list(sheet["row_key"][:3]) == [
        "synthetic.csv:17",
        "synthetic.csv:2",
        "synthetic.csv:3",
    ]
    keys = set(sheet["row_key"])
    chosen = frame[frame["row_key"].isin(keys)]
    assert chosen["polarity"].value_counts().to_dict() == {p: 4 for p in POLARITY_VALUES}
    assert list(sheet["gold_id"]) == [str(i) for i in range(1, 13)]
    assert tuple(sheet.columns) == SHEET_COLUMNS


def test_sample_sheet_hides_dataset_label() -> None:
    sheet = sample_sheet(_f30(), 12)
    assert (sheet[list(SHEET_COLUMNS[3:])] == "").all().all()


@pytest.mark.parametrize("size", [9, 201])
def test_sample_sheet_rejects_size_out_of_range(size: int) -> None:
    with pytest.raises(DatasetError, match="sample size out of range"):
        sample_sheet(_f30(), size)


def test_sample_sheet_rejects_unstratifiable_size() -> None:
    with pytest.raises(DatasetError, match="cannot stratify sample"):
        sample_sheet(_f30(), 28)


def test_write_sheets_writes_two_identical_files(tmp_path: Path) -> None:
    previous = os.umask(0o077)
    try:
        first, second = write_sheets(sample_sheet(_f30(), 12), tmp_path / "gold")
    finally:
        os.umask(previous)
    assert first.read_bytes() == second.read_bytes()
    assert first.stat().st_mode & 0o777 == 0o600
    assert (first.name, second.name) == SHEET_FILES


def test_write_sheets_refuses_overwrite(tmp_path: Path) -> None:
    gold_dir = tmp_path / "gold"
    gold_dir.mkdir()
    (gold_dir / "sheet_a.csv").write_text("x", encoding="utf-8")
    with pytest.raises(DatasetError, match="gold sheets already exist"):
        write_sheets(sample_sheet(_f30(), 12), gold_dir)
    assert (gold_dir / "sheet_a.csv").read_text(encoding="utf-8") == "x"
    assert not (gold_dir / "sheet_b.csv").exists()


def test_main_sample_returns_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(gold, "load_dataset", lambda _dir: _f30())
    assert main(["sample", "--n", "12"]) == 0
    assert "event=gold_sample rows=12" in capsys.readouterr().out
    assert (tmp_path / "gold" / "sheet_b.csv").is_file()


def test_main_returns_two_on_app_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(gold, "load_dataset", lambda _dir: _f30())
    assert main(["sample", "--n", "9"]) == 2
    assert capsys.readouterr().err == "ml.gold failed: sample size out of range\n"


def _boom(_dir: Path) -> pd.DataFrame:
    raise RuntimeError("boom")


def test_main_returns_one_on_unexpected_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(gold, "load_dataset", _boom)
    assert main(["sample"]) == 1
    captured = capsys.readouterr()
    assert captured.err == "ml.gold failed: unexpected error, see the log.\n"
    assert "RuntimeError: boom" in captured.out


def test_main_sets_umask_first(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    calls: list[int] = []

    def record(mask: int) -> int:
        calls.append(mask)
        return 0o022

    monkeypatch.setattr(os, "umask", record)
    monkeypatch.setattr(gold, "load_dataset", _boom)
    assert main(["sample"]) == 1
    assert calls[0] == 0o077
