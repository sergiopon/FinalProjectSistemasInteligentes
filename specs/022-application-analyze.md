# 022 - Application analyze use cases
Riesgo: alto

## Objective
The API needs two use cases that turn comments into `CommentAnalysis` entities: `AnalyzeComment` for `POST /predict`
(caller's own text, unmasked, with word influences) and `AnalyzeBatch` for `POST /predict-batch` (up to 5,000
comments, text masked by the `Anonymizer` port, SEC-02). Both receive every dependency through the constructor
(`ARCHITECTURE.md` §2 rule 5) and depend only on ports and domain functions. After this spec,
`api/application/analyze.py` exists and is tested with in-memory fake ports, without any model or network.

## Depends on
004, 005, 006 (decision agent, clauses, ports). All three MUST be `Implemented` before this spec starts.

## Governing files
- `ARCHITECTURE.md` §2 rules 2 and 5 (application imports only `api.domain`, `api.ports`, standard library;
  constructor injection, no globals), §3 step 7, §6 (≤ 20 statements per function, ≤ 6 arguments, ≤ 300 lines per
  module, `mypy --strict`, `from __future__ import annotations`, Google docstrings, only `AppError` subclasses).
- `security-rules.md` SEC-02 (batch text masked before it leaves the use case; `/predict` returns the caller's own
  text), SEC-05 (no comment text in logs: this module does not log), SEC-09 (synthetic fixtures only).
- `docs/contracts.md` §1.1, §2, §3, §4.1, §4.2, §5. ADR-002 (decision agent).

## Files to create/modify
1. `api/application/analyze.py` (new). No module of this layer exists yet; the structure follows
   `docs/contracts.md` §5.
2. `tests/fixtures/fake_ports.py` (new). Fake ports reused by specs 023 and 024.
3. `tests/unit/application/test_analyze.py` (new). Tests of `AnalyzeComment`.
4. `tests/unit/application/test_analyze_batch.py` (new). Tests of `AnalyzeBatch`.

## External dependencies
None new.

## Interfaces and types
`api/application/analyze.py` imports exactly: `collections.abc.Sequence`; from `api.domain.entities`: `Comment`,
`CommentAnalysis`, `ClauseAnalysis`, `AspectSentiment`, `ClassProbabilities`, `ConformalSet`, `AspectScores`;
from `api.domain.decision`: `DecisionCosts`, `decide`; from `api.domain.clauses`: `split_clauses`,
`aspect_sentiments`; from `api.domain.errors`: `InferenceError`, `InvalidInputError`; from `api.ports.models`:
`PolarityModel`, `AspectModel`, `Explainer`; from `api.ports.text`: `Anonymizer`.

Constants:
- `MAX_PORT_TEXTS: int = 5000` (port precondition, `docs/contracts.md` §3).
- `MIN_INFLUENCE_COUNT: int = 1`, `MAX_INFLUENCE_COUNT: int = 20` (`Explainer.explain` `top_k` range).

Classes (exact constructor signatures of `docs/contracts.md` §5; attributes are private, set once, never mutated):
- `class AnalyzeComment:` `__init__(self, polarity: PolarityModel, aspects: AspectModel, explainer: Explainer,
  costs: DecisionCosts, influence_count: int = 5) -> None`; `execute(self, comment: Comment) -> CommentAnalysis`.
- `class AnalyzeBatch:` `__init__(self, polarity: PolarityModel, aspects: AspectModel, anonymizer: Anonymizer,
  costs: DecisionCosts) -> None`; `execute(self, comments: Sequence[Comment]) -> tuple[CommentAnalysis, ...]`.

Module-private functions (names binding so both classes share them):
- `_checked[T](results: tuple[T, ...], expected: int, port: str) -> tuple[T, ...]` (PEP 695 type parameter,
  no `TypeVar`; ruff `UP047`): returns
  `results` when `len(results) == expected`, else raises `InferenceError(f"{port} returned {len(results)} results
  for {expected} texts")`.
- `_chunks(texts: Sequence[str]) -> tuple[Sequence[str], ...]`: consecutive slices of at most `MAX_PORT_TEXTS`
  items, in order.
