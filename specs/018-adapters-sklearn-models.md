# 018 - Adapters scikit-learn models and occlusion explainer
Riesgo: alto

## Objective

The use cases (`docs/contracts.md` §5) depend on the ports `PolarityModel`, `AspectModel` and `Explainer`, but no
class implements them over the verified bundle loaded by `TrustedModelStore` (spec 017). This spec creates
`SklearnPolarityModel`, `SklearnAspectModel` (`api/adapters/sklearn_models.py`) and `OcclusionExplainer`
(`api/adapters/explainer.py`). After it, the composition root (spec 024) can build the three adapters from
`ModelStore.bundle()` keys `polarity_pipeline`, `conformal_classifier`, `aspect_pipeline` and `aspect_thresholds`
(`docs/contracts.md` §9.1). Empty input raises a typed error; ambiguous input (no known word) returns the model's
probabilities unchanged, and the domain decision agent sends it to review.

## Depends on

006 (ports), 017 (model store; implies 007 for `ml.data.normalize_text`, 013 for the bundle layout).

## Governing files

- `ARCHITECTURE.md` §2 (adapters may import `api.domain`, `api.ports`, `ml`, third parties), §4 (port table), §6
  (≤ 20 statements per function, ≤ 300 lines per module, `mypy --strict`, errors wrapped with `raise ... from e`).
- `security-rules.md` SEC-05 (no comment text in logs), SEC-14 and SEC-15 (this spec loads nothing from disk and
  MUST NOT call `joblib.load`, `pickle` or `torch.load`), SEC-21.
- ADR-002 (probabilities from the refit pipeline, sets from `CrossConformalClassifier.predict_set`), ADR-003.
- `docs/contracts.md` §1.1, §2, §3, §9.1.

## Files to create/modify

1. `api/adapters/sklearn_models.py` (new). Reference pattern: `api/adapters/model_store.py` (spec 017).
2. `api/adapters/explainer.py` (new). Same reference pattern.
3. `tests/unit/adapters/test_sklearn_models.py` (new).
4. `tests/unit/adapters/test_explainer.py` (new).

No existing test changes expectation.

## External dependencies

None new (scikit-learn `==1.9.1`, mapie `==1.6.0`, numpy `==2.5.4` from `CONTEXT.md`).

## Interfaces and types

Module `api/adapters/sklearn_models.py`:

- Constants: `MAX_TEXTS: int = 5000`, `CLASS_COUNT: int = 3`, `ASPECT_COUNT: int = 9`.
- `validate_texts(texts: Sequence[str]) -> list[str]`: public helper reused by `api/adapters/explainer.py`;
  returns `[normalize_text(t) for t in texts]` (`normalize_text` from `ml.data`, contract §8).
- `class SklearnPolarityModel` (implements `PolarityModel`):
  - `__init__(self, pipeline: object, conformal: object, confidence_level: float) -> None`
  - `predict_proba(self, texts: Sequence[str]) -> tuple[ClassProbabilities, ...]`
  - `predict_set(self, texts: Sequence[str]) -> tuple[ConformalSet, ...]`
- `class SklearnAspectModel` (implements `AspectModel`):
  - `__init__(self, pipeline: object, thresholds: tuple[float, ...]) -> None`
  - `detect(self, texts: Sequence[str]) -> tuple[AspectScores, ...]`

Module `api/adapters/explainer.py`:

- Constants: `WORD_PATTERN: re.Pattern[str] = re.compile(r"\w+")`, `MIN_TOP_K: int = 1`, `MAX_TOP_K: int = 20`.
- `class OcclusionExplainer` (implements `Explainer`):
  - `__init__(self, model: PolarityModel) -> None`
  - `explain(self, text: str, top_k: int) -> tuple[WordInfluence, ...]`

Attribute narrowing: constructors check `isinstance(pipeline, sklearn.pipeline.Pipeline)` and
`isinstance(conformal, mapie.classification.CrossConformalClassifier)` and store the narrowed objects in private
attributes (`_pipeline`, `_conformal`, `_confidence_level`, `_thresholds`, `_model`). Untyped imports (`sklearn`,
`mapie`) follow the mypy configuration of `pyproject.toml` (spec 000); this spec adds no `# type: ignore` and no
`# noqa`. Every public class and method has a Google-style docstring.

