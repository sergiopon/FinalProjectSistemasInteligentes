# 021 - Adapters HTTP schemas and CSV body reader
Riesgo: alto

## Objective

The HTTP API (`docs/contracts.md` §6) receives JSON and raw `text/csv` bodies from untrusted clients. SEC-01 and
SEC-11 require the CSV to be read in memory, capped at 2,097,152 bytes (on `Content-Length` and while reading) and
5,000 data rows, strict UTF-8 with optional BOM, with columns `feedback` and `curso`, and every text of 1 to 2,000
characters after strip, answering 4xx otherwise. This spec creates the pydantic request and response models with
4-decimal float rounding (`api/adapters/http_schemas.py`) and the CSV body reader (`api/adapters/csv_reader.py`).
Routes (spec 024) use them; this spec adds no route.

## Depends on

016 (settings: `LimitSettings` in `api/adapters/settings.py`; implies 002 and 003).

## Governing files

- `ARCHITECTURE.md` §2, §6 (`api/adapters/http_schemas.py` is exempt from the 300-line module limit; functions
  ≤ 20 statements; `mypy --strict`), §7 (limits).
- `security-rules.md` SEC-01 (raw body, no temporary file), SEC-05 and SEC-06 (no file name, no body content in
  logs), SEC-11, SEC-21 (error details hold no comment text).
- `docs/contracts.md` §1, §2 (`InvalidInputError` 422, `CsvFormatError` 422, `PayloadTooLargeError` 413), §6, §7.

## Files to create/modify

1. `api/adapters/http_schemas.py` (new). Reference pattern: `api/adapters/settings.py` (spec 016).
2. `api/adapters/csv_reader.py` (new). Same reference pattern.
3. `tests/unit/adapters/test_http_schemas.py` (new).
4. `tests/unit/adapters/test_csv_reader.py` (new).
5. `tests/integration/test_csv_reader_dataset.py` (new), marked `pytest.mark.integration`.

No existing test changes expectation.

## External dependencies

None new (pydantic `==2.14.3`; standard library `csv`, `io`).

## Interfaces and types

`api/adapters/http_schemas.py`. Constants: `MAX_TEXT_CHARS: int = 2000`, `FLOAT_DECIMALS: int = 4`. Type alias
`Rounded = Annotated[float, PlainSerializer(round_float, return_type=float)]`, with
`round_float(value: float) -> float` returning `round(value, 4)`. Every model has
`model_config = ConfigDict(frozen=True)`; `PredictRequest` adds `extra="forbid"`. Fields (`str` unless stated):

| Model | Fields |
|---|---|
| `PredictRequest` | `text` (validator below) |
| `ProbabilitiesJson` | `negative`, `neutral`, `positive`: `Rounded` |
| `AspectJson` | `group`, `polarity`, `score: Rounded` |
| `InfluenceJson` | `word`, `delta: Rounded` |
| `PredictResponse` | `model_version`, `text`, `predicted`, `probabilities: ProbabilitiesJson`, `conformal_set: list[str]`, `confidence_level: Rounded`, `decision`, `reason`, `aspects: list[AspectJson]`, `influences: list[InfluenceJson]` |
| `RowJson` | `row: int`, `course: str \| None`, `text`, `predicted`, `probabilities: ProbabilitiesJson`, `conformal_set: list[str]`, `decision`, `reason`, `aspects: list[AspectJson]` |
| `DecisionCountsJson` | `classify: int`, `review: int` |
| `PolarityCountsJson` | `negative: int`, `neutral: int`, `positive: int` |
| `AspectCellJson` | `group`, `mentions: int`, `negative: int`, `neutral: int`, `positive: int`, `negative_share: Rounded \| None` |
| `PriorityJson` | `rank: int`, `group`, `mentions: int`, `negative: int`, `prevalence: Rounded`, `smoothed_negative_share: Rounded`, `score: Rounded`, `low_support: bool` |
| `TopicJson` | `topic: int`, `size: int`, `terms: list[str]`, `quote` |
| `CourseReportJson` | `course`, `comment_count: int`, `review_count: int`, `polarity_counts: PolarityCountsJson`, `aspects: list[AspectCellJson]`, `priorities: list[PriorityJson]`, `topics: list[TopicJson]`, `quotes: list[str]` |
| `BatchResponse` | `model_version`, `row_count: int`, `decision_counts: DecisionCountsJson`, `rows: list[RowJson]`, `courses: list[CourseReportJson]` |
| `DriftReportJson` | `body_sha256`, `row_count: int`, `length_psi: Rounded`, `oov_rate: Rounded`, `reference_oov_rate: Rounded`, `drifted: bool`, `created_at` |
| `LatencyJson` | `p50: Rounded \| None`, `p95: Rounded \| None` |
| `MetricsResponse` | `request_count: int`, `latency_ms: LatencyJson`, `decisions: DecisionCountsJson`, `abstention_rate: Rounded \| None`, `last_drift: DriftReportJson \| None` |
| `ModelInfoJson` | `version`, `created_at`, `dataset_sha256`, `polarity_model`, `representation`, `confidence_level: Rounded`, `test_macro_f1: Rounded`, `empirical_coverage: Rounded` |
| `HealthResponse` | `status`, `model_version` |
| `ErrorResponse` | `error`, `message`, `request_id` |

