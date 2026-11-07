# 012 - ML aspects and topics
Riesgo: alto

## Objective

The product answers "which of the 9 aspect groups does a comment mention, and with what sentiment" and groups a
course's comments into topics (`ARCHITECTURE.md` §1, `docs/analysis.md` §2 and §6). This spec adds:
- `ml/aspects.py`: the 9-label presence model (TF-IDF word 1-2 + one-vs-rest logistic regression), per-group
  thresholds chosen on grouped out-of-fold scores, and a per-group precision/recall/F1 report.
- `ml/topics.py`: the KMeans topic model stored in the bundle (`topic_vectorizer`, `topic_kmeans`, `topic_terms`).

Per-aspect sentiment is not a separate model: at inference `api.domain.clauses.aspect_sentiments` (spec 005) takes,
per group, the clause with the highest aspect score and uses the polarity probabilities of that clause
(`docs/contracts.md` §4.2). This spec measures that path in an integration test.

Measured on 2026-11-05 on the real `Dataset/` (grouped split of ADR-001, 494 train rows, 124 test rows), with the
model and threshold rule of this spec:

| Group | Test support | Threshold | Precision | Recall | F1 |
|---|---|---|---|---|---|
| content | 75 | 0.10 | 0.605 | 1.000 | 0.754 |
| assessment | 22 | 0.45 | 0.448 | 0.591 | 0.510 |
| feedback | 18 | 0.40 | 0.429 | 0.500 | 0.462 |
| methodology_clarity | 12 | 0.45 | 0.091 | 0.083 | 0.087 |
| materials | 17 | 0.40 | 0.280 | 0.412 | 0.333 |
| organization_schedule | 12 | 0.40 | 0.769 | 0.833 | 0.800 |
| platform | 3 | 0.40 | 0.143 | 0.333 | 0.200 |
| communication_climate | 6 | 0.40 | 0.750 | 1.000 | 0.857 |
| workload_pace | 8 | 0.30 | 0.214 | 0.750 | 0.333 |

Macro-F1 over the 9 groups is 0.4818. Clause-level aspect sentiment matches the labeled group sentiment in 81 of 156
pairs (0.5192). Topics: with `max_df=0.2` the silhouette picks k = 10 (silhouette 0.0133) and the top terms are
content words (`"carga", "ritmo", "trabajo", "académica"`); without `max_df` the top terms of every topic are
function words (`"el", "la", "fue", "del", "de"`), so `max_df=0.2` is added (reported as a contract addition).

## Depends on

008 (`ml.split.cv_splitter`, `template_groups`, `grouped_split`), 009 (index dependency), 007 (`ml.data.load_dataset`,
`ml.schemas.SEED`, clean columns `aspect_<group>`), 005 (`split_clauses`, `aspect_sentiments`; integration test only),
002 (`api/domain/entities.py`, `api/domain/errors.py`).

## Governing files

- `ARCHITECTURE.md` §2 rule 4, §3 step 4, §6 (≤ 20 statements per function, ≤ 6 arguments, ≤ 300 lines per module,
  `mypy --strict`, seed 42, every fit on train rows only, no `print`, no `assert` in production code).
- `security-rules.md` SEC-02 (topic terms are single words, no quotes are produced here), SEC-05, SEC-09.
- ADR-001 §3 (aspect thresholds use `StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)` with the same
  group ids).
- `docs/contracts.md` §1.1 (`ASPECT_ORDER`, `AspectScores`), §3 (`AspectModel`, `TopicModel`), §8 (`ml.aspects`,
  `ml.topics`), §9.1, §9.4 (`aspects`, `topics` keys), §10.

## Files to create/modify

1. `ml/aspects.py` (new). No `ml` module exists yet; follow the module layout of `ml/split.py` (spec 008).
2. `ml/topics.py` (new). Same reference.
3. `tests/unit/ml/test_aspects.py` (new).
4. `tests/unit/ml/test_topics.py` (new).
5. `tests/integration/test_aspects_topics_dataset.py` (new; `pytestmark = pytest.mark.integration`).

## External dependencies

None new (`scikit-learn==1.9.1`, `numpy==2.5.4`, `pandas==3.1.1`, spec 000). Verified at these pins:
`StratifiedGroupKFold.split` with a 2-D multi-label target raises `ValueError("Supported target types are:
('binary', 'multiclass'). Got 'multilabel-indicator' instead.")`, so a 1-D stratification key is derived (step A2).
`OneVsRestClassifier(LogisticRegression(...)).predict_proba` returns a `numpy.ndarray` of shape `(n, 9)`.
`TfidfVectorizer.get_feature_names_out()` returns the vocabulary sorted alphabetically.

