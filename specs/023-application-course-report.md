# 023 - Application course report use case
Riesgo: alto

## Objective
Program directors need, per course, an aspect heatmap, a priority ranking, topics and representative quotes
(`ARCHITECTURE.md` §1). The use case `BuildCourseReport` turns the comments of one batch and their analyses into one
`CourseReport` per course. Every quote and topic quote leaves the use case masked by the `Anonymizer` port
(SEC-02). It has no endpoint of its own: spec 024 calls it inside `POST /predict-batch` and returns the reports in
the `courses` field of `BatchResponse`. After this spec, `api/application/course_report.py` exists and is tested
with fake ports.

## Depends on
022 (`tests/fixtures/fake_ports.py`, `AnalyzeBatch`), and through it 004, 005, 006. 022 MUST be `Implemented`.

## Governing files
- `ARCHITECTURE.md` §2 rules 2 and 5, §6 (≤ 20 statements per function, ≤ 300 lines per module, `mypy --strict`,
  immutable entities, only `AppError` subclasses).
- `security-rules.md` SEC-02 (quotes masked), SEC-05 (no logging of comment text: this module does not log),
  SEC-09 (synthetic fixtures).
- `docs/contracts.md` §1.2 (`PolarityCounts`, `AspectCell`, `PriorityEntry`, `TopicSummary`, `CourseReport`), §3
  (`Anonymizer`, `Summarizer`, `TopicModel`), §4.3 (`rank_priorities`), §5 (`BuildCourseReport`).

## Files to create/modify
1. `api/application/course_report.py` (new). Same structure as `api/application/analyze.py` (spec 022): module
   constants, one class with constructor injection, module-private helpers.
2. `tests/fixtures/fake_ports.py` (modify): add `FakeSummarizer` and `FakeTopicModel`; existing fakes unchanged.
3. `tests/unit/application/test_course_report.py` (new).

## External dependencies
None new.

## Interfaces and types
`api/application/course_report.py` imports only from `collections.abc`, `api.domain.entities` (`Comment`,
`CommentAnalysis`, `ASPECT_ORDER`, `Decision`, `Polarity`), `api.domain.reports` (`AspectCell`, `CourseReport`,
`PolarityCounts`, `TopicSummary`), `api.domain.priority` (`rank_priorities`), `api.domain.errors`
(`InferenceError`, `InvalidInputError`), `api.ports.text` (`Anonymizer`, `Summarizer`, `TopicModel`).

Constants:
- `UNKNOWN_COURSE: str = "unknown"` (course key of comments whose `course` is `None`).
- `MIN_QUOTE_COUNT: int = 1`, `MAX_QUOTE_COUNT: int = 10` (`Summarizer.summarize` `k` range).
- `MAX_BATCH_COMMENTS: int = 5000`.

Class (constructor and method exactly as `docs/contracts.md` §5):
- `class BuildCourseReport:` `__init__(self, anonymizer: Anonymizer, summarizer: Summarizer, topics: TopicModel,
  quote_count: int = 3) -> None`; `execute(self, comments: Sequence[Comment], analyses:
  Sequence[CommentAnalysis]) -> tuple[CourseReport, ...]`.

Module-private functions (each ≤ 20 statements):
- `_course_key(comment: Comment) -> str` → `comment.course` or `UNKNOWN_COURSE`.
- `_group_indices(comments: Sequence[Comment]) -> tuple[tuple[str, tuple[int, ...]], ...]` → `(course, indices in
  input order)` pairs sorted by course ascending (Python `str` ordering).
- `_polarity_counts(analyses: Sequence[CommentAnalysis]) -> PolarityCounts` (counts of `decision.label`).
- `_aspect_cells(analyses: Sequence[CommentAnalysis]) -> tuple[AspectCell, ...]` (9 cells in `ASPECT_ORDER`).
- `_topic_summaries(self, texts: Sequence[str], topic_ids: Sequence[int]) -> tuple[TopicSummary, ...]` (method).

`tests/fixtures/fake_ports.py` additions:
- `class FakeSummarizer:` `__init__(self, empty: bool = False) -> None`; attribute `calls: list[tuple[tuple[str,
  ...], int]]`; `summarize(texts, k)` appends `(tuple(texts), k)` and returns the first `k` distinct texts in input
  order (`()` when `empty` is `True`).
- `class FakeTopicModel:` `__init__(self, topic_by_text: Mapping[str, int], terms_by_topic: Mapping[int,
  tuple[str, ...]], short_by: int = 0) -> None`; attribute `assign_calls: list[tuple[str, ...]]`;
  `assign(texts)` appends `tuple(texts)` and returns `topic_by_text.get(t, 0)` per text, dropping the last
  `short_by`; `terms(topic)` returns `terms_by_topic[topic]`, unknown id → `InvalidInputError("unknown topic")`.

