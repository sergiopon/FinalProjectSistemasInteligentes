# 010 - ML model selection
Riesgo: alto

## Objective

The polarity model is chosen by grouped cross-validation over 3 representations (spec 009) and 8 classifiers on the
train split only (spec 008), scored by macro-F1, and then measured once on the held-out test split. When this spec
is done, `ml/selection.py` builds every candidate pipeline, runs the grid search on the shared grouped folds, applies
one deterministic winner rule and refits the winner; `ml/evaluation.py` returns the test metrics and the per-file
macro-F1 that the report stores (`docs/contracts.md` §9.4).

Measured on 2026-11-07 (scikit-learn 1.9.1) on the 494 train rows of the real dataset, representation `"tfidf"`,
best grid point per classifier, mean CV macro-F1: dummy 0.1969, logistic_regression 0.6078, naive_bayes 0.605,
random_forest 0.6028, extra_trees 0.629 (std 0.0493), knn 0.5271, sgd_log_loss 0.6002; `"tfidf_svd"` peaks at
0.6092; the two representations together run in about 120 s. Test macro-F1 after refit: extra_trees 0.6312,
logistic_regression 0.6071, dummy 0.197.

## Depends on

008 (`ml.split.cv_splitter`, `grouped_split`, `template_groups`), 009 (`ml.representations.build_representation`,
`REPRESENTATIONS`); 007 through both (`ml.schemas.SEED`, `ml.data.load_dataset`).

## Governing files

- `ARCHITECTURE.md` §2 rule 4, §3 steps 3-4, §6 (≤ 20 statements, ≤ 6 arguments, complexity ≤ 8, ≤ 8 branches,
  modules ≤ 300 lines, classes ≤ 150 lines, `mypy --strict`, custom exceptions only, no `print`, no `assert` in
  production code).
- `docs/adr/ADR-001` §3 (every later CV uses `StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)` and
  the template groups), `docs/adr/ADR-002` decision 2 (class probabilities come from the refit selected pipeline).
  Design choices of this spec, not ADR quotes: no `CalibratedClassifierCV` (it would need an inner CV that ADR-001
  does not define) and `linear_svm` never wins (a raw `LinearSVC` has no `predict_proba`).
- `security-rules.md` SEC-05 (no text in logs), SEC-09 (synthetic unit fixtures).
- `docs/contracts.md` §8 (`ml.selection`, `ml.evaluation`), §9.4 (`selection`, `test`, `per_file_macro_f1`).

## Files to create/modify

1. `ml/selection.py` (new). Reference pattern: `ml/split.py` (spec 008). Budget ≤ 220 lines.
2. `ml/evaluation.py` (new; spec 011 later adds `risk_coverage`). Same reference pattern. Budget ≤ 120 lines.
3. `tests/unit/ml/test_selection.py` (new).
4. `tests/unit/ml/test_evaluation.py` (new).
5. `tests/integration/test_selection_dataset.py` (new; module-level `pytestmark = pytest.mark.integration`; needs
   the embedding cache of spec 009).

No existing test changes expectation.

## External dependencies

None new (`scikit-learn==1.9.1`, `numpy==2.5.4`). Verified at this pin: `GridSearchCV(..., refit=False)` exposes
`best_score_`, `best_index_`, `best_params_` and `cv_results_["std_test_score"]`; with `param_grid={}` it scores one
candidate; ties in `rank_test_score` resolve to the first grid point; `hasattr(pipeline, "predict_proba")` is
`False` for a pipeline ending in `LinearSVC` and `True` for the other 7 classifiers.

## Interfaces and types

`ml/selection.py`:
- `CLASSIFIERS: Final[tuple[str, ...]] = ("dummy", "logistic_regression", "linear_svm", "naive_bayes",
  "random_forest", "extra_trees", "knn", "sgd_log_loss")`
- `build_pipeline(representation: str, classifier: str) -> Pipeline`: `Pipeline([("features",
  build_representation(representation)), ("classifier", _estimator(representation, classifier))])`, unfitted, new
  objects per call. The representation is built first, so when both names are unknown the representation error is
  the one raised. The classifier name is validated against the factory mapping inside `_estimator`, not against
  `CLASSIFIERS` (tests 8 and 9 patch `CLASSIFIERS` only for the grid loop).
