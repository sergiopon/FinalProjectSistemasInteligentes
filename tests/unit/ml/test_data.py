"""Tests for ml/schemas.py and the text, polarity and aspect helpers of ml/data.py."""

from __future__ import annotations

import json
from collections import Counter
from typing import cast

import pytest

from api.domain.entities import AspectGroup, Polarity
from api.domain.errors import DatasetError
from ml.data import normalize_polarity, normalize_text, parse_aspects
from ml.schemas import (
    ASPECT_LABEL_TO_GROUP,
    BUNDLE_SCHEMA_VERSION,
    CLEAN_COLUMNS,
    POLARITY_RAW_MAP,
    RAW_COLUMNS,
    SEED,
)


def aspects_json(*pairs: tuple[str, str]) -> str:
    return json.dumps([{"aspecto": label, "sentimiento": sentiment} for label, sentiment in pairs])


def test_schemas_constants() -> None:
    assert SEED == 42
    assert BUNDLE_SCHEMA_VERSION == 1
    assert RAW_COLUMNS == (
        "id",
        "curso",
        "feedback",
        "polaridad_basica",
        "grano_fino",
        "emocion",
        "aspectos",
        "semestre",
    )
    assert CLEAN_COLUMNS == (
        "row_key",
        "source_file",
        "source_id",
        "course",
        "semester",
        "text",
        "polarity",
        "aspect_content",
        "aspect_assessment",
        "aspect_feedback",
        "aspect_methodology_clarity",
        "aspect_materials",
        "aspect_organization_schedule",
        "aspect_platform",
        "aspect_communication_climate",
        "aspect_workload_pace",
    )
    assert len(CLEAN_COLUMNS) == 16
    assert len(ASPECT_LABEL_TO_GROUP) == 22
    content_label = "cantidad de temasrepaso al inicio del curso"
    assert ASPECT_LABEL_TO_GROUP[content_label] is AspectGroup.CONTENT
    assert ASPECT_LABEL_TO_GROUP["carga_académica"] is AspectGroup.WORKLOAD_PACE
    labels_per_group = Counter(ASPECT_LABEL_TO_GROUP.values())
    assert all(labels_per_group[group] >= 2 for group in AspectGroup)


def test_schemas_mappings_are_read_only() -> None:
    with pytest.raises(TypeError):
        cast("dict[str, Polarity]", POLARITY_RAW_MAP)["mixto"] = Polarity.NEUTRAL


def test_normalize_text_collapses_whitespace() -> None:
    assert normalize_text("  El curso\n fue\tbueno  ") == "El curso fue bueno"
    assert normalize_text("muy bueno") == "muy bueno"


def test_normalize_text_applies_nfc() -> None:
    decomposed = "Me gustó"
    assert len(decomposed) == 9
    result = normalize_text(decomposed)
    assert result == "Me gustó"
    assert len(result) == 8


def test_normalize_text_keeps_case_and_intensifiers() -> None:
    assert normalize_text("Muy MUY bastante bueno!") == "Muy MUY bastante bueno!"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("neutral", Polarity.NEUTRAL),
        ("['neutral']", Polarity.NEUTRAL),
        ("negativo", Polarity.NEGATIVE),
        ("['negativo']", Polarity.NEGATIVE),
        ("positivo", Polarity.POSITIVE),
        ("['positivo']", Polarity.POSITIVE),
        ("positiva", Polarity.POSITIVE),
        ("[\"['positivo']\"]", Polarity.POSITIVE),
        ("['posicion']", Polarity.POSITIVE),
        (" Positivo ", Polarity.POSITIVE),
    ],
)
def test_normalize_polarity_raw_values(raw: str, expected: Polarity) -> None:
    assert normalize_polarity(raw) is expected


@pytest.mark.parametrize("raw", ["mixto", ""])
def test_normalize_polarity_rejects_unknown(raw: str) -> None:
    with pytest.raises(DatasetError) as info:
        normalize_polarity(raw)
    assert info.value.detail == "unknown polarity label"


def test_parse_aspects_maps_groups() -> None:
    raw = aspects_json(
        ("horario", "neutral"),
        ("contenidos", "positivo"),
        ("Contenido y pertinencia", "positivo"),
    )
    result = parse_aspects(raw)
    assert result == {
        AspectGroup.CONTENT: Polarity.POSITIVE,
        AspectGroup.ORGANIZATION_SCHEDULE: Polarity.NEUTRAL,
    }
    assert list(result) == [AspectGroup.CONTENT, AspectGroup.ORGANIZATION_SCHEDULE]


def test_parse_aspects_conflict_becomes_neutral() -> None:
    raw = aspects_json(
        ("parciales", "negativo"),
        ("Diseño de la evaluación y criterios", "positivo"),
    )
    assert parse_aspects(raw) == {AspectGroup.ASSESSMENT: Polarity.NEUTRAL}


def test_parse_aspects_empty_list() -> None:
    assert parse_aspects("[]") == {}


@pytest.mark.parametrize(
    ("raw", "detail"),
    [
        ("[{", "aspect list is not valid JSON"),
        ("{}", "aspect list must be a JSON list"),
        ('[{"aspecto": "horario"}]', "aspect entry is malformed"),
        ('["x"]', "aspect entry is malformed"),
        (aspects_json(("comida", "neutral")), "unknown aspect label"),
        (aspects_json(("horario", "positiva")), "unknown aspect sentiment"),
    ],
)
def test_parse_aspects_rejects_bad_input(raw: str, detail: str) -> None:
    with pytest.raises(DatasetError) as info:
        parse_aspects(raw)
    assert info.value.detail == detail
