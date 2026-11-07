# 014 - ML train CLI
Riesgo: alto

## Objective

The training modules (specs 007 to 013) exist as separate functions, but nothing runs them in order, so no model
version exists and the API (spec 024) cannot start. This spec adds `ml/train.py`, the entry point
`python -m ml.train` of `docs/contracts.md` §8: clean → split → select → evaluate → conformal → aspects → topics →
write version → activate. It also builds the two artifacts spec 013 leaves out of scope: the `report.json` content
(§9.4) and `reference_stats.json` (§9.5). After this spec, `.venv/bin/python -m ml.train` writes `models/v001/` and
makes it active in `models/registry.json`.

## Depends on

013 (`ml.artifact`), and through it 007 to 012. Transitively 002 (errors, entities) and 003 (`resolve_within`,
`RedactingFilter`).

## Governing files

- `ARCHITECTURE.md` §2 rule 4 (`ml` imports only `api.domain` and third parties), §3 steps 1 to 5, §6 (≤ 20
  statements and ≤ 6 arguments per function, ≤ 300 lines per module, `mypy --strict`, seed 42, every fit on train
  rows only, `print` and the generic `except` only in `main()`), §7 (`conformal.alpha`).
- `security-rules.md` SEC-02 (no comment text in `report.json`, enforced by `write_version`), SEC-04, SEC-05,
  SEC-07 (`ml.train` writes only under `models/`), SEC-11 (dataset read through `load_dataset`), SEC-12, SEC-13
  (`json` only), SEC-17 (embedding name and revision in the manifest).
- ADR-001 §3, ADR-002, ADR-003. `docs/contracts.md` §2 (exit codes 0 / 2 / 1), §4.5, §7, §8, §9.1 to §9.5.

## Files to create/modify

1. `ml/train.py` (new). Same layout as `ml/artifact.py` (spec 013). Budget: ≤ 300 lines, ≤ 14 functions.
2. `tests/unit/ml/test_train_config.py` (new): `read_confidence_level`, `reference_stats`, `main`.
3. `tests/unit/ml/test_train_pipeline.py` (new): `train` wiring with stubbed stages.
4. `tests/integration/test_train_dataset.py` (new; module-level `pytestmark = pytest.mark.integration`).

No existing test changes expectation.

## External dependencies

None new (`scikit-learn==1.9.1`, `numpy==2.5.4`, `pandas==3.1.1`, spec 000). Verified with `numpy==2.5.4` on
Python 3.12: `np.percentile(values, (10, 20, 30, 40, 50, 60, 70, 80, 90), method="lower")` returns values taken
from the data (`numpy.int64` for integer input).

## Interfaces and types

Names consumed from earlier specs. Names pinned by specs 007 to 013 and `docs/contracts.md` §8; the implementer checks every
name against the implemented code first and, on any mismatch, stops and reports it without adapting:

| Spec | Name |
|---|---|
| 007 | `ml.data.load_dataset`, `dataset_files`, `dataset_sha256`; `ml.schemas.SEED`, `BUNDLE_SCHEMA_VERSION`, `Manifest`, `Report`, `ReferenceStats` |
| 008 | `ml.split.template_groups`, `grouped_split` |
| 009 | `ml.representations.EMBEDDING_MODEL_NAME`, `EMBEDDING_REVISION` |
| 010 | `ml.selection.select_model(texts, y, groups) -> SelectionResult` with fields `pipeline: Pipeline` (selected pipeline refit on the rows passed in), `representation: str`, `classifier: str`, `best_params: dict[str, object]`, `cv_macro_f1_mean: float`, `cv_macro_f1_std: float`, `selection: tuple[dict[str, object], ...]` (one `report.json` `selection` entry per representation × classifier); `ml.evaluation.evaluate`; `ml.evaluation.per_file_macro_f1(pipeline: Pipeline, texts: Sequence[str], y: np.ndarray, source_files: Sequence[str]) -> dict[str, float]` |
| 011 | `ml.conformal.fit_cross_conformal`, `conformal_report`; `ml.evaluation.risk_coverage` |
| 012 | `ml.aspects.aspect_targets`, `fit_aspect_model`, `aspect_report`; `ml.topics.fit_topics` |
| 013 | `ml.artifact.write_version`, `activate` |

Public functions of `ml/train.py` (Google docstrings; `from __future__ import annotations` first):
- `read_confidence_level(config_path: Path) -> float`
- `reference_stats(train_texts: Sequence[str], test_texts: Sequence[str], y_train: np.ndarray, vocabulary:
  frozenset[str]) -> ReferenceStats`
