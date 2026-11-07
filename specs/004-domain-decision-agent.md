# 004 - Domain decision agent
Riesgo: alto

## Objective

The polarity model reaches a macro-F1 of 0.62 on the best baseline and the global label agrees with its own aspects
in about 50 % of rows (`docs/analysis.md` §2). The product MUST say when it does not know. This spec creates the
domain decision agent of ADR-002: a pure function that, from the class probabilities and the conformal set of one
comment, returns `classify` or `review` with a reason and the top label. After this spec, `api/domain/decision.py`
exists with `DecisionCosts`, `DecisionResult` and `decide`, covered by the contract test vectors and by the edge
cases below. Use cases (spec 022) call `decide`; nothing else changes.

## Depends on

002 (`api/domain/entities.py`, `api/domain/errors.py`).

## Governing files

- `ARCHITECTURE.md` §2 rule 1 (domain imports the standard library only), §6 (size: ≤ 20 statements per function,
  cyclomatic complexity ≤ 8, modules ≤ 300 lines; `mypy --strict`; `from __future__ import annotations`; entities
  `@dataclass(frozen=True, slots=True)` validated in `__post_init__`; errors inherit from `AppError`; no `assert` in
  production code; no logging of comment text), §7 (costs come from `config/app.json` `costs`).
- `ADR-002` decision 3 (the four review conditions).
- `docs/contracts.md` §1.1 (`Polarity`, `Decision`, `DecisionReason`, `ClassProbabilities`, `ConformalSet`), §2
  (`InvalidInputError`), §4.1 (this contract, binding), §7 (default costs 5.0, 1.0, true).
- `security-rules.md` SEC-05: the module logs nothing and holds no comment text.

## Files to create/modify

1. `api/domain/decision.py` (new). Same structure as `api/domain/entities.py` (spec 002): module docstring,
   `from __future__ import annotations`, standard library imports, then `api.domain` imports.
2. `tests/unit/domain/test_decision.py` (new). Same structure as `tests/unit/domain/test_entities.py` (spec 002).

No existing test changes expectation.

## External dependencies

None new. Standard library modules used: `math`, `dataclasses`.

## Interfaces and types

Module `api/domain/decision.py`, imports exactly: `from __future__ import annotations`, `import math`,
`from dataclasses import dataclass`, and from `api.domain.entities` the names `ASPECT_ORDER`, `AspectSentiment`,
`ClassProbabilities`, `Comment`, `ConformalSet`, `Decision`, `DecisionReason`, `Polarity`, `WordInfluence`; from `api.domain.errors` the name `InvalidInputError`.

- Private constant `_COST_TOLERANCE: float = 1e-12` (the only occurrence of the literal `1e-12` in the module).
- `@dataclass(frozen=True, slots=True) class DecisionCosts` with fields, in this order:
  `error_cost: float`, `review_cost: float`, `review_if_set_not_singleton: bool`.
  `__post_init__(self) -> None` validates both costs (step 1 of Expected behavior).
- `@dataclass(frozen=True, slots=True) class DecisionResult` with fields, in this order: `decision: Decision`,
  `reason: DecisionReason`, `label: Polarity`. It defines no `__post_init__` (the contract sets no field rule
  beyond the types).
- `@dataclass(frozen=True, slots=True) class CommentAnalysis` (`docs/contracts.md` §1.1; it lives in this module
  because its `decision` field needs `DecisionResult`, and `api.domain.entities` cannot import this module) with
  fields, in this order: `comment: Comment`, `probabilities: ClassProbabilities`, `conformal_set: ConformalSet`,
  `decision: DecisionResult`, `aspects: tuple[AspectSentiment, ...]`, `influences: tuple[WordInfluence, ...]`.
  `__post_init__(self) -> None` validates `aspects` (step 5 of Expected behavior).
- `def decide(probabilities: ClassProbabilities, conformal_set: ConformalSet, costs: DecisionCosts) ->
  DecisionResult`.

Google-style docstrings on the module, the three classes, both `__post_init__` methods and `decide`; the `decide` docstring lists the five rules in
order and has a `Returns:` section. Private helpers, if any, start with `_` and stay ≤ 20 statements.

## Expected behavior

1. `DecisionCosts.__post_init__`: for `error_cost`, then `review_cost`, if `math.isfinite(value)` is false or
   `value <= 0.0`, raise `InvalidInputError` with `detail` `"error_cost must be finite and > 0"` (for
   `error_cost`) or `"review_cost must be finite and > 0"` (for `review_cost`). `error_cost` is checked first.
2. `decide` input: a valid `ClassProbabilities`, a valid `ConformalSet` and a valid `DecisionCosts`. It computes
   `label = probabilities.top()` once (tie → first in `POLARITY_ORDER`, behavior of spec 002).
