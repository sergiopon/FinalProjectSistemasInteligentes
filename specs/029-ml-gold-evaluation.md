# 029 - ML gold-set evaluation
Riesgo: alto

## Objective

The dataset labels are noisy: the global label agrees with the sentiment of its own aspects in about 50 % of rows
and aspect labels have low recall (`docs/analysis.md` §2, findings 1 and 2), so test metrics against them understate
or misstate model quality. Spec 015 produces two annotator sheets over the same sample (`gold/sheet_a.csv`,
`gold/sheet_b.csv`). This spec adds the command-line module `ml.gold_eval`, which evaluates the active model bundle
against the rows where both annotators agree: polarity metrics, conformal coverage, the share of agreed rows whose
dataset label matches the gold label, and per-aspect presence precision, recall and F1. It writes
`reports/gold_eval.json`, which holds counts and metrics only, never comment text or row keys.

## Depends on

013 (`ml.artifact.load_verified`, bundle and report files), 015 (gold sheets). Contracts used: `docs/contracts.md`
§1.1, §2, §4.4, §8 (`ml.data`, `ml.evaluation`, `ml.conformal`, `ml.artifact`), §9.1, §9.3, §9.4, §10.

## Governing files

- `ARCHITECTURE.md` §2 (layer `ml`: imports `api.domain` and third parties only; rule 4), §6 (≤ 20 statements per
  function, ≤ 6 arguments, ≤ 300 lines per module, `mypy --strict`, only `AppError` subclasses, generic `except`
  only in `main()`, one logger per module, `key=value` logs, seed 42).
- `security-rules.md` SEC-04 (umask first in `main()`, files 0600, directories 0700), SEC-05 (no comment text in
  logs), SEC-07 (`ml` writes only under `data/`, `models/`, `reports/`, `gold/`), SEC-10 (`reports/` ignored),
  SEC-11 (input files validated), SEC-12 (`resolve_within` on every output path, fixed file name), SEC-13 (`json`
  only), SEC-14 (no `joblib.load` here: loading goes through `ml.artifact.load_verified`).
- ADR-003 (verified bundles, registry).

## Files to create/modify

1. `ml/gold_eval.py` (new). No existing `ml` module exists yet; follow the module layout of `docs/contracts.md` §8.
2. `tests/unit/ml/test_gold_eval_sheets.py` (new): sheet reading, agreement and metric functions.
3. `tests/unit/ml/test_gold_eval_report.py` (new): `evaluate_gold`, `write_report`, `main`.

No existing test changes expectation.

## External dependencies

None new. Uses pinned pandas `==3.1.1`, numpy `==2.5.4`, scikit-learn `==1.9.1`, mapie `==1.6.0` (`CONTEXT.md`).
Verified at these pins: `pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")` keeps empty
cells as `""` and strips the BOM from the first header; `sklearn.metrics.precision_score`, `recall_score`,
`f1_score` accept `zero_division=0.0`; a `Pipeline` ending in `OneVsRestClassifier(LogisticRegression())` fitted on
an (n, 9) indicator matrix returns `predict_proba` of shape (n, 9) with one independent score per column;
`mapie.classification.CrossConformalClassifier(estimator=...)` can be constructed unfitted.

## Interfaces and types

Module `ml/gold_eval.py` starts with `from __future__ import annotations`; logger `logging.getLogger(__name__)`.

Constants:
- `GOLD_SHEETS: tuple[str, str] = ("sheet_a.csv", "sheet_b.csv")`
- `REPORT_NAME: str = "gold_eval.json"`
- `REPORTS_DIR: Path = Path("reports")`
- `ASPECT_COLUMNS: tuple[str, ...] = tuple(f"aspect_{group.value}" for group in ASPECT_ORDER)` (9 names)
- `GOLD_COLUMNS: tuple[str, ...] = ("row_key", "polarity", *ASPECT_COLUMNS)` (11 names)
- `POLARITY_VALUES: frozenset[str] = frozenset(p.value for p in POLARITY_ORDER)`
- `ASPECT_VALUES: frozenset[str] = POLARITY_VALUES | {""}`

