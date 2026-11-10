from __future__ import annotations

import pytest

from api.adapters.monitoring import ReferenceDriftDetector
from api.domain.errors import InvalidInputError, ModelIntegrityError

SHA = "a" * 64
NOW = "2026-11-10T12:00:00Z"
TOLERANCE = 1e-6
UNIFORM: dict[str, object] = {
    "length_edges": [10, 20, 30, 40, 50, 60, 70, 80, 90],
    "length_shares": [0.1] * 10,
    "reference_oov_rate": 0.2,
    "class_shares": [0.33, 0.42, 0.25],
}
CONTRACT_TEXTS = ["a" * 5] * 3 + ["b" * length for length in (15, 25, 35, 45, 55, 65, 75)]
ONE_PER_BIN = ["c" * length for length in range(5, 100, 10)]


def detector(vocabulary: frozenset[str] = frozenset()) -> ReferenceDriftDetector:
    return ReferenceDriftDetector(UNIFORM, vocabulary)


def with_values(**changes: object) -> dict[str, object]:
    return {**UNIFORM, **changes}


def test_drift_contract_vector() -> None:
    report = detector().compare(CONTRACT_TEXTS, SHA, NOW)
    assert abs(report.length_psi - 1.599892) <= TOLERANCE
    assert report.drifted is True
    assert report.row_count == 10


def test_drift_one_text_per_bin_has_zero_psi() -> None:
    report = detector(frozenset(ONE_PER_BIN)).compare(ONE_PER_BIN, SHA, NOW)
    assert abs(report.length_psi) <= TOLERANCE
    assert report.oov_rate == 0.0
    assert report.drifted is False


def test_drift_bin_edges_use_bisect_right() -> None:
    report = detector().compare(["d" * 9, "d" * 10, "d" * 90], SHA, NOW)
    assert abs(report.length_psi - 5.673374) <= TOLERANCE


def test_drift_single_bin_batch() -> None:
    report = detector().compare(["x" * 50] * 4, SHA, NOW)
    assert abs(report.length_psi - 8.283089) <= TOLERANCE
    assert report.drifted is True


def test_drift_oov_rate_and_margin() -> None:
    shares = [0.0001, 0.9991] + [0.0001] * 8
    vocabulary = frozenset({"curso", "claro", "profesor"})
    texts = ["El curso fue claro", "profesor nuevo"]
    reference = with_values(length_shares=shares, reference_oov_rate=0.4)
    report = ReferenceDriftDetector(reference, vocabulary).compare(texts, SHA, NOW)
    assert abs(report.oov_rate - 0.5) <= TOLERANCE
    assert abs(report.length_psi - 8.103647e-07) <= 1e-12
    assert report.drifted is False
    lower = with_values(length_shares=shares, reference_oov_rate=0.39)
    assert ReferenceDriftDetector(lower, vocabulary).compare(texts, SHA, NOW).drifted is True


def test_drift_no_tokens_gives_zero_oov() -> None:
    assert detector().compare(["a b"], SHA, NOW).oov_rate == 0.0


INVALID_REFERENCES: list[dict[str, object]] = [
    {key: value for key, value in UNIFORM.items() if key != "length_edges"},
    with_values(length_edges=[10, 20, 30, 40, 50, 60, 70, 80]),
    with_values(length_edges=[90, 80, 70, 60, 50, 40, 30, 20, 10]),
    with_values(length_shares=[0.0] + [0.1] * 8 + [0.2]),
    with_values(length_shares=[0.09] * 10),
    with_values(length_edges=[True, 20, 30, 40, 50, 60, 70, 80, 90]),
    with_values(length_shares=[True] + [0.1] * 9),
    with_values(reference_oov_rate=True),
    with_values(reference_oov_rate=1.5),
]


@pytest.mark.parametrize("reference", INVALID_REFERENCES)
def test_drift_rejects_invalid_reference(reference: dict[str, object]) -> None:
    with pytest.raises(ModelIntegrityError) as error:
        ReferenceDriftDetector(reference, frozenset())
    assert error.value.detail == "reference stats are invalid"


@pytest.mark.parametrize("count", [0, 5001])
def test_drift_rejects_invalid_texts_count(count: int) -> None:
    with pytest.raises(InvalidInputError) as error:
        detector().compare(["texto"] * count, SHA, NOW)
    assert error.value.detail == "texts must hold 1 to 5000 items"


def test_drift_rejects_invalid_sha() -> None:
    with pytest.raises(InvalidInputError):
        detector().compare(["texto"], "XYZ", NOW)


def test_drift_report_fields() -> None:
    report = detector().compare(CONTRACT_TEXTS, SHA, NOW)
    assert report.body_sha256 == SHA
    assert report.created_at == NOW
    assert report.reference_oov_rate == 0.2