- `train(dataset_dir: Path, models_dir: Path, confidence_level: float) -> str` (returns the version name)
- `main(argv: Sequence[str] | None = None) -> int`

Private constants: `_DECILES: tuple[int, ...] = (10, 20, 30, 40, 50, 60, 70, 80, 90)`; `_SHARE_FLOOR: float =
1e-4`; `_TOKEN_PATTERN = re.compile(r"(?u)\b\w\w+\b")` (the drift token rule of `docs/contracts.md` §4.5).
Private helpers start with `_`, each ≤ 20 statements; `_configure_logging() -> None` and `_parser() ->
argparse.ArgumentParser` are two of them. Untyped-library calls rely on the mypy overrides of spec 000; no
`# type: ignore` and no `# noqa`.

## Expected behavior

`read_confidence_level(config_path)`:
1. `json.loads(config_path.read_text(encoding="utf-8"))`; `OSError` or `json.JSONDecodeError` →
   `ConfigError("config file unreadable")` raised `from` the cause.
2. The value MUST be a `dict` whose `conformal` is a `dict` whose `alpha` is an `int` or `float` (not `bool`) with
   `0 < alpha < 1`; otherwise `ConfigError("conformal.alpha must be a number in (0, 1)")`.
3. Returns `1.0 - float(alpha)`. Vectors: alpha `0.1` → `0.9`; alpha `0.05` → `0.95` (both exact in binary
   floating point, so spec 024's 1e-9 check holds).

`reference_stats(train_texts, test_texts, y_train, vocabulary)`:
1. `lengths = [len(t) for t in train_texts]`; `length_edges = [int(v) for v in np.percentile(lengths, _DECILES,
   method="lower")]`.
2. Bin of a text = `bisect.bisect_right(length_edges, len(text))` (0..9); `raw_i = max(count_i / len(train_texts),
   _SHARE_FLOOR)`; `length_shares = [raw_i / sum(raw)]` for i in 0..9 (every share > 0, as spec 020 requires).
3. `reference_oov_rate` = tokens of `test_texts` (`_TOKEN_PATTERN.findall(text.lower())`) not in `vocabulary`,
   divided by all those tokens; `0.0` when there are no tokens.
4. `class_shares = [count of y_train == k / len(y_train) for k in 0, 1, 2]`. All values are Python `int`/`float`.

`train(dataset_dir, models_dir, confidence_level)`:
1. `frame = load_dataset(dataset_dir)`; `sha = dataset_sha256(dataset_files(dataset_dir))`; `texts =
   frame["text"].tolist()`; `y = np.array([POLARITY_ORDER.index(Polarity(v)) for v in frame["polarity"]],
   dtype=np.int64)`. Logs `INFO` `"event=train_dataset rows=%d dataset_sha256=%s"`.
2. `groups = template_groups(texts)`; `train_idx, test_idx = grouped_split(y, groups)`; train and test texts, `y`,
   `groups`, `source_file` and `row_key` lists are taken by those indices. Logs `INFO` `"event=train_split
   train_rows=%d test_rows=%d groups=%d"`.
3. Polarity, train rows only for every fit: `selection = select_model(train_texts, y_train, groups_train)`;
   `pipeline = selection.pipeline`; `test = evaluate(pipeline, test_texts, y_test)`; `per_file =
   per_file_macro_f1(pipeline, test_texts, y_test, test_files)`; `test_macro_f1 = float(f1_score(y_test,
   pipeline.predict(test_texts), average="macro"))`; `conformal = fit_cross_conformal(pipeline, train_texts, y_train,
   groups_train, confidence_level)`; `conformal_metrics = conformal_report(conformal, test_texts, y_test)`; `curve =
   risk_coverage(pipeline.predict_proba(test_texts), y_test)`. Logs `INFO` `"event=train_selected representation=%s
   classifier=%s"`.
4. Aspects: `Y = aspect_targets(frame)`; `aspect_pipeline, thresholds = fit_aspect_model(train_texts, Y[train_idx],
   groups_train)`; `aspects = aspect_report(aspect_pipeline, thresholds, test_texts, Y[test_idx])`.
5. Topics: `vectorizer, kmeans, terms = fit_topics(train_texts)`; `topics = [{"topic": t, "size":
   int((kmeans.labels_ == t).sum()), "terms": list(terms[t])} for t in range(len(terms))]`.
6. `reference = reference_stats(train_texts, test_texts, y_train, frozenset(vectorizer.vocabulary_))`.
7. Bundle (§9.1, 10 keys): `schema_version` `BUNDLE_SCHEMA_VERSION`, `class_order` `tuple(p.value for p in
   POLARITY_ORDER)`, `aspect_order` `tuple(g.value for g in ASPECT_ORDER)`, `polarity_pipeline` `pipeline`,
   `conformal_classifier` `conformal`, `aspect_pipeline`, `aspect_thresholds` `thresholds`, `topic_vectorizer`
   `vectorizer`, `topic_kmeans` `kmeans`, `topic_terms` `terms`.
8. Report (§9.4, 9 keys): `selection` `list(selection.selection)`, `test`, `per_file_macro_f1` `per_file`, `conformal`
   `conformal_metrics`, `risk_coverage` `[[c, r] for c, r in curve]`, `aspects`, `topics`, `split`
   `{"train_rows": len(train_idx), "test_rows": len(test_idx), "groups": int(np.unique(groups).size)}`,
   `test_row_keys` (list of `str`).
9. Manifest (§9.2): `dataset_sha256` `sha`, `embedding` `{"model_name": EMBEDDING_MODEL_NAME, "revision":
   EMBEDDING_REVISION}`, `polarity_model` `selection.classifier`, `representation` `selection.representation`,
   `best_params` `selection.best_params`, `confidence_level`, `seed` `SEED`, `metrics` `{"test_macro_f1":
   test_macro_f1, "empirical_coverage": conformal_metrics["empirical_coverage"]}`. The 6 keys that `write_version`
   replaces get the placeholders `version` `""`, `created_at` `""`, `bundle_sha256` `""`, `python_version` `""`,
   `library_versions` `{}`, `smoke` `{"texts": [], "probabilities": []}`.
10. `version = write_version(models_dir, bundle, manifest, report, reference).name`; `activate(models_dir,
    version)`; logs `INFO` `"event=train_done version=%s test_macro_f1=%.4f empirical_coverage=%.4f"`; returns
    `version`.

`main(argv)`:
1. `os.umask(0o077)` is the first statement (SEC-04); then `_configure_logging()`, identical to `ml.gold`
   (spec 015): `logging.basicConfig(handlers=[h], level=logging.INFO, force=True)`, `h =
   logging.StreamHandler(sys.stdout)`, formatter `"level=%(levelname)s logger=%(name)s %(message)s"`,
   `RedactingFilter()` added to `h`.
2. `_parser()`: `prog="ml.train"`, options `--dataset` (default `"Dataset"`), `--models` (default `"models"`),
   `--config` (default `"config/app.json"`). Each path = `resolve_within(Path.cwd(), Path(value))` (SEC-07, SEC-12).
3. `version = train(dataset_dir, models_dir, read_confidence_level(config_path))`; prints `f"trained={version}"`
   to stdout; returns 0.
4. `except AppError as error`: prints `f"error={error.code}"` to stderr; returns 2. `except Exception`:
   `logger.exception("event=train_failed code=unexpected")`, prints `"error=internal_error"` to stderr; returns 1.
5. Module tail: `if __name__ == "__main__": raise SystemExit(main())`.

No log line holds comment text, `row_key` values or file names (SEC-05).

## Edge cases and error handling

| Condition | Result |
|---|---|
| Config file missing, or content `{` | `ConfigError("config file unreadable")`; `main` → 2, stderr `error=internal_error` |
| `alpha` `0`, `1`, `-0.1`, `true`, `"0.1"`; `conformal` absent; top level a list | `ConfigError("conformal.alpha must be a number in (0, 1)")` |
| `--models ../x` (escapes the working directory) | `UnsafePathError` → 2, stderr `error=internal_error` |
| `reference_stats` with empty `train_texts`, empty `test_texts` or `len(y_train) != len(train_texts)` | `InvalidInputError("reference statistics need matching non-empty inputs")` |
| All train texts of one length (every edge equal) | shares 1 to 9 floored to `1e-4`, then normalized (vector below) |
| A stage raises an `AppError` (`DatasetError` from `load_dataset`, `InvalidInputError` from `fit_cross_conformal` for a pipeline without `predict_proba`, `ModelIntegrityError` from `activate`) | propagates; `main` → 2, stderr `error=<code>` |
| `activate` fails after `write_version` | the written `vNNN/` stays and is not active (spec 013 behavior) |
| Any other exception | `main` → 1, traceback in the stdout log through `RedactingFilter` |

If an existing test not listed here fails because of this change, the implementer does NOT modify it: report its
name and the reason.

## Acceptance tests (prose)

`tests/unit/ml/test_train_config.py` (all files under `tmp_path`):
1. `test_read_confidence_level_from_config`: `{"conformal": {"alpha": 0.1}}` → `0.9`; `0.05` → `0.95`.
2. `test_read_confidence_level_rejects_invalid_alpha` (parametrized over the 7 inputs of the edge cases row) →
   `"conformal.alpha must be a number in (0, 1)"`.
3. `test_read_confidence_level_rejects_unreadable_file`: missing file and content `{` →
   `"config file unreadable"`.
4. `test_reference_stats_deciles_and_shares`: train texts `"x" * k` for `k` in `1..20`, `y_train` 5 × 0, 10 × 1,
   5 × 2 → `length_edges [2, 4, 6, 8, 10, 12, 14, 16, 18]`, `length_shares [0.05, 0.1 × 8, 0.15]` (within 1e-12),
   `class_shares [0.25, 0.5, 0.25]`.
5. `test_reference_stats_floors_empty_bins`: 20 train texts of 10 characters → edges `[10] * 9`; shares 0 to 8 equal
   `1e-4 / 1.0009 = 9.991008092716556e-05`, share 9 `1 / 1.0009 = 0.9991008092716556` (within 1e-12); sum 1 within
   1e-9.
6. `test_reference_stats_oov_rate`: vocabulary `{"curso", "claro"}`, test texts `["El curso fue claro", "Curso
   malo"]` → `0.5` (3 of 6 tokens); test texts `["a b"]` → `0.0`.
7. `test_reference_stats_rejects_empty_inputs`: empty train, empty test, 3 labels for 2 texts → the detail above.
8. `test_main_exit_codes`: `monkeypatch.chdir(tmp_path)`; no config → 2, stderr `error=internal_error`;
   `--models ../x` → 2; with valid `config/app.json` and `ml.train.train` patched to return `"v007"` → 0, stdout
   last line `trained=v007`, the patch received `(tmp_path.resolve() / "Dataset", tmp_path.resolve() / "models",
   0.9)`; patched to raise `InvalidInputError("x")` → 2, `error=invalid_input`; to raise `RuntimeError("boom")` → 1,
   `error=internal_error`.
9. `test_main_sets_umask`: after `main([])` (no config, exit 2), `os.umask(0o022)` returns `0o077` (restored after).

`tests/unit/ml/test_train_pipeline.py`: `monkeypatch.setattr` on `ml.train` replaces every stage; the real
`write_version` and `activate` run on `tmp_path / "models"`. Stubs: `load_dataset` → frame `F12` of 12 rows, row
`i` (0..11): `row_key` `f"f{i % 2}.csv:{i + 1}"`, `source_file` `f"f{i % 2}.csv"`, `text` `f"{w} curso {i}"` with
`w = ("malo", "regular", "bueno")[i % 3]`, `polarity` `("negative", "neutral", "positive")[i % 3]`, 9
`aspect_<group>` columns `""`; `dataset_files` → `(Path("a.csv"),)`; `dataset_sha256` → `"0" * 64`;
`template_groups` → `np.arange(12) % 6`; `grouped_split` → `(np.arange(9), np.arange(9, 12))`; `select_model` →
`SimpleNamespace(pipeline=make_bundle()["polarity_pipeline"], representation="tfidf",
classifier="logistic_regression", best_params={"classifier__C": 1.0}, cv_macro_f1_mean=0.6, cv_macro_f1_std=0.05, selection=({"representation": "tfidf",
"classifier": "logistic_regression", "best_params": {"classifier__C": 1.0}, "cv_macro_f1_mean": 0.6,
"cv_macro_f1_std": 0.05},))` (`make_bundle` from `tests/fixtures/synthetic_bundle.py`, spec 013); `evaluate` →
`{"accuracy": 0.5}`; `per_file_macro_f1` → `{"f0.csv": 0.5, "f1.csv": 0.4}`; `fit_cross_conformal` → `"stub"`;
`conformal_report` → `{"empirical_coverage": 0.9, "mean_set_size": 2.0, "singleton_rate": 0.1, "empty_rate":
0.0}`; `risk_coverage` → `[(0.5, 0.0), (1.0, 0.25)]`; `aspect_targets` → zeros `(12, 9)` int64; `fit_aspect_model`
→ `("stub", (0.5,) * 9)`; `aspect_report` → each group `{"precision": 0.5, "recall": 0.5, "f1": 0.5, "threshold":
0.5}`; `fit_topics` → `(SimpleNamespace(vocabulary_={"curso": 0, "bueno": 1}), SimpleNamespace(labels_=np.array([0,
0, 0, 0, 0, 1, 1, 1, 1])), (("curso", "bueno", "malo", "regular", "clase"), ("tema", "uno", "dos", "tres",
"cuatro")))`. Each stub records its arguments.
1. `test_train_writes_and_activates_v001`: returns `"v001"`; `registry.json` `{"active": "v001", "history":
   ["v001"]}`.
2. `test_train_fits_on_train_rows_only`: `select_model`, `fit_cross_conformal`, `fit_aspect_model` and `fit_topics`
   each received 9 texts, the texts of rows 0..8; `fit_cross_conformal` received `confidence_level` 0.9.
3. `test_train_manifest_fields`: `dataset_sha256 "0" * 64`, `polarity_model "logistic_regression"`,
   `representation "tfidf"`, `best_params {"classifier__C": 1.0}`, `confidence_level 0.9`, `seed 42`,
   `metrics.empirical_coverage 0.9`, `0.0 <= metrics.test_macro_f1 <= 1.0`, `embedding.revision` equals
   `EMBEDDING_REVISION`.
4. `test_train_report_fields`: `split {"train_rows": 9, "test_rows": 3, "groups": 6}`; `test_row_keys
   ["f1.csv:10", "f0.csv:11", "f1.csv:12"]`; `topics [{"topic": 0, "size": 5, ...}, {"topic": 1, "size": 4, ...}]`;
   `risk_coverage [[0.5, 0.0], [1.0, 0.25]]`; `per_file_macro_f1` received source files `["f1.csv", "f0.csv",
   "f1.csv"]`.
5. `test_train_reference_stats_file`: `class_shares` 3 × `1/3` (within 1e-12); `reference_oov_rate 0.5` (test
   tokens `malo curso regular curso 10 bueno curso 11`: 4 of 8 in the vocabulary).
6. `test_train_logs_hold_no_text`: no `caplog` message contains `"curso"` or `"f0.csv"`.

`tests/integration/test_train_dataset.py` (real `Dataset/`, embedding cache present):
1. `test_train_on_dataset`: `train(Path("Dataset").resolve(), tmp_path / "models", 0.9)` → `"v001"`; manifest
   `dataset_sha256` `5e3ac133828878229457420245bd2d674fdfe985e5a13632bf97b35bdbf2f666`; `train_rows + test_rows ==
   618`; `len(set(test_row_keys)) == test_rows`; `metrics.empirical_coverage >= 0.85` (`COVERAGE_TOLERANCE`, spec
   011); `metrics.test_macro_f1 > 0.20` (Dummy baseline, `docs/analysis.md` §2); `load_verified(models_dir,
   "v001")` returns 10 keys.

## Out of scope

Setting `HF_HUB_OFFLINE` in `ml.train` (embedding loading is offline through `local_files_only=True`, spec 009);
deleting old versions; choosing `alpha` from risk-coverage results; the gold-set evaluation (spec 029).

## Definition of Done

- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed`; `wc -l ml/train.py` ≤ 300.
- [ ] `grep -nE "# noqa|# type: ignore" ml/train.py tests/unit/ml/test_train_*.py tests/integration/test_train_dataset.py` → no output.
- [ ] `.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing` → `ml/train.py` ≥ 80 %.
- [ ] `grep -n "os.umask(0o077)" ml/train.py` → 1 line, the first statement of `main`.
- [ ] `grep -nE "joblib|pickle|eval\(|exec\(|shell=True|yaml" ml/train.py` → no output.
- [ ] `.venv/bin/pytest -q -m integration tests/integration/test_train_dataset.py` → `1 passed`.
- [ ] `.venv/bin/python -m ml.train` → last stdout line `trained=v001`, exit 0; then `.venv/bin/python -m
      ml.artifact verify v001` → `verified=v001`, exit 0; `stat -c %a models/v001 models/v001/report.json` → `700`,
      `600`.
- [ ] `bash scripts/security_grep.sh` → no output, exit 0; `bash scripts/gate.sh` → last line `GATE OK`.