## Expected behavior

`validate_texts(texts)`:
1. `len(texts) == 0` or `len(texts) > 5000` → `InvalidInputError("texts must hold 1 to 5000 items")`.
2. Any `t` with `t.strip() == ""` → `InvalidInputError("texts must be non-empty after strip")`.
3. Returns the list of `normalize_text(t)` in input order (training applies the same function, contract §10 rule 1).

`SklearnPolarityModel.__init__`:
1. `pipeline` not a `Pipeline` → `ModelIntegrityError("polarity pipeline has an unexpected type")`.
2. `conformal` not a `CrossConformalClassifier` → `ModelIntegrityError("conformal classifier has an unexpected
   type")`.
3. Reading `pipeline.classes_` raises `AttributeError` (unfitted pipeline), or
   `[int(c) for c in pipeline.classes_] != [0, 1, 2]` →
   `ModelIntegrityError("polarity classes differ from POLARITY_ORDER")`.
4. `not 0.0 < confidence_level < 1.0` → `ModelIntegrityError("confidence level out of range")`.

`SklearnPolarityModel.predict_proba(texts)`:
1. `normalized = validate_texts(texts)`.
2. `matrix = self._pipeline.predict_proba(normalized)`; a raised `ValueError`, `TypeError` or `AttributeError` →
   `InferenceError("polarity inference failed")` raised `from` the cause.
3. `numpy.isfinite(matrix).all()` false or `matrix.shape != (len(texts), 3)` →
   `InferenceError("polarity model returned invalid probabilities")`.
4. Returns one `ClassProbabilities(negative=float(row[0]), neutral=float(row[1]), positive=float(row[2]))` per row,
   same order as `texts`.

`SklearnPolarityModel.predict_set(texts)`:
1. `normalized = validate_texts(texts)`.
2. `_, y_set = self._conformal.predict_set(numpy.asarray(normalized, dtype=object), agg_scores="mean")`; the same
   three exceptions → `InferenceError("conformal inference failed")` raised `from` the cause.
3. `y_set.shape != (len(texts), 3, 1)` → `InferenceError("conformal model returned an unexpected shape")`.
4. Returns one `ConformalSet(labels=frozenset(POLARITY_ORDER[j] for j in range(3) if y_set[i, j, 0]),
   confidence_level=self._confidence_level)` per text.

`SklearnAspectModel.__init__`:
1. `pipeline` not a `Pipeline` → `ModelIntegrityError("aspect pipeline has an unexpected type")`.
2. `len(thresholds) != 9` or any threshold outside `[0.0, 1.0]` →
   `ModelIntegrityError("aspect thresholds are invalid")`.

`SklearnAspectModel.detect(texts)`:
1. `normalized = validate_texts(texts)`.
2. `matrix = self._pipeline.predict_proba(normalized)`; the same three exceptions →
   `InferenceError("aspect inference failed")` raised `from` the cause.
3. Non-finite values or `matrix.shape != (len(texts), 9)` →
   `InferenceError("aspect model returned invalid scores")`.
4. Per row: `scores = tuple(float(v) for v in row)`; `present = frozenset(ASPECT_ORDER[j] for j in range(9) if
   scores[j] >= thresholds[j])`; returns `AspectScores(scores, present)` per text.

`OcclusionExplainer.explain(text, top_k)`:
1. `top_k` outside `1..20` → `InvalidInputError("top_k must be between 1 and 20")`; `text.strip() == ""` →
   `InvalidInputError("text must be non-empty after strip")`.
2. `words` = distinct lowercase `WORD_PATTERN` matches of `text`, in order of first appearance.
3. For each word, the occluded text is `text` with every `WORD_PATTERN` match whose lowercase equals the word
   replaced by `""`, then every whitespace run replaced by one space, then stripped. Words whose occluded text is
   `""` are dropped.
4. One call `probabilities = self._model.predict_proba([text, *occluded_texts])`.
5. `top = probabilities[0].top()`; `delta_i = probabilities[0].of(top) - probabilities[i].of(top)`.
6. Returns `WordInfluence(word, delta)` items sorted by `abs(delta)` descending, then `word` ascending, cut to the
   first `top_k`. No word left → `()` without calling the model.

