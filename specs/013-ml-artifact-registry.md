# 013 - ML artifact and registry
Riesgo: alto

## Objective

`joblib.load` runs code from the file it reads, and the guide requires trusted files, aligned library versions,
versioning and rollback (ADR-003). This spec adds `ml/artifact.py`, which writes one immutable directory per model
version (`models/vNNN/` with `bundle.joblib`, `manifest.json`, `report.json`, `reference_stats.json`) and loads a
version only after the SEC-14 checks, and `ml/registry.py`, which keeps `models/registry.json` (`activate` and
`rollback` live in `ml/artifact.py` and call it). After this spec, `ml.train` (spec 014) and `TrustedModelStore`
(spec 017) have one verified way to write and read bundles.

## Depends on

003 (`resolve_within`), 010, 011, 012 (bundle contents), 007 (`ml.schemas`: `Manifest`, `Registry`, `Report`,
`ReferenceStats`, `BUNDLE_SCHEMA_VERSION`, `SEED`), 002 (`api/domain/errors.py`).

## Governing files

- `ARCHITECTURE.md` §2 rule 4, §3 step 5, §5 (`models/` layout), §6 (≤ 20 statements per function, ≤ 300 lines per
  module, `mypy --strict`, UTC time read only in `ml`/adapters, `print` only in `main()`, generic `except` only in
  `main()`).
- `security-rules.md` SEC-02 (no comment text in `report.json`), SEC-04 (umask, 0700/0600), SEC-05, SEC-07 (`ml`
  writes only under `models/` here), SEC-10, SEC-12 (`resolve_within`, generated names `vNNN`), SEC-13 (`json` only),
  SEC-14 (hash and versions before `joblib.load`; `joblib.load` only in `ml/artifact.py` and
  `api/adapters/model_store.py`), SEC-15, SEC-17 (embedding revision in the manifest).
- ADR-003. `docs/contracts.md` §2, §8 (`ml.artifact`, `ml.registry`), §9.1 to §9.5.

## Files to create/modify

1. `ml/artifact.py` (new). No `ml` module exists yet; follow the module layout of `ml/split.py` (spec 008). Budget:
   ≤ 300 lines, each function ≤ 20 statements.
2. `ml/registry.py` (new). Same layout. Budget: ≤ 150 lines. It never calls `joblib`.
3. `tests/fixtures/synthetic_bundle.py` (new): `make_bundle() -> dict[str, object]`, `make_manifest() -> Manifest`,
   `make_report() -> Report`, `make_reference() -> ReferenceStats` (values in "Acceptance tests").
4. `tests/unit/ml/test_artifact_write.py` (new): `next_version`, `write_version`, `main`.
5. `tests/unit/ml/test_artifact_load.py` (new): `load_verified`, `activate`, `rollback`, registry file.
Each test file stays ≤ 300 lines (parametrize the rows that differ by one value).

## External dependencies

None new (`joblib==1.6.0`, `scikit-learn==1.9.1`, `numpy==2.5.4`, `mapie==1.6.0`, spec 000). Verified at these pins:
`joblib.dump(value, file_object)` writes to an open binary file; `joblib.load(io.BytesIO(raw))` loads from bytes;
`importlib.metadata.version("scikit-learn")` returns `"1.9.1"`; `platform.python_version()` returns `"3.12.14"`.
Spec 000 sets mypy `ignore_missing_imports` for `sklearn.*` and `joblib.*`: `from sklearn.pipeline import Pipeline`
needs no suppression and `typing.cast("Pipeline", bundle["polarity_pipeline"])` is the only way this spec narrows
the bundle object before `.predict_proba`.

## Interfaces and types

`ml/registry.py`: `VERSION_PATTERN = re.compile(r"v[0-9]{3}")` (always `fullmatch`); `dump_json(value: object) ->
str` = `json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"` (vector: `{"b": 1, "a": "é"}` →
`'{\n  "a": "é",\n  "b": 1\n}\n'`; every JSON file of this spec uses it); `read_registry(models_dir: Path) -> Registry |
None` (`None` when the file is absent); `push_version(models_dir: Path, version: str) -> bool` (`False` and no write
when `history` already ends with `version`); `pop_version(models_dir: Path) -> str`. Private: `_registry_path(models_dir:
Path) -> Path`, `_validate_registry(raw: object) -> Registry`, `_write_registry(models_dir: Path, registry: Registry) ->
None`, `_atomic_write(path: Path, text: str) -> None`.

