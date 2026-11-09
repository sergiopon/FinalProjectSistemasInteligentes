# 009 - ML representations
Riesgo: alto

## Objective

Model selection (spec 010) compares 3 text representations on the same grouped folds: word TF-IDF, TF-IDF reduced
by truncated SVD, and multilingual sentence embeddings. The embedding model must load from the local cache at one
pinned revision (SEC-15, SEC-16, SEC-17), must not travel inside the bundle (ADR-003, 470,641,600 bytes of
weights) and must reach the network only through an explicit download command. When this spec is done,
`ml/representations.py` builds each representation as an unfitted scikit-learn transformer and offers
`python -m ml.representations --download`.

## Depends on

001 (`scripts/gate.sh`, `scripts/security_grep.sh`, `tests/architecture/`); 007 (`ml.schemas.SEED`;
`api/domain/errors.py`: `InvalidInputError`, `InferenceError`, `AppError`).

## Governing files

- `ARCHITECTURE.md` §2 rule 4, §3 step 3, §6 (≤ 20 statements, ≤ 6 arguments, complexity ≤ 8, ≤ 8 branches,
  modules ≤ 300 lines, `mypy --strict`, custom exceptions only, no `assert` in production code).
- `docs/adr/ADR-003` (embedding weights stay in the local cache, never in the bundle; the bundle stores the model
  name and revision).
- `security-rules.md` SEC-04 (`os.umask(0o077)` first statement of `main`), SEC-05 (no text in logs), SEC-15 (pinned
  revision), SEC-16 (`local_files_only=True` outside download), SEC-17 (network only for `--download`), SEC-13 (no
  `pickle` of the model object).
- `docs/contracts.md` §2 (CLI exit codes 0, 1, 2; `error=<code>` on stderr), §8 (`ml.representations`).
- `specs/000-tooling-and-pins.md` per-file-ignores: `"ml/representations.py" = ["T201", "BLE001"]`.

## Files to create/modify

1. `ml/representations.py` (new). Reference pattern: `ml/split.py` (spec 008). Budget ≤ 200 lines.
2. `tests/unit/ml/test_representations.py` (new): tests 1 to 4 and 6 (no `FakeModel`).
3. `tests/unit/ml/test_embedding_transformer.py` (new): `FakeModel` and tests 5 and 7 to 21 (split from file 2 so
   each file stays under the 300-line limit of `tests/architecture`).
4. `tests/integration/test_embeddings_cache.py` (new; module-level `pytestmark = pytest.mark.integration`; needs the
   model cached by `.venv/bin/python -m ml.representations --download`).

No existing test changes expectation.

## External dependencies

None new (`sentence-transformers==6.2.0`, `torch==2.15.0+cpu`, `scikit-learn==1.9.1`, spec 000). Verified in the
installed 6.2.0 source: `SentenceTransformer.__init__` accepts `revision`, `local_files_only`, `device` and
`cache_folder`; `encode` accepts `batch_size` (default 32), `show_progress_bar`, `convert_to_numpy` and
`normalize_embeddings`, and its return type is a union (`list`, `ndarray` or `Tensor`). With an empty cache and
`local_files_only=True` the constructor raises `OSError`. Under `mypy --strict` with `ignore_missing_imports` for
`sklearn`, the class line subclassing `BaseEstimator` and `TransformerMixin` reports `Class cannot subclass
"BaseEstimator" (has type "Any")  [misc]`; one `# type: ignore[misc]` on that line clears both reports (verified).

Success path (the constructor with `local_files_only=True` and the 40-character `revision` loading from the cache,
then `encode(..., normalize_embeddings=True)` returning a `numpy.ndarray` of shape `(2, 384)` for 2 texts) is not
verifiable at spec time: no installed environment and no cached model exist. It is covered by the 2 integration
tests of the Definition of Done; if either fails, the implementer reports the observed error and does not change the
design.

## Interfaces and types

`ml/representations.py`:
- `EMBEDDING_MODEL_NAME: Final[str] = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"`
- `EMBEDDING_REVISION: Final[str] = "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"`
- `EMBEDDING_DIMENSIONS: Final[int] = 384`; `EMBEDDING_BATCH_SIZE: Final[int] = 32`; `SVD_COMPONENTS: Final[int] =
  100`
