# 005 - Domain clauses and priority
Riesgo: alto

## Objective

A comment often mixes opinions ("El contenido fue claro, pero los parciales fueron difíciles"), so one global label
per comment hides the sentiment of each aspect; the dataset's global label agrees with its own aspects in about
50 % of rows (`docs/analysis.md` §2). This spec creates two pure domain modules: `api/domain/clauses.py` splits a
comment into clauses and assigns one polarity per aspect group from the per-clause analyses, and
`api/domain/priority.py` ranks a course's aspect groups for action. After this spec both modules exist with the
contract vectors of `docs/contracts.md` §4.2 and §4.3 passing. Use cases (specs 022 and 023) call them.

## Depends on

001 (`tests/architecture`, `scripts/security_grep.sh`), 002 (`api/domain/entities.py`, `api/domain/reports.py`, `api/domain/errors.py`). Both MUST be `Implemented` before this spec runs.

## Governing files

- `ARCHITECTURE.md` §2 rule 1 (standard library only), §6 (≤ 20 statements per function, cyclomatic complexity
  ≤ 8, ≤ 8 branches, modules ≤ 300 lines, `mypy --strict`, `from __future__ import annotations`, errors inherit
  from `AppError`, no `assert`, no `print`, no logging of comment text).
- `docs/contracts.md` §1.1 (`AspectGroup`, `ASPECT_ORDER`, `ClassProbabilities.top`, `AspectScores.score`,
  `AspectSentiment`, `ClauseAnalysis`), §1.2 (`AspectCell`, `PriorityEntry`), §2 (`InvalidInputError`), §4.2 and
  §4.3 (binding).
- `security-rules.md` SEC-05: neither module logs; error `detail` strings hold no comment text.

## Files to create/modify

1. `api/domain/clauses.py` (new). Same structure as `api/domain/entities.py` (spec 002).
2. `api/domain/priority.py` (new). Same structure as `api/domain/entities.py` (spec 002).
3. `tests/unit/domain/test_clauses.py` (new). Same structure as `tests/unit/domain/test_entities.py` (spec 002).
4. `tests/unit/domain/test_priority.py` (new). Same structure as `tests/unit/domain/test_entities.py` (spec 002).

No existing test changes expectation.

## External dependencies

None new. Standard library modules used: `re`, `string`, `collections.abc`.

## Interfaces and types

`api/domain/clauses.py` imports only `__future__`, `re`, `string`, `collections.abc.Sequence`, and from
`api.domain.entities` the names `ASPECT_ORDER`, `AspectSentiment`, `ClauseAnalysis`; from `api.domain.errors`
`InvalidInputError`.

- `_SENTENCE_BOUNDARY: re.Pattern[str] = re.compile(r"(?<![.!?;])[.!?;]++(?=\s|$)")`
- `_CONNECTOR: re.Pattern[str] = re.compile(r"\b(?:pero|aunque|sin embargo|no obstante|mientras que)\b",
  re.IGNORECASE)` (the flag is passed as `re.IGNORECASE`, not inline).
- `_STRIP_CHARS: str = string.whitespace + _UNICODE_SPACES + ",;:"`, where `_UNICODE_SPACES: str = "\x1c\x1d\x1e\x1f\x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"` (the characters `str.isspace()` accepts that `string.whitespace` lacks)
- `_MIN_CLAUSE_CHARS: int = 3`
- `def split_clauses(text: str) -> tuple[str, ...]`
- `def aspect_sentiments(clauses: Sequence[ClauseAnalysis]) -> tuple[AspectSentiment, ...]`

`api/domain/priority.py` imports only `__future__`, `collections.abc.Sequence`, `ASPECT_ORDER` from
`api.domain.entities`, `AspectCell` and `PriorityEntry` from `api.domain.reports`, `InvalidInputError` from
`api.domain.errors`.

- `MIN_SUPPORT: int = 5` (public; written exactly as `MIN_SUPPORT: int = 5`).
- `def rank_priorities(cells: Sequence[AspectCell], comment_count: int) -> tuple[PriorityEntry, ...]`

Google-style docstrings on both modules and the three public functions. Private helpers start with `_` and stay
≤ 20 statements each.

## Expected behavior

