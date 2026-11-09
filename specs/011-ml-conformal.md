# 011 - ML conformal
Riesgo: alto

## Objective

The selected polarity model reaches macro-F1 about 0.62 on noisy labels (`docs/analysis.md` §2), so the product must
say when it does not know (ADR-002). This spec adds `ml/conformal.py`, which wraps the selected pipeline in a MAPIE
1.6.0 `CrossConformalClassifier` calibrated on grouped train folds and reports empirical coverage, mean set size,
singleton rate and empty rate. It also adds `risk_coverage` to `ml/evaluation.py`, which produces the risk-coverage
curve data for `models/vNNN/report.json` (`docs/contracts.md` §9.4).

MAPIE 1.6.0 `CrossConformalClassifier` has no `predict_proba` (verified by `dir()`: only `conformity_scores`,
`fit_conformalize`, `predict`, `predict_set`, `reset`). Class probabilities therefore come from a separate object:
the selected pipeline refit on all train rows, produced by `ml.selection` (spec 010) and stored as
`polarity_pipeline` in the bundle (ADR-002 §2). This module never fits that object.

Measured on 2026-11-05 on the real `Dataset/` (618 rows, 380 template groups, first fold of
`StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)` as test, 124 test rows), with TF-IDF word 1-2
(`sublinear_tf=True`, `min_df=2`) and `LogisticRegression(class_weight="balanced", max_iter=1000)`, at
`confidence_level` 0.9:

| Measure | Test split | Over the 5 outer folds |
|---|---|---|
| Empirical coverage | 0.9435 | 0.9435, 0.8710, 0.9516, 0.9274, 0.9262 (min 0.8710, mean 0.9240) |
| Mean set size | 2.105 | 2.04 to 2.26 |
| Singleton rate / empty rate | 0.073 / 0.000 | — |

With `ComplementNB` instead of logistic regression the test coverage is 0.9597 and the 5-fold minimum is 0.8871.

Coverage tolerance: `COVERAGE_TOLERANCE = 0.05`, so the acceptance bound at `confidence_level` 0.9 is
`0.9 - 0.05 = 0.85` (ADR-002 consequences). Justification: the binomial standard error at 124 rows is
`sqrt(0.9 * 0.1 / 124) = 0.026941`; `1.96 * 0.026941 = 0.052804`, which rounds to 0.05. The lowest coverage of the 5
measured outer folds (0.8710) is above 0.85, and the test split (0.9435) is 0.0935 above it.

`alpha` is not read here: `ml.train` (spec 014) reads `conformal.alpha` from `config/app.json` with `json` and
passes `confidence_level = 1 - alpha` (`docs/contracts.md` §7).

## Depends on

001 (`scripts/gate.sh`, `scripts/security_grep.sh`, `tests/architecture/`), 010 (`ml/evaluation.py`,
`ml.selection.build_pipeline`), 008 (`ml.split.cv_splitter`, `template_groups`,
`grouped_split`), 007 (`ml.data.load_dataset`, `ml.schemas.SEED`), 002 (`api/domain/errors.py`).

## Governing files

- `ARCHITECTURE.md` §2 rule 4 (`ml` imports only `api.domain` and third parties), §3 step 4, §6 (≤ 20 statements per
  function, ≤ 6 arguments, ≤ 300 lines per module, `mypy --strict`, seed 42, fits on train rows only, no `print`,
  no `assert` in production code, custom exceptions only).
- `security-rules.md` SEC-05 (no comment text in logs), SEC-13 (no `pickle`, `eval`, `exec`).
- ADR-001 §3 (every cross-validation uses `StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)` with the
  template group ids), ADR-002 §1 and §2.
- `docs/contracts.md` §1.1 (`POLARITY_ORDER`), §2 (`InvalidInputError`), §8 (`ml.conformal`, `ml.evaluation`), §9.4.

## Files to create/modify

1. `ml/conformal.py` (new). No module of the `ml` layer exists in the repository yet; follow the module layout of
   `ml/split.py` once spec 008 is implemented.
2. `ml/evaluation.py` (modify, created by spec 010): add `risk_coverage` only. Spec 010 MUST NOT define
   `risk_coverage`; no other function of that file changes.
