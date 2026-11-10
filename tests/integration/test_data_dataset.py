"""Integration tests of ml/data.py on the real Dataset/ (SEC-09 exception)."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.domain.entities import ASPECT_ORDER
from ml.data import dataset_files, dataset_sha256, load_dataset, normalize_text

pytestmark = pytest.mark.integration

DATASET_DIR = Path("Dataset")
ASPECT_COLUMNS = [f"aspect_{group.value}" for group in ASPECT_ORDER]


def test_dataset_counts() -> None:
    frame = load_dataset(DATASET_DIR)
    assert len(frame) == 618
    assert frame["source_file"].value_counts().sort_index().tolist() == [193, 405, 20]
    assert frame["polarity"].value_counts().to_dict() == {
        "negative": 205,
        "neutral": 259,
        "positive": 154,
    }
    assert [int((frame[column] != "").sum()) for column in ASPECT_COLUMNS] == [
        361,
        94,
        76,
        71,
        66,
        59,
        48,
        38,
        35,
    ]
    assert int((frame[ASPECT_COLUMNS] == "").all(axis=1).sum()) == 60
    assert frame["row_key"].is_unique


def test_dataset_values() -> None:
    frame = load_dataset(DATASET_DIR).set_index("row_key")
    assert frame["course"].nunique() == 7
    assert "Sistemas opertativos" in set(frame["course"])
    assert set(frame["semester"]) == {"2023-1", "2023-2", "2024-1", "2024-2"}
    assert frame.loc["feedback_curso_universitario3.csv:8", "source_id"] == 1
    text = frame.loc["feedback_curso_universitario3.csv:5", "text"]
    assert text.startswith("Estimado estudiante, Recuerda")
    assert "\n" not in text
    assert all(value == normalize_text(value) for value in frame["text"])


def test_dataset_sha256_value() -> None:
    result = dataset_sha256(dataset_files(DATASET_DIR))
    assert result == "5e3ac133828878229457420245bd2d674fdfe985e5a13632bf97b35bdbf2f666"
