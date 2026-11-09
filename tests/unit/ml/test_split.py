"""Tests for ml/split.py."""

from __future__ import annotations

import logging

import numpy as np
import pytest

from api.domain.errors import InvalidInputError
from ml.split import cv_splitter, grouped_split, template_groups

T5 = [
    "El curso fue bastante bueno y claro.",
    "El curso fue bastante bueno y muy claro.",
    "Las diapositivas llegaron tarde siempre.",
    "Las diapositivas llegaron tarde casi siempre.",
    "Horario incomodo los lunes por la noche.",
]
VECTOR_Y = np.arange(30) % 3
VECTOR_GROUPS = np.arange(30) // 3
VECTOR_TEST = [6, 7, 8, 24, 25, 26]


def assert_invalid(detail: str, info: pytest.ExceptionInfo[InvalidInputError]) -> None:
    assert info.value.detail == detail


def test_template_groups_partitions_templates() -> None:
    labels = template_groups(T5)
    assert labels[0] == labels[1]
    assert labels[2] == labels[3]
    assert len({labels[0], labels[2], labels[4]}) == 3
    assert len(set(labels.tolist())) == 3
    assert labels.dtype == np.int64
    assert len(labels) == 5


def test_template_groups_is_deterministic() -> None:
    assert np.array_equal(template_groups(T5), template_groups(T5))


def test_template_groups_two_distinct_texts() -> None:
    labels = template_groups([T5[0], T5[4]])
    assert len(set(labels.tolist())) == 2


@pytest.mark.parametrize("texts", [[], [T5[0]], [""]])
def test_template_groups_rejects_too_few(texts: list[str]) -> None:
    with pytest.raises(InvalidInputError) as info:
        template_groups(texts)
    assert_invalid("template_groups needs at least 2 texts", info)


@pytest.mark.parametrize("texts", [[T5[0], ""], [T5[0], "   "]])
def test_template_groups_rejects_blank(texts: list[str]) -> None:
    with pytest.raises(InvalidInputError) as info:
        template_groups(texts)
    assert_invalid("template_groups texts must not be blank", info)


def test_template_groups_logs_counts(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        template_groups(T5)
    messages = [record.getMessage() for record in caplog.records]
    assert "template_groups rows=5 groups=3 largest=2" in messages
    assert not any("curso" in message for message in messages)


def test_cv_splitter_configuration() -> None:
    splitter = cv_splitter()
    assert splitter.n_splits == 5
    assert splitter.shuffle is True
    assert splitter.random_state == 42
    assert cv_splitter() is not splitter


def test_grouped_split_vector() -> None:
    train_idx, test_idx = grouped_split(VECTOR_Y, VECTOR_GROUPS)
    assert test_idx.tolist() == VECTOR_TEST
    assert train_idx.tolist() == [index for index in range(30) if index not in VECTOR_TEST]
    assert train_idx.dtype == np.int64
    assert test_idx.dtype == np.int64


def test_grouped_split_keeps_groups_apart() -> None:
    train_idx, test_idx = grouped_split(VECTOR_Y, VECTOR_GROUPS)
    train_groups = set(VECTOR_GROUPS[train_idx].tolist())
    test_groups = set(VECTOR_GROUPS[test_idx].tolist())
    assert train_groups.isdisjoint(test_groups)


def test_grouped_split_ignores_group_label_values() -> None:
    train_idx, test_idx = grouped_split(VECTOR_Y, VECTOR_GROUPS)
    shifted_train, shifted_test = grouped_split(VECTOR_Y, VECTOR_GROUPS + 1000)
    assert np.array_equal(train_idx, shifted_train)
    assert np.array_equal(test_idx, shifted_test)


def test_grouped_split_rejects_2d() -> None:
    with pytest.raises(InvalidInputError) as info:
        grouped_split(VECTOR_Y.reshape(30, 1), VECTOR_GROUPS)
    assert_invalid("y and groups must be 1-D arrays", info)


def test_grouped_split_rejects_length_mismatch() -> None:
    with pytest.raises(InvalidInputError) as info:
        grouped_split(VECTOR_Y, VECTOR_GROUPS[:29])
    assert_invalid("y and groups must have the same length", info)


def test_grouped_split_rejects_few_groups() -> None:
    with pytest.raises(InvalidInputError) as info:
        grouped_split(VECTOR_Y, np.arange(30) % 4)
    assert_invalid("groups must hold at least 5 distinct values", info)


def test_grouped_split_rejects_2d_groups() -> None:
    with pytest.raises(InvalidInputError) as info:
        grouped_split(VECTOR_Y, VECTOR_GROUPS.reshape(30, 1))
    assert_invalid("y and groups must be 1-D arrays", info)


def test_grouped_split_checks_shape_before_length() -> None:
    with pytest.raises(InvalidInputError) as info:
        grouped_split(VECTOR_Y.reshape(30, 1), VECTOR_GROUPS[:29])
    assert_invalid("y and groups must be 1-D arrays", info)
