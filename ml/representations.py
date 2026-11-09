"""Text representations for model selection and the embedding download command (spec 009)."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Callable, Sequence
from typing import Final

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import Normalizer

from api.domain.errors import AppError, InferenceError, InvalidInputError
from ml.schemas import SEED

logger = logging.getLogger(__name__)

EMBEDDING_MODEL_NAME: Final[str] = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
EMBEDDING_REVISION: Final[str] = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"
EMBEDDING_DIMENSIONS: Final[int] = 384
EMBEDDING_BATCH_SIZE: Final[int] = 32
SVD_COMPONENTS: Final[int] = 100
REPRESENTATIONS: Final[tuple[str, ...]] = ("tfidf", "tfidf_svd", "embeddings")


class _ModelSlot:
    """Holder of one loaded model, shared by a transformer and every clone of it.

    It drops the model when copied or persisted, so weights never travel (ADR-003). Transformers
    copied or persisted in one object graph keep sharing one slot.
    """

    def __init__(self) -> None:
        self.model: SentenceTransformer | None = None

    def __getstate__(self) -> dict[str, object]:
        """Return an empty state: the model is reloaded from the local cache when needed."""
        return {"model": None}


class EmbeddingTransformer(BaseEstimator, TransformerMixin):  # type: ignore[misc]
    """Scikit-learn transformer that encodes texts with a pre-trained sentence-transformers model.

    The model loads lazily from the local cache at a pinned revision and is never copied or
    persisted with the transformer (ADR-003). ``sklearn.base.clone`` returns a twin that shares
    the loaded model, so cross-validation and conformal folds hold one copy in memory.

    Args:
        model_name: Hugging Face model id.
        revision: Pinned commit of the model.
    """

    def __init__(self, model_name: str, revision: str) -> None:
        self.model_name = model_name
        self.revision = revision
        self._slot = _ModelSlot()

    @property
    def _model(self) -> SentenceTransformer | None:
        """The loaded model, or ``None`` before the first ``transform``."""
        return self._slot.model

    def __sklearn_clone__(self) -> EmbeddingTransformer:
        """Return an unfitted twin with the same parameters that shares this model slot."""
        twin = EmbeddingTransformer(self.model_name, self.revision)
        twin._slot = self._slot
        return twin

    def fit(self, X: Sequence[str], y: object = None) -> EmbeddingTransformer:
        """Return the transformer unchanged: the model is pre-trained and learns nothing here.

        Args:
            X: Texts, ignored.
            y: Targets, ignored.

        Returns:
            This transformer.
        """
        return self

    def transform(self, X: Sequence[str]) -> np.ndarray:
        """Encode texts into L2-normalized embeddings.

        Args:
            X: Texts to encode.

        Returns:
            A ``float32`` array of shape ``(len(X), EMBEDDING_DIMENSIONS)`` with unit-norm rows.

        Raises:
            InvalidInputError: ``X`` is empty.
            InferenceError: The model is not cached, or its output is not an array of the
                expected shape.
        """
        if len(X) == 0:
            raise InvalidInputError("transform needs at least 1 text")
        output = self._load_model().encode(
            list(X),
            batch_size=EMBEDDING_BATCH_SIZE,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        if not isinstance(output, np.ndarray):
            raise InferenceError("embedding output is not an array")
        embeddings = output.astype(np.float32)
        if embeddings.shape != (len(X), EMBEDDING_DIMENSIONS):
            raise InferenceError("embedding output has an unexpected shape")
        return embeddings

    def _load_model(self) -> SentenceTransformer:
        """Load the model from the local cache on first use and keep it."""
        if self._slot.model is None:
            try:
                self._slot.model = SentenceTransformer(
                    self.model_name, revision=self.revision, local_files_only=True, device="cpu"
                )
            except OSError as error:
                raise InferenceError("embedding model is not in the local cache") from error
            logger.info("embedding_model_loaded revision=%s", self.revision)
        return self._slot.model


def build_representation(name: str) -> TransformerMixin:
    """Build a new, unfitted text representation.

    Args:
        name: One of ``REPRESENTATIONS``.

    Returns:
        A scikit-learn transformer that maps texts to a feature matrix.

    Raises:
        InvalidInputError: ``name`` is not a known representation.
    """
    factories: dict[str, Callable[[], TransformerMixin]] = {
        "tfidf": _tfidf,
        "tfidf_svd": _tfidf_svd,
        "embeddings": _embeddings,
    }
    factory = factories.get(name)
    if factory is None:
        raise InvalidInputError(f"unknown representation: {name}")
    return factory()


def download(model_name: str, revision: str) -> None:
    """Download the embedding model into the local cache (the only network access, SEC-17).

    Args:
        model_name: Hugging Face model id.
        revision: Pinned commit of the model.

    Raises:
        InferenceError: The download failed.
    """
    try:
        SentenceTransformer(model_name, revision=revision, device="cpu")
    except OSError as error:
        raise InferenceError("embedding model download failed") from error
    logger.info("embedding_downloaded revision=%s", revision)


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point: ``python -m ml.representations --download``.

    Args:
        argv: Arguments without the program name; ``None`` reads ``sys.argv``.

    Returns:
        ``0`` on success, ``2`` on an application error, ``1`` on any other error.
    """
    os.umask(0o077)
    parser = argparse.ArgumentParser(prog="ml.representations")
    parser.add_argument("--download", action="store_true", required=True)
    parser.parse_args(argv)
    try:
        download(EMBEDDING_MODEL_NAME, EMBEDDING_REVISION)
    except AppError as error:
        print(f"error={error.code}", file=sys.stderr)
        return 2
    except Exception:
        logger.exception("representations_command_failed")
        print("error=internal_error", file=sys.stderr)
        return 1
    print(f"downloaded={EMBEDDING_REVISION}")
    return 0


def _tfidf() -> TfidfVectorizer:
    """Word 1-2 gram TF-IDF."""
    return TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=2)


def _tfidf_svd() -> Pipeline:
    """Word TF-IDF reduced by truncated SVD, then L2-normalized."""
    return Pipeline(
        [
            ("tfidf", _tfidf()),
            ("svd", TruncatedSVD(n_components=SVD_COMPONENTS, random_state=SEED)),
            ("normalize", Normalizer()),
        ]
    )


def _embeddings() -> EmbeddingTransformer:
    """Multilingual sentence embeddings at the pinned revision."""
    return EmbeddingTransformer(EMBEDDING_MODEL_NAME, EMBEDDING_REVISION)


if __name__ == "__main__":
    raise SystemExit(main())
