# 015 - ML gold set and agreement
Riesgo: alto

## Objective

The dataset labels are noisy: the global label agrees with the sentiment of its own aspects in about 50 % of rows and
the best baseline reaches macro-F1 0.62 (`docs/analysis.md` §2). Without human labels nobody knows how much of that
gap is label noise. After this spec `python -m ml.gold sample --n 100` writes 2 identical blank annotation sheets of
100 comments, stratified by polarity, for 2 independent annotators; `gold/guidelines.md` tells them how to fill
them; `python -m ml.gold agreement` reads both filled sheets under SEC-11 and writes `gold/agreement.json` with
Cohen's kappa for polarity and for each of the 9 aspect groups.

## Depends on

001 (`scripts/security_grep.sh`, `tests/architecture`, used by the Definition of Done); 002 (`AppError`,
`DatasetError`, `ASPECT_ORDER`, `POLARITY_ORDER`); 003 (`resolve_within`, `RedactingFilter`); 007 (`ml.data.load_dataset`,
`ml.data.validate_input_file`, `ml.schemas.SEED`).

## Governing files

- `ARCHITECTURE.md` §2 (`ml` imports `api.domain` and third parties only; rule 4), §5 (`gold/`), §6 (≤ 20 statements,
  ≤ 300 lines per module, errors, logging, `print` only in `main()`, seed 42).
- `security-rules.md` SEC-04 (umask first, 0700/0600), SEC-05 (stdout, `RedactingFilter`, no comment text or file
  names in logs), SEC-07 (`ml` writes only under `gold/` here), SEC-09, SEC-11 (input CSV checks), SEC-12, SEC-13.
- `docs/contracts.md` §2 (`DatasetError`, CLI exit codes 0 / 2 / 1), §8 (`ml.gold` row), §10 (clean frame).

## Files to create/modify

1. `ml/gold.py` (new). Reference pattern: `ml/data.py` (spec 007).
2. `gold/guidelines.md` (new).
3. `tests/unit/ml/test_gold.py` (new): sampling, sheet writing, `main`.
4. `tests/unit/ml/test_gold_agreement.py` (new): sheet reading, kappa, agreement file.

## External dependencies

None new. `scikit-learn==1.9.1`: `sklearn.model_selection.train_test_split` and `sklearn.metrics.cohen_kappa_score`
(signature measured: `(y1, y2, *, labels=None, weights=None, sample_weight=None, replace_undefined_by=nan)`);
`pandas==3.1.1` (`read_csv`, `DataFrame.to_csv(mode="x")` raises `FileExistsError`, measured); `numpy==2.5.4`.
`pyproject.toml` (spec 000) sets mypy `ignore_missing_imports` for `sklearn.*` and `pandas.*`, so no import needs a
suppression; mypy `strict` reports an unused `# type: ignore`. No suppression is allowed in this spec.

## Interfaces and types

Constants in `ml/gold.py`:
- `DATASET_DIR: Path = Path("Dataset")`, `GOLD_DIR: Path = Path("gold")` (relative to the working directory).
- `SHEET_FILES: tuple[str, str] = ("sheet_a.csv", "sheet_b.csv")`, `AGREEMENT_FILE: str = "agreement.json"`.
- `DEFAULT_SAMPLE_SIZE: int = 100`, `MIN_SAMPLE_SIZE: int = 10`, `MAX_SAMPLE_SIZE: int = 200`.
- `ASPECT_COLUMNS: tuple[str, ...] = tuple(f"aspect_{group.value}" for group in ASPECT_ORDER)` (9 names).
- `SHEET_COLUMNS: tuple[str, ...] = ("gold_id", "row_key", "text", "polarity", *ASPECT_COLUMNS)` (13 names).
- `POLARITY_VALUES: tuple[str, ...] = tuple(p.value for p in POLARITY_ORDER)`.
- `ASPECT_VALUES: tuple[str, ...] = ("", *POLARITY_VALUES)`; `PRESENCE_VALUES: tuple[str, str] = ("absent", "present")`.