Functions (no others public):
- `read_gold_sheet(path: Path, gold_dir: Path) -> pd.DataFrame`
- `agreed_polarity(sheet_a: pd.DataFrame, sheet_b: pd.DataFrame) -> pd.DataFrame` (columns `row_key`, `polarity`)
- `agreed_presence(sheet_a: pd.DataFrame, sheet_b: pd.DataFrame, group: AspectGroup) -> pd.DataFrame` (columns
  `row_key`, `present` of dtype `bool`)
- `presence_metrics(gold: Sequence[bool], predicted: Sequence[bool]) -> dict[str, float | int]` (keys `agreed_rows`,
  `gold_present`, `precision`, `recall`, `f1`)
- `active_version(models_dir: Path) -> str`
- `evaluate_gold(gold_dir: Path, dataset_dir: Path, models_dir: Path) -> dict[str, object]`
- `write_report(reports_dir: Path, report: Mapping[str, object]) -> Path`
- `main(argv: Sequence[str] | None = None) -> int`

Private helpers are allowed to keep every function ≤ 20 statements; their names start with `_`.

Imports used (exact): `api.domain.entities` (`ASPECT_ORDER`, `POLARITY_ORDER`, `AspectGroup`, `Polarity`),
`api.domain.errors` (`AppError`, `DatasetError`, `InvalidInputError`, `ModelUnavailableError`), `api.domain.safety` (`resolve_within`),
`ml.data` (`validate_input_file`, `load_dataset`), `ml.evaluation` (`evaluate`), `ml.conformal`
(`conformal_report`), `ml.artifact` (`load_verified`), `sklearn.pipeline.Pipeline`,
`mapie.classification.CrossConformalClassifier`, `sklearn.metrics` (`precision_score`, `recall_score`,
`f1_score`). Untyped-library imports rely on the mypy configuration of spec 000; no `# type: ignore` and no `# noqa` are added.

Report schema written to `reports/gold_eval.json` (keys sorted, `indent=2`, trailing newline):

```json
{"model_version": "v001", "gold_rows": 100,
 "polarity": {"agreed_rows": 81, "test_rows": 17, "dataset_label_accuracy": 0.6667,
              "metrics": {"<evaluate output>": "..."}, "conformal": {"<conformal_report output>": 0.0}},
 "aspects": {"content": {"agreed_rows": 95, "gold_present": 60, "precision": 0.5, "recall": 0.3333,
                         "f1": 0.4, "threshold": 0.35}},
 "aspect_macro_f1": 0.0444}
```

Values above are illustrative except the key names. `aspects` has exactly 9 keys, the group values. Floats are
written unrounded (`json` default).

## Expected behavior

1. `read_gold_sheet(path, gold_dir)`: call `validate_input_file(path, gold_dir)` (SEC-11); read the returned path
   with `pd.read_csv(..., dtype=str, keep_default_na=False, encoding="utf-8-sig")`; require every name in
   `GOLD_COLUMNS` (other columns ignored); apply `str.strip().lower()` to `polarity` and the 9 aspect columns and
   `str.strip()` to `row_key`; check uniqueness of `row_key` and value sets; return the frame with the 11
   `GOLD_COLUMNS` in that order.
2. `agreed_polarity(a, b)`: the two `row_key` sets MUST be equal; inner join on `row_key`; keep rows where
   `a.polarity == b.polarity`; return `row_key`, `polarity`, sorted by `row_key` ascending.
3. `agreed_presence(a, b, group)`: presence of a row = the cell of `f"aspect_{group.value}"` is not `""`; keep rows
   where both sheets agree on presence; return `row_key`, `present`, sorted by `row_key`.
4. `presence_metrics(gold, predicted)`: equal lengths; `agreed_rows = len(gold)`, `gold_present = sum(gold)`,
   precision, recall and F1 of the positive class from scikit-learn with `zero_division=0.0`, as Python `float`.
5. `active_version(models_dir)`: read `resolve_within(models_dir, Path("registry.json"))` with `json`; return its
   `active` value when it is a `str` matching `^v\d{3}$`.
