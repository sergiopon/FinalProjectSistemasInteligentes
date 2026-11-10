"""Synthetic model versions for the tests of api/adapters/model_store.py (spec 017)."""

from __future__ import annotations

import hashlib
import json
from importlib.metadata import version as installed_version
from pathlib import Path

import joblib

from api.domain.entities import ASPECT_ORDER

LIBRARIES = ("scikit-learn", "numpy", "joblib", "mapie")


def fake_bundle() -> dict[str, object]:
    """Return a bundle with the 10 keys of docs/contracts.md section 9.1 and stub parts."""
    return {
        "schema_version": 1,
        "class_order": ("negative", "neutral", "positive"),
        "aspect_order": tuple(group.value for group in ASPECT_ORDER),
        "polarity_pipeline": "placeholder",
        "conformal_classifier": "placeholder",
        "aspect_pipeline": "placeholder",
        "aspect_thresholds": (0.5,) * 9,
        "topic_vectorizer": "placeholder",
        "topic_kmeans": "placeholder",
        "topic_terms": (("alpha", "beta", "gamma", "delta", "epsilon"),),
    }


def fake_manifest(version: str, bundle_sha256: str) -> dict[str, object]:
    """Return a manifest of docs/contracts.md section 9.2 with the installed library versions."""
    return {
        "version": version,
        "created_at": "2026-11-10T12:00:00Z",
        "bundle_sha256": bundle_sha256,
        "dataset_sha256": "a" * 64,
        "library_versions": {name: installed_version(name) for name in LIBRARIES},
        "polarity_model": "logistic_regression",
        "representation": "tfidf",
        "confidence_level": 0.9,
        "metrics": {"test_macro_f1": 0.61, "empirical_coverage": 0.9},
    }


def _sha256(path: Path) -> str:
    with path.open("rb") as file:
        return hashlib.file_digest(file, "sha256").hexdigest()


def write_fake_version(models_dir: Path, version: str, bundle: object | None = None) -> Path:
    """Write models_dir/version with a dumped bundle and a manifest holding its real hash."""
    version_dir = models_dir / version
    version_dir.mkdir(parents=True)
    joblib.dump(fake_bundle() if bundle is None else bundle, version_dir / "bundle.joblib")
    manifest = fake_manifest(version, _sha256(version_dir / "bundle.joblib"))
    (version_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return version_dir


def replace_bundle_bytes(version_dir: Path, content: bytes) -> None:
    """Overwrite the bundle with content and rewrite the manifest with the matching hash."""
    (version_dir / "bundle.joblib").write_bytes(content)
    manifest = fake_manifest(version_dir.name, hashlib.sha256(content).hexdigest())
    (version_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def write_registry(models_dir: Path, active: str, history: list[str]) -> None:
    """Write models_dir/registry.json."""
    registry = {"active": active, "history": history}
    (models_dir / "registry.json").write_text(json.dumps(registry), encoding="utf-8")
