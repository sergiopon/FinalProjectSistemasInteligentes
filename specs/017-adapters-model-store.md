# 017 - Adapters model store
Riesgo: alto

## Objective

`joblib.load` runs code stored in the file, so the service must load only a bundle written by `ml.artifact` and
built with the installed library versions. After this spec `TrustedModelStore` (port `ModelStore`) reads
`models/registry.json`, takes the `active` version, rejects symlinks and paths that leave `models/`, checks the
manifest, the 4 library versions and the SHA-256 of `bundle.joblib` before calling `joblib.load`, checks the bundle
shape after it, and raises `ModelIntegrityError` on any mismatch. Every construction repeats every check; nothing is
cached between instances. Rollback is `python -m ml.artifact rollback` (spec 013) followed by a restart: the store
always follows `registry.json`.

## Depends on

006 (`api/ports/models.py`: `ModelStore`), 013 (`ml.artifact` writes `models/vNNN/` and `registry.json`;
`ml.schemas.BUNDLE_SCHEMA_VERSION`), 016. Transitively 002 (`ModelInfo`, `ModelUnavailableError`,
`ModelIntegrityError`, `POLARITY_ORDER`, `ASPECT_ORDER`) and 003 (`resolve_within`, `UnsafePathError`).

## Governing files

- `ARCHITECTURE.md` §2 (adapters may import `ml`), §4 (`ModelStore` → `TrustedModelStore`), §6 (≤ 20 statements per
  function, classes ≤ 150 lines, modules ≤ 300 lines, errors wrapped with `from`, `Any` only at the library boundary).
- `security-rules.md` SEC-12, SEC-13, SEC-14, SEC-15. `docs/adr/ADR-003-verified-joblib-bundles-with-registry.md`.
- `docs/contracts.md` §1.2 (`ModelInfo`), §2, §3 (`ModelStore` rows, `TrustedModelStore(models_dir: Path)`), §9.

## Files to create/modify

1. `api/adapters/model_store.py` (new). Reference pattern: `api/adapters/settings.py` (spec 016).
2. `tests/fixtures/model_bundles.py` (new): synthetic version writer.
3. `tests/unit/adapters/test_model_store.py` (new): registry, paths, happy path.
4. `tests/unit/adapters/test_model_store_integrity.py` (new): manifest, versions, hash, bundle shape.

## External dependencies

None new. `joblib==1.6.0` (`joblib.load`, `joblib.dump` in the fixture), standard library `hashlib.file_digest`,
`importlib.metadata.version`, `json`, `types.MappingProxyType`. joblib 1.6.0 ships no `py.typed`; `pyproject.toml` (spec 000)
sets mypy `ignore_missing_imports` for `joblib.*`, so `import joblib` needs no suppression and `joblib.load` returns
`Any`, assigned at once to a variable typed `object`. No `# type: ignore` and no `# noqa` are allowed in this spec.

## Interfaces and types

Constants in `api/adapters/model_store.py`:
- `VERSION_PATTERN: re.Pattern[str] = re.compile(r"v\d{3}")`, always used with `fullmatch`.
- `SHA256_PATTERN: re.Pattern[str] = re.compile(r"[0-9a-f]{64}")`, always used with `fullmatch`.
- `REGISTRY_FILE: str = "registry.json"`, `MANIFEST_FILE: str = "manifest.json"`, `BUNDLE_FILE: str = "bundle.joblib"`.
- `CHECKED_LIBRARIES: tuple[str, ...] = ("scikit-learn", "numpy", "joblib", "mapie")`.
- `BUNDLE_KEYS: frozenset[str]` = the 10 keys of contracts §9.1: `schema_version`, `class_order`, `aspect_order`,
  `polarity_pipeline`, `conformal_classifier`, `aspect_pipeline`, `aspect_thresholds`, `topic_vectorizer`,
  `topic_kmeans`, `topic_terms`.

`class TrustedModelStore` (satisfies `ModelStore` structurally; does not inherit from it):
- `__init__(self, models_dir: Path) -> None`: runs steps 1 to 9 below; stores `self._info: ModelInfo` and
  `self._bundle: Mapping[str, object]`.
