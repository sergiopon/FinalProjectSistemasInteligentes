"""Integration test for api/adapters/csv_reader.py on the real dataset (spec 021)."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.adapters.csv_reader import parse_csv_body
from api.adapters.settings import LimitSettings

pytestmark = pytest.mark.integration

DATASET = Path(__file__).resolve().parents[2] / "Dataset"
LIMITS = LimitSettings(max_text_chars=2000, max_upload_bytes=2097152, max_upload_rows=5000)
EXPECTED_COUNTS = {
    "feedback_curso_universitario.csv": 193,
    "feedback_curso_universitario2.csv": 405,
    "feedback_curso_universitario3.csv": 20,
}


def test_parse_csv_reads_course_files() -> None:
    for name, count in EXPECTED_COUNTS.items():
        comments = parse_csv_body((DATASET / name).read_bytes(), LIMITS)
        assert len(comments) == count
        assert all(comment.course is not None for comment in comments)