- `@dataclass(frozen=True, slots=True) class SelectionResult`: `representation: str`, `classifier: str`,
  `best_params: dict[str, object]`, `cv_macro_f1_mean: float`, `cv_macro_f1_std: float`, `pipeline: Pipeline`
  (fitted), `selection: tuple[dict[str, object], ...]`.
- `select_model(texts: Sequence[str], y: np.ndarray, groups: np.ndarray) -> SelectionResult`
- Imports `N_SPLITS` and `cv_splitter` from `ml.split` (spec 008 exports `N_SPLITS: Final[int] = 5`).
- Private helpers, each ≤ 20 statements, ≤ 8 branches, complexity ≤ 8 (ruff `PLR0915`, `PLR0912`, `C901`), with no
  `if`/`elif` chain over the 8 classifier names:
  - `_estimator(representation: str, classifier: str) -> object`: looks the classifier up in a mapping of factories
    built inside the function (the `naive_bayes` factory picks `ComplementNB` when `representation == "tfidf"`, else
    `GaussianNB`); an absent name raises `InvalidInputError(f"unknown classifier: {classifier}")`.
  - `_param_grid(representation: str, classifier: str) -> dict[str, list[object]]`: looks `_GRIDS[key]` up in the
    module constant `_GRIDS` (the grids of the table below, keys of the inner dicts without prefix) with `key =
    "naive_bayes_dense"` when `classifier == "naive_bayes"` and `representation != "tfidf"`, else `classifier`;
    returns the grid with every key prefixed `classifier__`.
  - `_validate_selection_input(texts: Sequence[str], y: np.ndarray, groups: np.ndarray) -> None`: step 1, checks in
    the order lengths, classes, groups; the group minimum is `N_SPLITS`.
  - `_score_candidate(X: np.ndarray, y: np.ndarray, groups: np.ndarray, representation: str, classifier: str) ->
    dict[str, object]`: steps 2 and 3 for one candidate (grid search, selection row, the `candidate_scored` log).
  - `_pick_winner(rows: Sequence[dict[str, object]]) -> dict[str, object]`: steps 4 and 5 (eligibility through
    `build_pipeline(...)`, minimum key, the `"no candidate exposes predict_proba"` error). Fields read from a row
    are narrowed with `str(...)`, `float(...)` and `typing.cast`.

`ml/evaluation.py`:
- Private helper `_validate_labels(texts: Sequence[str], y: np.ndarray) -> None`: length check, then class-value
  check (edge-case table order), used by `evaluate` and `per_file_macro_f1`.
- `evaluate(pipeline: Pipeline, texts: Sequence[str], y: np.ndarray) -> dict[str, object]`
- `per_file_macro_f1(pipeline: Pipeline, texts: Sequence[str], y: np.ndarray, source_files: Sequence[str]) ->
  dict[str, float]`

Labels are the class indices of `POLARITY_ORDER` (`0` negative, `1` neutral, `2` positive).

## Expected behavior

Candidate estimators (`random_state=SEED` where listed) and grids:

| `classifier` | Estimator | Grid |
|---|---|---|
| `dummy` | `DummyClassifier(strategy="prior")` | `{}` |
| `logistic_regression` | `LogisticRegression(class_weight="balanced", max_iter=1000)` | `C`: `[0.1, 1.0, 10.0]` |
| `linear_svm` | `LinearSVC(class_weight="balanced", random_state=SEED)` | `C`: `[0.1, 1.0, 10.0]` |
| `naive_bayes`, representation `"tfidf"` | `ComplementNB()` | `alpha`: `[0.1, 0.5, 1.0]` |
| `naive_bayes`, other representations | `GaussianNB()` | `var_smoothing`: `[1e-9, 1e-6, 1e-3]` |
| `random_forest` | `RandomForestClassifier(n_estimators=300, class_weight="balanced", random_state=SEED)` | `min_samples_leaf`: `[1, 3]` |
| `extra_trees` | `ExtraTreesClassifier(n_estimators=300, class_weight="balanced", random_state=SEED)` | `min_samples_leaf`: `[1, 3]` |
| `knn` | `KNeighborsClassifier(metric="cosine")` | `n_neighbors`: `[5, 15, 25]` |
| `sgd_log_loss` | `SGDClassifier(loss="log_loss", class_weight="balanced", max_iter=1000, random_state=SEED)` | `alpha`: `[1e-5, 1e-4, 1e-3]` |