`ml/artifact.py`, public (`docs/contracts.md` §8):
- `SMOKE_TEXTS: tuple[str, str, str] = ("El curso fue excelente y las clases muy claras.", "Los parciales fueron
  injustos y la retroalimentación llegó tarde.", "El contenido estuvo bien, aunque el horario fue incómodo.")`
- `next_version(models_dir: Path) -> str`; `write_version(models_dir: Path, bundle: dict[str, object], manifest:
  Manifest, report: Report, reference: ReferenceStats) -> Path`; `load_verified(models_dir: Path, version: str) ->
  dict[str, object]`; `activate(models_dir: Path, version: str) -> None`; `rollback(models_dir: Path) -> str`;
  `main(argv: Sequence[str] | None = None) -> int`.

Private constants: `_BUNDLE_KEYS: frozenset[str]` = the 10 keys of §9.1; `_REPORT_KEYS: frozenset[str]` =
`selection`, `test`, `per_file_macro_f1`, `conformal`, `risk_coverage`, `aspects`, `topics`, `split`,
`test_row_keys`; `_CHECKED_LIBRARIES = ("scikit-learn", "numpy", "joblib", "mapie")`; `_RECORDED_LIBRARIES` = the 9
names of §9.2 in that order; `_SMOKE_TOLERANCE = 1e-9`; `_MAX_REPORT_WORDS = 3`; `_MAX_REPORT_CHARS = 80`. Hashes:
`hashlib.sha256` over raw bytes, lowercase hex (vector: `b"abc"` →
`"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"`).
Private functions: `_check_bundle(bundle)`, `_check_manifest(manifest)`, `_check_report(report)`, `_has_comment_text(value:
object) -> bool`, `_check_reference(reference)`, `_smoke_rows(bundle) -> list[list[float]]`, `_write_file(path: Path,
data: bytes) -> None`, `_complete_manifest(manifest, sha: str, smoke: list[list[float]]) -> Manifest`,
`_checked_file(models_dir: Path, version: str, name: str) -> Path`, `_read_manifest(path: Path, version: str) ->
dict[str, object]`, `_check_libraries(manifest: Mapping[str, object]) -> None`, `_read_smoke(models_dir: Path,
version: str) -> tuple[list[str], list[list[float]]]`, `_models_path(raw: str) -> Path`, `_parser() ->
argparse.ArgumentParser`, `_verify(models_dir: Path, version: str) -> None`.

## Expected behavior

`next_version`: names of the entries of `models_dir` (files or directories, partial version directories included)
that `fullmatch` `VERSION_PATTERN`; none → `"v001"`; else maximum number + 1, formatted `f"v{n:03d}"`.

`write_version`:
1. Validates `bundle`, `manifest`, `report`, `reference` (edge cases table) before touching the disk.
2. `smoke = typing.cast("Pipeline", bundle["polarity_pipeline"]).predict_proba(list(SMOKE_TEXTS))`, converted with
   `.tolist()`; shape other than 3 × 3 → error.
3. `models_dir.mkdir(mode=0o700, exist_ok=True)`; `version = next_version(models_dir)`;
   `vdir = resolve_within(models_dir, Path(version))`; `vdir.mkdir(mode=0o700)`.
4. Every file is created with `os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)`; the bundle with
   `joblib.dump(bundle, file_object)`; JSON files as `dump_json(value)` in UTF-8. Every path comes from
   `resolve_within(vdir, Path(name))`.
5. The written manifest is a copy of `manifest` with 6 keys replaced: `version`; `created_at` =
   `datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")`; `bundle_sha256` of the written `bundle.joblib`;
   `python_version` = `platform.python_version()`; `library_versions` = `{name: importlib.metadata.version(name)}`
   for `_RECORDED_LIBRARIES`; `smoke` = `{"texts": list(SMOKE_TEXTS), "probabilities": smoke}`. Every other key
   (`dataset_sha256`, `embedding`, `polarity_model`, `representation`, `best_params`, `confidence_level`, `seed`,
   `metrics`) is written as given.
6. Writes `bundle.joblib`, then `report.json`, `reference_stats.json` and `manifest.json` last; logs `INFO`
   `"version_written version=%s bundle_sha256=%s"`; returns `vdir`. A failure after step 3 leaves a directory without
   `manifest.json`, which `load_verified` and `activate` reject; it is not deleted, and `next_version` counts it, so
   the next write is `v002` (intended).