3. `tests/unit/ml/test_conformal.py` (new).
4. `tests/unit/ml/test_evaluation_risk_coverage.py` (new; separate from spec 010's `tests/unit/ml/test_evaluation.py`).
5. `tests/integration/test_conformal_dataset.py` (new; module-level `pytestmark = pytest.mark.integration`).

## External dependencies

None new. `mapie==1.6.0`, `scikit-learn==1.9.1`, `numpy==2.5.4` are pinned by spec 000. Verified in a Python 3.12.14
venv with these pins:
- `CrossConformalClassifier.__init__(self, estimator=LogisticRegression(), confidence_level=0.9,
  conformity_score="lac", cv=5, n_jobs=None, verbose=0, random_state=None)`.
- `fit_conformalize(self, X, y, groups=None, fit_params=None, predict_params=None)` returns `self`. A Python `list` of
  `str` as `X` raises `TypeError("Unable to find the number of features from X of type list ...")`; a
  `numpy.ndarray` with `dtype=object` works.
- `predict_set(self, X, conformity_score_params=None, agg_scores="mean")` returns `(y_pred, y_set)` with
  `y_pred.shape == (n,)` (int64) and `y_set.shape == (n, 3, 1)` (bool).
- The estimator passed in is cloned: after `fit_conformalize` the original pipeline is still unfitted.
- A pipeline ending in `LinearSVC` fails with `AttributeError("This 'Pipeline' has no attribute 'predict_proba'")`;
  `hasattr(pipeline, "predict_proba")` on an unfitted `Pipeline` is `True` for `LogisticRegression` and `False` for
  `LinearSVC`.
- `confidence_level=1.0` is accepted by MAPIE without error, so this module validates the range itself.

## Interfaces and types

`ml/conformal.py` (starts with `from __future__ import annotations`; Google docstrings):

- Constant `COVERAGE_TOLERANCE: float = 0.05`.
- `fit_cross_conformal(pipeline: Pipeline, texts: Sequence[str], y: np.ndarray, groups: np.ndarray,
  confidence_level: float) -> CrossConformalClassifier`.
- `conformal_report(model: CrossConformalClassifier, texts: Sequence[str], y: np.ndarray) -> dict[str, float]` with
  exactly the keys `"empirical_coverage"`, `"mean_set_size"`, `"singleton_rate"`, `"empty_rate"`, values Python
  `float`.

`ml/evaluation.py` (added function):

- `risk_coverage(probabilities: np.ndarray, y: np.ndarray) -> list[tuple[float, float]]`.

`Sequence` comes from `collections.abc`; `Pipeline` from `sklearn.pipeline`; `CrossConformalClassifier` from
`mapie.classification`. `y` holds class indices `0`, `1`, `2` in `POLARITY_ORDER`. Untyped-library imports rely on
the mypy configuration of spec 000; no `# type: ignore` and no `# noqa` are added.

## Expected behavior

`fit_cross_conformal`:
1. Validates the inputs in this order (first failure raises, see edge cases): `confidence_level`, lengths, classes,
   groups, `predict_proba`.
2. Builds `CrossConformalClassifier(estimator=pipeline, confidence_level=confidence_level, conformity_score="lac",
   cv=cv_splitter(), random_state=SEED)`.
3. Calls `fit_conformalize(np.asarray(texts, dtype=object), y, groups=groups)` and returns the fitted classifier. The
   `pipeline` argument is not mutated.

`conformal_report`:
1. Validates `len(texts) == len(y) >= 1`, then that every value of `y` is in `{0, 1, 2}`.
2. Calls `model.predict_set(np.asarray(texts, dtype=object), agg_scores="mean")` and keeps `sets = y_set[:, :, 0]`
   (shape `(n, 3)`, bool, columns in `POLARITY_ORDER`).
3. Returns `empirical_coverage` = mean of `sets[i, y[i]]`; `mean_set_size` = mean of the row sums;
   `singleton_rate` = share of rows with sum 1; `empty_rate` = share of rows with sum 0. No rounding.

`risk_coverage`:
1. Validates the shapes (see edge cases).
2. `confidence[i] = max(probabilities[i])`; `predicted[i] = argmax(probabilities[i])` (tie → lowest class index).
3. Orders rows by `confidence` descending with a stable sort (tie → lower row index first).
4. For `k = 1..n` over that order emits `(k / n, errors_k / k)`, where `errors_k` is the number of the first `k`
   rows with `predicted != y`. Returns the `n` points as Python floats, no rounding. `report.json` stores them as
   `[coverage, risk]` pairs (spec 013).

Logging: one `logging.getLogger(__name__)`; `fit_cross_conformal` logs at `INFO`
`"conformal_fitted rows=%d groups=%d confidence_level=%s"` with row count, distinct group count and the level. No
text is logged.

## Edge cases and error handling

All errors are `InvalidInputError` from `api/domain/errors.py`, raised before any fit, with these exact details:

| Function | Condition | Detail |
|---|---|---|
| `fit_cross_conformal` | `not 0.0 < confidence_level < 1.0` | `"confidence_level must be in (0, 1)"` |
| `fit_cross_conformal` | `len(texts)`, `len(y)`, `len(groups)` differ | `"texts, y and groups must have the same length"` |
| `fit_cross_conformal` | `set(y.tolist()) != {0, 1, 2}` | `"y must contain the classes 0, 1 and 2"` |
| `fit_cross_conformal` | fewer than 5 distinct values in `groups` | `"groups must hold at least 5 distinct values"` |
| `fit_cross_conformal` | `hasattr(pipeline, "predict_proba")` is `False` | `"pipeline must expose predict_proba"` |
| `conformal_report` | `len(texts) != len(y)` or `len(y) == 0` | `"texts and y must have the same non-zero length"` |
| `conformal_report` | a value of `y` outside `{0, 1, 2}`, a non-integer dtype or a `y` that is not 1-D | `"y must hold only the class indices 0, 1 and 2"` |
| `risk_coverage` | `y.ndim != 1` | `"y must be a 1-D array"` |
| `risk_coverage` | `probabilities.ndim != 2`, `probabilities.shape[1] != 3` or `shape[0] == 0` | `"probabilities must have shape (n, 3) with n >= 1"` |
| `risk_coverage` | `len(y) != probabilities.shape[0]` | `"probabilities and y must have the same length"` |

Errors raised by MAPIE or scikit-learn during the fit propagate unchanged (the `ml.train` CLI maps them to exit 1).
If an existing test not listed here fails because of this change, the implementer does NOT modify it: report its
name and the reason.

## Acceptance tests (prose)

Synthetic data for unit tests: `WORDS = ("malo", "regular", "bueno")`; for `i` in `0..149`, text
`f"{WORDS[i % 3]} curso numero {i}"`, `y[i] = i % 3`, `groups[i] = i // 3`. Pipeline:
`Pipeline([("features", TfidfVectorizer()), ("classifier", LogisticRegression(max_iter=1000))])`.

`tests/unit/ml/test_conformal.py`:
1. `test_fit_cross_conformal_returns_singleton_sets_for_clear_texts`: fit at 0.9; `predict_set(np.asarray(["malo
   curso", "regular curso", "bueno curso"], dtype=object), agg_scores="mean")` returns `y_pred == [0, 1, 2]` and `y_set[:, :, 0]` equal to
   `[[True, False, False], [False, True, False], [False, False, True]]` (verified at 0.9 and 0.8).
2. `test_fit_cross_conformal_leaves_input_pipeline_unfitted`: after the fit,
   `sklearn.utils.validation.check_is_fitted(pipeline)` raises `NotFittedError`.
3. `test_fit_cross_conformal_sets_lac_and_seed`: with `unittest.mock.patch("ml.conformal.CrossConformalClassifier",
   wraps=CrossConformalClassifier)` the single constructor call has keyword arguments `estimator` (the input
   pipeline), `confidence_level=0.9`, `conformity_score="lac"`, `random_state=42` and `cv` a `StratifiedGroupKFold`
   with `n_splits == 5`, `shuffle is True`, `random_state == 42`. (MAPIE 1.6.0 keeps these values only in private
   attributes, so the test checks the call, not the object.)
4. `test_fit_cross_conformal_rejects_confidence_level_out_of_range`: `0.0`, `1.0` and `1.5` each raise
   `InvalidInputError` with detail `"confidence_level must be in (0, 1)"`.
5. `test_fit_cross_conformal_rejects_length_mismatch`: 150 texts, 149 labels → detail
   `"texts, y and groups must have the same length"`.
6. `test_fit_cross_conformal_rejects_missing_class`: `y[i] = i % 2` → detail `"y must contain the classes 0, 1 and 2"`.
7. `test_fit_cross_conformal_rejects_too_few_groups`: `groups[i] = i % 4` → detail
   `"groups must hold at least 5 distinct values"`.
8. `test_fit_cross_conformal_rejects_pipeline_without_predict_proba`: classifier step `LinearSVC()` → detail
   `"pipeline must expose predict_proba"`.
9. `test_conformal_report_computes_set_metrics`: a test-local stub class whose `predict_set(X, agg_scores)` returns the tuple
   `(np.zeros(4, dtype=np.int64), y_set)` with `y_set` a bool array of shape `(4, 3, 1)` whose `[:, :, 0]` slice
   equals `[[1,0,0], [1,1,0], [0,0,0], [0,1,1]]`, for 4 texts with `y = [0, 1, 2, 0]` → exactly
   `{"empirical_coverage": 0.5, "mean_set_size": 1.25, "singleton_rate": 0.25, "empty_rate": 0.25}`; the stub records
   `agg_scores == "mean"`.
10. `test_conformal_report_rejects_empty_input`: `texts = []`, `y` empty → detail
    `"texts and y must have the same non-zero length"`.
11. `test_coverage_tolerance_value`: `COVERAGE_TOLERANCE == 0.05`.
12. `test_fit_cross_conformal_logs_counts_no_text`: with `caplog` at `INFO`, the synthetic data at 0.9 emits exactly
    one record of logger `ml.conformal`, whose message is `"conformal_fitted rows=150 groups=50
    confidence_level=0.9"`; no record message contains `"curso"`.
13. `test_conformal_report_rejects_length_mismatch`: 4 texts and `y` of length 3 → detail `"texts and y must have the
    same non-zero length"`.
14. `test_conformal_report_rejects_out_of_range_y` (parametrized `y = [0, 3]` and `y = [0, -1]`, 2 texts, the stub of
    test 9): detail `"y must hold only the class indices 0, 1 and 2"`.

`tests/unit/ml/test_evaluation_risk_coverage.py`:
1. `test_risk_coverage_orders_by_confidence`: probabilities `[[0.9, 0.05, 0.05], [0.2, 0.7, 0.1], [0.4, 0.35,
   0.25], [0.1, 0.3, 0.6]]`, `y = [0, 0, 0, 2]` → `[(0.25, 0.0), (0.5, 0.5), (0.75, 0.333333...), (1.0, 0.25)]`
   (compared with `abs` ≤ 1e-9; the third risk is `1 / 3`).
2. `test_risk_coverage_breaks_ties_by_row_index`: `[[0.5, 0.3, 0.2], [0.2, 0.5, 0.3]]`, `y = [1, 1]` →
   `[(0.5, 1.0), (1.0, 0.5)]`.
3. `test_risk_coverage_rejects_bad_shape` (parametrized): shape `(2, 2)`, shape `(0, 3)` and shape `(3,)` → detail
   `"probabilities must have shape (n, 3) with n >= 1"`.
4. `test_risk_coverage_rejects_length_mismatch`: shape `(2, 3)`, `y` of length 3 → detail
   `"probabilities and y must have the same length"`.

`tests/integration/test_conformal_dataset.py` (real `Dataset/`, SEC-09 exception; no embedding cache needed):
1. `test_conformal_coverage_on_test_split_within_tolerance`: `load_dataset(Path("Dataset"))`, `template_groups` on
   `text`; `y` = the index of each `polarity` value in `POLARITY_ORDER`; `grouped_split(y, groups)` gives `train_idx`
   and `test_idx`; the train texts, train `y` and train groups are the rows of `texts`, `y` and `groups` at
   `train_idx`, and the 124 test rows are those at `test_idx`; `fit_cross_conformal(build_pipeline("tfidf",
   "logistic_regression"), train texts, train y, train groups, 0.9)`; `conformal_report` on the 124 test rows gives
   `empirical_coverage >= 0.9 - COVERAGE_TOLERANCE` (0.85) and `0.0 <= mean_set_size <= 3.0`.
2. `test_risk_coverage_on_test_split`: `build_pipeline("tfidf", "logistic_regression")` fit on train rows;
   `risk_coverage(pipeline.predict_proba(test texts), test y)` has 124 points, the last point has coverage `1.0` and
   risk equal to `1 - accuracy` of `pipeline.predict` on the test rows (`abs` ≤ 1e-9).

## Out of scope

- Reading `config/app.json` and choosing `alpha` (spec 014). The bundle layout (spec 013). The decision agent (spec
  004). The HTTP adapter `SklearnPolarityModel` (spec 018).
- Fitting the probability pipeline (spec 010). Any conformity score other than `"lac"`. Mondrian or class-conditional
  coverage. Tuning the costs in `config/app.json`.

## Definition of Done

- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/pytest -q -m integration tests/integration/test_conformal_dataset.py` → `2 passed`, exit code 0.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed` (dependency rule and size limits).
- [ ] `grep -nE "# noqa|# type: ignore" ml/conformal.py ml/evaluation.py tests/unit/ml/test_conformal.py tests/unit/ml/test_evaluation_risk_coverage.py tests/integration/test_conformal_dataset.py`
      → no output.
- [ ] `.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing` → `ml/conformal.py`
      line coverage ≥ 80 % and the `Missing` column of the `ml/evaluation.py` row lists no line number inside
      `risk_coverage`.
- [ ] `grep -c "CrossConformalClassifier(" ml/conformal.py` → `1`.
- [ ] `grep -c 'agg_scores="mean"' ml/conformal.py` → `1`.
- [ ] `grep -nE "joblib|pickle|print\(" ml/conformal.py` → no output.
- [ ] `bash scripts/security_grep.sh` → no output, exit code 0.
- [ ] `bash scripts/gate.sh` → last line `GATE OK`, exit code 0.