6. `evaluate_gold(gold_dir, dataset_dir, models_dir)`:
   1. `version = active_version(models_dir)`; `bundle = load_verified(models_dir, version)` (hash and versions
      checked there, SEC-14).
   2. Narrow `bundle["polarity_pipeline"]` and `bundle["aspect_pipeline"]` with `isinstance(..., Pipeline)`,
      `bundle["conformal_classifier"]` with `isinstance(..., CrossConformalClassifier)`, and
      `bundle["aspect_thresholds"]` to a tuple of 9 `float`.
   3. Read `test_row_keys` from `resolve_within(models_dir, Path(version) / "report.json")` with `json`.
   4. Read both sheets from `gold_dir / GOLD_SHEETS[i]` with `read_gold_sheet`.
   5. `frame = load_dataset(dataset_dir)`; map `row_key` to `text` and to `polarity`; every sheet `row_key` MUST be
      in the frame.
   6. Polarity block: `agreed = agreed_polarity(a, b)`; `y` = class index of each gold polarity in
      `POLARITY_ORDER`; `metrics = evaluate(polarity_pipeline, texts, y)`; `conformal =
      conformal_report(conformal_classifier, texts, y)`; `dataset_label_accuracy` = share of agreed rows whose
      dataset `polarity` equals the gold polarity; `test_rows` = agreed rows whose `row_key` is in `test_row_keys`.
   7. Aspect block: one `aspect_pipeline.predict_proba` call over the texts of all sheet rows (sorted by
      `row_key`); for group index `j` in `ASPECT_ORDER`, predicted presence = `score[:, j] >= thresholds[j]`;
      `presence_metrics` over the rows of `agreed_presence(a, b, group)`, plus `threshold = thresholds[j]`.
   8. `aspect_macro_f1` = arithmetic mean of the 9 `f1` values. Return the dict of the report schema.
7. `write_report(reports_dir, report)`: `reports_dir.mkdir(mode=0o700, parents=True, exist_ok=True)`; `target =
   resolve_within(reports_dir, Path(REPORT_NAME))`; write `json.dumps(report, indent=2, sort_keys=True) + "\n"`
   in UTF-8; `os.chmod(target, 0o600)`; return `target`.
8. `main(argv)`: `os.umask(0o077)` is the first instruction (SEC-04). `argparse` flags `--gold` (default
   `"gold"`), `--dataset` (default `"Dataset"`), `--models` (default `"models"`); the output directory is always
   `REPORTS_DIR`. Runs `evaluate_gold` then `write_report`; logs `"gold_eval_done version=%s agreed_rows=%d"`
   at `INFO`; prints the returned path; returns 0. `AppError` → log `"gold_eval_failed code=%s"` at `ERROR` with
   `error.code`, return 2. Any other exception → `logger.exception("gold_eval_crashed")`, return 1.
9. Logs and error details hold no comment text, no `row_key` and no file name (SEC-05).

## Edge cases and error handling

All `detail` strings are literal and carry no input data.

| Input | Result |
|---|---|
| Sheet file fails SEC-11 (symlink, extension `.txt`, > 2 MB, outside `gold_dir`, missing) | the `DatasetError` raised by `validate_input_file` propagates |
| Sheet lacks any of `GOLD_COLUMNS` | `DatasetError("gold sheet missing columns")` |
| Repeated `row_key` in a sheet | `DatasetError("gold sheet has duplicate row keys")` |
| `polarity` not in `POLARITY_VALUES` after normalization (including `""`) | `DatasetError("gold sheet has an invalid polarity value")` |
| Aspect cell not in `ASPECT_VALUES` after normalization | `DatasetError("gold sheet has an invalid aspect value")` |
| `row_key` sets of the two sheets differ | `DatasetError("gold sheets have different row keys")` |
| A sheet `row_key` missing from `load_dataset` | `DatasetError("gold row key not in dataset")` |
| Zero rows with agreed polarity | `DatasetError("no agreed gold rows")` |
| `presence_metrics` lengths differ | `InvalidInputError("gold and predicted lengths differ")` |
| Group with no agreed rows, or no positives in gold and predictions | that group's precision, recall, F1 are `0.0` |
| `registry.json` missing | `ModelUnavailableError("registry not found")` |
| `active` missing or not `^v\d{3}$` | `ModelUnavailableError("registry has no active version")` |
| `report.json` of the version missing | `ModelUnavailableError("report not found")` |
| Bundle object of wrong type, or thresholds not 9 floats | `ModelUnavailableError("bundle object has an unexpected type")` |
| Bundle hash or version mismatch | the `ModelIntegrityError` of `load_verified` propagates; `main` returns 2 |