3. Rules in this order; the first that matches returns `DecisionResult(decision, reason, label)`:
   1. `len(conformal_set.labels) == 0` → `Decision.REVIEW`, `DecisionReason.EMPTY_SET`.
   2. `len(conformal_set.labels) > 1` and `costs.review_if_set_not_singleton` is true → `Decision.REVIEW`,
      `DecisionReason.SET_NOT_SINGLETON`.
   3. `label not in conformal_set.labels` → `Decision.REVIEW`, `DecisionReason.LABEL_OUTSIDE_SET`.
   4. `(1.0 - probabilities.of(label)) * costs.error_cost > costs.review_cost + _COST_TOLERANCE` →
      `Decision.REVIEW`, `DecisionReason.EXPECTED_COST`.
   5. Otherwise `Decision.CLASSIFY`, `DecisionReason.CONFIDENT`.
4. `label` in the result is always `probabilities.top()`, also when the decision is `review`.
5. `decide` reads no configuration, no clock and no global state, logs nothing and raises nothing for valid inputs.
   `conformal_set.confidence_level` is not read.

With the defaults (5.0, 1.0, true), rule 4 classifies a singleton set holding the top label when `p_top >= 0.8`.
5. `CommentAnalysis.__post_init__`: let `positions` be `[ASPECT_ORDER.index(item.group) for item in aspects]`; if
   `positions` is not strictly increasing (a repeated group or a group out of `ASPECT_ORDER`), raise
   `InvalidInputError` with `detail` `"aspects must be unique and follow ASPECT_ORDER"`. An empty `aspects` is
   valid. No other field is validated.

## Edge cases and error handling

| Case | Result |
|---|---|
| `error_cost` = `0.0`, `-1.0`, `math.inf` or `math.nan` | `InvalidInputError`, `detail` `"error_cost must be finite and > 0"` |
| `review_cost` = `0.0`, `-0.5`, `math.inf` or `math.nan` | `InvalidInputError`, `detail` `"review_cost must be finite and > 0"` |
| Both costs invalid (`0.0`, `0.0`) | `InvalidInputError`, `detail` `"error_cost must be finite and > 0"` |
| Expected cost equal to `review_cost` in floating point (`(0.20, 0.30, 0.50)`, costs 2.0 and 1.0: cost `1.0`) | `classify`, `confident` (strict `>` plus tolerance) |
| Expected cost `0.9999999999999998` (p_top `0.80`, default costs) | `classify`, `confident` |
| Expected cost `1.0004999999999997` (p_top `0.7999`, default costs) | `review`, `expected_cost` |
| Probability tie for the top (`(0.40, 0.40, 0.20)`, set `{negative}`) | label `negative`; cost 3.0 → `review`, `expected_cost` |
| Empty set and the flag false | rule 1 still applies: `review`, `empty_set` |
| Set of 3 labels, flag false, `(0.80, 0.10, 0.10)` | rules 2 and 3 skip; cost `0.9999999999999998` → `classify`, `confident`, `negative` |

Invalid `ClassProbabilities` and `ConformalSet` are rejected by their own constructors (spec 002); `decide` adds no
check on them. If a test not listed in this spec fails because of this change, the implementer does not modify it:
the implementer reports its name and the reason.

## Acceptance tests (prose)

File `tests/unit/domain/test_decision.py`. Synthetic values only. A probability triple `(a, b, c)` means
`ClassProbabilities(negative=a, neutral=b, positive=c)`; every set is `ConformalSet(labels=frozenset(...),
confidence_level=0.9)`; "defaults" means `DecisionCosts(5.0, 1.0, True)`; "flag false" means
`DecisionCosts(5.0, 1.0, False)`. Each test asserts the three fields `decision`, `reason`, `label` of the result.

Contract vectors (`docs/contracts.md` §4.1), one test each:

1. `test_decide_classifies_confident_singleton`: `(0.05, 0.10, 0.85)`, `{positive}`, defaults →
   `(classify, confident, positive)`.
2. `test_decide_reviews_when_expected_cost_exceeds_review_cost`: `(0.15, 0.25, 0.60)`, `{positive}`, defaults →
   `(review, expected_cost, positive)`.
3. `test_decide_classifies_at_threshold_080`: `(0.10, 0.10, 0.80)`, `{positive}`, defaults →
   `(classify, confident, positive)`.
4. `test_decide_reviews_set_not_singleton`: `(0.45, 0.40, 0.15)`, `{negative, neutral}`, defaults →
   `(review, set_not_singleton, negative)`.
5. `test_decide_reviews_empty_set`: `(0.30, 0.40, 0.30)`, `{}`, defaults → `(review, empty_set, neutral)`.
6. `test_decide_reviews_label_outside_set`: `(0.10, 0.82, 0.08)`, `{negative}`, defaults →
   `(review, label_outside_set, neutral)`.
7. `test_decide_classifies_multi_label_set_when_flag_false`: `(0.02, 0.90, 0.08)`, `{neutral, positive}`,
   flag false → `(classify, confident, neutral)`.

Additional vectors:

8. `test_decide_flag_false_falls_through_to_expected_cost`: `(0.30, 0.40, 0.30)`, `{neutral, positive}`, flag
   false → `(review, expected_cost, neutral)`.
9. `test_decide_flag_false_falls_through_to_label_outside_set`: `(0.50, 0.30, 0.20)`, `{neutral, positive}`, flag
   false → `(review, label_outside_set, negative)`.