## Expected behavior
`BuildCourseReport.__init__`:
1. `quote_count` outside `1..10` → `InvalidInputError("quote_count must be between 1 and 10")`.

`BuildCourseReport.execute(comments, analyses)`:
1. `len(comments) != len(analyses)` → `InvalidInputError("comments and analyses differ in length")`.
2. `len(comments)` outside `1..5000` → `InvalidInputError("batch must hold between 1 and 5000 comments")`.
3. Any `i` with `analyses[i].comment.course != comments[i].course` → `InvalidInputError("comment and analysis are
   not paired")`.
4. `topic_ids = topics.assign(tuple(c.text for c in comments))`: exactly one call over all original (unmasked)
   texts in input order. `len(topic_ids) != len(comments)` → `InferenceError(f"TopicModel.assign returned
   {len(topic_ids)} results for {len(comments)} texts")`.
5. For each `(course, indices)` of `_group_indices(comments)`, builds `CourseReport` with:
   - `course`; `comment_count = len(indices)`;
   - `review_count` = number of `analyses[i].decision.decision == Decision.REVIEW`;
   - `polarity_counts` = counts of `analyses[i].decision.label` (`negative`, `neutral`, `positive`);
   - `aspects`: for each group in `ASPECT_ORDER`, `mentions` = number of analyses whose `aspects` contain an
     `AspectSentiment` of that group; `negative`, `neutral`, `positive` = counts of that sentiment's `polarity`;
   - `priorities = rank_priorities(aspects, comment_count)`;
   - `topics`: one `TopicSummary` per topic id present in the course; `size` = comments of the course in that
     topic; sorted by `size` descending, then topic id ascending; `terms = topics.terms(topic)`; `quote =
     anonymizer.mask(summary[0])` where `summary = summarizer.summarize(topic texts in input order, 1)`;
   - `quotes = tuple(anonymizer.mask(s) for s in summarizer.summarize(course texts in input order,
     quote_count))`.
6. Returns the reports in course order. Summaries are computed on original texts and masked afterwards, so no
   unmasked text is returned (SEC-02).

## Edge cases and error handling
| Input | Result |
|---|---|
| `quote_count` 0 or 11 | `InvalidInputError`, detail `"quote_count must be between 1 and 10"` |
| `comments` and `analyses` of lengths 2 and 1 | `InvalidInputError`, detail `"comments and analyses differ in length"`; no port called |
| Empty `comments` and `analyses` | `InvalidInputError`, detail `"batch must hold between 1 and 5000 comments"` |
| `analyses[i].comment.course` differs from `comments[i].course` | `InvalidInputError`, detail `"comment and analysis are not paired"` |
| `assign` returns fewer ids | `InferenceError`, detail `"TopicModel.assign returned <n> results for <m> texts"` |
| `summarize(..., 1)` for a topic returns `()` | `InferenceError`, detail `"Summarizer.summarize returned no sentence"` |
| `course` is `None` | Grouped under `"unknown"` |
| Course whose comments mention no aspect | 9 cells with `mentions == 0`; `priorities == ()` |
| Port raises (`InferenceError`, `AnonymizerUnavailableError`, `InvalidInputError` from `terms`) | Propagates unchanged |

The module has no `try` and does not log. If an existing test not listed here fails because of this change, the
implementer does not modify it: they report its name and the reason.

## Acceptance tests (prose)
Helper inside the test file: `analysis(comment, label, decision, aspects)` builds a `CommentAnalysis` with
probabilities `(0.1, 0.1, 0.8)` reordered so `label` gets 0.8, set `{label}` at 0.9, `DecisionResult(decision,
CONFIDENT if decision is CLASSIFY else EXPECTED_COST, label)`, the given `aspects` (score 0.9, clause index 0 and
1 in order) and `influences = ()`.

Data (synthetic): `c0 = Comment("Ana explicó bien el contenido.", "Redes")`, `c1 = Comment("Los parciales fueron
difíciles.", "Redes")`, `c2 = Comment("El horario fue malo.", "Redes")`, `c3 = Comment("Buen curso.")`.
Analyses: `a0` positive, classify, `(content, positive)`; `a1` negative, review, `(content, negative)`,
`(assessment, negative)`; `a2` negative, classify, `(organization_schedule, negative)`; `a3` neutral, review, no
aspects. Fakes: `FakeTopicModel({c0.text: 1, c1.text: 0, c2.text: 1, c3.text: 0}, {0: ("parciales", "examen",
"notas", "preguntas", "dificultad"), 1: ("contenido", "horario", "clase", "tema", "curso")})`, `FakeSummarizer()`,
`FakeAnonymizer()`, `quote_count = 3`. `R = execute((c0, c1, c2, c3), (a0, a1, a2, a3))`.

