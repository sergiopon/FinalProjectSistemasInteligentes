"""Tests for the file checks, dataset hash and load_dataset of ml/data.py."""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from api.domain.errors import DatasetError
from ml.data import (
    MAX_INPUT_BYTES,
    dataset_files,
    dataset_sha256,
    load_dataset,
    validate_input_file,
)
from ml.schemas import CLEAN_COLUMNS, RAW_COLUMNS

HEADER = ",".join(RAW_COLUMNS)
ROW_1 = (
    "7,Bases de datos,\"Las clases  fueron\nclaras y útiles.\",['positivo'],3,neutral,"
    '"[{""aspecto"": ""contenidos"", ""sentimiento"": ""positivo""}]",2023-1'
)
ROW_2 = (
    "7,Bases de datos,Los parciales fueron muy difíciles para todos.,negativo,3,neutral,"
    '"[{""aspecto"": ""parciales"", ""sentimiento"": ""negativo""}, '
    '{""aspecto"": ""horario"", ""sentimiento"": ""neutral""}]",2024-2'
)
SYN = "﻿" + "\n".join([HEADER, HEADER, ROW_1, ROW_2]) + "\n"


def write_syn(directory: Path, name: str = "synthetic.csv") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text(SYN, encoding="utf-8")
    return path


def assert_file_error(path: Path, base: Path, detail: str) -> None:
    with pytest.raises(DatasetError) as info:
        validate_input_file(path, base)
    assert info.value.detail == detail