- `info(self) -> ModelInfo`: returns `self._info`.
- `bundle(self) -> Mapping[str, object]`: returns `self._bundle`, a `types.MappingProxyType` (read-only).

Private module functions (each ≤ 20 statements): `_checked_path(root: Path, relative: Path, directory: bool,
missing: ModelUnavailableError) -> Path`, `_read_object(path: Path, label: str) -> dict[str, object]`, `_active_version(root: Path) -> str`,
`_field[T](source: Mapping[str, object], key: str, kind: type[T]) -> T`, `_model_info(manifest: Mapping[str,
object], version: str) -> ModelInfo`, `_check_libraries(manifest: Mapping[str, object]) -> None`,
`_check_hash(path: Path, expected: str) -> None`, `_load_bundle(path: Path) -> Mapping[str, object]`.

`tests/fixtures/model_bundles.py`:
- `fake_bundle() -> dict[str, object]`: `schema_version` 1, `class_order` `("negative", "neutral", "positive")`,
  `aspect_order` the 9 `AspectGroup` values in `ASPECT_ORDER`, `aspect_thresholds` 9 × `0.5`, `topic_terms`
  `(("alpha", "beta", "gamma", "delta", "epsilon"),)`, the other 5 keys the string `"placeholder"`.
- `fake_manifest(version: str, bundle_sha256: str) -> dict[str, object]`: contracts §9.2 shape with `version`,
  `bundle_sha256`, `created_at` `"2026-11-10T12:00:00Z"`, `dataset_sha256` `"a" * 64`, `library_versions` holding
  `importlib.metadata.version(name)` for the 4 `CHECKED_LIBRARIES`, `polarity_model` `"logistic_regression"`,
  `representation` `"tfidf"`, `confidence_level` `0.9`, `metrics` `{"test_macro_f1": 0.61, "empirical_coverage": 0.9}`.
- `write_fake_version(models_dir: Path, version: str, bundle: object | None = None) -> Path`: creates
  `models_dir / version` (parents included), `joblib.dump` of `bundle` (default `fake_bundle()`), writes
  `manifest.json` from `fake_manifest` with the real SHA-256 of the dumped file; returns the version directory.
- `replace_bundle_bytes(version_dir: Path, content: bytes) -> None`: overwrites `bundle.joblib` with `content` and
  rewrites `manifest.json` with the SHA-256 of `content` (hash stays consistent).
- `write_registry(models_dir: Path, active: str, history: list[str]) -> None`: writes `registry.json`.

## Expected behavior

`TrustedModelStore(models_dir)`:
1. `root = models_dir.resolve(strict=True)`; `OSError` → `ModelUnavailableError("models directory not found")`.
   A `models_dir` that is itself a symlink is accepted (it is resolved here).
2. `_checked_path(root, Path(REGISTRY_FILE), False, ModelUnavailableError("registry not found"))`; then `_active_version` reads it with
   `_read_object(path, "registry")`: `active` MUST be a `str` matching `VERSION_PATTERN`, `history` a non-empty `list`
   of `str` whose last item equals `active`; otherwise `ModelIntegrityError("invalid registry")`.
3. `_checked_path(root, Path(version), True, ModelUnavailableError("model version not found"))`.
4. `manifest_path` and then `bundle_path` = `_checked_path(root, Path(version) / name, False,
   ModelIntegrityError("model file missing"))` with `name` `MANIFEST_FILE`, then `BUNDLE_FILE`.
5. `manifest = _read_object(manifest_path, "manifest")`; `manifest["version"] != version` →
   `ModelIntegrityError("manifest version mismatch")`; `bundle_sha256` not a `str` matching `SHA256_PATTERN` →
   `ModelIntegrityError("invalid manifest")`.
6. `info = _model_info(manifest, version)`: reads `created_at`, `dataset_sha256`, `polarity_model`, `representation`
   (`str`), `confidence_level` (`float`), `metrics.test_macro_f1` and `metrics.empirical_coverage` (`float`) with
   `_field` (`isinstance(value, kind)` false or key absent → `ModelIntegrityError("invalid manifest")`); an
   `InvalidInputError` from `ModelInfo` → `ModelIntegrityError("invalid manifest")` from it.