`load_verified` (SEC-14; every check runs before `joblib.load`):
1. `version` must `fullmatch` `VERSION_PATTERN`.
2. `models_dir / version`, its `manifest.json` and its `bundle.joblib` (`_checked_file`): any `is_symlink()` → error;
   directory or file missing or not regular → error. Paths come from `resolve_within(models_dir, Path(version) / name)`.
3. `_read_manifest`: `json.loads(path.read_text(encoding="utf-8"))`; `OSError`, `UnicodeDecodeError`,
   `json.JSONDecodeError`, a non-`dict`, `bundle_sha256` not 64 lowercase hex characters or `library_versions` not a
   `dict` → `"manifest.json is invalid"` (`from` the cause when there is one); then `version` equal to `version`.
4. `raw = bundle_path.read_bytes()`; `hashlib.sha256(raw).hexdigest()` must equal `bundle_sha256`.
5. `_check_libraries`: for each name in `_CHECKED_LIBRARIES`, `importlib.metadata.version(name)` must equal
   `library_versions[name]`; a name absent from `library_versions`, a non-`str` value or `PackageNotFoundError` →
   the same mismatch error.
6. `bundle = joblib.load(io.BytesIO(raw))` (the exact hashed bytes, no second read); `OSError`, `EOFError`, `KeyError`,
   `ValueError`, `ImportError` or `AttributeError` → `"bundle failed to load"` (`from` it). The result must be a
   `dict` whose key set equals `_BUNDLE_KEYS` with `schema_version == BUNDLE_SCHEMA_VERSION`, else `"bundle schema
   is invalid"`.
7. Logs `INFO` `"version_loaded version=%s"`; returns the bundle.

Registry (`models/registry.json`, §9.3), written with `dump_json`; path `resolve_within(models_dir,
Path("registry.json"))`; a symlink is rejected. Valid content: a `dict` with exactly the keys `active` and `history`,
`history` a non-empty list of `str` that each `fullmatch` `VERSION_PATTERN`, `active == history[-1]`. Writes go to
`tempfile.mkstemp(dir=models_dir, prefix=".registry-", suffix=".tmp")` (mode 0600); one `try` covers writing the
text, `os.fsync` and `os.replace` onto `registry.json`; on `OSError` the temporary file is removed and the error
re-raised. After `activate v001` on a new registry the file text is `'{\n  "active": "v001",\n  "history": [\n    "v001"\n  ]\n}\n'`.
- `activate` (`ml/artifact.py`): `load_verified(models_dir, version)` (all its errors propagate); then
  `push_version`; missing registry → history `[]`; appends the version and sets `active` unless `history` already
  ends with it (no write then); logs `INFO` `"version_activated version=%s"` after a write.
- `rollback`: `pop_version` removes the last entry, sets `active = history[-1]`, writes, returns `active`; logs
  `INFO` `"version_rolled_back active=%s"`.

`main`: first statement `os.umask(0o077)` (SEC-04). `argparse` with prog `"ml.artifact"`, option `--models`
(default `"models"`) and required subcommands `activate VERSION`, `rollback`, `verify VERSION`. `_models_path(raw)` =
`resolve_within(Path.cwd(), Path(raw))`, which must be `Path.cwd().resolve() / "models"` or inside it, else
`UnsafePathError("path escapes base")` (SEC-07; spec 014 applies the same rule to its `--models`). `verify` =
`load_verified`, then `_read_smoke` re-reads `manifest.json` through `resolve_within(models_dir, Path(version) /
"manifest.json")`; its smoke texts must equal `list(SMOKE_TEXTS)` and `typing.cast("Pipeline",
bundle["polarity_pipeline"]).predict_proba(texts)` must match the manifest probabilities element by element within
`_SMOKE_TOLERANCE`. Output on stdout: `activate` and `rollback` → `"active=<version>"`, `verify` → `"verified=<version>"`;
return 0. `AppError` → stderr `"error=<code>"`, return 2. Any other exception → `logger.exception("artifact_command_failed")`,
stderr `"error=internal_error"`, return 1.

## Edge cases and error handling

