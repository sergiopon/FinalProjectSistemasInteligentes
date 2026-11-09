"""Integration tests of the embedding representation with the real cached model (no network).

Needs the model cached by ``.venv/bin/python -m ml.representations --download``.
"""

from __future__ import annotations

import numpy as np
import pytest

from ml.representations import build_representation

pytestmark = pytest.mark.integration

TEXTS = ["El curso fue claro.", "Las diapositivas llegaron tarde."]


def test_embeddings_shape_and_norm() -> None:
    output = build_representation("embeddings").fit_transform(TEXTS)
    assert output.shape == (2, 384)
    assert output.dtype == np.float32
    assert np.allclose(np.linalg.norm(output, axis=1), 1.0, atol=1e-5)


def test_embeddings_deterministic() -> None:
    first = build_representation("embeddings").fit_transform(TEXTS)
    second = build_representation("embeddings").fit_transform(TEXTS)
    assert np.allclose(first, second, atol=1e-6)