def test_validate_input_file_returns_resolved_path(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    (base / "a.csv").write_text("x", encoding="utf-8")
    (base / "A.CSV").write_text("x", encoding="utf-8")
    assert validate_input_file(base / "a.csv", base) == (base / "a.csv").resolve()
    assert validate_input_file(base / "A.CSV", base) == (base / "A.CSV").resolve()


def test_validate_input_file_rejects_extension(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    assert_file_error(tmp_path / "a.txt", tmp_path, "input file must have the .csv extension")


def test_validate_input_file_rejects_symlink(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("x", encoding="utf-8")
    (tmp_path / "link.csv").symlink_to(tmp_path / "a.csv")
    assert_file_error(tmp_path / "link.csv", tmp_path, "input file must not be a symlink")


def test_validate_input_file_rejects_missing(tmp_path: Path) -> None:
    assert_file_error(tmp_path / "missing.csv", tmp_path, "input file not found")


def test_validate_input_file_rejects_symlink_loop(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    (base / "l1").symlink_to(base / "l2")
    (base / "l2").symlink_to(base / "l1")
    assert_file_error(base / "l1" / "x.csv", base, "input file not found")


def test_validate_input_file_rejects_missing_base(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_text("x", encoding="utf-8")
    assert_file_error(tmp_path / "a.csv", tmp_path / "nope", "input base directory not found")


def test_validate_input_file_rejects_outside_base(tmp_path: Path) -> None:
    base = tmp_path / "base"
    base.mkdir()
    (tmp_path / "out.csv").write_text("x", encoding="utf-8")
    assert_file_error(base / ".." / "out.csv", base, "input file is outside its base directory")


def test_validate_input_file_rejects_directory(tmp_path: Path) -> None:
    (tmp_path / "d.csv").mkdir()
    assert_file_error(tmp_path / "d.csv", tmp_path, "input file must be a regular file")


def test_validate_input_file_rejects_fifo(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "x.csv")
    assert_file_error(tmp_path / "x.csv", tmp_path, "input file must be a regular file")


def test_validate_input_file_rejects_oversize(tmp_path: Path) -> None:
    (tmp_path / "big.csv").write_bytes(b"x" * (MAX_INPUT_BYTES + 1))
    assert_file_error(tmp_path / "big.csv", tmp_path, "input file exceeds 2097152 bytes")


def test_validate_input_file_accepts_size_limit(tmp_path: Path) -> None:
    (tmp_path / "limit.csv").write_bytes(b"x" * MAX_INPUT_BYTES)
    assert (
        validate_input_file(tmp_path / "limit.csv", tmp_path) == (tmp_path / "limit.csv").resolve()
    )


def test_dataset_files_sorted_top_level(tmp_path: Path) -> None:
    for name in ("b.csv", "a.csv", "notes.txt"):
        (tmp_path / name).write_text("x", encoding="utf-8")
    (tmp_path / "__MACOSX").mkdir()
    (tmp_path / "__MACOSX" / "c.csv").write_text("x", encoding="utf-8")
    result = dataset_files(tmp_path)
    assert result == ((tmp_path / "a.csv").resolve(), (tmp_path / "b.csv").resolve())


def test_dataset_files_rejects_missing_and_empty(tmp_path: Path) -> None:
    with pytest.raises(DatasetError) as missing:
        dataset_files(tmp_path / "nope")
    assert missing.value.detail == "dataset directory not found"
    (tmp_path / "notes.txt").write_text("x", encoding="utf-8")
    with pytest.raises(DatasetError) as empty:
        dataset_files(tmp_path)
    assert empty.value.detail == "no CSV files in dataset directory"


def test_dataset_sha256_vector(tmp_path: Path) -> None:
    (tmp_path / "a.csv").write_bytes(b"x\n")
    (tmp_path / "b.csv").write_bytes(b"y\n")
    result = dataset_sha256([tmp_path / "b.csv", tmp_path / "a.csv"])
    assert result == "393bea311dcb44194f89bc26c627e0dd485632584b5b827ca0bacbb4d2f723f3"


def test_load_dataset_builds_clean_frame(tmp_path: Path) -> None:
    write_syn(tmp_path)
    frame = load_dataset(tmp_path)
    assert len(frame) == 2
    assert tuple(frame.columns) == CLEAN_COLUMNS
    assert frame["row_key"].tolist() == ["synthetic.csv:1", "synthetic.csv:2"]
    assert frame["source_id"].tolist() == [7, 7]
    assert str(frame["source_id"].dtype) == "int64"
    assert frame["text"][0] == "Las clases fueron claras y útiles."
    assert frame["polarity"].tolist() == ["positive", "negative"]
    assert frame["aspect_content"][0] == "positive"
    assert frame["aspect_assessment"][1] == "negative"
    assert frame["aspect_organization_schedule"][1] == "neutral"
    aspect_cells = [frame[column][row] for column in CLEAN_COLUMNS[7:] for row in (0, 1)]
    assert sum(cell == "" for cell in aspect_cells) == 15


def test_load_dataset_orders_files_by_name(tmp_path: Path) -> None:
    write_syn(tmp_path, "b.csv")
    write_syn(tmp_path, "a.csv")
    frame = load_dataset(tmp_path)
    assert frame["row_key"][0] == "a.csv:1"
    assert len(frame) == 4


@pytest.mark.parametrize(
    ("content", "detail"),
    [
        (b"id,curso\n1,\xff\n", "dataset file is not a parseable CSV"),
        (b"", "dataset file is not a parseable CSV"),
        ((HEADER + '\n7,"unterminated\n').encode(), "dataset file is not a parseable CSV"),
        ((",".join(RAW_COLUMNS[:-1]) + "\n").encode(), "dataset columns do not match"),
        ((HEADER + "\n").encode(), "dataset has no rows"),
        (
            (HEADER + "\n" + ROW_2.replace("7,", "x1,", 1) + "\n").encode(),
            "dataset id is not an integer",
        ),
        (
            (
                HEADER
                + "\n"
                + ROW_2.replace("Los parciales fueron muy difíciles para todos.", "   ")
                + "\n"
            ).encode(),
            "dataset text is empty",
        ),
    ],
    ids=["undecodable", "empty", "unterminated", "columns", "header_only", "bad_id", "blank_text"],
)
def test_load_dataset_rejects_bad_files(tmp_path: Path, content: bytes, detail: str) -> None:
    (tmp_path / "bad.csv").write_bytes(content)
    with pytest.raises(DatasetError) as info:
        load_dataset(tmp_path)
    assert info.value.detail == detail


def test_load_dataset_logs_no_text(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    write_syn(tmp_path)
    with caplog.at_level(logging.INFO):
        load_dataset(tmp_path)
    messages = [record.getMessage() for record in caplog.records]
    assert "dataset_loaded files=1 rows=2" in messages
    assert not any("clases" in message or "synthetic" in message for message in messages)
