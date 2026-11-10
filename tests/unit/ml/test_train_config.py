"""Tests for read_confidence_level, reference_stats and main of ml/train.py."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest

from api.domain.errors import ConfigError, InvalidInputError
from ml import train as train_module
from ml.train import main, read_confidence_level, reference_stats

ALPHA_ERROR = "conformal.alpha must be a number in (0, 1)"


@pytest.fixture
def umask_restored() -> Iterator[None]:
    previous = os.umask(0o022)
    yield
    os.umask(previous)


def write_config(path: Path, content: object) -> Path:
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


@pytest.mark.parametrize(("alpha", "expected"), [(0.1, 0.9), (0.05, 0.95)])
def test_read_confidence_level_from_config(tmp_path: Path, alpha: float, expected: float) -> None:
    path = write_config(tmp_path / "app.json", {"conformal": {"alpha": alpha}})
    assert read_confidence_level(path) == expected


@pytest.mark.parametrize(
    "content",
    [
        {"conformal": {"alpha": 0}},
        {"conformal": {"alpha": 1}},
        {"conformal": {"alpha": -0.1}},
        {"conformal": {"alpha": True}},
        {"conformal": {"alpha": "0.1"}},
        {"other": 1},
        [1],
    ],
)
def test_read_confidence_level_rejects_invalid_alpha(tmp_path: Path, content: object) -> None:
    path = write_config(tmp_path / "app.json", content)
    with pytest.raises(ConfigError) as info:
        read_confidence_level(path)
    assert info.value.detail == ALPHA_ERROR


def test_read_confidence_level_rejects_unreadable_file(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    for path in (tmp_path / "missing.json", broken):
        with pytest.raises(ConfigError) as info:
            read_confidence_level(path)
        assert info.value.detail == "config file unreadable"


def test_reference_stats_deciles_and_shares() -> None:
    texts = ["x" * k for k in range(1, 21)]
    y_train = np.array([0] * 5 + [1] * 10 + [2] * 5)
    stats = reference_stats(texts, ["a"], y_train, frozenset())
    assert stats["length_edges"] == [2, 4, 6, 8, 10, 12, 14, 16, 18]
    expected = [0.05, *[0.1] * 8, 0.15]
    assert stats["length_shares"] == pytest.approx(expected, abs=1e-12)
    assert stats["class_shares"] == pytest.approx([0.25, 0.5, 0.25], abs=1e-12)


def test_reference_stats_floors_empty_bins() -> None:
    stats = reference_stats(["x" * 10] * 20, ["a"], np.zeros(20, dtype=np.int64), frozenset())
    assert stats["length_edges"] == [10] * 9
    shares = stats["length_shares"]
    assert shares[:9] == pytest.approx([9.991008092716556e-05] * 9, abs=1e-12)
    assert shares[9] == pytest.approx(0.9991008092716556, abs=1e-12)
    assert sum(shares) == pytest.approx(1.0, abs=1e-9)


def test_reference_stats_oov_rate() -> None:
    vocabulary = frozenset({"curso", "claro"})
    texts = ["El curso fue claro", "Curso malo"]
    stats = reference_stats(["abc"], texts, np.array([0]), vocabulary)
    assert stats["reference_oov_rate"] == 0.5
    assert reference_stats(["abc"], ["a b"], np.array([0]), vocabulary)["reference_oov_rate"] == 0.0


@pytest.mark.parametrize(
    ("train_texts", "test_texts", "y"),
    [([], ["a"], []), (["a"], [], [0]), (["a", "b"], ["c"], [0, 1, 2])],
)
def test_reference_stats_rejects_empty_inputs(
    train_texts: list[str], test_texts: list[str], y: list[int]
) -> None:
    with pytest.raises(InvalidInputError) as info:
        reference_stats(train_texts, test_texts, np.array(y), frozenset())
    assert info.value.detail == "reference statistics need matching non-empty inputs"


def prepare_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    write_config(tmp_path / "config" / "app.json", {"conformal": {"alpha": 0.1}})


def test_main_rejects_missing_config_and_unsafe_models(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main([]) == 2
    assert capsys.readouterr().err.strip() == "error=internal_error"
    prepare_config(tmp_path, monkeypatch)
    assert main(["--models", "../x"]) == 2
    assert capsys.readouterr().err.strip() == "error=internal_error"


def test_main_passes_resolved_paths_to_train(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    prepare_config(tmp_path, monkeypatch)
    calls: list[tuple[Path, Path, float]] = []

    def fake(dataset: Path, models: Path, level: float) -> str:
        calls.append((dataset, models, level))
        return "v007"

    monkeypatch.setattr(train_module, "train", fake)
    assert main([]) == 0
    assert capsys.readouterr().out.strip().splitlines()[-1] == "trained=v007"
    assert calls == [(tmp_path.resolve() / "Dataset", tmp_path.resolve() / "models", 0.9)]


@pytest.mark.parametrize(
    ("error", "code", "stderr"),
    [
        (InvalidInputError("x"), 2, "error=invalid_input"),
        (RuntimeError("boom"), 1, "error=internal_error"),
    ],
)
def test_main_maps_errors_to_exit_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    code: int,
    stderr: str,
) -> None:
    prepare_config(tmp_path, monkeypatch)

    def failing(dataset: Path, models: Path, level: float) -> str:
        raise error

    monkeypatch.setattr(train_module, "train", failing)
    assert main([]) == code
    assert capsys.readouterr().err.strip() == stderr


@pytest.mark.usefixtures("umask_restored")
def test_main_sets_umask(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert main([]) == 2
    assert os.umask(0o022) == 0o077