`split_clauses(text)`:
1. If `text.strip() == ""`, raise `InvalidInputError` with `detail` `"text must not be empty"`.
2. `sentences = _SENTENCE_BOUNDARY.split(text)` (delimiter runs removed).
3. Each sentence, in order, is split with `_CONNECTOR.split(sentence)`; the connector is dropped.
4. Each resulting piece becomes `piece.strip(_STRIP_CHARS)`; pieces with `len(piece) < _MIN_CLAUSE_CHARS` are
   dropped. The order of the source text is kept.
5. Return the kept pieces as a tuple; if none is kept, return `(text.strip(),)`.

`aspect_sentiments(clauses)`:
1. For each `group` in `ASPECT_ORDER`, candidates are the pairs `(index, clause)` of `enumerate(clauses)` with
   `group in clause.aspects.present`.
2. No candidate → the group is omitted.
3. Otherwise pick the candidate with the highest `clause.aspects.score(group)`; tie → the lowest `index`.
4. Emit `AspectSentiment(group=group, polarity=clause.probabilities.top(), score=clause.aspects.score(group),
   clause_index=index)`.
5. Return the emitted items as a tuple in `ASPECT_ORDER`. Scores of groups absent from `present` are never read.

`rank_priorities(cells, comment_count)`:
1. `comment_count < 1` → `InvalidInputError`, `detail` `"comment_count must be >= 1"`.
2. Over all cells, including those with `mentions == 0`, in input order: a `group` already seen →
   `InvalidInputError`, `detail` `"duplicate aspect group"`; `cell.mentions > comment_count` →
   `InvalidInputError`, `detail` `"mentions must not exceed comment_count"`. The duplicate check runs before the
   mentions check for the same cell.
3. For each cell with `mentions >= 1`: `prevalence = mentions / comment_count`; `smoothed_negative_share =
   (negative + 1) / (mentions + 2)`; `score = prevalence * smoothed_negative_share`; `low_support = mentions <
   MIN_SUPPORT`. Cells with `mentions == 0` are omitted.
4. Sort by `score` descending; tie → position of `group` in `ASPECT_ORDER`. `rank` = 1-based position after sorting.
5. Return `PriorityEntry(rank, group, mentions, negative, prevalence, smoothed_negative_share, score, low_support)`
   per kept cell. Floats are not rounded.

## Edge cases and error handling

| Case | Result |
|---|---|
| `split_clauses("")` or `split_clauses("   ")` | `InvalidInputError`, `detail` `"text must not be empty"` |
| Every piece shorter than 3 characters (`"Ok."`) | `("Ok.",)` (stripped original text) |
| Text that is only a connector (`"pero"`) | `("pero",)` |
| Period inside a number (`"3.5"`) | not a boundary (no whitespace or end after it) |
| Word that contains a connector (`"peroné"`) | not split (`\b` after `pero` fails) |
| Two spaces inside a connector (`"Sin  embargo"`) | not a connector |
| Inverted marks `¿` `¡` | kept: they are not in `_STRIP_CHARS` |
| `aspect_sentiments(())` | `()` |
| Score high but group not in `present` | group omitted |
| `rank_priorities` with `comment_count` 0 or -1 | `InvalidInputError`, `detail` `"comment_count must be >= 1"` |
| A cell with `mentions` 11 and `comment_count` 10 | `InvalidInputError`, `detail` `"mentions must not exceed comment_count"` |
| Two cells with group `content` | `InvalidInputError`, `detail` `"duplicate aspect group"` |
| Every cell with `mentions` 0, or `cells` empty | `()` |

If a test not listed in this spec fails because of this change, the implementer does not modify it: the
implementer reports its name and the reason.

## Acceptance tests (prose)

`tests/unit/domain/test_clauses.py`. Each split test asserts the exact tuple returned.

1. `test_split_clauses_contract_vector`: `"El contenido fue claro, pero los parciales fueron difíciles. Sin embargo,
   buen horario."` → `("El contenido fue claro", "los parciales fueron difíciles", "buen horario")`.