## Interfaces and types

`ml/aspects.py`:
- Private constant `_THRESHOLD_GRID: tuple[float, ...]` = the 17 values `0.10, 0.15, ..., 0.90`
  (`round(0.10 + 0.05 * i, 2)` for `i` in `0..16`).
- Private constant `_MIN_POSITIVES: int = 5`.
- `aspect_targets(frame: pd.DataFrame) -> np.ndarray`: shape `(n, 9)`, dtype `int64`, columns in `ASPECT_ORDER`.
- `fit_aspect_model(texts: Sequence[str], Y: np.ndarray, groups: np.ndarray) -> tuple[Pipeline, tuple[float, ...]]`.
- `aspect_report(pipeline: Pipeline, thresholds: tuple[float, ...], texts: Sequence[str], Y: np.ndarray) ->
  dict[str, object]`: keys are the 9 `AspectGroup` values in `ASPECT_ORDER`; each value is
  `{"precision": float, "recall": float, "f1": float, "threshold": float}`.

`ml/topics.py`:
- Private constants `_MIN_TEXTS: int = 50`, `_K_RANGE: tuple[int, ...] = (4, 5, 6, 7, 8, 9, 10)`,
  `_TERMS_PER_TOPIC: int = 5`.
- `fit_topics(texts: Sequence[str]) -> tuple[TfidfVectorizer, KMeans, tuple[tuple[str, ...], ...]]`.

Untyped-library imports rely on the mypy configuration of spec 000; no `# type: ignore` and no `# noqa` are added.

## Expected behavior

`aspect_targets`: for each group `g` in `ASPECT_ORDER`, column `aspect_<g.value>`; cell value `1` when the string is
not `""`, else `0`.

`fit_aspect_model`:
- A1. Validates the inputs (edge cases table).
- A2. Stratification key per row: among the groups present in that row, the one with the lowest column total in `Y`
  (tie → lower `ASPECT_ORDER` index); rows with no group get key `9`.
- A3. Template pipeline: `Pipeline([("features", TfidfVectorizer(ngram_range=(1, 2))), ("classifier",
  OneVsRestClassifier(LogisticRegression(class_weight="balanced", max_iter=1000)))])`.
- A4. Out-of-fold scores: for each `(fit_rows, held_rows)` of `cv_splitter().split(np.asarray(texts, dtype=object),
  key, groups)`, `sklearn.base.clone(template)` is fit on `fit_rows` and `predict_proba` fills the `held_rows` rows
  of an `(n, 9)` float array.
- A5. Threshold per group: the value of `_THRESHOLD_GRID` that maximizes
  `f1_score(Y[:, j], scores[:, j] >= t, zero_division=0)`; tie → lowest threshold.
- A6. The template is fit on all rows; returns `(pipeline, thresholds)` with 9 Python floats in `ASPECT_ORDER`.
- A7. Logs `INFO` `"aspect_model_fitted rows=%d thresholds=%s"` (thresholds tuple, no text).

`aspect_report`: `scores = pipeline.predict_proba(np.asarray(texts, dtype=object))`; for each group `j`,
`predicted = scores[:, j] >= thresholds[j]`; `precision_score`, `recall_score`, `f1_score` with `zero_division=0`
against `Y[:, j]`; values as Python floats, not rounded. This dict is the `aspects` key of `report.json`.

`fit_topics`:
- T1. Validates `len(texts) >= 50`.
- T2. `TfidfVectorizer(min_df=5, max_df=0.2)` fit on `list(texts)`; vocabulary of fewer than 5 terms → error.
- T3. For each `k` in `_K_RANGE`: `KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(X)`;
  score = `silhouette_score(X, labels)` (euclidean on L2-normalized TF-IDF rows); a `k` whose labels hold fewer than
  2 distinct values scores `-1.0`. The highest score wins (tie → smaller `k`).
- T4. Terms of topic `t`: the 5 features with the highest `cluster_centers_[t]` value, from
  `numpy.argsort(-center, kind="stable")[:5]` over `get_feature_names_out()` (tie → alphabetical), as `str`.
- T5. Returns `(vectorizer, kmeans, terms)`; `len(terms) == kmeans.n_clusters`. Logs `INFO`
  `"topics_fitted rows=%d k=%d silhouette=%.4f"`. The drift vocabulary is `vectorizer.vocabulary_` keys
  (`docs/contracts.md` §9.1).

## Edge cases and error handling