Functions:
- `sample_sheet(frame: pd.DataFrame, n: int) -> pd.DataFrame`
- `write_sheets(sheet: pd.DataFrame, gold_dir: Path) -> tuple[Path, Path]`
- `read_sheet(path: Path, gold_dir: Path) -> pd.DataFrame`
- `cohen_kappa(first: Sequence[str], second: Sequence[str], labels: Sequence[str]) -> float | None`
- `agreement(sheet_a: pd.DataFrame, sheet_b: pd.DataFrame) -> dict[str, object]`
- `main(argv: Sequence[str] | None = None) -> int`.
- Module constant `logger: logging.Logger = logging.getLogger(__name__)`.
- Private helpers (each ≤ 20 statements, complexity ≤ 8, ≤ 8 branches): `_configure_logging() -> None`,
  `_parser() -> argparse.ArgumentParser`, `_run_sample(n: int) -> None`, `_run_agreement() -> None`,
  `_normalize_sheet(frame: pd.DataFrame) -> pd.DataFrame`, `_check_sheet_values(frame: pd.DataFrame) -> None`.

## Expected behavior

`sample_sheet(frame, n)` (uses only columns `row_key`, `text`, `polarity` of the clean frame):
1. `n < MIN_SAMPLE_SIZE` or `n > MAX_SAMPLE_SIZE` → `DatasetError("sample size out of range")`.
2. `positions, _ = train_test_split(np.arange(len(frame)), train_size=n, stratify=frame["polarity"].to_numpy(),
   random_state=SEED)`; `ValueError` → `DatasetError("cannot stratify sample")` from it.
3. Returns a new frame with columns `SHEET_COLUMNS` in that order and `n` rows in the order of `positions`:
   `gold_id` = `"1"` … `str(n)`, `row_key` and `text` copied, `polarity` and the 9 aspect columns `""`. The dataset
   label never appears in the sheet.

`write_sheets(sheet, gold_dir)`:
1. `gold_dir.mkdir(exist_ok=True)`; targets = `resolve_within(gold_dir, Path(name))` for each name in `SHEET_FILES`.
2. Any target exists → `DatasetError("gold sheets already exist")`, nothing written (protects filled sheets).
3. Each target: `sheet.to_csv(target, index=False, encoding="utf-8", mode="x", lineterminator="\n")`. Returns both.

`read_sheet(path, gold_dir)`:
1. `validate_input_file(path, gold_dir)` (SEC-11: `.csv`, regular file, ≤ 2 MB, inside `gold/`, parses).
2. `pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")` (accepts a BOM written by
   spreadsheet tools); `pandas.errors.ParserError`, `pandas.errors.EmptyDataError` or `UnicodeDecodeError` →
   `DatasetError("gold sheet unreadable")` from it.
3. `list(columns) != list(SHEET_COLUMNS)` → `DatasetError("gold sheet columns mismatch")`.
4. `_normalize_sheet` strips and lowercases `polarity` and the 9 aspect columns. `_check_sheet_values` checks
   `polarity` over all rows first: row `i` (1-based, first failing row) with `polarity` not in `POLARITY_VALUES` →
   `DatasetError(f"gold sheet incomplete: row {i}")`. Only then the aspect cells, row by row and, inside a row, in
   `ASPECT_COLUMNS` order: first cell not in `ASPECT_VALUES` → `DatasetError(f"gold sheet invalid aspect: row {i}")`.
5. `len(frame) == 0` (header only) → `DatasetError("gold sheet has no rows")`. Returns the normalized frame.

`cohen_kappa(first, second, labels)`: `len(set(first) | set(second)) == 1` → `None` (kappa undefined: both raters
used one same value; sklearn would warn); otherwise `float(cohen_kappa_score(list(first), list(second),
labels=list(labels)))`.