2. `test_split_clauses_falls_back_when_all_pieces_short`: `"Ok."` → `("Ok.",)`.
3. `test_split_clauses_strips_whitespace`: `"  Bueno  "` → `("Bueno",)`.
   `test_split_clauses_strips_unicode_whitespace`: `"Bien.\xa0\xa0\xa0"` (written with escapes: three no-break spaces after the period) → `("Bien",)`; and every character `c` below `chr(0x3100)` with `c.isspace()` is in `_STRIP_CHARS`.
   `test_split_clauses_long_punctuation_run_is_linear`: `"." * 100000 + "x"` returns in under 1 second.
4. `test_split_clauses_keeps_decimal_number`: `"Nota 3.5 pero injusta."` → `("Nota 3.5", "injusta")`.
5. `test_split_clauses_ellipsis_and_uppercase_connector`: `"Bien... PERO lento!"` → `("Bien", "lento")`.
6. `test_split_clauses_ignores_connector_inside_word`: `"Me dolió el peroné, pero sigo."` →
   `("Me dolió el peroné", "sigo")`.
7. `test_split_clauses_aunque_and_no_obstante`: `"Clases buenas aunque largas; el material, no obstante, es pobre"`
   → `("Clases buenas", "largas", "el material", "es pobre")`.
8. `test_split_clauses_mientras_que`: `"La plataforma falla mientras que el profesor ayuda."` →
   `("La plataforma falla", "el profesor ayuda")`.
9. `test_split_clauses_double_space_is_not_connector`: `"Sin  embargo bien"` → `("Sin  embargo bien",)`.
10. `test_split_clauses_only_connector`: `"pero"` → `("pero",)`.
11. `test_split_clauses_drops_short_sentences`: `"Sí. No. Tal vez."` → `("Tal vez",)`.
12. `test_split_clauses_keeps_inverted_marks`: `"¿Qué? ¡Nada!"` → `("¿Qué", "¡Nada")`.
13. `test_split_clauses_rejects_empty_text`: parametrized over `""` and `"   "` → `InvalidInputError` whose
    `detail` equals `"text must not be empty"`.

Aspect tests build `AspectScores` with a 9-float tuple in `ASPECT_ORDER` that is `0.0` except the listed groups.
"Top positive" means `ClassProbabilities(0.1, 0.1, 0.8)`; "top negative" means `ClassProbabilities(0.7, 0.2, 0.1)`.
Clause texts are `"clause zero"` and `"clause one"`.

14. `test_aspect_sentiments_contract_vector`: clause 0 top positive, scores `{content: 0.9}`, present `{content}`;
    clause 1 top negative, scores `{content: 0.6, assessment: 0.8}`, present `{content, assessment}` →
    `(AspectSentiment(content, positive, 0.9, 0), AspectSentiment(assessment, negative, 0.8, 1))`.
15. `test_aspect_sentiments_order_and_tie`: clause 0 top positive, scores `{platform: 0.7, workload_pace: 0.4}`,
    present `{platform, workload_pace}`; clause 1 top negative, scores `{platform: 0.7, content: 0.3}`, present
    `{platform, content}` → `(AspectSentiment(content, negative, 0.3, 1), AspectSentiment(platform, positive, 0.7,
    0), AspectSentiment(workload_pace, positive, 0.4, 0))`.
16. `test_aspect_sentiments_ignores_groups_not_present`: one clause top positive, scores `{materials: 0.95}`,
    present `frozenset()` → `()`.
17. `test_aspect_sentiments_empty_input`: `()` → `()`.

`tests/unit/domain/test_priority.py`. A cell `(group, m, n)` means `AspectCell(group, mentions=m, negative=n,
neutral=0, positive=m - n)`. Float fields are compared with `pytest.approx(value, abs=1e-12)`; every other field
with `==`.

18. `test_rank_priorities_contract_vector`: cells `(content, 40, 10)`, `(assessment, 10, 8)`, `(platform, 2, 2)`,
    `(materials, 0, 0)`, `comment_count=100` → 3 entries: rank 1 content, prevalence 0.4, share
    0.2619047619047619, score 0.10476190476190478, low_support false; rank 2 assessment, 0.1, 0.75,
    0.07500000000000001, false; rank 3 platform, 0.02, 0.75, 0.015, true.