Builder functions (domain entity → model): `predict_response(analysis: CommentAnalysis, model_version: str) ->
PredictResponse`; `batch_response(analyses: Sequence[CommentAnalysis], reports: Sequence[CourseReport],
model_version: str) -> BatchResponse`; `course_report_json(report: CourseReport) -> CourseReportJson`;
`drift_report_json(report: DriftReport) -> DriftReportJson`; `metrics_response(snapshot: MetricsSnapshot) ->
MetricsResponse`; `model_info_json(info: ModelInfo) -> ModelInfoJson`.

`api/adapters/csv_reader.py`. Constants: `FEEDBACK_COLUMN: str = "feedback"`, `COURSE_COLUMN: str = "curso"`.

- `async def read_body_limited(chunks: AsyncIterable[bytes], content_length: str | None, limits: LimitSettings) ->
  bytes` (`chunks` is Starlette `Request.stream()`, verified in starlette 1.10.0 as `AsyncGenerator[bytes, None]`).
- `def parse_csv_body(body: bytes, limits: LimitSettings) -> tuple[Comment, ...]`.
- Private helpers `_column_indexes(header: list[str]) -> tuple[int, int]` and `_comment_from_row(row: list[str],
  indexes: tuple[int, int], limits: LimitSettings) -> Comment`.

No `# type: ignore`, no `# noqa`; Google-style docstrings on every public item.

## Expected behavior

`PredictRequest.text` validator (`field_validator`, mode `"after"`): `stripped = text.strip()`; length outside
`1..2000` → `ValueError("text length out of range")` (pydantic turns it into a `ValidationError`, FastAPI into
`RequestValidationError` → 422 `invalid_input`); returns `stripped`. Non-string `text` (`123`, `null`), a missing
`text` or any extra key → `ValidationError` (types `string_type`, `missing`, `extra_forbidden`, measured).

Builders:
1. `predicted = analysis.decision.label.value`; `conformal_set = [p.value for p in POLARITY_ORDER if p in
   analysis.conformal_set.labels]`; `decision`, `reason` = enum values; `aspects` from `analysis.aspects` in order
   (`group.value`, `polarity.value`, `score`); `influences` from `analysis.influences` in order.
2. `confidence_level = analysis.conformal_set.confidence_level`; `text = analysis.comment.text` (already masked by
   `AnalyzeBatch` in batch rows, SEC-02).
3. `batch_response`: `row` = 1-based position in `analyses`; `course = analysis.comment.course`; `row_count =
   len(analyses)`; `decision_counts` counts `Decision.CLASSIFY` and `Decision.REVIEW`; `courses` =
   `course_report_json` of each report in order.
4. `metrics_response`: `latency_ms = {p50: p50_ms, p95: p95_ms}`, `decisions = {classify_count, review_count}`,
   `abstention_rate = snapshot.abstention_rate`, `last_drift` = `drift_report_json` or `None`.
5. Floats serialize with `round(value, 4)` in `model_dump` and `model_dump_json`; `None` stays `null`.

