# 008 - ML grouped split
Riesgo: alto

## Objective

The 618 comments of `Dataset/` are generated from shared templates: near-identical texts appear in several files
and courses. A random row split leaks templates from train to test and inflates every metric (ADR-001). This spec
adds `ml/split.py`: template groups by character TF-IDF plus average-linkage clustering, the grouped 5-fold
splitter used by every cross-validation in `ml` (model selection 010, conformal 011, aspects 012), and the 80/20
train/test split (the first fold).

Measured on 2026-11-07 with scikit-learn 1.9.1 on `load_dataset(Path("Dataset"))["text"]`: 380 groups, the largest
holds 8 rows. First fold: 494 train rows, 124 test rows, 306 train groups, 74 test groups, no shared group; test
class counts `[41, 52, 31]`, train `[164, 207, 123]` (negative, neutral, positive). The 5 folds hold 124, 124, 124,
124 and 122 test rows.

## Depends on

001 (`scripts/gate.sh`, `scripts/security_grep.sh`, `tests/architecture/`); 002 (`api.domain.errors.InvalidInputError`,
`api.domain.entities.POLARITY_ORDER`); 007 (`ml.schemas.SEED`; `ml.data.load_dataset` in the integration test).

## Governing files

- `ARCHITECTURE.md` §2 rule 4, §3 step 2, §6 (≤ 20 statements, ≤ 6 arguments, complexity ≤ 8, ≤ 8 branches,
  modules ≤ 300 lines, `mypy --strict`, custom exceptions only, no `print`, no `assert` in production code).
- `docs/adr/ADR-001` (template grouping: `char_wb` 3-5 TF-IDF, cosine distance, average linkage,
  `distance_threshold` 0.7; first fold of `StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)` is the
  80/20 split; every CV in `ml` uses the same groups).
- `security-rules.md` SEC-05 (no text in logs), SEC-09 (synthetic unit fixtures).
- `docs/contracts.md` §8 (`ml.split`).

## Files to create/modify

1. `ml/split.py` (new). Reference pattern: `ml/data.py` (spec 007). Budget ≤ 120 lines.
2. `tests/unit/ml/test_split.py` (new).
3. `tests/integration/test_split_dataset.py` (new; module-level `pytestmark = pytest.mark.integration`).

No existing test changes expectation.

## External dependencies

None new (`scikit-learn==1.9.1`, `numpy==2.5.4`, spec 000). Verified at these pins:
`AgglomerativeClustering(n_clusters=None, metric="precomputed", linkage="average", distance_threshold=0.7)` accepts
a precomputed dense distance matrix and raises `ValueError` for 1 sample; `StratifiedGroupKFold.split` raises
`ValueError` `"Cannot have number of splits n_splits=5 greater than the number of groups: 4."` for 4 groups.

## Interfaces and types

`ml/split.py`:
- `N_SPLITS: Final[int] = 5`
- `TEMPLATE_DISTANCE_THRESHOLD: Final[float] = 0.7`
- `MIN_GROUP_TEXTS: Final[int] = 2`
- `template_groups(texts: Sequence[str]) -> np.ndarray`
- `cv_splitter() -> StratifiedGroupKFold`
- `grouped_split(y: np.ndarray, groups: np.ndarray) -> tuple[np.ndarray, np.ndarray]`

Return arrays are `numpy.ndarray` of dtype `int64`; `grouped_split` returns `(train_idx, test_idx)` positional
indices sorted ascending (the order `StratifiedGroupKFold.split` yields).

## Expected behavior

`template_groups(texts)`:
1. Validates the input (edge-case table).
2. `TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))` `.fit_transform(list(texts))`.
3. `sklearn.metrics.pairwise.cosine_distances` of that matrix (dense `(n, n)`).
4. `AgglomerativeClustering(n_clusters=None, metric="precomputed", linkage="average",
   distance_threshold=TEMPLATE_DISTANCE_THRESHOLD).fit_predict(distances)`.
5. Returns the labels as `int64`, length `n`, without renumbering.
6. Logs `INFO` `"template_groups rows=%d groups=%d largest=%d"` (rows, distinct labels, size of the largest group).

`cv_splitter()`: returns a new `StratifiedGroupKFold(n_splits=N_SPLITS, shuffle=True, random_state=SEED)` on each
call. Callers pass `X`, `y` and `groups` to `.split`; `X` only sets the row count (an object array of texts and
`np.zeros((n, 1))` give the same folds, verified).

`grouped_split(y, groups)`:
1. Validates the input (edge-case table).
2. `next(cv_splitter().split(np.zeros((len(y), 1)), y, groups))`.
3. Returns `(train_idx.astype(np.int64), test_idx.astype(np.int64))`.
4. Logs `INFO` `"grouped_split train=%d test=%d"`.

The split depends on group membership, not on the label values: adding 1000 to every group label gives the same
indices (verified).

## Edge cases and error handling

Every error is `InvalidInputError` (`api/domain/errors.py`) with this exact `detail`:

| Function | Condition | Detail |
|---|---|---|
| `template_groups` | fewer than 2 texts (0 or 1) | `"template_groups needs at least 2 texts"` |
| `template_groups` | a text that is `""` or only whitespace | `"template_groups texts must not be blank"` |
| `grouped_split` | `y` or `groups` not 1-D | `"y and groups must be 1-D arrays"` |
| `grouped_split` | `len(y) != len(groups)` | `"y and groups must have the same length"` |
| `grouped_split` | fewer than 5 distinct groups | `"groups must hold at least 5 distinct values"` |