`ComplementNB` needs non-negative features, so it applies only to `"tfidf"`. `linear_svm` is scored and reported but
never wins (no `predict_proba`; no calibration, a design choice of this spec).

`select_model(texts, y, groups)`:
1. `_validate_selection_input` (edge-case table; first failure wins). `X = np.asarray(texts, dtype=object)`.
2. For each `representation` in `REPRESENTATIONS` and each `classifier` in `CLASSIFIERS`, in that order (both names
   are read from the module globals at call time), `_score_candidate` runs: `GridSearchCV(build_pipeline(representation, classifier),
   _param_grid(representation, classifier), scoring="f1_macro", cv=cv_splitter(), refit=False, n_jobs=1,
   error_score="raise").fit(X, y, groups=groups)`.
3. Per candidate, one selection row `{"representation": str, "classifier": str, "best_params": dict(best_params_),
   "cv_macro_f1_mean": float(best_score_), "cv_macro_f1_std": float(cv_results_["std_test_score"][best_index_])}`;
   logs `INFO` `"candidate_scored representation=%s classifier=%s mean=%.4f std=%.4f"`.
4. Eligible rows: those whose `build_pipeline(representation, classifier)` has the attribute `predict_proba`.
5. Winner: the eligible row with the minimum of `(-cv_macro_f1_mean, cv_macro_f1_std, representation, classifier)`.
6. Refit (in `select_model`): `build_pipeline(representation, classifier).set_params(**best_params).fit(X, y)` on all given rows.
7. Logs `INFO` `"model_selected representation=%s classifier=%s mean=%.4f"`; returns `SelectionResult` with
   `selection` = all rows in step-2 order.

`evaluate(pipeline, texts, y)`: validates, predicts `pipeline.predict(np.asarray(texts, dtype=object))`, and returns
(all values Python `float` or `int`, `labels=[0, 1, 2]`, `zero_division=0`):
`{"accuracy": float, "macro_precision": float, "macro_recall": float, "macro_f1": float, "per_class": {"negative":
{"precision", "recall", "f1", "support"}, "neutral": {...}, "positive": {...}}, "confusion_matrix": list[list[int]]}`
(rows true class, columns predicted class, both in `POLARITY_ORDER`; `per_class` keys are the `Polarity` values).

`per_file_macro_f1(pipeline, texts, y, source_files)`: one prediction pass, then for each distinct file name (keys
sorted ascending) `f1_score(y_file, pred_file, labels=[0, 1, 2], average="macro", zero_division=0)` as `float`.

## Edge cases and error handling

Every error is `InvalidInputError` with this exact `detail`:

| Function | Condition | Detail |
|---|---|---|
| `build_pipeline` | `classifier` `"svm"` | `"unknown classifier: svm"` |
| `build_pipeline` | `representation` `"bow"` | `"unknown representation: bow"` (from spec 009) |
| `build_pipeline` | `representation` `"bow"` and `classifier` `"svm"` | `"unknown representation: bow"` (representation wins) |
| `select_model` | lengths of `texts`, `y`, `groups` differ | `"texts, y and groups must have the same length"` |
| `select_model` | `set(y) != {0, 1, 2}` | `"y must contain the classes 0, 1 and 2"` |
| `select_model` | fewer than 5 distinct groups | `"groups must hold at least 5 distinct values"` |
| `select_model` | no eligible candidate | `"no candidate exposes predict_proba"` |
| `select_model` | several conditions fail | the first of the three `select_model` rows above, in table order |
| `evaluate`, `per_file_macro_f1` | `len(texts) != len(y)` or 0 rows | `"texts and y must have the same non-zero length"` |
| `evaluate`, `per_file_macro_f1` | a `y` value outside `{0, 1, 2}` | `"y must hold only the class indices 0, 1 and 2"` |
| `per_file_macro_f1` | `len(source_files) != len(y)` (checked after the two rows above) | `"source_files must have the same length as y"` |

