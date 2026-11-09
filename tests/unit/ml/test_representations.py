"""Tests for the constants and the TF-IDF representations of ml/representations.py."""

from __future__ import annotations

import numpy as np
import pytest

from api.domain.errors import InvalidInputError
from ml.representations import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_REVISION,
    REPRESENTATIONS,
    SVD_COMPONENTS,
    build_representation,
)

SVD_TEXTS = [f"palabra{i} palabra{i + 1} comun" for i in range(120)]


def test_constants() -> None:
    assert REPRESENTATIONS == ("tfidf", "tfidf_svd", "embeddings")
    assert EMBEDDING_REVISION == "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
    assert len(EMBEDDING_REVISION) == 40
    assert EMBEDDING_DIMENSIONS == 384
    assert SVD_COMPONENTS == 100


def test_build_representation_tfidf() -> None:
    first = build_representation("tfidf")
    params = first.get_params()
    assert params["ngram_range"] == (1, 2)
    assert params["sublinear_tf"] is True
    assert params["min_df"] == 2
    assert build_representation("tfidf") is not first


def test_build_representation_tfidf_svd_vector() -> None:
    representation = build_representation("tfidf_svd")
    output = representation.fit_transform(SVD_TEXTS)
    assert output.shape == (120, 100)
    assert np.allclose(np.linalg.norm(output, axis=1), 1.0, atol=1e-6)
    assert [name for name, _ in representation.steps] == ["tfidf", "svd", "normalize"]
    assert representation.named_steps["svd"].random_state == 42


def test_build_representation_tfidf_svd_few_terms() -> None:
    with pytest.raises(ValueError, match=r"n_components\(100\) must be <= n_features\(20\)"):
        build_representation("tfidf_svd").fit_transform(SVD_TEXTS[:20])


def test_build_representation_rejects_unknown() -> None:
    with pytest.raises(InvalidInputError) as info:
        build_representation("bow")
    assert info.value.detail == "unknown representation: bow"
