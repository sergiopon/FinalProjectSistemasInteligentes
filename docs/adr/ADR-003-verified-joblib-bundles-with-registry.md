# ADR-003 — Verified joblib bundles with a registry

Status: Accepted (2026-11-05)

## Context

The guide requires saving the full pipeline with joblib, loading only trusted files, keeping scikit-learn versions
aligned, versioning and rollback, and never retraining on startup. `joblib.load` executes code from the file.

## Decision

1. `ml.artifact` writes one directory per version, `models/vNNN/` (`NNN` = previous maximum + 1, starting at
   `v001`), containing `bundle.joblib`, `manifest.json`, `report.json` and `reference_stats.json`
   (`docs/contracts.md` §9).
2. `manifest.json` records the SHA-256 of `bundle.joblib`, the dataset SHA-256, the Python version, library versions,
   the embedding model name and revision, the selected model, metrics and synthetic smoke-test predictions.
3. `models/registry.json` holds `active` and an activation `history` stack; `activate` pushes, `rollback` pops.
4. `api/adapters/model_store.py` (`TrustedModelStore`) loads only the active version after the SEC-14 checks; a
   mismatch raises `ModelIntegrityError` and the process exits. The API never trains.
5. Embedding weights are not in the bundle: the bundle stores model name and revision, and sentence-transformers
   loads them from the local cache with `local_files_only=True` (SEC-15).

## Consequences

- `joblib.load` appears only in `api/adapters/model_store.py` and `ml/artifact.py` (SEC-14 grep).
- `bundle.joblib` is not versioned (SEC-10); `manifest.json`, `report.json` and `reference_stats.json` hold no
  comment text, so they can be versioned.
- A library upgrade requires retraining: an old bundle fails the version check.