| Function | Condition | Exception and detail |
|---|---|---|
| `next_version` | maximum is `v999` | `InvalidInputError("version limit v999 reached")` |
| `write_version` | `set(bundle) != _BUNDLE_KEYS` or `schema_version != BUNDLE_SCHEMA_VERSION` | `InvalidInputError("bundle keys do not match the schema")` |
| `write_version` | smoke probabilities not 3 × 3 | `InvalidInputError("smoke probabilities must have shape (3, 3)")` |
| `write_version` | `dataset_sha256` not 64 lowercase hex | `InvalidInputError("dataset_sha256 must be 64 lowercase hex characters")` |
| `write_version` | `embedding["revision"]` absent or not 40 lowercase hex | `InvalidInputError("embedding revision must be a 40-character commit hash")` |
| `write_version` | `metrics` lacks `test_macro_f1` or `empirical_coverage`, or one of the two is not a `float` in `[0.0, 1.0]` (a `bool` or an `int` is rejected) | `InvalidInputError("manifest metrics are incomplete")` |
| `write_version` | `set(report) != _REPORT_KEYS` | `InvalidInputError("report.json keys do not match the schema")` |
| `write_version` | any `str` key or value in `report` (recursive over `dict`, `list`, `tuple`) with more than 3 whitespace-separated words or more than 80 characters | `InvalidInputError("report.json must not contain comment text")` (every dataset comment has at least 6 words, measured 2026-11-05) |
| `write_version` | `reference` keys other than `length_edges` (9 ints, non-decreasing), `length_shares` (10 floats), `reference_oov_rate` (float in `[0, 1]`), `class_shares` (3 floats); `length_shares` or `class_shares` not summing to 1 within 1e-6 | `InvalidInputError("reference_stats.json does not match the schema")` |
| `write_version` | a value `json.dumps` cannot encode (`numpy.int64`) | `TypeError` propagates |
| `load_verified`, `activate` | version name invalid | `ModelIntegrityError("invalid version name")` |
| same | a symlink in step 2 | `ModelIntegrityError("symlink rejected")` |
| same | directory or file missing (also a partial directory without `manifest.json`) | `ModelIntegrityError("version files are missing")` |
| same | manifest unparsable, not UTF-8, or step 3 fails | `ModelIntegrityError("manifest.json is invalid")` |
| same | `manifest["version"]` absent or `!= version` | `ModelIntegrityError("manifest version mismatch")` |
| same | hash differs | `ModelIntegrityError("bundle hash mismatch")` |
| same | library differs, absent from the manifest or not installed | `ModelIntegrityError("library version mismatch: <name>")` (`"library version mismatch: scikit-learn"`) |
| same | `joblib.load` raises one of the 6 listed exceptions | `ModelIntegrityError("bundle failed to load")` |
| same | step 6 schema check fails | `ModelIntegrityError("bundle schema is invalid")` |
| registry read | invalid JSON, invalid structure or a history item not matching `VERSION_PATTERN` | `ModelIntegrityError("registry.json is invalid")` |
| registry read | `registry.json` is a symlink | `ModelIntegrityError("symlink rejected")` |
| `rollback` | `registry.json` missing | `ModelUnavailableError("registry.json is missing")` |
| `rollback` | `len(history) < 2` | `ModelUnavailableError("no previous version to roll back to")` |
| `main` | `--models` outside `<cwd>/models` (`../x`, `src`) | `UnsafePathError("path escapes base")` → stderr `"error=internal_error"`, exit 2 |
| `main` | `verify` texts differ / probabilities differ / manifest `smoke` malformed | `ModelIntegrityError("smoke texts mismatch")` / `("smoke probabilities mismatch")` / `("manifest.json is invalid")` → exit 2 |

No log line contains comment text or file contents (SEC-05). If an existing test not listed here fails because of
this change, the implementer does NOT modify it: report its name and the reason.

## Acceptance tests (prose)

Fixture `tests/fixtures/synthetic_bundle.py`: `make_bundle()` fits `Pipeline([("features", TfidfVectorizer()),
("classifier", LogisticRegression(max_iter=1000))])` on the 30 texts `f"{w} curso {i % 5}"` (`w` =
`("malo", "regular", "bueno")[i % 3]`, `y = i % 3`, `i` in `0..29`) as `polarity_pipeline`; `schema_version` 1;
`class_order` and `aspect_order` per §9.1; `aspect_thresholds` `(0.5,) * 9`; `topic_terms`
`(("alfa", "beta", "gamma", "delta", "epsilon"),)`; the other 4 keys hold the string `"stub"`. `make_manifest()`:
§9.2 example values with `dataset_sha256 = "0" * 64` and `bundle_sha256 = "f" * 64`. `make_report()`: the 9 keys,
strings only `"tfidf"`, `"logistic_regression"`, `"classifier__C"`, `"feedback_curso_universitario.csv"`, group
values, `"carga"`, `"ritmo"`, and `"feedback_curso_universitario.csv:1"`. `make_reference()`: `length_edges`
`[40, 60, 80, 100, 120, 140, 160, 180, 200]`, `length_shares` `[0.1] * 10`, `reference_oov_rate` 0.05,
`class_shares` `[0.33, 0.42, 0.25]`. All tests use `tmp_path`; tests alter a manifest by reading it with `json.loads`,
changing one key and writing it back with `Path.write_text`. Tests never call `joblib.load` themselves.