All errors are `InvalidInputError` (`api/domain/errors.py`), raised before any fit, with these exact details:

| Function | Condition | Detail |
|---|---|---|
| `aspect_targets` | column `aspect_<g>` missing | `"missing column aspect_<g>"` (`<g>` is the group value, `"missing column aspect_platform"`) |
| `fit_aspect_model` | `Y.ndim != 2` or `Y.shape[1] != 9` | `"Y must have shape (n, 9)"` |
| `fit_aspect_model` | `len(texts)`, `Y.shape[0]`, `len(groups)` differ | `"texts, Y and groups must have the same length"` |
| `fit_aspect_model` | a value of `Y` outside `{0, 1}` | `"Y must hold only 0 and 1"` |
| `fit_aspect_model` | a column with fewer than 5 ones | `"aspect group <g> has fewer than 5 positive rows"` |
| `fit_aspect_model` | fewer than 5 distinct `groups` values | `"groups must hold at least 5 distinct values"` |
| `aspect_report` | `len(thresholds) != 9` or `Y.shape != (len(texts), 9)` | `"thresholds and Y must cover the 9 aspect groups"` |
| `fit_topics` | `len(texts) < 50` | `"fit_topics needs at least 50 texts"` |
| `fit_topics` | vectorizer raises `ValueError` or keeps fewer than 5 terms | `"topic vocabulary has fewer than 5 terms"` (raised `from` the `ValueError` when there is one) |

If an existing test not listed here fails because of this change, the implementer does NOT modify it: report its
name and the reason.

## Acceptance tests (prose)

Aspect synthetic data: `KEYWORDS = ("contenidos", "parciales", "retroalimentación", "metodología", "diapositivas",
"horario", "plataforma", "correos", "carga")`; for `i` in `0..179`, text `f"comentario sobre {KEYWORDS[i % 9]} del
curso"`, `Y[i, i % 9] = 1` (other cells 0), `groups[i] = i // 9`.

`tests/unit/ml/test_aspects.py`:
1. `test_aspect_targets_marks_present_groups`: frame of 2 rows with all 9 `aspect_<g>` columns `""`, except row 0
   `aspect_content = "positive"` and row 1 `aspect_platform = "negative"`, `aspect_workload_pace = "neutral"` →
   `[[1,0,0,0,0,0,0,0,0], [0,0,0,0,0,0,1,0,1]]`, dtype `int64`.
2. `test_aspect_targets_rejects_missing_column`: the same frame without `aspect_platform` → detail
   `"missing column aspect_platform"`.
3. `test_fit_aspect_model_picks_lowest_threshold_on_ties`: synthetic data → thresholds `(0.1,) * 9` (verified at the
   pins of `CONTEXT.md`).
4. `test_fit_aspect_model_detects_keyword`: `predict_proba(["el horario del curso", "las diapositivas"])` ≥
   thresholds only at `organization_schedule` for row 0 (score 0.869) and only at `materials` for row 1 (score 0.717);
   scores compared with `abs` ≤ 0.001.
5. `test_fit_aspect_model_pipeline_steps`: step names `("features", "classifier")`; `ngram_range == (1, 2)`;
   `classifier.estimator.class_weight == "balanced"`, `max_iter == 1000`.
6. `test_fit_aspect_model_rejects_bad_shape`: `Y` of shape `(180, 8)` → `"Y must have shape (n, 9)"`.
7. `test_fit_aspect_model_rejects_length_mismatch`: 179 texts → `"texts, Y and groups must have the same length"`.
8. `test_fit_aspect_model_rejects_non_binary`: `Y[0, 0] = 2` → `"Y must hold only 0 and 1"`.
9. `test_fit_aspect_model_rejects_rare_group`: column `platform` set to 0 except 4 rows →
   `"aspect group platform has fewer than 5 positive rows"`.
10. `test_fit_aspect_model_rejects_too_few_groups`: `groups[i] = i % 4` →
    `"groups must hold at least 5 distinct values"`.
11. `test_aspect_report_computes_per_group_metrics`: a test-local stub whose `predict_proba` returns, for 4 texts,
    column 0 `[0.9, 0.2, 0.6, 0.1]` and 0.0 elsewhere; `Y[:, 0] = [1, 1, 0, 0]`, other columns 0; thresholds
    `(0.5,) * 9` → `"content": {"precision": 0.5, "recall": 0.5, "f1": 0.5, "threshold": 0.5}` and
    `"assessment": {"precision": 0.0, "recall": 0.0, "f1": 0.0, "threshold": 0.5}`; keys in `ASPECT_ORDER`.