`agreement(sheet_a, sheet_b)`:
1. Different length, or different `gold_id` or `row_key` sequences → `DatasetError("gold sheets do not match")`.
2. Returns `{"rows": n, "polarity": {"kappa": k, "observed_agreement": o}, "aspects": {group.value: {"presence_kappa":
   pk, "label_kappa": lk} for group in ASPECT_ORDER}}` where `k` = `cohen_kappa` of the two `polarity` columns with
   `POLARITY_VALUES`; `o` = share of rows with equal `polarity`; `pk` = `cohen_kappa` of the two columns mapped to
   `"present"` (non-empty) or `"absent"` with `PRESENCE_VALUES`; `lk` = `cohen_kappa` of the raw aspect columns with
   `ASPECT_VALUES`. Every float is `round(value, 6)`; `None` stays `None`.

`main(argv)`:
1. `os.umask(0o077)` is the first statement (SEC-04). Then `_configure_logging()`: `logging.basicConfig(handlers=[h],
   level=logging.INFO, force=True)` with `h = logging.StreamHandler(sys.stdout)`, formatter
   `"level=%(levelname)s logger=%(name)s %(message)s"` and `RedactingFilter()` added.
2. `_parser()`: `prog="ml.gold"`, required subcommands `sample` (option `--n`, `type=int`, default
   `DEFAULT_SAMPLE_SIZE`) and `agreement`. argparse usage errors exit with status 2 (argparse behavior).
3. `main` only runs `os.umask`, `_configure_logging`, `_parser().parse_args(argv)`, dispatches to `_run_sample` or
   `_run_agreement`, returns 0 or the exit code of step 4; `_run_*` contain no `print`.
   `_run_sample(n)`: `write_sheets(sample_sheet(load_dataset(DATASET_DIR), n), resolve_within(Path.cwd(),
   GOLD_DIR))`; logs INFO `"event=gold_sample rows=%d"`. `_run_agreement()`: `gold_dir = resolve_within(Path.cwd(),
   GOLD_DIR)`; `read_sheet(gold_dir / name, gold_dir)` for each `name` in `SHEET_FILES` (a missing file gives
   `DatasetError("input file not found")` from `validate_input_file`); `agreement`; the result is written to
   `resolve_within(gold_dir, Path(AGREEMENT_FILE))` with `json.dumps(result, indent=2, allow_nan=False) + "\n"`
   (UTF-8, overwrites); logs INFO `"event=gold_agreement rows=%d"` (the kappa value is not logged: the
   `RedactingFilter` phone pattern would mask a number of 7 digits).
4. `except AppError as error`: logs ERROR `"event=gold_failed code=%s detail=%s"`, prints
   `f"ml.gold failed: {error.detail}"` to stderr, returns 2. `except Exception` (the single generic handler allowed
   by ARCHITECTURE §6): `logger.exception("event=gold_failed code=unexpected")`, prints
   `"ml.gold failed: unexpected error, see the log."` to stderr, returns 1.
5. Module tail: `if __name__ == "__main__": raise SystemExit(main())`. No log line holds comment text or file names.

`gold/guidelines.md` (English, at most 60 lines) MUST contain, in this order, sections `# Gold-set annotation
guidelines`, `## Independence`, `## Polarity`, `## Aspects`, `## Saving` with these rules: annotate alone and never
compare sheets before `agreement` runs; annotator A fills `gold/sheet_a.csv`, annotator B `gold/sheet_b.csv`; do not
edit `gold_id`, `row_key`, `text` or the column order; `polarity` is one of `negative`, `positive`, `neutral` for the
whole comment (`neutral` = no evaluation, or praise and criticism of equal weight); an aspect cell is empty when the
comment does not mention that group, else the sentiment of that mention (`negative`, `neutral`, `positive`); a table
of the 9 groups with the original labels of `docs/contracts.md` §10; save as CSV, UTF-8, comma separator.

## Edge cases and error handling