`tests/unit/ml/test_artifact_write.py`:
1. `test_next_version_starts_at_v001`: empty directory → `"v001"`.
2. `test_next_version_skips_non_version_names`: entries `v001/`, `v002/`, `v010/`, file `v011`, `notes/`, `v1/` → `"v012"`.
3. `test_next_version_rejects_v999`: entry `v999/` → `"version limit v999 reached"`. `test_next_version_after_v998`: `v998/` → `"v999"`.
4. `test_write_version_creates_files_with_private_modes`: with `os.umask(0o022)` set by the test (restored after),
   `tmp_path / "models"` absent → returns `tmp_path / "models" / "v001"`; `models` and `v001` modes `0o700`; the 4
   files `0o600`.
5. `test_write_version_completes_manifest`: `bundle_sha256` equals `hashlib.sha256` of `bundle.joblib` bytes;
   `version == "v001"`; `created_at` matches `^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$`; `library_versions` has the 9
   names with `"scikit-learn": "1.9.1"`; `smoke.texts == list(SMOKE_TEXTS)`; each smoke row sums to 1 within 1e-9;
   `dataset_sha256 == "0" * 64` unchanged.
6. `test_write_version_rejects_comment_text_in_report`: `test_row_keys = ["El curso fue muy bueno y claro"]` →
   `"report.json must not contain comment text"`; no `v001` directory created.
7. `test_write_version_rejects_report_keys`: report without `topics` → `"report.json keys do not match the schema"`.
8. `test_write_version_rejects_reference_shape`: `length_shares` of 9 values → `"reference_stats.json does not match
   the schema"`.
9. `test_write_version_rejects_bundle_keys`: bundle without `topic_kmeans` → `"bundle keys do not match the schema"`.
10. `test_write_version_rejects_short_revision`: revision `"abc"` and a manifest `embedding` without `revision` →
    `"embedding revision must be a 40-character commit hash"` each.
11. `test_write_version_rejects_bad_dataset_hash`: `dataset_sha256 = "G" * 64` → `"dataset_sha256 must be 64
    lowercase hex characters"`.
12. `test_write_version_rejects_incomplete_metrics`: `metrics` without `test_macro_f1`, and `empirical_coverage = 1` (an
    `int`) → `"manifest metrics are incomplete"` each.
13. `test_write_version_rejects_bad_smoke_shape`: `polarity_pipeline` fitted on 2 classes → `"smoke probabilities must
    have shape (3, 3)"`.
14. `test_write_version_propagates_numpy_int`: `manifest["seed"] = numpy.int64(42)` → `TypeError`.
15. `test_main_commands_and_exit_codes`: `monkeypatch.chdir(tmp_path)`; `main(["activate", "v001"])` → 0, stdout
    `"active=v001"`; `main(["verify", "v001"])` → 0, `"verified=v001"`; `main(["rollback"])` → 2, stderr
    `"error=model_unavailable"`; `--models` set to `../x` and to `src` with `rollback` → 2, stderr
    `"error=internal_error"` each.
16. `test_main_verify_detects_smoke_drift`: manifest smoke probability `[0][0]` changed by 0.01 → exit 2; smoke texts
    changed → exit 2 with the `"smoke texts mismatch"` code path; `smoke` set to `[]` → exit 2.
17. `test_main_sets_umask`: `monkeypatch.chdir(tmp_path)` with no `models` directory; after `main(["rollback"])` (exit
    2), `os.umask(0o022)` returns `0o077` (the test restores it).
18. `test_main_unexpected_error_returns_one`: `monkeypatch` makes `load_verified` raise `RuntimeError("boom")` → exit 1,
    stderr `"error=internal_error"`, `caplog` holds the record `"artifact_command_failed"`.

`tests/unit/ml/test_artifact_load.py` (each starts from one `write_version` call):
1. `test_load_verified_returns_bundle`: the returned dict has the 10 keys and `schema_version == 1`.
2. `test_load_verified_rejects_tampered_bundle`: one byte `b"\x00"` appended → `"bundle hash mismatch"`.
3. `test_load_verified_rejects_library_mismatch`: manifest `library_versions["scikit-learn"] = "0.0.0"` → `"library
   version mismatch: scikit-learn"`; key `mapie` deleted → `"library version mismatch: mapie"`.