10. `test_decide_empty_set_wins_with_flag_false`: `(0.30, 0.40, 0.30)`, `{}`, flag false →
    `(review, empty_set, neutral)`.
11. `test_decide_classifies_when_cost_equals_review_cost`: `(0.20, 0.30, 0.50)`, `{positive}`,
    `DecisionCosts(2.0, 1.0, True)` → `(classify, confident, positive)`.
12. `test_decide_reviews_just_above_review_cost`: `(0.21, 0.30, 0.49)`, `{positive}`, `DecisionCosts(2.0, 1.0,
    True)` → `(review, expected_cost, positive)` (cost 1.02).
13. `test_decide_reviews_just_below_threshold_080`: `(0.10, 0.1001, 0.7999)`, `{positive}`, defaults →
    `(review, expected_cost, positive)`.
14. `test_decide_tie_uses_first_polarity`: `(0.40, 0.40, 0.20)`, `{negative}`, defaults →
    `(review, expected_cost, negative)`.
15. `test_decide_three_label_set_flag_false`: `(0.80, 0.10, 0.10)`, `{negative, neutral, positive}`, flag false →
    `(classify, confident, negative)`.
16. `test_decision_costs_rejects_invalid_error_cost`: parametrized over `0.0`, `-1.0`, `math.inf`, `math.nan` as
    `error_cost` with `review_cost=1.0`, flag true → `InvalidInputError` whose `detail` equals
    `"error_cost must be finite and > 0"`.
17. `test_decision_costs_rejects_invalid_review_cost`: parametrized over `0.0`, `-0.5`, `math.inf`, `math.nan` as
    `review_cost` with `error_cost=5.0` → `InvalidInputError` whose `detail` equals
    `"review_cost must be finite and > 0"`.
18. `test_decision_costs_checks_error_cost_first`: `DecisionCosts(0.0, 0.0, True)` → `InvalidInputError` with
    `detail` `"error_cost must be finite and > 0"`.
19. `test_decision_costs_accepts_defaults`: `DecisionCosts(5.0, 1.0, True)` builds; its three fields equal
    `5.0`, `1.0`, `True`.
20. `test_decision_result_is_frozen`: on a `DecisionResult(Decision.CLASSIFY, DecisionReason.CONFIDENT,
    Polarity.POSITIVE)`, the test calls `setattr(result, field_name, Decision.REVIEW)` where `field_name` is a local
    variable holding `"decision"`, inside `pytest.raises(dataclasses.FrozenInstanceError)` (a constant string in
    `setattr` triggers ruff `B010`; a direct assignment is a `mypy --strict` error).

21. `test_comment_analysis_accepts_ordered_aspects`: `Comment("Buen curso.")`, probabilities `(0.05, 0.10, 0.85)`, set
    `{positive}` at 0.9, `DecisionResult(Decision.CLASSIFY, DecisionReason.CONFIDENT, Polarity.POSITIVE)`,
    `aspects=(AspectSentiment(AspectGroup.CONTENT, Polarity.POSITIVE, 0.9, 0), AspectSentiment(AspectGroup.PLATFORM,
    Polarity.NEGATIVE, 0.8, 0))`, `influences=()` builds; `aspects` has 2 items. Tests 22 and 23 change only
    `aspects`; test 24 uses the same base values.
22. `test_comment_analysis_rejects_repeated_group`: two `AspectSentiment` with `AspectGroup.CONTENT` →
    `InvalidInputError`, `detail` `"aspects must be unique and follow ASPECT_ORDER"`.
23. `test_comment_analysis_rejects_out_of_order`: `PLATFORM` then `CONTENT` → same error and `detail`.
24. `test_comment_analysis_accepts_empty_aspects`: `aspects=()` builds.

## Out of scope

- Reading `config/app.json` (spec 016) and building `DecisionCosts` from it (spec 024).
- Calling `decide` from use cases (spec 022) and serializing `DecisionResult` and `CommentAnalysis` (spec 021).
- Conformal calibration and the choice of cost values (spec 011, risk-coverage report).
- Any change to `api/domain/entities.py`.

## Definition of Done

- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/pytest -q tests/unit/domain/test_decision.py` → `30 passed` (tests 1-15: 15; tests 16 and 17:
      4 cases each; tests 18-24: 7), exit code 0.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`.
- [ ] `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed` (domain imports the standard library only; size limits).
- [ ] `.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing` → the row of
      `api/domain/decision.py` shows ≥ 80 %.
- [ ] `grep -nE "# noqa|# type: ignore" api/domain/decision.py tests/unit/domain/test_decision.py` → no output.
- [ ] `grep -c "1e-12" api/domain/decision.py` → `1`.
- [ ] `grep -nE "^\s*assert |print\(|logging" api/domain/decision.py` → no output (the words `logging` and `print(`
      MUST NOT appear in the module, docstrings and comments included).
- [ ] `bash scripts/security_grep.sh` → no output, exit code 0.
- [ ] `bash scripts/gate.sh` → last line `GATE OK`, exit code 0.