- `_clause_sentiments(polarity: PolarityModel, aspects: AspectModel, clause_groups: Sequence[tuple[str, ...]]) ->
  tuple[tuple[AspectSentiment, ...], ...]`: one entry per group, in order.

`tests/fixtures/fake_ports.py` (structural implementations of the ports; instance attributes may be lists because
they record calls; no module-level mutable state):
- `DEFAULT_PROBABILITIES: tuple[float, float, float] = (0.1, 0.1, 0.8)`; `DEFAULT_SET: frozenset[Polarity] =
  frozenset({Polarity.POSITIVE})`.
- `class FakePolarityModel:` `__init__(self, probabilities: Mapping[str, tuple[float, float, float]], sets:
  Mapping[str, frozenset[Polarity]], confidence_level: float = 0.9, short_by: int = 0) -> None`; attributes
  `proba_calls: list[tuple[str, ...]]`, `set_calls: list[tuple[str, ...]]`. `predict_proba` appends
  `tuple(texts)` to `proba_calls` and returns `ClassProbabilities(*probabilities.get(t, DEFAULT_PROBABILITIES))`
  per text; `predict_set` appends to `set_calls` and returns `ConformalSet(sets.get(t, DEFAULT_SET),
  confidence_level)` per text. Both drop the last `short_by` results.
- `class FakeAspectModel:` `__init__(self, scores: Mapping[str, Mapping[AspectGroup, float]], threshold: float =
  0.5, short_by: int = 0) -> None`; attribute `detect_calls: list[tuple[str, ...]]`. `detect` returns per text
  `AspectScores(scores tuple in ASPECT_ORDER with 0.0 for missing groups, present = groups with score >=
  threshold)`, dropping the last `short_by` results.
- `class FakeExplainer:` `__init__(self, influences: tuple[WordInfluence, ...]) -> None`; attribute `calls:
  list[tuple[str, int]]`; `explain(text, top_k)` appends `(text, top_k)` and returns `influences[:top_k]`.
- `class FakeAnonymizer:` `__init__(self) -> None`; attribute `calls: list[str]`; `mask(text)` appends `text` and
  returns `text.replace("Ana", "[PERSON]")`.

## Expected behavior
`AnalyzeComment.__init__`:
1. `influence_count` outside `1..20` → `InvalidInputError("influence_count must be between 1 and 20")`.

`AnalyzeComment.execute(comment)`:
1. `texts = (comment.text,)`. `probabilities = _checked(polarity.predict_proba(texts), 1,
   "PolarityModel.predict_proba")[0]`; `conformal_set = _checked(polarity.predict_set(texts), 1,
   "PolarityModel.predict_set")[0]`.
2. `decision = decide(probabilities, conformal_set, costs)`.
3. `clauses = split_clauses(comment.text)`; `sentiments = _clause_sentiments(polarity, aspects, (clauses,))[0]`.
4. `influences = explainer.explain(comment.text, influence_count)`.
5. Returns `CommentAnalysis(comment, probabilities, conformal_set, decision, sentiments, influences)` with the
   same `comment` object (text unmasked, SEC-02).

`AnalyzeBatch.execute(comments)`:
1. `len(comments)` outside `1..5000` → `InvalidInputError("batch must hold between 1 and 5000 comments")`.
2. `texts = tuple(c.text for c in comments)`; one `predict_proba(texts)` and one `predict_set(texts)` call, each
   checked with `_checked(..., len(texts), "<Port.method>")`.
3. `decisions[i] = decide(probabilities[i], sets[i], costs)`.
4. `sentiments = _clause_sentiments(polarity, aspects, tuple(split_clauses(t) for t in texts))`.
5. `masked[i] = Comment(text=anonymizer.mask(comments[i].text), course=comments[i].course)`; `mask` is called
   exactly once per comment, in input order.
6. Returns `CommentAnalysis(masked[i], probabilities[i], sets[i], decisions[i], sentiments[i], ())` for each `i`,
   in input order.