No method logs comment text; the module logs nothing.

## Edge cases and error handling

| Input | Result |
|---|---|
| `texts == []` or 5001 texts | `InvalidInputError("texts must hold 1 to 5000 items")` |
| a text `"   "` | `InvalidInputError("texts must be non-empty after strip")` |
| text with no word known to the vectorizer (`"zzz qqq"`) | valid probabilities from the model, no error; the set may be empty |
| unfitted `Pipeline` passed to the constructor | `ModelIntegrityError("polarity classes differ from POLARITY_ORDER")` |
| `pipeline.predict_proba` raises `ValueError` | `InferenceError("polarity inference failed")`, `__cause__` is the `ValueError` |
| pipeline fitted on 2 classes | `ModelIntegrityError("polarity classes differ from POLARITY_ORDER")` |
| `confidence_level` 1.0 | `ModelIntegrityError("confidence level out of range")` |
| 8 thresholds, or a threshold 1.5 | `ModelIntegrityError("aspect thresholds are invalid")` |
| `top_k` 0 or 21 | `InvalidInputError("top_k must be between 1 and 20")` |
| explained text `"Excelente"` (single word) | `()`, model not called |
| `InferenceError` raised by the wrapped model | propagates unchanged from `explain` |

`InferenceError`, `InvalidInputError` and `ModelIntegrityError` details hold no comment text. If an existing test
not listed in this spec fails because of this change, the implementer does not modify it: they report its name and
the reason.

## Acceptance tests (prose)

Fixture `polarity_fixture` (in `tests/unit/adapters/test_sklearn_models.py`): texts = `"el curso fue terrible"` ×
10, `"el curso fue normal"` × 10, `"el curso fue excelente"` × 10; `y` = 0 × 10, 1 × 10, 2 × 10; groups
`numpy.arange(30)`. Pipeline `Pipeline([("features", TfidfVectorizer()), ("classifier", LogisticRegression())])`
fitted on the list. Conformal: `CrossConformalClassifier(<same unfitted pipeline>, confidence_level=0.9,
conformity_score="lac", cv=StratifiedGroupKFold(n_splits=3, shuffle=True, random_state=42), random_state=42)` with
`fit_conformalize(numpy.asarray(texts, dtype=object), y, groups=groups)`. Values below were measured with the pins
of `CONTEXT.md`; float comparisons use `abs` difference ≤ 1e-6.

1. `test_polarity_predict_proba_returns_rows_in_order`: `["el curso fue excelente", "el curso fue terrible"]` →
   `(0.111532, 0.111532, 0.776936)` and `(0.776936, 0.111532, 0.111532)`.
2. `test_polarity_predict_proba_unknown_words_returns_uniform`: `["zzz qqq"]` → `(0.333333, 0.333333, 0.333333)`.
3. `test_polarity_predict_proba_normalizes_whitespace`: `["  el   curso fue excelente "]` equals the result of
   `["el curso fue excelente"]`.
4. `test_polarity_predict_set_maps_labels`: `["el curso fue excelente", "el curso fue terrible", "zzz qqq"]` →
   labels `{positive}`, `{negative}`, `{}`; every `confidence_level == 0.9`.
5. `test_polarity_rejects_empty_sequence`: `[]` → `InvalidInputError`, for `predict_proba` and `predict_set`.
6. `test_polarity_rejects_too_many_texts`: 5001 copies of `"el curso"` → `InvalidInputError`.
7. `test_polarity_rejects_blank_text`: `["el curso", "   "]` → `InvalidInputError`.
8. `test_polarity_library_error_raises_inference_error`: fitted pipeline whose instance attribute
   `predict_proba` is replaced (pytest `monkeypatch.setattr`) by a function raising `ValueError("x")` after
   construction; `predict_proba(["el curso"])` → `InferenceError` whose `__cause__` is that `ValueError`. An
   unfitted pipeline passed to the constructor → `ModelIntegrityError`.
9. `test_polarity_rejects_wrong_types`: `pipeline="x"` → `ModelIntegrityError`; `conformal="x"` →
   `ModelIntegrityError`.