If an existing test not listed here fails because of this change, the implementer does not modify it: report it with
its name and the reason.

## Acceptance tests (prose)

Fixtures are synthetic: sheets written to `tmp_path / "gold"` with hand-written row keys `"f.csv:1"` to `"f.csv:5"`;
`load_dataset` and `load_verified` are replaced with `monkeypatch.setattr` on `ml.gold_eval`.

`tests/unit/ml/test_gold_eval_sheets.py`:
- `test_read_gold_sheet_normalizes_values`: BOM file with header in `GOLD_COLUMNS` order plus an extra column
  `notes`, row `" f.csv:1 ", " Negative ", "POSITIVE", "", ...` → frame has 11 columns, `row_key` `"f.csv:1"`,
  `polarity` `"negative"`, `aspect_content` `"positive"`, `aspect_assessment` `""`.
- `test_read_gold_sheet_rejects_missing_column`: no `aspect_platform` column → `DatasetError`, message `"gold sheet
  missing columns"`.
- `test_read_gold_sheet_rejects_duplicate_keys`: two rows `"f.csv:1"` → `DatasetError`.
- `test_read_gold_sheet_rejects_invalid_polarity`: polarity `"mixed"` → `DatasetError`; a second case with `""`.
- `test_read_gold_sheet_rejects_invalid_aspect`: `aspect_content` `"yes"` → `DatasetError`.
- `test_read_gold_sheet_rejects_symlink`: a symlink in `gold/` pointing to a valid sheet → `DatasetError`.
- `test_read_gold_sheet_rejects_wrong_extension`: `gold/sheet_a.txt` → `DatasetError`.
- `test_agreed_polarity_keeps_matching_rows`: keys 1..4, sheet A `negative, neutral, positive, positive`, sheet B
  `negative, positive, positive, positive` → rows `f.csv:1, f.csv:3, f.csv:4` with `negative, positive, positive`.
- `test_agreed_polarity_rejects_different_keys`: sheet B has `f.csv:9` in place of `f.csv:4` → `DatasetError`.
- `test_agreed_presence_keeps_matching_rows`: keys 1..5, `aspect_content` A `negative, "", positive, "", neutral`,
  B `positive, "", "", "", neutral` → keys `f.csv:1, f.csv:2, f.csv:4, f.csv:5`, `present` `True, False, False,
  True`.
- `test_presence_metrics_vector`: gold `T, T, T, F, F`, predicted `T, F, F, F, T` → `agreed_rows` 5,
  `gold_present` 3, precision 0.5, recall 0.333333, F1 0.4 (compare with `pytest.approx(abs=1e-6)`).
- `test_presence_metrics_no_positives`: gold `F, F`, predicted `F, F` → precision, recall, F1 `0.0`.
- `test_presence_metrics_rejects_length_mismatch`: lengths 2 and 3 → `InvalidInputError`.
- `test_active_version_reads_registry`: `{"active": "v002", "history": ["v001", "v002"]}` → `"v002"`.
- `test_active_version_rejects_missing_or_invalid`: no file → `ModelUnavailableError("registry not found")`;
  `{"active": "2"}` → `ModelUnavailableError("registry has no active version")`.

