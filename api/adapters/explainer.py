"""Word influence explainer that occludes one word at a time."""

from __future__ import annotations

import re
from typing import Final

from api.domain.entities import WordInfluence
from api.domain.errors import InvalidInputError
from api.ports.models import PolarityModel

WORD_PATTERN: Final[re.Pattern[str]] = re.compile(r"\w+")
MIN_TOP_K: Final[int] = 1
MAX_TOP_K: Final[int] = 20
_WHITESPACE_RUN: Final[re.Pattern[str]] = re.compile(r"\s+")


def _occlude(text: str, word: str) -> str:
    """Remove every occurrence of the word, ignoring case, and tidy the whitespace."""
    kept = WORD_PATTERN.sub(
        lambda match: "" if match.group().lower() == word else match.group(), text
    )
    return _WHITESPACE_RUN.sub(" ", kept).strip()


class OcclusionExplainer:
    """Explains the top polarity by measuring how much removing each word lowers its probability."""

    def __init__(self, model: PolarityModel) -> None:
        """Keep the polarity model that is queried.

        Args:
            model: Polarity model used to score the occluded texts.
        """
        self._model = model

    def explain(self, text: str, top_k: int) -> tuple[WordInfluence, ...]:
        """Return the most influential words of a text.

        Args:
            text: Comment text, not blank.
            top_k: Number of words to return, from 1 to 20.

        Returns:
            At most `top_k` items sorted by `abs(delta)` descending, then `word` ascending.

        Raises:
            InvalidInputError: `top_k` is out of range or the text is blank.
            InferenceError: The polarity model fails.
        """
        if not MIN_TOP_K <= top_k <= MAX_TOP_K:
            raise InvalidInputError("top_k must be between 1 and 20")
        if text.strip() == "":
            raise InvalidInputError("text must be non-empty after strip")
        words = dict.fromkeys(match.lower() for match in WORD_PATTERN.findall(text))
        occluded = {word: _occlude(text, word) for word in words}
        pairs = [(word, variant) for word, variant in occluded.items() if variant != ""]
        if not pairs:
            return ()
        probabilities = self._model.predict_proba([text, *(variant for _, variant in pairs)])
        top = probabilities[0].top()
        base = probabilities[0].of(top)
        influences = [
            WordInfluence(word, base - probabilities[index].of(top))
            for index, (word, _) in enumerate(pairs, start=1)
        ]
        influences.sort(key=lambda item: (-abs(item.delta), item.word))
        return tuple(influences[:top_k])