`evaluate` on rows that hold only 1 or 2 of the 3 classes returns 0.0 for the absent classes (spec 029 passes
gold rows). If an existing test not listed here fails because of this change, the implementer does NOT modify it:
report its name and the reason.

## Acceptance tests (prose)

`S60` = 60 texts `f"{('malo', 'regular', 'bueno')[i % 3]} curso numero {i}"` (`i` = 0..59), `y = np.arange(60) %
3`, `groups = np.arange(60) // 3`. Selection unit tests patch `ml.selection.REPRESENTATIONS` to `("tfidf",)`.
`STUB` = a test object whose `predict` returns `np.array([0, 1, 1, 1, 2, 0])`; `Y6 = np.array([0, 0, 1, 1, 2, 2])`.

`tests/unit/ml/test_selection.py`:
1. `test_classifiers_constant`: `CLASSIFIERS` equals the 8-name tuple above.
2. `test_build_pipeline_steps` (parametrized over `CLASSIFIERS`, representation `"tfidf"`): step names `["features", "classifier"]`; two calls
   return distinct objects.
3. `test_build_pipeline_naive_bayes_depends_on_representation`: `"tfidf"` → `ComplementNB`; `"tfidf_svd"` and
   `"embeddings"` → `GaussianNB`.
4. `test_build_pipeline_predict_proba`: `hasattr(..., "predict_proba")` is `False` for `"linear_svm"` and `True`
   for the other 7 on `"tfidf"`.
5. `test_build_pipeline_rejects_unknown`: `("tfidf", "svm")` → `"unknown classifier: svm"`; `("bow", "dummy")` →
   `"unknown representation: bow"`; `("bow", "svm")` → `"unknown representation: bow"`.
6. `test_select_model_vector`: `S60` → `representation == "tfidf"`, `classifier == "extra_trees"`, `best_params ==
   {"classifier__min_samples_leaf": 1}`, `cv_macro_f1_mean == 1.0`, `cv_macro_f1_std == 0.0`; 8 selection rows in
   `CLASSIFIERS` order; the dummy row mean `0.16666666666666666` (tolerance 1e-9) and std 0.0; the `linear_svm` row
   mean 1.0 with `best_params == {"classifier__C": 0.1}`.
7. `test_select_model_refits_winner`: from that result, `pipeline.predict(np.asarray(["bueno curso", "malo
   curso"], dtype=object))` → `[2, 0]`; `predict_proba` of `"bueno curso"` has argmax 2 and value ≥ 0.9.
8. `test_select_model_excludes_no_proba`: `CLASSIFIERS` patched to `("dummy", "linear_svm")` → winner `"dummy"`
   although `linear_svm` scores 1.0.
9. `test_select_model_no_eligible`: `CLASSIFIERS` patched to `("linear_svm",)` → `"no candidate exposes
   predict_proba"`.
10. `test_select_model_rejects_length_mismatch`: `groups` of 59 rows → `"texts, y and groups must have the same
    length"`.
11. `test_select_model_rejects_missing_class`: `y = np.arange(60) % 2` → `"y must contain the classes 0, 1 and 2"`.
12. `test_select_model_rejects_few_groups`: `groups = np.arange(60) % 4` → `"groups must hold at least 5 distinct
    values"`.
13. `test_select_model_logs_no_text`: with `caplog` at `INFO`, 8 `"candidate_scored"` records, 1 `"model_selected
    representation=tfidf classifier=extra_trees mean=1.0000"` record, no record holding `"curso"`.

`tests/unit/ml/test_evaluation.py`:
1. `test_evaluate_vector`: `STUB`, 6 texts `"t0"`..`"t5"`, `Y6` → accuracy `0.6666666666666666`, macro precision
   `0.7222222222222222`, macro recall `0.6666666666666666`, macro F1 `0.6555555555555556` (tolerance 1e-9);
   `per_class` precision `[0.5, 0.6666666666666666, 1.0]`, recall `[0.5, 1.0, 0.5]`, F1 `[0.5, 0.8,
   0.6666666666666666]`, support `[2, 2, 2]` for negative, neutral, positive; confusion matrix `[[1, 1, 0], [0, 2,
   0], [1, 0, 1]]`; every value is a Python `float` or `int`, and `json.dumps` of the result succeeds.
