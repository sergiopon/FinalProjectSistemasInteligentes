"""Tests for SpacyAnonymizer in api/adapters/anonymizer.py."""

from __future__ import annotations

import pytest
import spacy

from api.adapters.anonymizer import SpacyAnonymizer
from api.domain.errors import AnonymizerUnavailableError


@pytest.fixture(scope="module")
def anonymizer() -> SpacyAnonymizer:
    return SpacyAnonymizer()


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Escribir a ana.gomez@uni.edu.co o al 300 123 4567, código 20231045",
            "Escribir a [EMAIL] o al [PHONE], código [ID]",
        ),
        ("El profesor Juan Pérez explica muy bien.", "El profesor [PERSON] explica muy bien."),
        (
            "Le escribí a Carlos Ramírez a carlos.ramirez@correo.com y no contestó.",
            "Le escribí a [PERSON] a [EMAIL] y no contestó.",
        ),
        ("Juan Pérez y Ana Gómez llegaron tarde.", "[PERSON] y [PERSON] llegaron tarde."),
        (
            "Mi código es 1234567 y mi celular es 3001234567.",
            "Mi código es [ID] y mi celular es [ID].",
        ),
        (
            "El contenido fue claro, pero los parciales fueron difíciles.",
            "El contenido fue claro, pero los parciales fueron difíciles.",
        ),
        ("", ""),
        (
            "Además, el curso fue bueno y también útil.",
            "Además, el curso fue bueno y también útil.",
        ),
        ("Profesor, gracias por todo el semestre.", "Profesor, gracias por todo el semestre."),
        (
            "Me encontré con muchas dudas en los parciales.",
            "Me encontré con muchas dudas en los parciales.",
        ),
    ],
)
def test_anonymizer_masks(anonymizer: SpacyAnonymizer, text: str, expected: str) -> None:
    assert anonymizer.mask(text) == expected


def test_anonymizer_missing_model_fails() -> None:
    with pytest.raises(AnonymizerUnavailableError) as info:
        SpacyAnonymizer("xx_missing_model")
    assert info.value.detail == "spaCy model failed to load"
    assert isinstance(info.value.__cause__, OSError)


def test_anonymizer_without_ner_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_load(name: str, **kwargs: object) -> spacy.language.Language:
        return spacy.blank("es")

    monkeypatch.setattr(spacy, "load", fake_load)
    with pytest.raises(AnonymizerUnavailableError) as info:
        SpacyAnonymizer()
    assert info.value.detail == "spaCy model has no ner component"
