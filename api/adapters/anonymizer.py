"""Anonymizer adapter: contact data through the domain helper and person names through spaCy."""

from __future__ import annotations

import threading
from typing import Final

import spacy
from spacy.tokens import Span

from api.domain.errors import AnonymizerUnavailableError
from api.domain.safety import mask_contact_data

DEFAULT_MODEL: Final = "es_core_news_sm"
PERSON_LABEL: Final = "PER"
PERSON_MASK: Final = "[PERSON]"
PROPER_NOUN: Final = "PROPN"
ROLE_WORDS: Final[frozenset[str]] = frozenset(
    {"profesor", "profesora", "docente", "maestro", "maestra", "tutor", "tutora"}
)
EXCLUDED_PIPES: Final[tuple[str, ...]] = ("parser", "lemmatizer")


class SpacyAnonymizer:
    """Masks emails, phones, ids and person entities of a Spanish text.

    Args:
        model_name: Installed spaCy pipeline with a ner component.

    Raises:
        AnonymizerUnavailableError: If the pipeline cannot be loaded or has no ner component.
    """

    def __init__(self, model_name: str = DEFAULT_MODEL) -> None:
        try:
            self._nlp = spacy.load(model_name, exclude=EXCLUDED_PIPES)
        except (OSError, ImportError, ValueError) as error:
            raise AnonymizerUnavailableError("spaCy model failed to load") from error
        if "ner" not in self._nlp.pipe_names:
            raise AnonymizerUnavailableError("spaCy model has no ner component")
        self._lock = threading.Lock()

    def mask(self, text: str) -> str:
        """Return the text with contact data and person names masked.

        Args:
            text: Comment text.

        Returns:
            The masked text; a text without matches is returned unchanged.

        Raises:
            AnonymizerUnavailableError: If the language model fails on the text.
        """
        masked = mask_contact_data(text)
        try:
            with self._lock:
                doc = self._nlp(masked)
        except ValueError as error:
            raise AnonymizerUnavailableError("anonymizer failed") from error
        for entity in reversed(doc.ents):
            if _is_person(entity):
                masked = masked[: entity.start_char] + PERSON_MASK + masked[entity.end_char :]
        return masked


def _is_person(entity: Span) -> bool:
    """Keep a PER entity only when every token is a proper noun and it is not a lone role word.

    The small Spanish model tags capitalized sentence openers ("Además", "También") and verbs
    ("encontré") as PER; the part-of-speech check drops them.
    """
    if entity.label_ != PERSON_LABEL or not all(token.pos_ == PROPER_NOUN for token in entity):
        return False
    return not (len(entity) == 1 and entity.text.lower() in ROLE_WORDS)