2. `test_evaluate_absent_class`: texts `["t0", "t1"]`, `y = np.array([0, 0])`, stub whose `predict` returns
   `np.array([0, 0])` → macro F1 `0.3333333333333333`, positive
   F1 `0.0`, confusion matrix `[[2, 0, 0], [0, 0, 0], [0, 0, 0]]`, no warning raised.
3. `test_evaluate_rejects_length` (parametrized: 6 texts `"t0"`..`"t5"` with `Y6[:5]`; `[]` with `np.array([],
   dtype=np.int64)`) → `"texts and y must have the same non-zero length"`.
4. `test_evaluate_rejects_class_values`: texts `["t0", "t1"]`, `y = np.array([0, 3])` → `"y must hold only the class
   indices 0, 1 and 2"`.
5. `test_per_file_macro_f1_vector`: `STUB`, `Y6`, `source_files` `["a.csv"] * 3 + ["b.csv"] * 3` → `{"a.csv":
   0.4444444444444444, "b.csv": 0.5555555555555555}` (tolerance 1e-9), keys in that order.
6. `test_per_file_macro_f1_rejects_source_file_count`: `STUB`, 6 texts, `Y6`, 5 source files `["a.csv"] * 5` →
   `"source_files must have the same length as y"`.
7. `test_per_file_macro_f1_rejects_length` (parametrized: 6 texts with `Y6[:5]`; `[]` with `np.array([],
   dtype=np.int64)`; `source_files = ["a.csv"] * len(y)` in both) → `"texts and y must have the same non-zero
   length"`.
8. `test_per_file_macro_f1_rejects_class_values`: texts `["t0", "t1"]`, `y = np.array([0, 3])`, `source_files =
   ["a.csv", "a.csv"]` → `"y must hold only the class indices 0, 1 and 2"`.

`tests/integration/test_selection_dataset.py` (real `Dataset/` and cached embeddings): rows from
`load_dataset(Path("Dataset"))`, `y` from `POLARITY_ORDER` indices, `groups = template_groups(texts)`, train and
test from `grouped_split(y, groups)`; `result = select_model(train texts, train y, train groups)`.
The `embeddings` representation was not measured when this spec was written (the encoder is re-run in every CV fit,
so the run takes longer than the 120 s measured for the two other representations). The thresholds below are
conservative bounds from the `tfidf` measurement above and the 0.62 baseline of `docs/analysis.md`, not measured
values for `embeddings`.
1. `test_dataset_selection_table`: 24 selection rows; best `cv_macro_f1_mean` ≥ 0.50; every `dummy` row mean < 0.25;
   `result.classifier != "linear_svm"`.
2. `test_dataset_test_metrics`: `evaluate(result.pipeline, test texts, test y)["macro_f1"]` ≥ 0.45; the keys of
   `per_file_macro_f1` (test rows with their `source_file`) are a non-empty subset of the 3 file names of
   `Dataset/` (the 20-row file may have no test row).

## Out of scope

- `risk_coverage` (spec 011); conformal wrapping (spec 011); writing the report and manifest (specs 013, 014).
- Probability calibration, class rebalancing beyond `class_weight="balanced"`, parallel jobs (`n_jobs=1` fixed).

## Definition of Done

- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/pytest -q -m integration tests/integration/test_selection_dataset.py` → `2 passed`, exit code 0.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed` (dependency rule and size limits).
- [ ] `grep -nE "# noqa|# type: ignore" ml/selection.py ml/evaluation.py tests/unit/ml/test_selection.py tests/unit/ml/test_evaluation.py tests/integration/test_selection_dataset.py`
      → no output.
- [ ] `.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing` → `ml/selection.py`
      and `ml/evaluation.py` each ≥ 80 % line coverage.
- [ ] `grep -c "cv=cv_splitter()" ml/selection.py` → `1`; `grep -nE "CalibratedClassifierCV|KFold\(|cross_val_score"
      ml/selection.py` → no output.
- [ ] `grep -nE "pickle|joblib|print\(" ml/selection.py ml/evaluation.py` → no output.
- [ ] `bash scripts/security_grep.sh` → no output, exit code 0.
- [ ] `bash scripts/gate.sh` → last line `GATE OK`, exit code 0.