`_clause_sentiments(polarity, aspects, clause_groups)`:
1. `flat` = every clause of every group, in order. For each slice of `_chunks(flat)`: one `predict_proba(slice)`
   and one `detect(slice)` call, each checked against `len(slice)`. With ≤ 5,000 clauses this is exactly one call
   of each method.
2. Rebuilds, per group, `ClauseAnalysis(text, probabilities, aspects)` for its clauses and returns
   `aspect_sentiments(group_clauses)`; `clause_index` is therefore the index inside that comment's clauses.

## Edge cases and error handling
| Input | Result |
|---|---|
| `influence_count = 0` or `21` | `InvalidInputError`, detail `"influence_count must be between 1 and 20"` |
| `AnalyzeBatch.execute(())` or 5,001 comments | `InvalidInputError`, detail `"batch must hold between 1 and 5000 comments"`; no port is called |
| A port returns fewer results than texts | `InferenceError`, detail `"<Port.method> returned <n> results for <m> texts"`; ports listed as `PolarityModel.predict_proba`, `PolarityModel.predict_set`, `AspectModel.detect` |
| Port raises `InferenceError` or `AnonymizerUnavailableError` | Propagates unchanged (no `try` in this module) |
| More than 5,000 clauses in one batch | Clause calls split into slices of 5,000 (precondition of `docs/contracts.md` §3) |
| Comment with no aspect present in any clause | `aspects == ()` |

The use cases never catch exceptions and never log comment text. If an existing test not listed here fails
because of this change, the implementer does not modify it: they report its name and the reason.

## Acceptance tests (prose)
Shared data: `costs = DecisionCosts(5.0, 1.0, True)`. Clause texts and fake values below are synthetic.

`tests/unit/application/test_analyze.py`. Comment `C1 = Comment("El contenido fue claro, pero los parciales
fueron difíciles.")`. Fake polarity: full text → `(0.31, 0.52, 0.17)` with set `{negative, neutral}`;
`"El contenido fue claro"` → `(0.05, 0.10, 0.85)`; `"los parciales fueron difíciles"` → `(0.80, 0.15, 0.05)`. Fake
aspects: `"El contenido fue claro"` → `{content: 0.91}`; `"los parciales fueron difíciles"` → `{assessment: 0.77}`.
Fake explainer influences: `(WordInfluence("difíciles", 0.14), WordInfluence("claro", -0.09))`.
1. `test_analyze_comment_returns_decision` — result decision is `DecisionResult(REVIEW, SET_NOT_SINGLETON,
   NEUTRAL)`; probabilities `(0.31, 0.52, 0.17)`; conformal set labels `{negative, neutral}`.
2. `test_analyze_comment_aspects_from_clauses` — `aspects == (AspectSentiment(CONTENT, POSITIVE, 0.91, 0),
   AspectSentiment(ASSESSMENT, NEGATIVE, 0.77, 1))`.
3. `test_analyze_comment_port_calls` — `proba_calls == [(C1.text,), ("El contenido fue claro", "los parciales
   fueron difíciles")]`; `set_calls == [(C1.text,)]`; `detect_calls == [("El contenido fue claro", "los parciales
   fueron difíciles")]`; explainer `calls == [(C1.text, 5)]`.
4. `test_analyze_comment_returns_unmasked_text` — comment `Comment("Ana explicó bien.", "Redes")`: `result.comment
   is` the input object and `result.comment.text == "Ana explicó bien."`.
5. `test_analyze_comment_influences_limited` — `influence_count=1`: `influences == (WordInfluence("difíciles",
   0.14),)` and explainer `calls == [(C1.text, 1)]`.
6. `test_analyze_comment_rejects_influence_count` — `influence_count` 0 and 21 each raise `InvalidInputError`;
   20 and 1 construct without error.
7. `test_analyze_comment_short_port_result` — `FakePolarityModel(..., short_by=1)`: `execute(C1)` raises
   `InferenceError` whose `detail == "PolarityModel.predict_proba returned 0 results for 1 texts"`.