| Input | Result |
|---|---|
| `n` = 9 or 201 | `DatasetError("sample size out of range")`, exit 2 |
| 30 rows, `n` = 28 (test side below 3 classes) | `DatasetError("cannot stratify sample")` |
| `gold/sheet_a.csv` already exists | `DatasetError("gold sheets already exist")`; `sheet_b.csv` not created |
| Sheet path `gold/sheet_a.txt`, a symlink, or outside `gold/` | the `DatasetError` of `validate_input_file` (spec 007) |
| `agreement` run before `sample` (no `gold/sheet_a.csv`) | `DatasetError("input file not found")`, exit 2 |
| Sheet with the header row only | `DatasetError("gold sheet has no rows")` |
| Sheet without column `aspect_platform` | `DatasetError("gold sheet columns mismatch")` |
| Row 3 `polarity` `""` / `"mixed"` | `DatasetError("gold sheet incomplete: row 3")` |
| Row 2 `aspect_content` `"good"` | `DatasetError("gold sheet invalid aspect: row 2")` |
| Sheet B `row_key` order differs | `DatasetError("gold sheets do not match")` |
| Both raters write `""` in every `aspect_platform` cell | `presence_kappa` and `label_kappa` `null` |
| Unexpected `RuntimeError` in a command | exit 1, traceback in the stdout log |

No existing test changes expectation. If an existing test not listed here fails because of this change, the
implementer does not modify it: they report its name and the reason.

## Acceptance tests (prose)

Synthetic frame `F30`: 30 rows, `row_key` `"synthetic.csv:1"` … `"synthetic.csv:30"`, `text` `"Comentario sintético
número i."`, `polarity` `POLARITY_VALUES[i % 3]` for 0-based `i`. Every test that runs `main` uses
`monkeypatch.chdir(tmp_path)`, monkeypatches `ml.gold.load_dataset` to return `F30`, and an autouse fixture restores
the root logger handlers and level after each test.

`tests/unit/ml/test_gold.py`:
- `test_sample_sheet_is_stratified_and_deterministic`: `sample_sheet(F30, 12)` → 12 rows; first 3 `row_key`
  `"synthetic.csv:17"`, `"synthetic.csv:2"`, `"synthetic.csv:3"` (positions `[16, 1, 2, 0, 3, 25, 15, 24, 29, 4, 8,
  20]`, measured); 4 rows of each class in the 12-row sample; `gold_id` `"1"` … `"12"`; columns equal `SHEET_COLUMNS`.
- `test_sample_sheet_hides_dataset_label`: every `polarity` and aspect cell of the sheet is `""`.
- `test_sample_sheet_rejects_size_out_of_range`: `n` 9 and 201 → `"sample size out of range"`.
- `test_sample_sheet_rejects_unstratifiable_size`: `n` 28 → `"cannot stratify sample"`.
- `test_write_sheets_writes_two_identical_files`: both files exist with identical bytes; mode `0o600` after
  `os.umask(0o077)` (the test restores the previous umask).
- `test_write_sheets_refuses_overwrite`: pre-existing `sheet_a.csv` with content `"x"` → error; content still `"x"`;
  `sheet_b.csv` absent.
- `test_main_sample_returns_zero`: `main(["sample", "--n", "12"])` → 0; captured stdout holds
  `"event=gold_sample rows=12"` (`main` replaces root handlers, so tests read `capsys`, not `caplog`).
- The implementer runs the two measured values (the 12 positions above and the `0.0` of
  `test_cohen_kappa_disjoint_single_values`) first; if they differ, they report it and do not change the test.
- `test_main_returns_two_on_app_error`: `main(["sample", "--n", "9"])` → 2; stderr
  `"ml.gold failed: sample size out of range\n"`.
- `test_main_returns_one_on_unexpected_error`: `load_dataset` patched to raise `RuntimeError("boom")` → 1; stderr
  `"ml.gold failed: unexpected error, see the log.\n"` and captured stdout contains `"RuntimeError: boom"`.
- `test_main_sets_umask_first`: `os.umask` patched with a recorder, `load_dataset` raising → first recorded call
  argument `0o077`.

`tests/unit/ml/test_gold_agreement.py` (sheets written under `tmp_path / "gold"`):
- `test_cohen_kappa_polarity_vector`: A = `[neg, neg, neu, neu, pos, pos, pos, neg, neu, pos]`, B = `[neg, neu,
  neu, neu, pos, pos, neg, neg, neu, pos]` (full values) → `0.7014925373134329` (observed 0.8, expected 0.33).