7. `_check_libraries(manifest)`: `library_versions` MUST be a `dict`; for each name in `CHECKED_LIBRARIES` in order:
   `importlib.metadata.PackageNotFoundError` → `ModelIntegrityError(f"library not installed: {name}")`; recorded
   value absent, not a `str` or `!=` installed → `ModelIntegrityError(f"library version mismatch: {name}")`.
8. `_check_hash(bundle_path, manifest["bundle_sha256"])`: `hashlib.file_digest(file, "sha256").hexdigest()` on the
   file opened `"rb"`; different → `ModelIntegrityError("bundle hash mismatch")`. Steps 5 to 8 run before
   `joblib.load`; a failure there means `joblib.load` is never called.
9. `_load_bundle(bundle_path)`: `joblib.load(bundle_path)`; `OSError`, `EOFError`, `KeyError`, `ValueError`,
   `ImportError` or `AttributeError` → `ModelIntegrityError("bundle failed to load")` from it. Then, in order:
   not a `dict` or `set(keys) != BUNDLE_KEYS` → `"bundle keys mismatch"`; `schema_version != BUNDLE_SCHEMA_VERSION`
   → `"bundle schema mismatch"`; `class_order != tuple(p.value for p in POLARITY_ORDER)` →
   `"bundle class order mismatch"`; `aspect_order != tuple(g.value for g in ASPECT_ORDER)` →
   `"bundle aspect order mismatch"` (all `ModelIntegrityError`). Returns `MappingProxyType(loaded)`.
10. Logs INFO `"event=model_loaded version=%s"` with `version`. No other log line; no comment text, no path.

`_checked_path(root, relative, directory, missing)`: `candidate = root / relative`; `candidate.is_symlink()` →
`ModelIntegrityError("symlink rejected")`; `target = resolve_within(root, relative)`, `UnsafePathError` →
`ModelIntegrityError("path escapes models directory")` from it; `not target.exists()` → raise `missing`; `directory` and not `target.is_dir()` →
`ModelIntegrityError("not a directory")`; not `directory` and not `target.is_file()` →
`ModelIntegrityError("not a regular file")`. Returns `target`.

`_read_object(path, label)`: `json.loads(path.read_text(encoding="utf-8"))`; `OSError`, `UnicodeDecodeError`,
`json.JSONDecodeError` or a result that is not a `dict` → `ModelIntegrityError(f"invalid {label}")`.

The adapter never calls `sys.exit`. The composition root (spec 024) constructs the store at startup without a
`try`, so `ModelIntegrityError` aborts startup and the process exits. No `functools` cache, no module-level state.

## Edge cases and error handling

`Unavailable` = exactly `ModelUnavailableError` (not the subclass); `Integrity` = `ModelIntegrityError`.

| Input | Result |
|---|---|
| `models_dir` absent | Unavailable `"models directory not found"` |
| `registry.json` absent | Unavailable `"registry not found"` |
| Registry text `{` | Integrity `"invalid registry"` |
| Registry `active` `"../v001"`, `"v1"`, `"v001\n"` or `7` | Integrity `"invalid registry"` |
| Registry `{"active": "v001", "history": ["v002"]}` or `"history": []` | Integrity `"invalid registry"` |
| `registry.json` is a symlink | Integrity `"symlink rejected"` |
| Active version directory absent | Unavailable `"model version not found"` |
| `v001` is a symlink to a directory outside `models/` | Integrity `"symlink rejected"` |
| `v001` is a regular file | Integrity `"not a directory"` |
| `v001/bundle.joblib` is a symlink | Integrity `"symlink rejected"` |
| `v001/bundle.joblib` absent | Integrity `"model file missing"` |
| `v001/bundle.joblib` is a directory | Integrity `"not a regular file"` |
| Manifest `version` `"v002"` inside `v001/` | Integrity `"manifest version mismatch"` |
| Manifest `bundle_sha256` in uppercase hex | Integrity `"invalid manifest"` |
| Manifest without `metrics`, or `confidence_level` `"0.9"` | Integrity `"invalid manifest"` |
| Manifest `library_versions.numpy` `"0.0.0"` | Integrity `"library version mismatch: numpy"` |
| Manifest without `library_versions.mapie` | Integrity `"library version mismatch: mapie"` |
| One byte appended to `bundle.joblib` after the manifest | Integrity `"bundle hash mismatch"`, `joblib.load` not called |
| `replace_bundle_bytes(v001, b"not a joblib file at all")` | Integrity `"bundle failed to load"` (joblib raises `KeyError`, measured) |
| `replace_bundle_bytes(v001, b"")` | Integrity `"bundle failed to load"` (joblib raises `EOFError`, measured) |
| Bundle without `topic_terms`, or a list instead of a dict | Integrity `"bundle keys mismatch"` |
| `schema_version` 2 | Integrity `"bundle schema mismatch"` |
| `class_order` reversed | Integrity `"bundle class order mismatch"` |
| `aspect_order` reversed | Integrity `"bundle aspect order mismatch"` |