8. `test_analyze_comment_confident_default` — comment `Comment("Buen curso.")` with no fake entries: decision
   `DecisionResult(CLASSIFY, CONFIDENT, POSITIVE)` (cost `0.9999999999999998 <= 1.0`), `aspects == ()`.

`tests/unit/application/test_analyze_batch.py`. Comments `B0 = Comment("Ana dio buen contenido.", "Redes")`, `B1 =
Comment("Los parciales fueron difíciles; el horario fue malo.", "Redes")`. Fake polarity: `B1.text` → `(0.60,
0.30, 0.10)` with set `{negative}`; `"Los parciales fueron difíciles"` → `(0.80, 0.15, 0.05)`; `"el horario fue
malo"` → `(0.70, 0.20, 0.10)`. Fake aspects: `"Ana dio buen contenido"` → `{content: 0.9}`; `"Los parciales
fueron difíciles"` → `{assessment: 0.8}`; `"el horario fue malo"` → `{organization_schedule: 0.7}`.
9. `test_analyze_batch_masks_text` — `result[0].comment == Comment("[PERSON] dio buen contenido.", "Redes")`;
   `result[1].comment.text == B1.text`; anonymizer `calls == [B0.text, B1.text]`.
10. `test_analyze_batch_decisions` — `result[0].decision == DecisionResult(CLASSIFY, CONFIDENT, POSITIVE)`;
    `result[1].decision == DecisionResult(REVIEW, EXPECTED_COST, NEGATIVE)` (cost `2.0 > 1.0`).
11. `test_analyze_batch_aspects` — `result[0].aspects == (AspectSentiment(CONTENT, POSITIVE, 0.9, 0),)`;
    `result[1].aspects == (AspectSentiment(ASSESSMENT, NEGATIVE, 0.8, 0), AspectSentiment(ORGANIZATION_SCHEDULE,
    NEGATIVE, 0.7, 1))`.
12. `test_analyze_batch_one_call_per_port` — `proba_calls == [(B0.text, B1.text), ("Ana dio buen contenido", "Los
    parciales fueron difíciles", "el horario fue malo")]`; `set_calls == [(B0.text, B1.text)]`; `detect_calls`
    has 1 entry equal to the 3 clauses.
13. `test_analyze_batch_no_influences` — every result has `influences == ()`.
14. `test_analyze_batch_rejects_empty` — `execute(())` raises `InvalidInputError`; `proba_calls == []`.
15. `test_analyze_batch_rejects_over_limit` — 5,001 copies of `Comment("Buen curso.")` raise `InvalidInputError`;
    5,000 copies return 5,000 results.
16. `test_analyze_batch_chunks_clauses` — 2,500 copies of `Comment("Uno bueno; dos bueno; tres bueno.")` (3
    clauses each, 7,500 clauses): `proba_calls` lengths are `[2500, 5000, 2500]`; `detect_calls` lengths are
    `[5000, 2500]`; 2,500 results.
17. `test_analyze_batch_short_aspect_result` — `FakeAspectModel(..., short_by=1)` raises `InferenceError` with
    `detail == "AspectModel.detect returned 2 results for 3 texts"`.

## Out of scope
HTTP schemas, CSV parsing and the length limit of each text (spec 021); course reports (spec 023); routes and
composition (spec 024); concurrency (the use cases hold no mutable state); real model adapters (specs 018, 019).

## Definition of Done
- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/pytest -q tests/unit/application` → `17 passed`.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed` (dependency rule and size limits).
- [ ] `grep -rnE "# noqa|# type: ignore" api/application/analyze.py tests/fixtures/fake_ports.py tests/unit/application`
      → no output.
- [ ] `grep -nE "^(from|import) (api\.adapters|api\.main|ml)(\.| |$)" api/application/analyze.py` → no output.
- [ ] `grep -nE "^\s*(import logging|try:|except)|print\(" api/application/analyze.py` → no output.
- [ ] `.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing` → line for
      `api/application/analyze.py` ≥ 80 %.
- [ ] `bash scripts/gate.sh` → last line `GATE OK`, exit code 0.