- `REPRESENTATIONS: Final[tuple[str, ...]] = ("tfidf", "tfidf_svd", "embeddings")`
- `build_representation(name: str) -> TransformerMixin`
- `class EmbeddingTransformer(BaseEstimator, TransformerMixin):  # type: ignore[misc]` (the only suppression this
  spec authorizes)
  - `__init__(self, model_name: str, revision: str) -> None`: stores `self.model_name`, `self.revision`, sets
    `self._slot = _ModelSlot()` (a private holder of the loaded model). No other work (scikit-learn `clone`
    contract). `_model` is a read-only property returning `self._slot.model`.
  - `fit(self, X: Sequence[str], y: object = None) -> EmbeddingTransformer`
  - `transform(self, X: Sequence[str]) -> np.ndarray`
  - `__sklearn_clone__(self) -> EmbeddingTransformer`: a new transformer with the same parameters that shares this
    one's `_slot`, so every clone made by `GridSearchCV` or MAPIE uses one loaded model
  - `_ModelSlot` (private): `model: SentenceTransformer | None`; its `__getstate__` returns `{"model": None}`
- `download(model_name: str, revision: str) -> None`
- `main(argv: Sequence[str] | None = None) -> int`
- Module tail: `if __name__ == "__main__":` then `raise SystemExit(main())`.

`SentenceTransformer` is imported as `from sentence_transformers import SentenceTransformer` at module level, so
unit tests replace `ml.representations.SentenceTransformer` with `monkeypatch.setattr`.

## Expected behavior

`build_representation(name)` returns a new unfitted object per call:

| `name` | Returned object |
|---|---|
| `"tfidf"` | `TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=2)` |
| `"tfidf_svd"` | `Pipeline([("tfidf", TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=2)), ("svd", TruncatedSVD(n_components=SVD_COMPONENTS, random_state=SEED)), ("normalize", Normalizer())])` |
| `"embeddings"` | `EmbeddingTransformer(EMBEDDING_MODEL_NAME, EMBEDDING_REVISION)` |

`EmbeddingTransformer`:
1. `fit` loads nothing and returns `self` (the model is pre-trained; folds see no fitted state).
2. `transform(X)`: `len(X) == 0` → error. When `self._model is None`, sets it to `SentenceTransformer(
   self.model_name, revision=self.revision, local_files_only=True, device="cpu")` and logs `INFO`
   `"embedding_model_loaded revision=%s"`.
3. `self._model.encode(list(X), batch_size=EMBEDDING_BATCH_SIZE, show_progress_bar=False, convert_to_numpy=True,
   normalize_embeddings=True)`; a result that is not `np.ndarray` → error; `astype(np.float32)`; shape other than
   `(len(X), EMBEDDING_DIMENSIONS)` → error. Returns rows of L2 norm 1.0 (tolerance 1e-5).
4. `_ModelSlot.__getstate__` returns `{"model": None}`, so a copied or persisted transformer never carries the
   weights (ADR-003); the next `transform` reloads from the cache. Copies made in one object graph (one `deepcopy`
   or one persisted bundle) keep sharing one slot.

`download(model_name, revision)`: `SentenceTransformer(model_name, revision=revision, device="cpu")` (the only call
without `local_files_only=True`, SEC-17); logs `INFO` `"embedding_downloaded revision=%s"`.

`main(argv)`:
1. `os.umask(0o077)` first (SEC-04).
2. `argparse.ArgumentParser(prog="ml.representations")` with one required flag `--download`
   (`action="store_true"`, `required=True`); a missing flag or an unknown argument exits through argparse with
   `SystemExit(2)`.
3. `download(EMBEDDING_MODEL_NAME, EMBEDDING_REVISION)`; on success prints `"downloaded=<revision>"` to stdout and
   returns `0`.
4. `AppError` → prints `"error=<code>"` to stderr (`code` of the error), returns `2`. Any other `Exception` →
   `logger.exception("representations_command_failed")`, prints `"error=internal_error"` to stderr, returns `1`.