A truncated bundle with a matching hash makes joblib raise the unpickling error class, which this module cannot name
(the SEC-13 grep forbids that word in `api/`); it propagates and stops startup. No existing test changes expectation.
If an existing test not listed here fails because of this change, the implementer does not modify it: they report
its name and the reason.

## Acceptance tests (prose)

All tests use pytest `tmp_path / "models"` and the fixture helpers; one test per row of the table above, named
`test_trusted_model_store_<behavior>`, asserting the exception class with `type(error) is ...` and `error.detail`.
`test_model_store.py` holds the registry and path rows; `test_model_store_integrity.py` the manifest, library, hash
and bundle rows. Additional cases:
- `test_trusted_model_store_loads_active_version`: `write_fake_version(models, "v001")`, registry
  `{"active": "v001", "history": ["v001"]}` → `info()` equals `ModelInfo("v001", "2026-11-10T12:00:00Z", "a" * 64,
  "logistic_regression", "tfidf", 0.9, 0.61, 0.9)`; `bundle()["schema_version"] == 1`; with
  `caplog.set_level(logging.INFO)`, caplog holds the message
  `"event=model_loaded version=v001"`.
- `test_trusted_model_store_follows_registry_after_rollback`: versions `v001` and `v002` written; registry
  `{"active": "v002", "history": ["v001", "v002"]}` → `info().version == "v002"`; registry rewritten to
  `{"active": "v001", "history": ["v001"]}` and a new store → `"v001"`.
- `test_trusted_model_store_accepts_symlinked_models_dir`: `tmp_path / "link"` symlinks to a valid `models` → loads.
- `test_trusted_model_store_bundle_is_read_only`: assigning key `"schema_version"` on
  `typing.cast(dict[str, object], store.bundle())` raises `TypeError`.
- `test_trusted_model_store_verifies_on_every_load`: a first store loads; one byte is appended to `bundle.joblib`; a
  second `TrustedModelStore(models)` raises Integrity `"bundle hash mismatch"`.
- The hash-mismatch row monkeypatches `api.adapters.model_store.joblib.load` with a recorder and asserts 0 calls.

## Out of scope

- Writing versions, `activate`, `rollback` and `verify` (spec 013). Narrowing bundle objects to scikit-learn and
  MAPIE types (spec 018). Process exit, the `1 - alpha` check and `/model` (spec 024).

## Definition of Done

- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed`.
- [ ] `grep -rnE "# noqa|# type: ignore" api/adapters/model_store.py tests/fixtures/model_bundles.py tests/unit/adapters/test_model_store.py tests/unit/adapters/test_model_store_integrity.py`
      → no output.
- [ ] `.venv/bin/pytest -q tests/unit/adapters/test_model_store.py tests/unit/adapters/test_model_store_integrity.py --cov=api/adapters --cov-report=term-missing`
      → the row of `api/adapters/model_store.py` shows Cover ≥ 80 %.
- [ ] `grep -rln "joblib.load" api/ ml/` → exactly `api/adapters/model_store.py` and `ml/artifact.py` (SEC-14).
- [ ] `grep -nE "sys\.exit|lru_cache|functools" api/adapters/model_store.py` → no output.
- [ ] `bash scripts/security_grep.sh` → no output, exit code 0 (SEC-13, SEC-15).
