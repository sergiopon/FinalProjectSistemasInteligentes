"""Ports for text processing: anonymizer, summarizer and topic model."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol


class Anonymizer(Protocol):
    """Masks personal data in a text."""

    def mask(self, text: str) -> str:
        """Return the text with personal data masked.

        Preconditions:
            `text` is a `str`.

        Postconditions:
            Emails, phones, ids and person entities masked as in docs/contracts.md §4.4. A text
            without matches is returned unchanged.

        Raises:
            `AnonymizerUnavailableError`: the language model is not loaded.
        """
        ...


class Summarizer(Protocol):
    """Picks the most representative sentences of a set of texts."""

    def summarize(self, texts: Sequence[str], k: int) -> tuple[str, ...]:
        """Return up to k representative sentences.

        Preconditions:
            `texts` holds 1 to 5000 items and every item is non-empty after `strip()`. `k` is in
            1..10.

        Postconditions:
            At most `k` distinct sentences taken from `texts`, most representative first.

        Raises:
            `InferenceError`: the vectorizer fails.
        """
        ...


class TopicModel(Protocol):
    """Assigns texts to topics and names the topics."""

    def assign(self, texts: Sequence[str]) -> tuple[int, ...]:
        """Return the topic id of each text.

        Preconditions:
            `texts` holds 1 to 5000 items and every item is non-empty after `strip()`.

        Postconditions:
            One topic id in `0..n_topics-1` per text, same order.

        Raises:
            `InferenceError`: the model fails.
        """
        ...

    def terms(self, topic: int) -> tuple[str, ...]:
        """Return the terms that describe a topic.

        Preconditions:
            `topic` is an `int`.

        Postconditions:
            The 5 terms of the trained topic.

        Raises:
            `InvalidInputError`: `topic` is not a trained topic id.
        """
        ...
