"""Ports for the trained models: store, polarity, aspects and explainer."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from api.domain.entities import AspectScores, ClassProbabilities, ConformalSet, WordInfluence
from api.domain.reports import ModelInfo


class ModelStore(Protocol):
    """Gives access to the verified active model bundle."""

    def info(self) -> ModelInfo:
        """Return the metadata of the active model.

        Preconditions:
            None.

        Postconditions:
            The `ModelInfo` of the active version, already verified.

        Raises:
            `ModelUnavailableError`: no verified active version.
        """
        ...

    def bundle(self) -> Mapping[str, object]:
        """Return the verified bundle dictionary.

        Preconditions:
            None.

        Postconditions:
            The verified bundle dictionary with the keys of docs/contracts.md §9.1.

        Raises:
            `ModelUnavailableError`: no verified active version.
        """
        ...


class PolarityModel(Protocol):
    """Predicts polarity probabilities and conformal prediction sets."""

    def predict_proba(self, texts: Sequence[str]) -> tuple[ClassProbabilities, ...]:
        """Return class probabilities for each text.

        Preconditions:
            `texts` holds 1 to 5000 items and every item is non-empty after `strip()`.

        Postconditions:
            One `ClassProbabilities` per text, same length and order as `texts`.

        Raises:
            `InferenceError`: the model fails.
        """
        ...

    def predict_set(self, texts: Sequence[str]) -> tuple[ConformalSet, ...]:
        """Return the conformal set for each text.

        Preconditions:
            `texts` holds 1 to 5000 items and every item is non-empty after `strip()`.

        Postconditions:
            One `ConformalSet` per text, same length and order. `confidence_level` equals the
            manifest value.

        Raises:
            `InferenceError`: the model fails.
        """
        ...


class AspectModel(Protocol):
    """Detects the aspect groups mentioned in a text."""

    def detect(self, texts: Sequence[str]) -> tuple[AspectScores, ...]:
        """Return aspect scores for each text.

        Preconditions:
            `texts` holds 1 to 5000 items and every item is non-empty after `strip()`.

        Postconditions:
            One `AspectScores` per text, same order. `present` holds the groups whose score is >=
            the bundle threshold of that group.

        Raises:
            `InferenceError`: the model fails.
        """
        ...


class Explainer(Protocol):
    """Explains a polarity prediction with word influences."""

    def explain(self, text: str, top_k: int) -> tuple[WordInfluence, ...]:
        """Return the most influential words of a text.

        Preconditions:
            `text` is non-empty after `strip()`. `top_k` is in 1..20.

        Postconditions:
            At most `top_k` items sorted by `abs(delta)` descending, then `word` ascending.

        Raises:
            `InferenceError`: the model fails.
        """
        ...