`tests/unit/ml/test_gold_eval_report.py` (fake bundle: `polarity_pipeline` = `Pipeline` of `TfidfVectorizer` and
`LogisticRegression(random_state=42)` fitted on 12 hand-written Spanish comments, 4 per class;
`aspect_pipeline` = `Pipeline` of `TfidfVectorizer` and `OneVsRestClassifier(LogisticRegression())` fitted on the
same texts with a 12 × 9 indicator matrix where every column has both values; `conformal_classifier` = unfitted
`CrossConformalClassifier(estimator=LogisticRegression())`; `aspect_thresholds` = nine `0.5`;
`ml.gold_eval.conformal_report` replaced by a function returning `{"empirical_coverage": 0.9, "mean_set_size":
1.2, "singleton_rate": 0.8, "empty_rate": 0.0}`; `report.json` with `test_row_keys` `["f.csv:1", "f.csv:2"]`):
- `test_evaluate_gold_report_shape`: 5 rows, 3 with agreed polarity → keys `model_version`, `gold_rows` (5),
  `polarity`, `aspects` (9 keys in `ASPECT_ORDER` values), `aspect_macro_f1`; `polarity.agreed_rows` 3.
- `test_evaluate_gold_dataset_label_accuracy`: agreed gold `negative, positive, positive`, dataset labels
  `negative, neutral, positive` → `dataset_label_accuracy` 0.666667 (abs 1e-6).
- `test_evaluate_gold_counts_test_rows`: agreed keys `f.csv:1, f.csv:3, f.csv:4` → `test_rows` 1.
- `test_evaluate_gold_threshold_is_inclusive`: `aspect_pipeline` replaced by a stub `Pipeline` subclass whose
  `predict_proba` returns 0.55 in column 0 for every row, thresholds 0.55 → content predicted present on every row;
  with 0.5499 returned → absent on every row.
- `test_evaluate_gold_macro_f1_vector`: 5 rows, every aspect cell `""` except `aspect_content` `positive` on
  keys 1, 2, 3 in both sheets; stub `predict_proba` returns column 0 `0.9, 0.1, 0.1, 0.1, 0.9` and 0.0 elsewhere,
  thresholds 0.5 → content precision 0.5, recall 0.333333, F1 0.4, the other 8 F1 0.0, `aspect_macro_f1` 0.044444
  (abs 1e-6).
- `test_evaluate_gold_rejects_unknown_row_key`: sheet key `f.csv:7` absent from the dataset frame → `DatasetError`.
- `test_evaluate_gold_rejects_no_agreement`: every row disagrees → `DatasetError("no agreed gold rows")`.
- `test_evaluate_gold_rejects_wrong_bundle_type`: `polarity_pipeline` is the string `"x"` →
  `ModelUnavailableError`.
- `test_evaluate_gold_rejects_missing_report`: no `v001/report.json` → `ModelUnavailableError("report not found")`.
- `test_write_report_permissions_and_name`: writes into `tmp_path / "reports"` → path ends in
  `reports/gold_eval.json`, file mode `0o600`, directory mode `0o700`, content parses with `json.loads`.
- `test_write_report_has_no_comment_text`: after a full `evaluate_gold` plus `write_report`, the file contains none
  of the 12 fixture texts, none of the 5 row keys and the substring `"text"` does not appear.
- `test_main_exit_codes`: `monkeypatch.chdir(tmp_path)` with valid fixtures → 0 and `reports/gold_eval.json`
  exists; registry removed → 2; `evaluate_gold` replaced by a function raising `RuntimeError` → 1.

## Out of scope

Producing the sheets and Cohen's kappa (spec 015); per-aspect sentiment on gold; adjudication of disagreements;
any API route or UI for gold results; writing into `models/`; changes to `docs/contracts.md`.

## Definition of Done

- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed` (dependency rule and size limits).
- [ ] No new suppressions: `grep -nE "# noqa|# type: ignore" ml/gold_eval.py tests/unit/ml/test_gold_eval_*.py` →
      no output.
- [ ] Coverage: `.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing` → line
      `ml/gold_eval.py` ≥ 80 %.
- [ ] `grep -c "os.umask(0o077)" ml/gold_eval.py` → `1`.
- [ ] `grep -nE "joblib\.load|pickle|yaml|eval\(|exec\(" ml/gold_eval.py` → no output.
- [ ] `grep -nE "^from (api\.(ports|application|adapters|main)|ml\.train)|^import api\.main" ml/gold_eval.py` → no
      output.
- [ ] `bash scripts/security_grep.sh` → no output, exit code 0.
- [ ] `bash scripts/gate.sh` → last line `GATE OK`.
