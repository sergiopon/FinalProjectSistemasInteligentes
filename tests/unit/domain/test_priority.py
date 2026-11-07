"""Tests for api/domain/priority.py."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from api.domain.entities import AspectGroup
from api.domain.errors import InvalidInputError
from api.domain.priority import MIN_SUPPORT, rank_priorities
from api.domain.reports import AspectCell, PriorityEntry

CONTENT = AspectGroup.CONTENT
ASSESSMENT = AspectGroup.ASSESSMENT


def cell(group: AspectGroup, mentions: int, negative: int) -> AspectCell:
    return AspectCell(group, mentions, negative, 0, mentions - negative)


def _as_tuples(entries: Sequence[PriorityEntry]) -> list[tuple[object, ...]]:
    return [
        (
            entry.rank,
            entry.group,
            entry.mentions,
            entry.negative,
            pytest.approx(entry.prevalence, abs=1e-12),
            pytest.approx(entry.smoothed_negative_share, abs=1e-12),
            pytest.approx(entry.score, abs=1e-12),
            entry.low_support,
        )
        for entry in entries
    ]


def assert_invalid(cells: Sequence[AspectCell], comment_count: int, detail: str) -> None:
    with pytest.raises(InvalidInputError) as info:
        rank_priorities(cells, comment_count)
    assert info.value.detail == detail


def test_rank_priorities_contract_vector() -> None:
    cells = (
        cell(CONTENT, 40, 10),
        cell(ASSESSMENT, 10, 8),
        cell(AspectGroup.PLATFORM, 2, 2),
        cell(AspectGroup.MATERIALS, 0, 0),
    )
    expected = [
        (1, CONTENT, 40, 10, 0.4, 0.2619047619047619, 0.10476190476190478, False),
        (2, ASSESSMENT, 10, 8, 0.1, 0.75, 0.07500000000000001, False),
        (3, AspectGroup.PLATFORM, 2, 2, 0.02, 0.75, 0.015, True),
    ]
    assert expected == _as_tuples(rank_priorities(cells, 100))


def test_rank_priorities_tie_follows_aspect_order() -> None:
    cells = (cell(AspectGroup.MATERIALS, 5, 1), cell(AspectGroup.FEEDBACK, 5, 1))
    expected = [
        (1, AspectGroup.FEEDBACK, 5, 1, 0.1, 0.2857142857142857, 0.02857142857142857, False),
        (2, AspectGroup.MATERIALS, 5, 1, 0.1, 0.2857142857142857, 0.02857142857142857, False),
    ]
    assert expected == _as_tuples(rank_priorities(cells, 50))


def test_rank_priorities_full_prevalence() -> None:
    cells = (cell(AspectGroup.WORKLOAD_PACE, 3, 3),)
    expected = [(1, AspectGroup.WORKLOAD_PACE, 3, 3, 1.0, 0.8, 0.8, True)]
    assert expected == _as_tuples(rank_priorities(cells, 3))


def test_rank_priorities_low_support_boundary() -> None:
    cells = (cell(CONTENT, 4, 0), cell(ASSESSMENT, 5, 0))
    expected = [
        (1, ASSESSMENT, 5, 0, 0.25, 0.14285714285714285, 0.03571428571428571, False),
        (2, CONTENT, 4, 0, 0.2, 0.16666666666666666, 0.03333333333333333, True),
    ]
    assert expected == _as_tuples(rank_priorities(cells, 20))


def test_rank_priorities_all_zero_mentions() -> None:
    assert rank_priorities((cell(CONTENT, 0, 0),), 10) == ()


def test_rank_priorities_empty_cells() -> None:
    assert rank_priorities((), 10) == ()


@pytest.mark.parametrize("comment_count", [0, -1])
def test_rank_priorities_rejects_comment_count(comment_count: int) -> None:
    assert_invalid((), comment_count, "comment_count must be >= 1")


def test_rank_priorities_rejects_mentions_above_count() -> None:
    assert_invalid((cell(CONTENT, 11, 0),), 10, "mentions must not exceed comment_count")


def test_rank_priorities_rejects_duplicate_group() -> None:
    cells = (cell(CONTENT, 1, 0), cell(CONTENT, 2, 1))
    assert_invalid(cells, 10, "duplicate aspect group")


def test_min_support_value() -> None:
    assert MIN_SUPPORT == 5