1. `test_course_report_groups_and_sorts` — `len(R) == 2`; `R[0].course == "Redes"`; `R[1].course == "unknown"`.
2. `test_course_report_counts` — `R[0].comment_count == 3`, `R[0].review_count == 1`, `R[0].polarity_counts ==
   PolarityCounts(2, 0, 1)`; `R[1].comment_count == 1`, `R[1].review_count == 1`, `R[1].polarity_counts ==
   PolarityCounts(0, 1, 0)`.
3. `test_course_report_aspect_cells` — `R[0].aspects` has 9 cells in `ASPECT_ORDER`; content `(mentions 2,
   negative 1, neutral 0, positive 1)`, assessment `(1, 1, 0, 0)`, organization_schedule `(1, 1, 0, 0)`, the other
   6 `(0, 0, 0, 0)`; every cell of `R[1]` has `mentions == 0`.
4. `test_course_report_priorities` — `R[0].priorities` groups in order `content`, `assessment`,
   `organization_schedule` with ranks 1, 2, 3; scores `0.3333333333333333` (prevalence `2/3`, smoothed share
   `0.5`), `0.2222222222222222` (prevalence `1/3`, share `2/3`), `0.2222222222222222` (tie broken by
   `ASPECT_ORDER`); all `low_support` true (compare floats with `pytest.approx(abs=1e-12)`); `R[1].priorities ==
   ()`.
5. `test_course_report_topics` — `R[0].topics == (TopicSummary(1, 2, ("contenido", "horario", "clase", "tema",
   "curso"), "[PERSON] explicó bien el contenido."), TopicSummary(0, 1, ("parciales", "examen", "notas",
   "preguntas", "dificultad"), "Los parciales fueron difíciles."))`; `R[1].topics == (TopicSummary(0, 1,
   ("parciales", "examen", "notas", "preguntas", "dificultad"), "Buen curso."),)`.
6. `test_course_report_quotes_masked` — `R[0].quotes == ("[PERSON] explicó bien el contenido.", "Los parciales
   fueron difíciles.", "El horario fue malo.")`; `R[1].quotes == ("Buen curso.",)`; no string in any
   `quote`/`quotes` of `R` contains `"Ana"`.
7. `test_course_report_assign_once_on_original_texts` — `assign_calls == [(c0.text, c1.text, c2.text, c3.text)]`.
8. `test_course_report_summarizer_calls` — summarizer `calls` contains `((c0.text, c2.text), 1)`, `((c1.text,),
   1)`, `((c0.text, c1.text, c2.text), 3)`, `((c3.text,), 1)` and `((c3.text,), 3)`.
9. `test_course_report_topic_size_tie_by_id` — 2 comments of course `"Redes"` assigned to topics 3 and 1: topics
   order `1`, `3`.
10. `test_course_report_rejects_length_mismatch` — `execute((c0, c1), (a0,))` raises `InvalidInputError`;
    `assign_calls == []`.
11. `test_course_report_rejects_empty` — `execute((), ())` raises `InvalidInputError`.
12. `test_course_report_rejects_unpaired` — `execute((c3,), (a0,))` raises `InvalidInputError` with detail
    `"comment and analysis are not paired"`.
13. `test_course_report_short_assign` — `FakeTopicModel(..., short_by=1)` raises `InferenceError` with detail
    `"TopicModel.assign returned 3 results for 4 texts"`.
14. `test_course_report_empty_summary` — `FakeSummarizer(empty=True)` raises `InferenceError` with detail
    `"Summarizer.summarize returned no sentence"`.
15. `test_course_report_rejects_quote_count` — `quote_count` 0 and 11 raise `InvalidInputError`; 1 and 10 do not.
16. `test_course_report_with_analyze_batch` — `AnalyzeBatch` (spec 022 fakes, defaults) over `(c0, c3)`, then
    `execute((c0, c3), batch_result)`: 2 reports, `"Redes"` quotes `("[PERSON] explicó bien el contenido.",)`.

## Out of scope
JSON serialization of `CourseReport` and rounding to 4 decimals (spec 021); the `POST /predict-batch` route
(spec 024); training of the topic model (spec 012); the heatmap UI (spec 026); priority formula (spec 005).

## Definition of Done
- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/pytest -q tests/unit/application/test_course_report.py` → `16 passed`.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed`.
- [ ] `grep -rnE "# noqa|# type: ignore" api/application/course_report.py tests/fixtures/fake_ports.py
      tests/unit/application/test_course_report.py` → no output.
- [ ] `grep -nE "^(from|import) (api\.adapters|api\.main|ml)(\.| |$)" api/application/course_report.py` → no
      output.
- [ ] `grep -nE "^\s*(import logging|try:|except)|print\(" api/application/course_report.py` → no output.
- [ ] `grep -n "@app\.\|APIRouter\|add_api_route" api/application/course_report.py` → no output (no endpoint).
- [ ] `.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing` → line for
      `api/application/course_report.py` ≥ 80 %.
- [ ] `bash scripts/gate.sh` → last line `GATE OK`, exit code 0.
