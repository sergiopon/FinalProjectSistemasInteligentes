# 002 - Domain errors and entities
Riesgo: alto

## Objective

Every later layer exchanges domain entities and raises `AppError` subclasses (`docs/contracts.md` §1 and §2), and
none exist yet. When this spec is done `api/domain/errors.py`, `api/domain/entities.py` and `api/domain/reports.py`
exist, use the standard library only, and reject invalid values on construction with `InvalidInputError`, so no
invalid probability, count or identifier crosses a layer boundary.

## Depends on

000 (`pyproject.toml`, `.venv`), 001 (`tests/architecture`, `scripts/security_grep.sh`).

## Governing files

- `ARCHITECTURE.md` §2 rule 1 (domain: standard library only), §6 (types: `@dataclass(frozen=True, slots=True)`
  with validation in `__post_init__`, `tuple` and `frozenset`, no `Any`; errors: only `AppError` subclasses; size
  limits; Google docstrings; `from __future__ import annotations`).
- `docs/contracts.md` §1.1, §1.2, §2. `security-rules.md` SEC-05 and SEC-21 (`detail` never holds comment text).

## Files to create/modify

1. `api/domain/errors.py` (new)
2. `api/domain/entities.py` (new)
3. `api/domain/reports.py` (new)
4. `tests/unit/domain/test_entities.py` (new)
5. `tests/unit/domain/test_reports.py` (new)

No module of the same layer exists yet; `reports.py` follows the structure of `entities.py`. Tests of the error
classes are in spec 003 (`tests/unit/domain/test_errors.py`); here errors are exercised through entity validation.

## External dependencies

None new (standard library: `dataclasses`, `enum`, `re`, `datetime`, `typing`).

## Interfaces and types

### `api/domain/errors.py`

Imports: `from __future__ import annotations`, `from typing import ClassVar`. Every module of this spec starts with
`from __future__ import annotations`.