`read_body_limited(chunks, content_length, limits)`:
1. `content_length` not `None` and not (`isascii()` and `isdigit()`) → `InvalidInputError("invalid
   content-length")`. `int(content_length) > limits.max_upload_bytes` → `PayloadTooLargeError("content-length over
   limit")` before reading any chunk.
2. Appends chunks to a `bytearray`; as soon as its length exceeds `limits.max_upload_bytes` →
   `PayloadTooLargeError("body over limit")` (remaining chunks are not read).
3. Returns `bytes`. Nothing is written to disk (SEC-01).

`parse_csv_body(body, limits)`:
1. `len(body) > limits.max_upload_bytes` → `PayloadTooLargeError("body over limit")`.
2. `text = body.decode("utf-8-sig")` (strict; one leading BOM removed); `UnicodeDecodeError` →
   `CsvFormatError("body is not valid UTF-8")` from the cause.
3. Rows from `csv.reader(io.StringIO(text, newline=""), strict=True)`; `csv.Error` (bad quoting, field over 131,072
   characters) → `CsvFormatError("malformed CSV")` from the cause.
4. No first row → `CsvFormatError("missing header row")`. `header = [cell.strip() for cell in first_row]`; a name
   repeated → `CsvFormatError("duplicate column names")`; `feedback` or `curso` absent →
   `CsvFormatError("missing required columns")`. Other columns are ignored.
5. Each later row: `[]` (blank line) is skipped; a row whose stripped cells equal `header` is skipped; `len(row) !=
   len(header)` → `CsvFormatError("row has a wrong number of fields")`.
6. Data row number `n` (1-based, after skips) `> limits.max_upload_rows` → `PayloadTooLargeError("too many rows")`.
7. `feedback = row[i].strip()`, length outside `1..limits.max_text_chars` → `CsvFormatError("feedback length out of
   range")`; `course = row[j].strip()`, `""` → `None`; yields `Comment(text=feedback, course=course)`.
8. Zero data rows → `CsvFormatError("no data rows")`. Returns the comments in file order.

The module logs nothing; error details hold no cell content and no file name (SEC-05, SEC-06).

## Edge cases and error handling

| Input | Result |
|---|---|
| JSON `{"text": "   "}` or 2001 characters after strip | `ValidationError` |
| `content_length "2097153"` (default limits) | `PayloadTooLargeError("content-length over limit")`, no chunk read |
| `content_length "abc"`, `"-1"`, `"²"` | `InvalidInputError("invalid content-length")` |
| chunks totaling 2,097,153 bytes, no `Content-Length` | `PayloadTooLargeError("body over limit")` |
| `b"feedback,curso\nlecci\xf3n,x\n"` (Latin-1) | `CsvFormatError("body is not valid UTF-8")` |
| two BOMs at the start | header `"﻿feedback"` → `CsvFormatError("missing required columns")` |
| `'feedback,curso\n"hola,x\n'` | `CsvFormatError("malformed CSV")` |
| `b""` | `CsvFormatError("missing header row")` |
| header only, or header plus repeated header rows | `CsvFormatError("no data rows")` |
| 5001 data rows | `PayloadTooLargeError("too many rows")` (413) |

If an existing test not listed in this spec fails because of this change, the implementer does not modify it: they
report its name and the reason.

## Acceptance tests (prose)

`LIMITS = LimitSettings(max_text_chars=2000, max_upload_bytes=2097152, max_upload_rows=5000)`. Async functions run
with `asyncio.run` (no async plugin). All data synthetic.

`tests/unit/adapters/test_http_schemas.py`:
1. `test_predict_request_strips_text`: `'{"text": "  hola  "}'` → `text == "hola"`.
2. `test_predict_request_rejects_invalid`: `'{"text": "   "}'`, `'{"text": 123}'`, `'{"text": null}'`, `'{}'`,
   `'{"text": "x", "extra": 1}'`, 2001 × `"a"` → `ValidationError`; 2000 × `"a"` padded with spaces → accepted.