## Edge cases and error handling

| Condition | Exception | Detail |
|---|---|---|
| `build_representation("bow")` | `InvalidInputError` | `"unknown representation: bow"` |
| `transform([])` | `InvalidInputError` | `"transform needs at least 1 text"` |
| `SentenceTransformer` raises `OSError` in `transform` | `InferenceError` (`from` it) | `"embedding model is not in the local cache"` |
| `encode` returns a `list` | `InferenceError` | `"embedding output is not an array"` |
| `encode` returns shape `(2, 10)` for 2 texts | `InferenceError` | `"embedding output has an unexpected shape"` |
| `SentenceTransformer` raises `OSError` in `download` | `InferenceError` (`from` it) | `"embedding model download failed"` |

`"tfidf_svd"` fitted on a vocabulary below 100 terms lets scikit-learn's `ValueError` `"n_components(100) must be <=
n_features(20)"` propagate unchanged (20 texts, verified); the real train split holds more than 100 terms. If an
existing test not listed here fails because of this change, the implementer does NOT modify it: report its name and
the reason.

## Acceptance tests (prose)

`FakeModel` (defined in `tests/unit/ml/test_embedding_transformer.py`) = a test class whose constructor records its positional and keyword arguments in a list and whose
`encode(texts, **kwargs)` records `kwargs` and returns `np.tile(np.eye(384, dtype=np.float64)[0], (len(texts), 1))`.
Unit tests patch `ml.representations.SentenceTransformer` with it; no unit test reaches the network or the cache.

`tests/unit/ml/test_representations.py` holds tests 1 to 4 and 6; `tests/unit/ml/test_embedding_transformer.py`
holds tests 5 and 7 to 21:
1. `test_constants`: `REPRESENTATIONS == ("tfidf", "tfidf_svd", "embeddings")`, `EMBEDDING_REVISION` equals the
   40-character value above, `EMBEDDING_DIMENSIONS == 384`, `SVD_COMPONENTS == 100`.
2. `test_build_representation_tfidf`: `get_params()` holds `ngram_range == (1, 2)`, `sublinear_tf is True`, `min_df
   == 2`; two calls return distinct objects.
3. `test_build_representation_tfidf_svd_vector`: fitted on the 120 texts `f"palabra{i} palabra{i + 1} comun"` (`i`
   = 0..119) → output shape `(120, 100)`, every row norm 1.0 (tolerance 1e-6); step names `["tfidf", "svd",
   "normalize"]`; `svd.random_state == 42`.
4. `test_build_representation_tfidf_svd_few_terms`: fitted on the first 20 of those texts → `ValueError` whose
   message contains `"n_components(100) must be <= n_features(20)"`.
5. `test_build_representation_embeddings`: returns an `EmbeddingTransformer` with `model_name ==
   EMBEDDING_MODEL_NAME` and `revision == EMBEDDING_REVISION`; `FakeModel` was not constructed.
6. `test_build_representation_rejects_unknown`: `"bow"` → `InvalidInputError` `"unknown representation: bow"`.
7. `test_embedding_fit_is_noop`: `fit(["a"])` returns the same object and constructs no `FakeModel`.
8. `test_embedding_transform_loads_cache_only`: `transform(["uno", "dos"])` → shape `(2, 384)`, dtype `float32`; the
   constructor kwargs equal `{"revision": EMBEDDING_REVISION, "local_files_only": True, "device": "cpu"}`; the
   encode kwargs equal `{"batch_size": 32, "show_progress_bar": False, "convert_to_numpy": True,
   "normalize_embeddings": True}`.
9. `test_embedding_transform_loads_once`: two `transform` calls construct `FakeModel` once.
10. `test_embedding_transform_rejects_empty`: `transform([])` → `"transform needs at least 1 text"`.
11. `test_embedding_transform_missing_cache`: the patched constructor raises `OSError("no cache")` →
    `InferenceError` `"embedding model is not in the local cache"` with `__cause__` the `OSError`.