12. `test_aspect_report_rejects_wrong_threshold_count`: 8 thresholds → `"thresholds and Y must cover the 9 aspect groups"`.

Topic synthetic data: 6 themes of 5 words each: `("alfa", "beta", "gamma", "delta", "epsilon")`, `("rojo", "verde",
"azul", "negro", "blanco")`, `("lunes", "martes", "jueves", "viernes", "sabado")`, `("perro", "gato", "raton",
"conejo", "caballo")`, `("mesa", "silla", "lampara", "puerta", "ventana")`, `("pera", "manzana", "uva", "mango",
"fresa")`; for theme `t` and `i` in `0..9`: `f"curso {w[i % 5]} {w[(i + 1) % 5]} {w[(i + 2) % 5]}"` (60 texts).

`tests/unit/ml/test_topics.py`:
1. `test_fit_topics_selects_k_by_silhouette`: `kmeans.n_clusters == 6` (silhouettes k=4..10: 0.2493, 0.3138, 0.3805,
   0.3767, 0.3730, 0.3692, 0.3654); 6 clusters of 10 texts.
2. `test_fit_topics_drops_frequent_words`: `"curso"` (in 60 of 60 texts) is not in `vectorizer.vocabulary_`;
   vocabulary size 30.
3. `test_fit_topics_terms_are_alphabetical_on_ties`: the set of term tuples equals the 6 sorted themes, among them
   `("azul", "blanco", "negro", "rojo", "verde")` and `("alfa", "beta", "delta", "epsilon", "gamma")`.
4. `test_fit_topics_assign_matches_terms`: `kmeans.predict(vectorizer.transform(["rojo verde azul"]))[0]` indexes
   the color tuple in `terms`.
5. `test_fit_topics_rejects_too_few_texts`: 49 texts → `"fit_topics needs at least 50 texts"`.
6. `test_fit_topics_rejects_empty_vocabulary`: 50 copies of `"curso uno"` → `"topic vocabulary has fewer than 5 terms"`.

`tests/integration/test_aspects_topics_dataset.py` (real `Dataset/`, grouped split of ADR-001):
1. `test_aspect_targets_counts_on_dataset`: column sums `[361, 94, 76, 71, 66, 59, 48, 38, 35]` (`docs/contracts.md` §10).
2. `test_aspect_model_macro_f1_on_test_split`: fit on train rows; mean of the 9 `f1` values of `aspect_report` on
   the test rows ≥ 0.40 (measured 0.4818); every threshold is in `_THRESHOLD_GRID`.
3. `test_clause_aspect_sentiment_on_test_split`: polarity pipeline `Pipeline([("features",
   TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, min_df=2)), ("classifier",
   LogisticRegression(max_iter=1000, class_weight="balanced"))])` fit on train rows; per test row, `split_clauses`,
   one `ClauseAnalysis` per clause (`ClassProbabilities` from the polarity pipeline, `AspectScores` with `present` =
   groups at or above their threshold), `aspect_sentiments`; over every labeled group that appears in the output,
   the share with `polarity` equal to the label ≥ 0.44 (measured 0.5192 on 156 pairs).
4. `test_topics_on_train_rows`: `fit_topics` on train texts → `4 <= n_clusters <= 10`, each topic has 5 distinct
   terms and no term is in `{"de", "la", "el", "en", "que", "los"}` (measured k = 10).

## Out of scope

- The bundle and `report.json` writing (spec 013); `ml.train` wiring (spec 014); the adapters `SklearnAspectModel`
  and `KMeansTopicModel` (specs 018, 019); gold-set evaluation (spec 029).
- A separate per-aspect sentiment model; embeddings for aspects or topics; stop-word lists.

## Definition of Done

- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/pytest -q -m integration tests/integration/test_aspects_topics_dataset.py` → `4 passed`, exit code 0.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed` (dependency rule and size limits).
- [ ] `grep -nE "# noqa|# type: ignore" ml/aspects.py ml/topics.py tests/unit/ml/test_aspects.py tests/unit/ml/test_topics.py tests/integration/test_aspects_topics_dataset.py`
      → no output.
- [ ] `.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing` → `ml/aspects.py` and
      `ml/topics.py` each ≥ 80 % line coverage.
- [ ] `grep -c "random_state=SEED" ml/topics.py` → `1`.
- [ ] `grep -nE "joblib|pickle|print\(" ml/aspects.py ml/topics.py` → no output.
- [ ] `bash scripts/security_grep.sh` → no output, exit code 0.
- [ ] `bash scripts/gate.sh` → last line `GATE OK`, exit code 0.