10. `test_polarity_rejects_two_class_pipeline`: pipeline fitted on the 20 rows of classes 0 and 2 →
    `ModelIntegrityError`.
11. `test_polarity_rejects_confidence_level_out_of_range`: 0.0 and 1.0 → `ModelIntegrityError`.

Fixture `aspect_fixture`: 18 texts `f"palabra{j} comentario"` for `j` in 0..8, each twice; `Y` int (18, 9) with
`Y[i, j] = 1` for the row of `palabra{j}`; pipeline `Pipeline([("features", TfidfVectorizer()), ("classifier",
OneVsRestClassifier(LogisticRegression()))])` fitted on them.

12. `test_aspect_detect_scores_match_pipeline`: `["palabra0 comentario"]` → `scores` equal
    `pipeline.predict_proba` row 0 within 1e-12, length 9, each a Python `float`.
13. `test_aspect_detect_threshold_zero_marks_all_present`: thresholds `(0.0,) * 9` → `present` has 9 groups.
14. `test_aspect_detect_threshold_one_marks_none`: thresholds `(1.0,) * 9` → `present == frozenset()`.
15. `test_aspect_detect_threshold_equal_score_is_present`: thresholds `(s0,) + (1.0,) * 8` with `s0` the content
    score of `"palabra0 comentario"` → `present == {content}`.
16. `test_aspect_rejects_invalid_thresholds`: 8 thresholds; and `(1.5,) + (0.5,) * 8` → `ModelIntegrityError`.
17. `test_aspect_detect_rejects_empty_sequence`: `[]` → `InvalidInputError`.

`tests/unit/adapters/test_explainer.py` uses a stub `PolarityModel` (class with `predict_proba` returning a fixed
mapping from text to `ClassProbabilities`, recording each call). Mapping for text `"Buen curso, mal horario"`:
itself → `(0.25, 0.25, 0.5)`; `"curso, mal horario"` → `(0.125, 0.125, 0.75)`; `"Buen , mal horario"` →
`(0.25, 0.25, 0.5)`; `"Buen curso, horario"` → `(0.0625, 0.0625, 0.875)`; `"Buen curso, mal"` →
`(0.375, 0.375, 0.25)`.

18. `test_explainer_ranks_by_absolute_delta`: `top_k=3` → `(("mal", -0.375), ("buen", -0.25), ("horario", 0.25))`;
    the stub received one call with 5 texts in the order above.
19. `test_explainer_top_k_larger_than_words`: `top_k=20` → 4 items, last `("curso", 0.0)`.
20. `test_explainer_repeated_word_counted_once`: text `"muy muy bueno"`, stub returns `(0.25, 0.25, 0.5)` for
    itself, `(0.5, 0.25, 0.25)` for `"bueno"`, `(0.25, 0.25, 0.5)` for `"muy muy"` → `(("muy", 0.25),
    ("bueno", 0.0))` with `top_k=5`.
21. `test_explainer_single_word_returns_empty`: `"Excelente"` → `()`, stub never called.
22. `test_explainer_rejects_top_k_out_of_range`: 0 and 21 → `InvalidInputError`.
23. `test_explainer_rejects_blank_text`: `"  "` → `InvalidInputError`.
24. `test_explainer_propagates_inference_error`: stub raising `InferenceError("x")` → `InferenceError`.

## Out of scope

- Loading or verifying the bundle (spec 017), building adapters in the composition root (spec 024), the decision
  rules (spec 004), embeddings download (spec 009).
- Caching predictions, batching beyond one call per method, thread pools.

## Definition of Done

- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed` (dependency rule and size limits).
- [ ] `grep -nE "noqa|type: ignore" api/adapters/sklearn_models.py api/adapters/explainer.py tests/unit/adapters/test_sklearn_models.py tests/unit/adapters/test_explainer.py`
      → no output.
- [ ] `grep -nE "joblib|pickle|torch\.load|open\(" api/adapters/sklearn_models.py api/adapters/explainer.py` → no
      output (SEC-14, SEC-15).
- [ ] `.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing` → rows
      `api/adapters/sklearn_models.py` and `api/adapters/explainer.py` each ≥ 80 %.
- [ ] `bash scripts/gate.sh` → last line `GATE OK`, exit code 0.