3. `test_predict_response_matches_contract_example`: analysis built from the `PredictResponse` example of
   `docs/contracts.md` §6 (probabilities `(0.31, 0.52, 0.17)`, set `{negative, neutral}` at 0.9, decision review
   `set_not_singleton` label neutral, aspects content positive 0.91 clause 0 and assessment negative 0.77 clause 1,
   influences `("difíciles", 0.14)`, `("claro", -0.09)`) → `model_dump(mode="json")` equals that JSON exactly.
4. `test_rounding_four_decimals`: probabilities `(0.333333333, 0.333333333, 0.333333334)` → `0.3333` each; a
   `PriorityJson` score `0.104761904` → `0.1048`; `negative_share None` → `null` in `model_dump_json`.
5. `test_batch_response_numbers_rows_and_counts`: two analyses (classify, review), one course report →
   `row_count 2`, rows `1` and `2`, `decision_counts {"classify": 1, "review": 1}`, `course None` kept as `null`.
6. `test_metrics_response_shape`: snapshot `(10, 12.5, 40.1, 7, 3, None)` → equals the `MetricsResponse` example of
   contract §6.
7. `test_model_info_and_drift_json_fields`: field names equal the entity field names.

`tests/unit/adapters/test_csv_reader.py`:
8. `test_parse_csv_reads_comments`: BOM + `"id,curso,feedback\r\n1,Bases de datos,  Buen curso  \r\n\r\nid,curso,
   feedback\r\n2,,Mal horario\r\n"` → `(Comment("Buen curso", "Bases de datos"), Comment("Mal horario", None))`.
9. `test_parse_csv_without_bom`: same body without BOM → same result.
10. `test_parse_csv_rejects_invalid_utf8`: `b"feedback,curso\n\xff,x\n"` and the Latin-1 body → `CsvFormatError`.
11. `test_parse_csv_rejects_columns`: `"feedback\nhola\n"`, `"feedback,feedback,curso\na,b,c\n"`, double BOM →
    `CsvFormatError`.
12. `test_parse_csv_rejects_structure`: `b""`, header only, `"feedback,curso\nhola\n"`, the unterminated quote,
    a field of 131,073 characters → `CsvFormatError`.
13. `test_parse_csv_text_length_bounds`: feedback `"   "` and 2001 × `"a"` → `CsvFormatError`; 2000 × `"a"` → one
    comment.
14. `test_parse_csv_row_limit`: 5000 rows → 5000 comments; 5001 → `PayloadTooLargeError`.
15. `test_parse_csv_body_over_limit`: limits with `max_upload_bytes=10` and a 11-byte body →
    `PayloadTooLargeError`.
16. `test_read_body_limited_cases`: `[b"ab", b"cd"]` with `"4"` → `b"abcd"`; `"2097153"` →
    `PayloadTooLargeError` and the generator yielded nothing; 3 chunks of 699,051 bytes and `None` →
    `PayloadTooLargeError`; `"abc"`, `"-1"`, `"²"` → `InvalidInputError`; exactly 2,097,152 bytes → returned.

`tests/integration/test_csv_reader_dataset.py`:
17. `test_parse_csv_reads_course_files`: each `Dataset/*.csv` read as bytes → 193, 405 and 20 comments
    (`docs/contracts.md` §10), every `course` not `None`.

## Out of scope

- Routes, `Content-Type` checks (415), error-response mapping, request ids (spec 024).
- Applying `limits.max_text_chars` below 2000 to `POST /predict` (the schema enforces the SEC-11 ceiling of 2000).

## Definition of Done

- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/pytest -q -m integration tests/integration/test_csv_reader_dataset.py` → `1 passed`.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed`.
- [ ] `grep -nE "noqa|type: ignore" api/adapters/http_schemas.py api/adapters/csv_reader.py tests/unit/adapters/test_http_schemas.py tests/unit/adapters/test_csv_reader.py tests/integration/test_csv_reader_dataset.py`
      → no output.
- [ ] `grep -nE "UploadFile|NamedTemporaryFile|SpooledTemporaryFile|open\(|logging" api/adapters/csv_reader.py api/adapters/http_schemas.py`
      → no output (SEC-01, SEC-05).
- [ ] `.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing` → rows
      `api/adapters/http_schemas.py` and `api/adapters/csv_reader.py` each ≥ 80 %.
- [ ] `bash scripts/gate.sh` → last line `GATE OK`, exit code 0.
