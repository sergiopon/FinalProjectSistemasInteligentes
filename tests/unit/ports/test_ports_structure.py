"""Structural tests for the ports of api/ports/."""

from __future__ import annotations

import inspect

import pytest

from api.ports.models import AspectModel, Explainer, ModelStore, PolarityModel
from api.ports.monitoring import DriftDetector, MetricsStore
from api.ports.text import Anonymizer, Summarizer, TopicModel

PORTS: tuple[type, ...] = (
    ModelStore,
    PolarityModel,
    AspectModel,
    Explainer,
    Anonymizer,
    Summarizer,
    TopicModel,
    DriftDetector,
    MetricsStore,
)

PORT_METHODS: dict[type, frozenset[str]] = {
    ModelStore: frozenset({"info", "bundle"}),
    PolarityModel: frozenset({"predict_proba", "predict_set"}),
    AspectModel: frozenset({"detect"}),
    Explainer: frozenset({"explain"}),
    Anonymizer: frozenset({"mask"}),
    Summarizer: frozenset({"summarize"}),
    TopicModel: frozenset({"assign", "terms"}),
    DriftDetector: frozenset({"compare"}),
    MetricsStore: frozenset({"record", "record_drift", "snapshot"}),
}

SIGNATURES: tuple[tuple[type, str, str], ...] = (
    (ModelStore, "info", "(self) -> 'ModelInfo'"),
    (ModelStore, "bundle", "(self) -> 'Mapping[str, object]'"),
    (
        PolarityModel,
        "predict_proba",
        "(self, texts: 'Sequence[str]') -> 'tuple[ClassProbabilities, ...]'",
    ),
    (
        PolarityModel,
        "predict_set",
        "(self, texts: 'Sequence[str]') -> 'tuple[ConformalSet, ...]'",
    ),
    (AspectModel, "detect", "(self, texts: 'Sequence[str]') -> 'tuple[AspectScores, ...]'"),
    (
        Explainer,
        "explain",
        "(self, text: 'str', top_k: 'int') -> 'tuple[WordInfluence, ...]'",
    ),
    (Anonymizer, "mask", "(self, text: 'str') -> 'str'"),
    (Summarizer, "summarize", "(self, texts: 'Sequence[str]', k: 'int') -> 'tuple[str, ...]'"),
    (TopicModel, "assign", "(self, texts: 'Sequence[str]') -> 'tuple[int, ...]'"),
    (TopicModel, "terms", "(self, topic: 'int') -> 'tuple[str, ...]'"),
    (
        DriftDetector,
        "compare",
        "(self, texts: 'Sequence[str]', body_sha256: 'str', created_at: 'str') -> 'DriftReport'",
    ),
    (
        MetricsStore,
        "record",
        "(self, route: 'str', latency_ms: 'float', decisions: 'Sequence[Decision]') -> 'None'",
    ),
    (MetricsStore, "record_drift", "(self, report: 'DriftReport') -> 'None'"),
    (MetricsStore, "snapshot", "(self) -> 'MetricsSnapshot'"),
)


@pytest.mark.parametrize("port", PORTS, ids=lambda port: port.__name__)
def test_port_is_not_runtime_checkable(port: type) -> None:
    with pytest.raises(TypeError, match="runtime_checkable"):
        isinstance(object(), port)


@pytest.mark.parametrize("port", PORTS, ids=lambda port: port.__name__)
def test_port_exposes_exactly_contract_methods(port: type) -> None:
    names = {
        name
        for name, value in vars(port).items()
        if inspect.isfunction(value) and not name.startswith("_")
    }
    assert names == PORT_METHODS[port]


@pytest.mark.parametrize(
    ("port", "method", "expected"),
    SIGNATURES,
    ids=lambda value: value if isinstance(value, str) else value.__name__,
)
def test_port_method_signature(port: type, method: str, expected: str) -> None:
    assert str(inspect.signature(getattr(port, method))) == expected


@pytest.mark.parametrize(
    ("port", "method"),
    [(port, method) for port, method, _ in SIGNATURES],
    ids=lambda value: value if isinstance(value, str) else value.__name__,
)
def test_port_method_documents_contract(port: type, method: str) -> None:
    doc = inspect.getdoc(getattr(port, method))
    assert doc is not None
    positions = [doc.find(section) for section in ("Preconditions:", "Postconditions:", "Raises:")]
    assert -1 not in positions
    assert positions == sorted(positions)