Rules are checked top to bottom in the order of the table; the first failure wins (same convention as spec 002).
Validation runs before any scikit-learn call, so no `ValueError` from scikit-learn escapes for the inputs of the
table. Inputs outside the table are out of contract and scikit-learn's own exceptions escape unwrapped: a `y` with a
non-integer target type, and a `y` where every class has fewer than 5 rows (`ValueError` "n_splits=5 cannot be
greater than the number of members in each class."). A class with fewer members than folds, while another class has
at least 5, is left to scikit-learn's own warning (`UserWarning`, not an error). If an existing
test not listed here fails because of this change, the implementer does NOT modify it: report its name and the
reason.

## Acceptance tests (prose)

`T5` = the 5 synthetic texts, in order: `"El curso fue bastante bueno y claro."`, `"El curso fue bastante bueno y muy
claro."`, `"Las diapositivas llegaron tarde siempre."`, `"Las diapositivas llegaron tarde casi siempre."`,
`"Horario incomodo los lunes por la noche."` (cosine distances 0.06 between texts 0 and 1, 0.066 between 2 and 3,
≥ 0.987 for every other pair).

`tests/unit/ml/test_split.py`:
1. `test_template_groups_partitions_templates`: `T5` → labels where `labels[0] == labels[1]`, `labels[2] ==
   labels[3]`, and labels 0, 2 and 4 are pairwise different; 3 distinct labels; dtype `int64`; length 5.
2. `test_template_groups_is_deterministic`: two calls on `T5` return equal arrays.
3. `test_template_groups_two_distinct_texts`: `T5[0]` and `T5[4]` → 2 distinct labels.
4. `test_template_groups_rejects_too_few` (parametrized `[]`, `[T5[0]]` and `[""]`) → `"template_groups needs at
   least 2 texts"` (the case `[""]` fixes the order: the count rule wins over the blank rule).
5. `test_template_groups_rejects_blank` (parametrized `[T5[0], ""]` and `[T5[0], "   "]`) → `"template_groups texts
   must not be blank"`.
6. `test_template_groups_logs_counts`: with `caplog` at `INFO`, `T5` emits `"template_groups rows=5 groups=3
   largest=2"` and no record holds `"curso"`.
7. `test_cv_splitter_configuration`: `n_splits == 5`, `shuffle is True`, `random_state == 42`; two calls return
   distinct objects.
8. `test_grouped_split_vector`: `y = np.arange(30) % 3`, `groups = np.arange(30) // 3` → `test_idx` equals `[6, 7,
   8, 24, 25, 26]`, `train_idx` holds the other 24 indices in ascending order, both dtype `int64`.
9. `test_grouped_split_keeps_groups_apart`: same vector → no group value appears in both index sets.
10. `test_grouped_split_ignores_group_label_values`: same vector with `groups + 1000` → the same two arrays.
11. `test_grouped_split_rejects_2d`: `y` of shape `(30, 1)` → `"y and groups must be 1-D arrays"`.
12. `test_grouped_split_rejects_length_mismatch`: `y` of 30 rows, `groups` of 29 → `"y and groups must have the
    same length"`.
13. `test_grouped_split_rejects_few_groups`: `y = np.arange(30) % 3`, `groups = np.arange(30) % 4` → `"groups must
    hold at least 5 distinct values"`.
14. `test_grouped_split_rejects_2d_groups`: `y = np.arange(30) % 3`, `groups` of shape `(30, 1)` → `"y and groups
    must be 1-D arrays"`.
15. `test_grouped_split_checks_shape_before_length`: `y` of shape `(30, 1)` and `groups` of 29 items → `"y and
    groups must be 1-D arrays"`.

`tests/integration/test_split_dataset.py` (real `Dataset/`, SEC-09 exception; `texts` = `load_dataset(Path(
"Dataset"))["text"].tolist()`, `y` = polarity mapped through `POLARITY_ORDER` indices, `groups =
template_groups(texts)`):
1. `test_dataset_template_groups`: 380 distinct groups, the largest holds 8 rows.
2. `test_dataset_grouped_split`: `grouped_split(y, groups)` → 494 train rows, 124 test rows, 306 and 74 distinct
   groups, no shared group, test class counts `[41, 52, 31]`.
3. `test_dataset_cv_folds`: `cv_splitter().split(np.asarray(texts, dtype=object), y, groups)` → test sizes `[124,
   124, 124, 124, 122]`, and its first fold equals `grouped_split(y, groups)`.

## Out of scope

- Features and classifiers (specs 009, 010); persisting `test_row_keys` in the report (spec 014).
- Tuning the threshold 0.7 or the n-gram range (fixed by ADR-001).

## Definition of Done

- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/pytest -q -m integration tests/integration/test_split_dataset.py` → `3 passed`, exit code 0.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed` (dependency rule and size limits).
- [ ] `grep -nE "# noqa|# type: ignore" ml/split.py tests/unit/ml/test_split.py tests/integration/test_split_dataset.py`
      → no output.
- [ ] `.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing` → `ml/split.py` line
      coverage ≥ 80 %.
- [ ] `grep -c "random_state=SEED" ml/split.py` → `1`; `grep -c "distance_threshold=TEMPLATE_DISTANCE_THRESHOLD"
      ml/split.py` → `1`.
- [ ] `grep -nE "pickle|joblib|print\(" ml/split.py` → no output.
- [ ] `bash scripts/security_grep.sh` → no output, exit code 0.
- [ ] `bash scripts/gate.sh` → last line `GATE OK`, exit code 0.