`class AppError(Exception)`: `code: ClassVar[str] = "internal_error"`; attribute `detail: str`;
`def __init__(self, detail: str) -> None` calls `super().__init__(detail)` and stores `detail`. Subclasses only set
`code` (a subclass without its own `code` inherits the parent's):

| Class | Parent | `code` |
|---|---|---|
| `InvalidInputError` | `AppError` | `"invalid_input"` |
| `CsvFormatError` | `InvalidInputError` | `"invalid_csv"` |
| `PayloadTooLargeError` | `AppError` | `"payload_too_large"` |
| `UnsupportedMediaTypeError` | `AppError` | `"unsupported_media_type"` |
| `NotFoundError` | `AppError` | `"not_found"` |
| `ModelUnavailableError` | `AppError` | `"model_unavailable"` |
| `ModelIntegrityError` | `ModelUnavailableError` | inherited `"model_unavailable"` |
| `ConfigError`, `AnonymizerUnavailableError`, `InferenceError`, `UnsafePathError`, `DatasetError` | `AppError` | inherited `"internal_error"` |

HTTP status and client message mapping belong to `api/main.py` (spec 024), not to this module.

### `api/domain/entities.py`

Imports: `from dataclasses import dataclass`, `from enum import StrEnum`, `from typing import Final`, and
`from api.domain.errors import InvalidInputError`.

Enums (`enum.StrEnum`, members in this order): `Polarity` (`NEGATIVE = "negative"`, `NEUTRAL = "neutral"`,
`POSITIVE = "positive"`); `Decision` (`CLASSIFY = "classify"`, `REVIEW = "review"`); `DecisionReason`
(`CONFIDENT = "confident"`, `EMPTY_SET = "empty_set"`, `SET_NOT_SINGLETON = "set_not_singleton"`,
`LABEL_OUTSIDE_SET = "label_outside_set"`, `EXPECTED_COST = "expected_cost"`); `AspectGroup` (`CONTENT =
"content"`, `ASSESSMENT = "assessment"`, `FEEDBACK = "feedback"`, `METHODOLOGY_CLARITY = "methodology_clarity"`,
`MATERIALS = "materials"`, `ORGANIZATION_SCHEDULE = "organization_schedule"`, `PLATFORM = "platform"`,
`COMMUNICATION_CLIMATE = "communication_climate"`, `WORKLOAD_PACE = "workload_pace"`).

Constants: `POLARITY_ORDER: Final[tuple[Polarity, ...]] = tuple(Polarity)`, `ASPECT_ORDER:
Final[tuple[AspectGroup, ...]] = tuple(AspectGroup)`, `PROBABILITY_SUM_TOLERANCE: Final[float] = 1e-6`.

Every entity below is `@dataclass(frozen=True, slots=True)`. "In unit range" means `0.0 <= v <= 1.0` (NaN fails).
"Blank" means `value.strip() == ""`. Values are stored as given (no stripping, no rounding). Each failed rule raises
`InvalidInputError` with the literal `detail` shown; rules are checked top to bottom, first failure wins.

| Entity | Fields | Rule → `detail` |
|---|---|---|
| `Comment` | `text: str`, `course: str \| None = None` | `text` blank → `"comment text is blank"`; `course` not `None` and blank → `"course is blank"` |
| `ClassProbabilities` | `negative: float`, `neutral: float`, `positive: float` | any field not in unit range → `"probability out of range"`; `abs(negative + neutral + positive - 1.0) > PROBABILITY_SUM_TOLERANCE` → `"probabilities do not sum to 1"` |
| `ConformalSet` | `labels: frozenset[Polarity]`, `confidence_level: float` | not `0.0 < confidence_level < 1.0` → `"confidence_level out of range"`; empty `labels` is valid |
| `AspectScores` | `scores: tuple[float, ...]`, `present: frozenset[AspectGroup]` | `len(scores) != len(ASPECT_ORDER)` → `"aspect scores must have 9 values"`; any score not in unit range → `"aspect score out of range"` |
| `AspectSentiment` | `group: AspectGroup`, `polarity: Polarity`, `score: float`, `clause_index: int` | `score` not in unit range → `"aspect score out of range"`; `clause_index < 0` → `"clause_index is negative"` |
| `ClauseAnalysis` | `text: str`, `probabilities: ClassProbabilities`, `aspects: AspectScores` | `text` blank → `"clause text is blank"` |
| `WordInfluence` | `word: str`, `delta: float` | `word` blank → `"word is blank"`; not `-1.0 <= delta <= 1.0` → `"delta out of range"` |

Methods (no others):
- `ClassProbabilities.of(self, polarity: Polarity) -> float` returns `negative` for `Polarity.NEGATIVE`, `neutral`
  for `Polarity.NEUTRAL` and `positive` for `Polarity.POSITIVE`.
- `ClassProbabilities.top(self) -> Polarity` returns the polarity with the highest probability; on a tie it returns
  the one that comes first in `POLARITY_ORDER`.
- `ConformalSet.is_singleton` (`@property`, `-> bool`) is `True` when `labels` holds exactly 1 element.
- `AspectScores.score(self, group: AspectGroup) -> float` returns `scores[i]`, where `i` is the position of `group`
  in `ASPECT_ORDER`.

### `api/domain/reports.py`

Imports: `import re`, `from dataclasses import dataclass`, `from datetime import datetime`, `from typing import
Final`, `from api.domain.entities import ASPECT_ORDER, AspectGroup` and `from api.domain.errors import
InvalidInputError`. Same dataclass and error conventions.

| Entity | Fields | Rule → `detail` |
|---|---|---|
| `PolarityCounts` | `negative: int`, `neutral: int`, `positive: int` | any `< 0` → `"count is negative"` |
| `AspectCell` | `group: AspectGroup`, `mentions: int`, `negative: int`, `neutral: int`, `positive: int` | any count `< 0` → `"count is negative"`; `negative + neutral + positive != mentions` → `"aspect counts do not sum to mentions"` |
| `PriorityEntry` | `rank: int`, `group: AspectGroup`, `mentions: int`, `negative: int`, `prevalence: float`, `smoothed_negative_share: float`, `score: float`, `low_support: bool` | `rank < 1` → `"rank is below 1"`; any of the 3 floats not in unit range → `"priority value out of range"` |
| `TopicSummary` | `topic: int`, `size: int`, `terms: tuple[str, ...]`, `quote: str` | `topic < 0` → `"topic is negative"`; `size < 1` → `"topic size is below 1"` |
| `CourseReport` | `course: str`, `comment_count: int`, `review_count: int`, `polarity_counts: PolarityCounts`, `aspects: tuple[AspectCell, ...]`, `priorities: tuple[PriorityEntry, ...]`, `topics: tuple[TopicSummary, ...]`, `quotes: tuple[str, ...]` | `tuple(cell.group for cell in aspects) != ASPECT_ORDER` → `"aspects must be the 9 groups in order"`; not `0 <= review_count <= comment_count` → `"review_count out of range"` |
| `DriftReport` | `body_sha256: str`, `row_count: int`, `length_psi: float`, `oov_rate: float`, `reference_oov_rate: float`, `drifted: bool`, `created_at: str` | `re.fullmatch(r"[0-9a-f]{64}", body_sha256)` is `None` → `"body_sha256 is not 64 lowercase hex"`; `re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", created_at)` is `None` or `datetime.fromisoformat(created_at)` raises `ValueError` → `"created_at is not ISO 8601 UTC"` |
| `MetricsSnapshot` | `request_count: int`, `p50_ms: float \| None`, `p95_ms: float \| None`, `classify_count: int`, `review_count: int`, `last_drift: DriftReport \| None` | any of the 3 counts `< 0` → `"count is negative"` |
| `ModelInfo` | `version: str`, `created_at: str`, `dataset_sha256: str`, `polarity_model: str`, `representation: str`, `confidence_level: float`, `test_macro_f1: float`, `empirical_coverage: float` | `re.fullmatch(r"v[0-9]{3}", version)` is `None` → `"version does not match vNNN"` |

Properties (`@property`, no others): `AspectCell.negative_share -> float | None` = `negative / mentions`, `None`
when `mentions == 0`; `MetricsSnapshot.abstention_rate -> float | None` = `review_count / (classify_count +
review_count)`, `None` when both are 0. Regex patterns are compiled module constants `SHA256_PATTERN`,
`UTC_TIMESTAMP_PATTERN`, `VERSION_PATTERN` (`Final[re.Pattern[str]]`).

## Expected behavior

1. Valid arguments build an immutable instance; assigning a field raises `dataclasses.FrozenInstanceError`.
2. Invalid arguments raise `InvalidInputError` with the `detail` of the table; `str(error) == error.detail`.
3. No module of this spec reads time, environment or files, and none logs.

## Edge cases and error handling

- `CommentAnalysis` (`docs/contracts.md` §1.1) is not created here: its `decision: DecisionResult` field needs
  `api/domain/decision.py`, so spec 004 creates `CommentAnalysis` in `api/domain/decision.py`.
- `ConformalSet(frozenset(), 0.9)` is valid (empty set means review).
- No runtime type check is added beyond the rules listed; wrong types are mypy errors.
- `AspectScores.present` is not cross-checked against `scores` (thresholds live in the adapter).
- `ModelInfo.version` uses `re.fullmatch(r"v[0-9]{3}", version)`, which is the ASCII-digit, no-trailing-newline
  reading of `^v\d{3}$` in `docs/contracts.md` §1.2.

## Acceptance tests (prose)

`tests/unit/domain/test_entities.py` (each invalid case asserts `InvalidInputError` and its exact `detail`). Baseline
valid instances; each test changes only the field it names: `Comment("Buen curso")`; `ClassProbabilities(0.2, 0.3,
0.5)`; `ConformalSet(frozenset({Polarity.POSITIVE}), 0.9)`; `AspectScores((0.0,) * 9, frozenset())`;
`AspectSentiment(AspectGroup.CONTENT, Polarity.POSITIVE, 0.5, 0)`; `ClauseAnalysis("Buen curso", <baseline
ClassProbabilities>, <baseline AspectScores>)`; `WordInfluence("curso", 0.1)`:
- `test_comment_valid`: `Comment("Buen curso", "Bases de datos")` keeps both values unchanged.
- `test_comment_blank_text`: `Comment("   ")` → `"comment text is blank"`.
- `test_comment_blank_course`: `Comment("Buen curso", " ")` → `"course is blank"`.
- `test_comment_frozen`: the test calls `setattr(comment, field_name, "x")` where `field_name` is a local variable
  holding `"text"`, inside `pytest.raises(dataclasses.FrozenInstanceError)` (a constant string in `setattr` triggers
  ruff `B010`; a direct assignment is a `mypy --strict` error).
- `test_class_probabilities_out_of_range`: `(1.2, -0.1, -0.1)` and `(float("nan"), 0.5, 0.5)` →
  `"probability out of range"`.
- `test_class_probabilities_bad_sum`: `(0.2, 0.3, 0.51)` → `"probabilities do not sum to 1"`.
- `test_class_probabilities_sum_tolerance`: `(0.2, 0.3, 0.5000005)` and `(0.1, 0.2, 0.7)` are accepted.
- `test_class_probabilities_of`: on `(0.1, 0.2, 0.7)`, `of(Polarity.NEUTRAL) == 0.2`.
- `test_class_probabilities_top`: `(0.1, 0.2, 0.7)` → `POSITIVE`; `(0.4, 0.4, 0.2)` → `NEGATIVE`; `(0.2, 0.4, 0.4)`
  → `NEUTRAL`.
- `test_conformal_set_singleton`: `frozenset({POSITIVE})` → `True`; `frozenset()` → `False`; `frozenset({NEGATIVE, NEUTRAL})` → `False`
  (all at `confidence_level` 0.9).
- `test_conformal_set_confidence_bounds`: `0.0` and `1.0` → `"confidence_level out of range"`; `0.9` accepted.
- `test_aspect_scores_present_not_cross_checked`: `AspectScores((0.0,) * 9, frozenset({AspectGroup.CONTENT}))` is
  built without error and `present == frozenset({AspectGroup.CONTENT})`.
- `test_conformal_set_empty`: `ConformalSet(frozenset(), 0.9).labels == frozenset()`.
- `test_aspect_scores_length`: `(0.0,) * 8` with `present=frozenset()` → `"aspect scores must have 9 values"`.
- `test_aspect_scores_range`: `(0.0,) * 8 + (1.5,)` with `present=frozenset()` → `"aspect score out of range"`.
- `test_aspect_scores_score`: scores `(0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8)` → `score(AspectGroup.MATERIALS) ==
  0.4`.
- `test_aspect_sentiment_invalid`: `score=1.1` → `"aspect score out of range"`; `clause_index=-1` →
  `"clause_index is negative"`.
- `test_clause_analysis_blank_text`: `text=""` → `"clause text is blank"`.
- `test_word_influence_invalid`: `word=" "` → `"word is blank"`; `delta=-1.5` → `"delta out of range"`; `delta=1.0`
  accepted.
- `test_enums_order`: `POLARITY_ORDER` values `("negative", "neutral", "positive")`; `len(ASPECT_ORDER) == 9`,
  first `"content"`, last `"workload_pace"`; `Polarity.POSITIVE == "positive"`.
- `test_entities_error_hierarchy`: `InvalidInputError("x")` is an `AppError`, `.code == "invalid_input"`,
  `.detail == "x"`, `str(InvalidInputError("x")) == "x"`.

`tests/unit/domain/test_reports.py`. Baseline valid instances; each test changes only the field it names:
`PolarityCounts(1, 1, 1)`; `AspectCell(AspectGroup.CONTENT, 3, 1, 1, 1)`; `PriorityEntry(1, AspectGroup.CONTENT, 10,
4, 0.5, 0.4, 0.2, False)`; `TopicSummary(0, 5, ("curso", "tema"), "Buen curso")`; `CourseReport("Redes", 10, 3,
PolarityCounts(1, 1, 1), tuple(AspectCell(group, 0, 0, 0, 0) for group in ASPECT_ORDER), (), (), ())`;
`DriftReport("a" * 64, 10, 0.1, 0.05, 0.04, False, "2026-11-10T12:00:00Z")`; `MetricsSnapshot(2, 1.0, 2.0, 7, 3,
None)`; `ModelInfo("v001", "2026-11-10T12:00:00Z", "a" * 64, "logistic_regression", "tfidf", 0.9, 0.62, 0.9)`:
- `test_polarity_counts_negative`: `PolarityCounts(-1, 0, 0)` → `"count is negative"`.
- `test_aspect_cell_negative_count`: `AspectCell(CONTENT, -1, 0, 0, 0)`, `AspectCell(CONTENT, 0, -1, 0, 0)`,
  `AspectCell(CONTENT, 0, 0, -1, 0)` and `AspectCell(CONTENT, 0, 0, 0, -1)` → `"count is negative"` each.
- `test_aspect_cell_sum_mismatch`: `AspectCell(CONTENT, 4, 1, 1, 1)` → `"aspect counts do not sum to mentions"`.
- `test_aspect_cell_negative_share`: `AspectCell(CONTENT, 4, 1, 1, 2).negative_share == 0.25`;
  `AspectCell(CONTENT, 0, 0, 0, 0).negative_share is None`.
- `test_priority_entry_invalid`: `rank=0` → `"rank is below 1"`; `prevalence=1.01` → `"priority value out of
  range"`.
- `test_topic_summary_invalid`: `topic=-1` → `"topic is negative"`; `size=0` → `"topic size is below 1"`.
- `test_course_report_aspects_order`: 9 cells with `CONTENT` and `ASSESSMENT` swapped, and 8 cells → both
  `"aspects must be the 9 groups in order"`.
- `test_course_report_review_count`: baseline with `comment_count=10`, `review_count=11` → `"review_count out of range"`.
- `test_drift_report_sha`: baseline with `body_sha256` `"A" * 64` and `"a" * 63` → `"body_sha256 is not 64 lowercase hex"`; `"a" * 64` accepted.
- `test_drift_report_created_at`: `"2026-11-10T12:00:00"`, `"2026-11-10T12:00:00+00:00"` and
  `"2026-02-30T00:00:00Z"` → `"created_at is not ISO 8601 UTC"`; `"2026-11-10T12:00:00Z"` accepted.
- `test_metrics_snapshot_abstention`: classify 7, review 3 → `0.3`; both 0 → `None`; `request_count=-1` →
  `"count is negative"`.
- `test_model_info_version`: `"v1"`, `"v0001"`, `"V001"` → `"version does not match vNNN"`; `"v001"` accepted.

## Out of scope

- `CommentAnalysis` (created in spec 004 in `api/domain/decision.py`), `DecisionResult`, `DecisionCosts` and
  `decide` (spec 004).
- Error tests in their own file and `api/domain/safety.py` (spec 003).
- JSON rounding, HTTP mapping and serialization (spec 021, 024).

## Definition of Done

- [ ] Tests: `.venv/bin/pytest -q -m "not integration"` prints `N passed`, exit code 0 (architecture tests
  included).
- [ ] Linter: `.venv/bin/ruff check .` prints `All checks passed!`; formatter: `.venv/bin/ruff format --check .`
  exits 0.
- [ ] Size limits: `.venv/bin/pytest -q tests/architecture` passes (each new module ≤ 300 lines, each class ≤ 150).
- [ ] Type checker: `.venv/bin/mypy --strict api tests` prints `Success: no issues found in N source files` (`ml`
  holds no module until spec 007).
- [ ] No new suppressions: `grep -rn "noqa\|type: ignore" --include="*.py" --exclude-dir=.venv .` prints nothing.
- [ ] Coverage: `.venv/bin/pytest -q -m "not integration" --cov=api --cov-report=term-missing` shows ≥ 80 % for
  each of the 3 new modules.
- [ ] Domain purity: `.venv/bin/pytest -q tests/architecture -k repository_has_no_violations` reports `1 passed`
  (the summary line also counts deselected tests) and exits 0.
- [ ] No time, environment, file or logging access: `grep -nE "datetime\.now|os\.environ|open\(|logging|print\("
  api/domain/errors.py api/domain/entities.py api/domain/reports.py` prints nothing (the words `logging` and `print(`
  MUST NOT appear in docstrings or comments of those files).
- [ ] Security grep: `bash scripts/security_grep.sh` prints nothing, exit code 0.