19. `test_rank_priorities_tie_follows_aspect_order`: cells `(materials, 5, 1)` then `(feedback, 5, 1)`,
    `comment_count=50` → rank 1 feedback, rank 2 materials; both prevalence 0.1, share 0.2857142857142857, score
    0.02857142857142857, low_support false.
20. `test_rank_priorities_full_prevalence`: `(workload_pace, 3, 3)`, `comment_count=3` → one entry: rank 1,
    prevalence 1.0, share 0.8, score 0.8, low_support true.
21. `test_rank_priorities_low_support_boundary`: `(content, 4, 0)`, `(assessment, 5, 0)`, `comment_count=20` →
    rank 1 assessment (0.25, 0.14285714285714285, 0.03571428571428571, false); rank 2 content (0.2,
    0.16666666666666666, 0.03333333333333333, true).
22. `test_rank_priorities_all_zero_mentions`: `(content, 0, 0)`, `comment_count=10` → `()`.
23. `test_rank_priorities_empty_cells`: `()`, `comment_count=10` → `()`.
24. `test_rank_priorities_rejects_comment_count`: parametrized over `0` and `-1` with cells `()` →
    `InvalidInputError`, `detail` `"comment_count must be >= 1"`.
25. `test_rank_priorities_rejects_mentions_above_count`: `(content, 11, 0)`, `comment_count=10` →
    `InvalidInputError`, `detail` `"mentions must not exceed comment_count"`.
26. `test_rank_priorities_rejects_duplicate_group`: `(content, 1, 0)`, `(content, 2, 1)`, `comment_count=10` →
    `InvalidInputError`, `detail` `"duplicate aspect group"`.
27. `test_min_support_value`: `MIN_SUPPORT == 5`.

Entry comparison: each test in `test_priority.py` builds the expected entries as a list of tuples `(rank, group,
mentions, negative, prevalence, smoothed_negative_share, score, low_support)` and compares it with the actual entries
converted by one private helper `_as_tuples(entries: Sequence[PriorityEntry]) -> list[tuple[...]]`. The helper has 1
parameter. The comparison of the 6 non-float fields uses `==` and of the 3 float fields `pytest.approx(value,
abs=1e-12)`. `mentions` and `negative` are the values of the input cell of the same group (test 18: content 40 and
10, assessment 10 and 8, platform 2 and 2). No test function exceeds 20 statements. No docstring or comment in the
test files uses the word "logging".

## Out of scope

- Building `AspectCell` counts from analyses and the course report (spec 023).
- Model calls that produce `ClauseAnalysis` (spec 022) and JSON rounding to 4 decimals (spec 021).
- Text normalization (`ml.data.normalize_text`, spec 007): `split_clauses` receives the text unchanged.
- Any change to `api/domain/entities.py`, `api/domain/reports.py` or `docs/contracts.md`.

## Definition of Done

- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/pytest -q tests/unit/domain/test_clauses.py` → `20 passed`, exit code 0.
- [ ] `.venv/bin/pytest -q tests/unit/domain/test_priority.py` → `11 passed`, exit code 0.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`.
- [ ] `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api tests` → `Success: no issues found in N source files` (`ml/` holds no module until spec 007).
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed`.
- [ ] `.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing` → the rows of
      `api/domain/clauses.py` and `api/domain/priority.py` show ≥ 80 %.
- [ ] `grep -nE "# noqa|# type: ignore" api/domain/clauses.py api/domain/priority.py tests/unit/domain/test_clauses.py tests/unit/domain/test_priority.py`
      → no output.
- [ ] `grep -nE "^\s*assert |print\(|logging" api/domain/clauses.py api/domain/priority.py` → no output.
- [ ] `grep -c "re.IGNORECASE" api/domain/clauses.py` → `1`.
- [ ] `grep -c "MIN_SUPPORT: int = 5" api/domain/priority.py` → `1`.
- [ ] `grep -n "round(" api/domain/priority.py` → no output.
- [ ] `bash scripts/security_grep.sh` → no output, exit code 0.
- [ ] Gate: not applicable until spec 007: `bash scripts/gate.sh` exits 2 at step 3 (mypy) while `ml/` holds no `.py` file; `GATE OK` is checked once spec 007 is implemented.