12. `test_embedding_transform_rejects_list_output`: `encode` returns `[[0.0] * 384]` → `"embedding output is not an
    array"`.
13. `test_embedding_transform_rejects_bad_shape`: `encode` returns `np.zeros((2, 10))` for 2 texts → `"embedding
    output has an unexpected shape"`.
14. `test_embedding_state_drops_model`: after one `transform`, `copy.deepcopy(t)._model is None`;
    `sklearn.base.clone(t)` has equal `model_name` and `revision`; `t._model` is still the `FakeModel` instance
    and only one `FakeModel` was built.
14b. `test_embedding_clones_share_one_model`: clones taken before and after the first `transform`, and a clone of
    a clone, all `transform` without building a second `FakeModel`; `before_load._model is original._model`.
14c. `test_embedding_copied_clones_share_one_model_after_loading`: `copy.deepcopy([t, clone(t)])` gives two
    transformers with no model; after both `transform`, one `FakeModel` exists and both share it; `t._model is None`.
14d. `test_embedding_independent_transformers_do_not_share`: two transformers built separately build two
    `FakeModel` instances.
15. `test_download_uses_network_call`: patched constructor; `download("m", "r")` records args `("m",)` and kwargs
    `{"revision": "r", "device": "cpu"}` (no `local_files_only`).
16. `test_download_failure`: constructor raises `OSError` → `InferenceError` `"embedding model download failed"`.
17. `test_main_download_success`: `main(["--download"])` → `0`; stdout `"downloaded=e8f8c211226b894fcb81acc59f3b34ba3efd5f42\n"`;
    `os.umask` patched with a recorder was called first with `0o077`.
18. `test_main_requires_flag`: `main([])` → `SystemExit` with code `2`.
19. `test_main_app_error`: `download` patched to raise `InferenceError("embedding model download failed")` → `2`,
    stderr `"error=internal_error\n"` (the `code` of `InferenceError`, `docs/contracts.md` §2).
20. `test_main_unexpected_error`: `download` patched to raise `RuntimeError("x")` → `1`, stderr
    `"error=internal_error\n"`, one `ERROR` log record `"representations_command_failed"`.
21. `test_main_rejects_unknown_argument`: `main(["--download", "--other"])` → `SystemExit` with code `2`.

`tests/integration/test_embeddings_cache.py` (real cached model, no network):
1. `test_embeddings_shape_and_norm`: `build_representation("embeddings").fit_transform(["El curso fue claro.",
   "Las diapositivas llegaron tarde."])` → shape `(2, 384)`, dtype `float32`, row norms 1.0 (tolerance 1e-5).
2. `test_embeddings_deterministic`: two fresh transformers on the same 2 texts → `np.allclose(a, b, atol=1e-6)`.

## Out of scope

- Classifiers and grid search (spec 010); the bundle and manifest (specs 013, 014); serving-side embedding (spec 018).
- Fine-tuning the embedding model, GPU devices, other embedding models.

## Definition of Done

- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/python -m ml.representations --download` → stdout `downloaded=e8f8c211226b894fcb81acc59f3b34ba3efd5f42`,
      exit code 0; then `.venv/bin/pytest -q -m integration tests/integration/test_embeddings_cache.py` → `2 passed`.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed` (dependency rule and size limits).
- [ ] `grep -nE "# noqa|# type: ignore" ml/representations.py tests/unit/ml/test_representations.py
      tests/unit/ml/test_embedding_transformer.py tests/integration/test_embeddings_cache.py`
      → exactly 1 line, the `class EmbeddingTransformer` line ending in `# type: ignore[misc]`.
- [ ] `.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing` →
      `ml/representations.py` line coverage ≥ 80 %.
- [ ] `grep -c "local_files_only=True" ml/representations.py` → `1`; `grep -nE "pickle|joblib|trust_remote_code"
      ml/representations.py tests/unit/ml/test_representations.py tests/unit/ml/test_embedding_transformer.py` → no output.
- [ ] `bash scripts/security_grep.sh` → no output, exit code 0.
- [ ] `bash scripts/gate.sh` → last line `GATE OK`, exit code 0.
