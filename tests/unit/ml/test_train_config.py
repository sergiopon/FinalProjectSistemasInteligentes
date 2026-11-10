"""Tests for read_confidence_level, reference_stats and main of ml/train.py (spec 014)."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from api.domain.errors import ConfigError, InvalidInputError
from ml import train
from ml.train import main, read_confidence_level, reference_stats

ALPHA_DETAIL = "conformal.alpha must be a number in (0, 1)"
EMPTY_DETAIL = "reference statistics need matching non-empty inputs"


@pytest.fixture
def logging_restored() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def write_config(directory: Path, content: str) -> Path:
    path = directory / "config" / "app.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_read_confidence_level_from_config(tmp_path: Path) -> None:
    path = write_config(tmp_path, '{"conformal": {"alpha": 0.1}}')
    assert read_confidence_level(path) == 0.9
    path = write_config(tmp_path, '{"conformal": {"alpha": 0.05}}')
    assert read_confidence_level(path) == 0.95


@pytest.mark.parametrize(
    "content",
    [
        '{"conformal": {"alpha": 0}}',
        '{"conformal": {"alpha": 1}}',
        '{"conformal": {"alpha": -0.1}}',
        '{"conformal": {"alpha": true}}',
        '{"conformal": {"alpha": "0.1"}}',
        '{"other": {}}',
        "[]",
    ],
)
def test_read_confidence_level_rejects_invalid_alpha(tmp_path: Path, content: str) -> None:
    with pytest.raises(ConfigError) as info:
        read_confidence_level(write_config(tmp_path, content))
    assert info.value.detail == ALPHA_DETAIL


def test_read_confidence_level_rejects_unreadable_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError) as missing:
        read_confidence_level(tmp_path / "absent.json")
    assert missing.value.detail == "config file unreadable"
    with pytest.raises(ConfigError) as broken:
        read_confidence_level(write_config(tmp_path, "{"))
    assert broken.value.detail == "config file unreadable"


def test_reference_stats_deciles_and_shares() -> None:
    texts = ["x" * k for k in range(1, 21)]
    y_train = np.array([0] * 5 + [1] * 10 + [2] * 5)
    stats = reference_stats(texts, ["a"], y_train, frozenset())
    assert stats["length_edges"] == [2, 4, 6, 8, 10, 12, 14, 16, 18]
    expected = [0.05, *[0.1] * 8, 0.15]
    assert stats["length_shares"] == pytest.approx(expected, abs=1e-12)
    assert stats["class_shares"] == pytest.approx([0.25, 0.5, 0.25], abs=1e-12)


def test_reference_stats_floors_empty_bins() -> None:
    texts = ["x" * 10] * 20
    stats = reference_stats(texts, ["a"], np.zeros(20, dtype=np.int64), frozenset())
    assert stats["length_edges"] == [10] * 9
    shares = stats["length_shares"]
    assert shares[:9] == pytest.approx([9.991008092716556e-05] * 9, abs=1e-12)
    assert shares[9] == pytest.approx(0.9991008092716556, abs=1e-12)
    assert sum(shares) == pytest.approx(1.0, abs=1e-9)


def test_reference_stats_oov_rate() -> None:
    train_texts = ["x" * k for k in range(1, 21)]
    y_train = np.zeros(20, dtype=np.int64)
    vocabulary = frozenset({"curso", "claro"})
    stats = reference_stats(train_texts, ["El curso fue claro", "Curso malo"], y_train, vocabulary)
    assert stats["reference_oov_rate"] == 0.5
    assert reference_stats(train_texts, ["a b"], y_train, vocabulary)["reference_oov_rate"] == 0.0


def test_reference_stats_rejects_empty_inputs() -> None:
    y_two = np.zeros(2, dtype=np.int64)
    cases = [
        ([], ["a"], np.zeros(0, dtype=np.int64)),
        (["a", "b"], [], y_two),
        (["a", "b"], ["a"], np.zeros(3, dtype=np.int64)),
    ]
    for train_texts, test_texts, y_train in cases:
        with pytest.raises(InvalidInputError) as info:
            reference_stats(train_texts, test_texts, y_train, frozenset())
        assert info.value.detail == EMPTY_DETAIL


@pytest.mark.usefixtures("logging_restored")
def test_main_exit_codes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main([]) == 2
    assert capsys.readouterr().err.strip() == "error=internal_error"
    assert main(["--models", "../x"]) == 2
    assert capsys.readouterr().err.strip() == "error=internal_error"
    write_config(tmp_path, '{"conformal": {"alpha": 0.1}}')
    received: list[tuple[Path, Path, float]] = []

    def fake_train(dataset_dir: Path, models_dir: Path, confidence_level: float) -> str:
        received.append((dataset_dir, models_dir, confidence_level))
        return "v007"

    monkeypatch.setattr(train, "train", fake_train)
    assert main([]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == "trained=v007"
    base = tmp_path.resolve()
    assert received == [(base / "Dataset", base / "models", 0.9)]
    for error, code, line in (
        (InvalidInputError("x"), 2, "error=invalid_input"),
        (RuntimeError("boom"), 1, "error=internal_error"),
    ):

        def failing(*_args: object, _error: Exception = error) -> str:
            raise _error

        monkeypatch.setattr(train, "train", failing)
        assert main([]) == code
        assert capsys.readouterr().err.strip() == line


@pytest.mark.usefixtures("logging_restored")
def test_main_sets_umask(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    previous = os.umask(0o022)
    try:
        assert main([]) == 2
        assert os.umask(0o022) == 0o077
    finally:
        os.umask(previous)