- `test_cohen_kappa_undefined_returns_none`: `[""] * 5` twice with `ASPECT_VALUES` → `None`.
- `test_cohen_kappa_disjoint_single_values`: `cohen_kappa([""] * 4, ["negative"] * 4, ASPECT_VALUES)` → `0.0`.
- `test_agreement_vector`: 10-row sheets (`gold_id` `"1"` … `"10"`, `row_key` `"synthetic.csv:1"` …
  `"synthetic.csv:10"`, `text` `"Comentario sintético número i."`) with the polarity vectors above, `aspect_content` A = `["", "negative", "",
  "", "positive", "", "", "", "neutral", ""]`, B = `["", "negative", "", "positive", "positive", "", "", "", "",
  ""]`, other aspects `""` → `rows` 10, polarity `{"kappa": 0.701493, "observed_agreement": 0.8}`, content
  `{"presence_kappa": 0.52381, "label_kappa": 0.583333}`, the other 8 groups both `None`.
- `test_main_agreement_writes_json`: both sheets of `test_agreement_vector` on disk, `main(["agreement"])` → 0;
  `json.loads` of `gold/agreement.json` equals the expected dict with `None` as `null`.
- `test_read_sheet_rejects_unsafe_path` (parametrized, `gold_dir = tmp_path / "gold"`): `gold/sheet_a.txt` →
  `"input file must have the .csv extension"`; `gold/link.csv` symlink to `sheet_a.csv` → `"input file must not be a
  symlink"`; `gold/missing.csv` → `"input file not found"`.
- `test_read_sheet_rejects_header_only`: a file with the `SHEET_COLUMNS` header and 0 rows → `"gold sheet has no rows"`.
- `test_main_agreement_missing_sheet_returns_two`: `main(["agreement"])` with no `gold/sheet_a.csv` → 2; stderr
  `"ml.gold failed: input file not found\n"`.
- `test_read_sheet_accepts_bom`: a sheet written with `encoding="utf-8-sig"` and `polarity` `" Positive "` → read as
  `"positive"`.
- One test per remaining table row: `test_read_sheet_rejects_missing_column`, `test_read_sheet_rejects_incomplete_row`
  (parametrized `""` and `"mixed"`), `test_read_sheet_rejects_invalid_aspect`, `test_agreement_rejects_mismatched_rows` (parametrized, each → `"gold sheets do not match"`: sheet B with 9 rows;
  sheet B with the `row_key` of rows 1 and 2 swapped; sheet B with the `gold_id` `"1"` and `"2"` swapped).

## Out of scope

- Consensus labels, gold-set evaluation of the model and the dataset-label agreement (spec 029). Spreadsheet
  formula escaping of sheet cells. Versioning decisions for filled sheets.

## Definition of Done

- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed` (dependency rule and size limits).
- [ ] `grep -nE "# noqa|# type: ignore" ml/gold.py tests/unit/ml/test_gold.py tests/unit/ml/test_gold_agreement.py`
      → no output.
- [ ] `.venv/bin/pytest -q tests/unit/ml/test_gold.py tests/unit/ml/test_gold_agreement.py --cov=ml --cov-report=term-missing`
      → the row of `ml/gold.py` shows Cover ≥ 80 %.
- [ ] `grep -n "os.umask(0o077)" ml/gold.py` → 1 line, inside `main` (SEC-04).
- [ ] `grep -nE "except Exception" ml/gold.py` → 1 line; `grep -nE "except:|except BaseException" ml/gold.py` → no output.
- [ ] `grep -nE "api\.(ports|application|adapters|main)" ml/gold.py` → no output (ARCHITECTURE §2 rule 4).
- [ ] `bash scripts/security_grep.sh` → no output, exit code 0.
- [ ] `grep -c "^## " gold/guidelines.md` → `4`; `wc -l < gold/guidelines.md` → a number ≤ 60.
- [ ] `grep -n "^#" gold/guidelines.md` → exactly 5 lines, in order: `# Gold-set annotation guidelines`,
      `## Independence`, `## Polarity`, `## Aspects`, `## Saving`.