4. `test_load_verified_rejects_symlinked_version`: `v002` symlink to `v001` → `"symlink rejected"`.
5. `test_load_verified_rejects_symlinked_bundle`: `bundle.joblib` replaced by a symlink to a copy → `"symlink rejected"`.
6. `test_load_verified_rejects_bad_names`: `"../v001"`, `"v1"`, `"v0001"` → `"invalid version name"`.
7. `test_load_verified_rejects_missing_manifest`: `manifest.json` deleted → `"version files are missing"`.
8. `test_load_verified_rejects_invalid_manifest`: content `"{"` and bytes `b"\xff\xfe"` → `"manifest.json is invalid"`.
9. `test_load_verified_rejects_bundle_schema`: `bundle.joblib` rewritten with `joblib.dump([1, 2])` and the manifest
   hash updated → `"bundle schema is invalid"`; the same with raw bytes `b"not joblib"` → `"bundle failed to load"`.
10. `test_load_verified_rejects_manifest_version`: manifest `version = "v009"` → `"manifest version mismatch"`.
11. `test_load_verified_rejects_library_not_installed`: `monkeypatch` makes `importlib.metadata.version` raise
    `PackageNotFoundError` for `"mapie"` → `"library version mismatch: mapie"`.
12. `test_activate_rejects_partial_version`: directory `v002` without `manifest.json` → `"version files are missing"`.
13. `test_activate_and_rollback_stack`: `activate v001` → `{"active": "v001", "history": ["v001"]}`; `activate v002`
    → `{"active": "v002", "history": ["v001", "v002"]}`; `rollback` returns `"v001"` and the file is `{"active":
    "v001", "history": ["v001"]}`; a second `rollback` → `"no previous version to roll back to"`.
14. `test_registry_text_format`: after `activate v001` the file text equals the literal of "Expected behavior".
15. `test_activate_same_version_keeps_history`: `activate v001` twice → history `["v001"]`.
16. `test_activate_rejects_unverified_version`: tampered `v002` → `"bundle hash mismatch"`; registry unchanged.
17. `test_registry_file_is_private_and_atomic`: after `activate`, `registry.json` mode `0o600`; no file matching
    `.registry-*.tmp` remains; with `os.replace` monkeypatched to raise `OSError`, `activate` re-raises and no
    `.registry-*.tmp` remains.
18. `test_rollback_rejects_missing_registry`: → `"registry.json is missing"`.
19. `test_registry_rejects_invalid_content`: `{"active": "v002", "history": ["v001"]}`, text `{`, `{"active": "v001",
    "history": ["v001", 3]}` and `"history": ["x1"]` → `"registry.json is invalid"` each.
20. `test_registry_rejects_symlink`: `registry.json` a symlink to a valid copy → `"symlink rejected"`.
21. `test_dump_json_vector`: `dump_json({"b": 1, "a": "é"})` equals the vector of "Interfaces and types".

## Out of scope

- Building `reference_stats` values and the `report` content (spec 014); `TrustedModelStore` (spec 017); Python
  version comparison at load; deleting old versions; cleanup of partial version directories.

## Definition of Done

- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed`; `wc -l ml/artifact.py ml/registry.py` → ≤ 300 and ≤ 150.
- [ ] `grep -nE "# noqa|# type: ignore" ml/artifact.py ml/registry.py tests/fixtures/synthetic_bundle.py tests/unit/ml/test_artifact_*.py` → no output.
- [ ] `.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing` → `ml/artifact.py` and `ml/registry.py` ≥ 80 %.
- [ ] `grep -rln --include="*.py" "joblib.load" api/ ml/` → only `ml/artifact.py` (plus `api/adapters/model_store.py` once spec 017 exists).
- [ ] `grep -c "joblib.load(io.BytesIO(raw))" ml/artifact.py` → `1` (the string appears in code only, not in docstrings or comments).
- [ ] `grep -n "os.umask(0o077)" ml/artifact.py` → 1 line, the first statement of `main`.
- [ ] `grep -nE "pickle|eval\(|exec\(|shell=True|yaml" ml/artifact.py ml/registry.py` → no output.
- [ ] `bash scripts/security_grep.sh` → no output, exit code 0; `bash scripts/gate.sh` → last line `GATE OK`.
