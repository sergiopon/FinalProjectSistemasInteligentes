"""Constants and typed dictionaries shared by every ml module (docs/contracts.md sections 8, 9)."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Final, TypedDict

from api.domain.entities import ASPECT_ORDER, AspectGroup, Polarity

SEED: Final[int] = 42
BUNDLE_SCHEMA_VERSION: Final[int] = 1

RAW_COLUMNS: Final[tuple[str, ...]] = (
    "id",
    "curso",
    "feedback",
    "polaridad_basica",
    "grano_fino",
    "emocion",
    "aspectos",
    "semestre",
)

POLARITY_RAW_MAP: Final[Mapping[str, Polarity]] = MappingProxyType(
    {
        "negativo": Polarity.NEGATIVE,
        "neutral": Polarity.NEUTRAL,
        "positivo": Polarity.POSITIVE,
        "positiva": Polarity.POSITIVE,
        "posicion": Polarity.POSITIVE,
    }
)

ASPECT_LABEL_TO_GROUP: Final[Mapping[str, AspectGroup]] = MappingProxyType(
    {
        "contenidos": AspectGroup.CONTENT,
        "Contenido y pertinencia": AspectGroup.CONTENT,
        "cantidad de temasrepaso al inicio del curso": AspectGroup.CONTENT,
        "parciales": AspectGroup.ASSESSMENT,
        "dificultad de las preguntas en los parciales": AspectGroup.ASSESSMENT,
        "Diseño de la evaluación y criterios": AspectGroup.ASSESSMENT,
        "retroalimentación de los examenes": AspectGroup.FEEDBACK,
        "Retroalimentación recibida": AspectGroup.FEEDBACK,
        "comentarios del profesor": AspectGroup.FEEDBACK,
        "metodología del profesor": AspectGroup.METHODOLOGY_CLARITY,
        "Actividades y metodología": AspectGroup.METHODOLOGY_CLARITY,
        "Claridad de exposición": AspectGroup.METHODOLOGY_CLARITY,
        "material de clase": AspectGroup.MATERIALS,
        "diseño de las diapositivas": AspectGroup.MATERIALS,
        "organización del curso y su planeación": AspectGroup.ORGANIZATION_SCHEDULE,
        "horario": AspectGroup.ORGANIZATION_SCHEDULE,
        "disponibilidad de los recursos en el aula digital": AspectGroup.PLATFORM,
        "Soporte técnico y plataforma": AspectGroup.PLATFORM,
        "respuesta oportuna a los correos": AspectGroup.COMMUNICATION_CLIMATE,
        "Clima de aula e interacción": AspectGroup.COMMUNICATION_CLIMATE,
        "carga_académica": AspectGroup.WORKLOAD_PACE,
        "Ritmo y carga de trabajo": AspectGroup.WORKLOAD_PACE,
    }
)

CLEAN_COLUMNS: Final[tuple[str, ...]] = (
    "row_key",
    "source_file",
    "source_id",
    "course",
    "semester",
    "text",
    "polarity",
    *(f"aspect_{group.value}" for group in ASPECT_ORDER),
)


class EmbeddingInfo(TypedDict):
    """Embedding model recorded in a manifest."""

    model_name: str
    revision: str


class ManifestMetrics(TypedDict):
    """Headline metrics recorded in a manifest."""

    test_macro_f1: float
    empirical_coverage: float


class SmokeCheck(TypedDict):
    """Synthetic texts and the probabilities the bundle gave them at build time."""

    texts: list[str]
    probabilities: list[list[float]]


class Manifest(TypedDict):
    """Content of models/vNNN/manifest.json."""

    version: str
    created_at: str
    bundle_sha256: str
    dataset_sha256: str
    python_version: str
    library_versions: dict[str, str]
    embedding: EmbeddingInfo
    polarity_model: str
    representation: str
    best_params: dict[str, object]
    confidence_level: float
    seed: int
    metrics: ManifestMetrics
    smoke: SmokeCheck


class Registry(TypedDict):
    """Content of models/registry.json."""

    active: str
    history: list[str]


class SplitInfo(TypedDict):
    """Sizes of the grouped train/test split."""

    train_rows: int
    test_rows: int
    groups: int


class Report(TypedDict):
    """Content of models/vNNN/report.json."""

    selection: list[dict[str, object]]
    test: dict[str, object]
    per_file_macro_f1: dict[str, float]
    conformal: dict[str, float]
    risk_coverage: list[tuple[float, float]]
    aspects: dict[str, object]
    topics: list[dict[str, object]]
    split: SplitInfo
    test_row_keys: list[str]


class ReferenceStats(TypedDict):
    """Content of models/vNNN/reference_stats.json, used by drift detection."""

    length_edges: list[int]
    length_shares: list[float]
    reference_oov_rate: float
    class_shares: list[float]
