# Contracts — FinalProjectTecEmergentes

Shared contract for every spec. Names, types, values and literals here are binding; a spec that needs a different
one amends this file first (row in `specs/README.md` corrections table). Layers and rules: `ARCHITECTURE.md`.
Every module starts with `from __future__ import annotations`; every entity is
`@dataclass(frozen=True, slots=True)` validated in `__post_init__`, raising `InvalidInputError` on violation.

## 1. Domain entities

### 1.1 `api/domain/entities.py`

Enums are `enum.StrEnum`; member order is the canonical order used by every tuple, vector and column.

| Enum | Members (`NAME = "value"`) |
|---|---|
| `Polarity` | `NEGATIVE = "negative"`, `NEUTRAL = "neutral"`, `POSITIVE = "positive"` (class index 0, 1, 2) |
| `Decision` | `CLASSIFY = "classify"`, `REVIEW = "review"` |
| `DecisionReason` | `CONFIDENT = "confident"`, `EMPTY_SET = "empty_set"`, `SET_NOT_SINGLETON = "set_not_singleton"`, `LABEL_OUTSIDE_SET = "label_outside_set"`, `EXPECTED_COST = "expected_cost"` |
| `AspectGroup` | `CONTENT = "content"`, `ASSESSMENT = "assessment"`, `FEEDBACK = "feedback"`, `METHODOLOGY_CLARITY = "methodology_clarity"`, `MATERIALS = "materials"`, `ORGANIZATION_SCHEDULE = "organization_schedule"`, `PLATFORM = "platform"`, `COMMUNICATION_CLIMATE = "communication_climate"`, `WORKLOAD_PACE = "workload_pace"` |

Constants: `POLARITY_ORDER: tuple[Polarity, ...] = tuple(Polarity)`, `ASPECT_ORDER: tuple[AspectGroup, ...] =
tuple(AspectGroup)`, `PROBABILITY_SUM_TOLERANCE: float = 1e-6`.

| Entity | Fields | Validation |
|---|---|---|
| `Comment` | `text: str`, `course: str \| None = None` | `text.strip()` non-empty; `course` is `None` or non-empty after strip. Length limits are enforced by the HTTP and CSV adapters (`limits.max_text_chars`). |
| `ClassProbabilities` | `negative: float`, `neutral: float`, `positive: float` | each in `[0.0, 1.0]`; `abs(sum - 1.0) <= 1e-6` |
| `ConformalSet` | `labels: frozenset[Polarity]`, `confidence_level: float` | `0.0 < confidence_level < 1.0`; `labels` may be empty |
| `AspectScores` | `scores: tuple[float, ...]`, `present: frozenset[AspectGroup]` | `len(scores) == 9` in `ASPECT_ORDER`; each in `[0.0, 1.0]` |
| `AspectSentiment` | `group: AspectGroup`, `polarity: Polarity`, `score: float`, `clause_index: int` | `score` in `[0.0, 1.0]`; `clause_index >= 0` |
| `ClauseAnalysis` | `text: str`, `probabilities: ClassProbabilities`, `aspects: AspectScores` | `text` non-empty |
| `WordInfluence` | `word: str`, `delta: float` | `word` non-empty; `-1.0 <= delta <= 1.0` |
| `CommentAnalysis` | Defined in `api/domain/decision.py` (spec 004), not here: its `decision: DecisionResult` field needs that module. Fields: `comment: Comment`, `probabilities: ClassProbabilities`, `conformal_set: ConformalSet`, `decision: DecisionResult`, `aspects: tuple[AspectSentiment, ...]`, `influences: tuple[WordInfluence, ...]` | `aspects` has no repeated group and follows `ASPECT_ORDER` |

Methods (no others): `ClassProbabilities.of(polarity: Polarity) -> float`; `ClassProbabilities.top() -> Polarity`
(highest value; tie → first in `POLARITY_ORDER`); `ConformalSet.is_singleton -> bool` (property);
`AspectScores.score(group: AspectGroup) -> float`.

### 1.2 `api/domain/reports.py`

| Entity | Fields | Validation |
|---|---|---|
| `PolarityCounts` | `negative: int`, `neutral: int`, `positive: int` | each `>= 0` |
| `AspectCell` | `group: AspectGroup`, `mentions: int`, `negative: int`, `neutral: int`, `positive: int` | counts `>= 0`; `negative + neutral + positive == mentions`. Property `negative_share -> float \| None` = `negative / mentions`, `None` when `mentions == 0`. |
| `PriorityEntry` | `rank: int`, `group: AspectGroup`, `mentions: int`, `negative: int`, `prevalence: float`, `smoothed_negative_share: float`, `score: float`, `low_support: bool` | `rank >= 1`; floats in `[0.0, 1.0]` |
| `TopicSummary` | `topic: int`, `size: int`, `terms: tuple[str, ...]`, `quote: str` | `topic >= 0`; `size >= 1`; `quote` is anonymized text |
| `CourseReport` | `course: str`, `comment_count: int`, `review_count: int`, `polarity_counts: PolarityCounts`, `aspects: tuple[AspectCell, ...]`, `priorities: tuple[PriorityEntry, ...]`, `topics: tuple[TopicSummary, ...]`, `quotes: tuple[str, ...]` | `aspects` has exactly 9 cells in `ASPECT_ORDER`; `0 <= review_count <= comment_count` |
| `DriftReport` | `body_sha256: str`, `row_count: int`, `length_psi: float`, `oov_rate: float`, `reference_oov_rate: float`, `drifted: bool`, `created_at: str` | `body_sha256` is 64 lowercase hex; `created_at` ISO 8601 UTC ending in `Z` |
| `MetricsSnapshot` | `request_count: int`, `p50_ms: float \| None`, `p95_ms: float \| None`, `classify_count: int`, `review_count: int`, `last_drift: DriftReport \| None` | counts `>= 0`. Property `abstention_rate -> float \| None` = `review / (classify + review)`, `None` when both are 0. |
| `ModelInfo` | `version: str`, `created_at: str`, `dataset_sha256: str`, `polarity_model: str`, `representation: str`, `confidence_level: float`, `test_macro_f1: float`, `empirical_coverage: float` | `version` matches `^v\d{3}$` |

## 2. Errors — `api/domain/errors.py`

`AppError(Exception)` has class attribute `code: str` and `__init__(self, detail: str)` storing `detail` (for logs
only; it MUST NOT contain comment text). The client never sees `detail`: `api/main.py` maps `code` to the literal
message below and the HTTP status.

| Class (parent) | `code` | HTTP | Client `message` | Raised by |
|---|---|---|---|---|
| `AppError` (`Exception`) | `internal_error` | 500 | `"Internal error."` | base, never raised directly |
| `InvalidInputError` (`AppError`) | `invalid_input` | 422 | `"The request is invalid."` | entities, HTTP schemas |
| `CsvFormatError` (`InvalidInputError`) | `invalid_csv` | 422 | `"The CSV file is invalid."` | `api/adapters/csv_reader.py` |
| `PayloadTooLargeError` (`AppError`) | `payload_too_large` | 413 | `"The upload exceeds the size limit."` | `csv_reader` |
| `UnsupportedMediaTypeError` (`AppError`) | `unsupported_media_type` | 415 | `"Unsupported content type."` | routes |
| `NotFoundError` (`AppError`) | `not_found` | 404 | `"Resource not found."` | routes, unknown path |
| `ModelUnavailableError` (`AppError`) | `model_unavailable` | 503 | `"The model is not available."` | `ModelStore` |
| `ModelIntegrityError` (`ModelUnavailableError`) | `model_unavailable` | startup exit 1 | — | `TrustedModelStore`, `ml.artifact` |
| `ConfigError` (`AppError`) | `internal_error` | startup exit 1 | — | `settings.py` |
| `AnonymizerUnavailableError` (`AppError`) | `internal_error` | startup exit 1 | — | `SpacyAnonymizer` |
| `InferenceError` (`AppError`) | `internal_error` | 500 | `"Internal error."` | model adapters |
| `UnsafePathError` (`AppError`) | `internal_error` | 500 | `"Internal error."` | `resolve_within` |
| `DatasetError` (`AppError`) | `internal_error` | CLI exit 2 | — | `ml.data`, `ml.gold` |

Starlette 405 maps to `{"error": "method_not_allowed", "message": "Method not allowed."}`. Any other exception →
500 `internal_error`, traceback logged through `RedactingFilter` (SEC-21). `ml` CLI exit codes: 0 success, 2
`AppError`, 1 any other exception.

## 3. Ports — `api/ports/`

All are `typing.Protocol` (not `runtime_checkable`). Files: `api/ports/models.py` (`ModelStore`, `PolarityModel`,
`AspectModel`, `Explainer`), `api/ports/text.py` (`Anonymizer`, `Summarizer`, `TopicModel`),
`api/ports/monitoring.py` (`DriftDetector`, `MetricsStore`). `texts` arguments are `Sequence[str]` with
`1 <= len(texts) <= 5000` and every text non-empty after strip (precondition for every method below).

| Port | Method | Postconditions | Raises |
|---|---|---|---|
| `ModelStore` | `info(self) -> ModelInfo` | Active version, already verified | `ModelUnavailableError` |
| `ModelStore` | `bundle(self) -> Mapping[str, object]` | The verified bundle dict of §9.1 | `ModelUnavailableError` |
| `PolarityModel` | `predict_proba(self, texts: Sequence[str]) -> tuple[ClassProbabilities, ...]` | Same length and order as `texts` | `InferenceError` |
| `PolarityModel` | `predict_set(self, texts: Sequence[str]) -> tuple[ConformalSet, ...]` | Same length; `confidence_level` from the manifest | `InferenceError` |
| `AspectModel` | `detect(self, texts: Sequence[str]) -> tuple[AspectScores, ...]` | `present` = groups with score ≥ the bundle threshold of that group | `InferenceError` |
| `Explainer` | `explain(self, text: str, top_k: int) -> tuple[WordInfluence, ...]` | ≤ `top_k` items sorted by `abs(delta)` descending, then word ascending; `top_k` in `1..20` | `InferenceError` |
| `Anonymizer` | `mask(self, text: str) -> str` | §4.4 masks applied; text without matches returned unchanged | `AnonymizerUnavailableError` |
| `Summarizer` | `summarize(self, texts: Sequence[str], k: int) -> tuple[str, ...]` | ≤ `k` distinct sentences taken from `texts`, most representative first; `k` in `1..10` | `InferenceError` |
| `TopicModel` | `assign(self, texts: Sequence[str]) -> tuple[int, ...]` | Topic id in `0..n_topics-1` per text | `InferenceError` |
| `TopicModel` | `terms(self, topic: int) -> tuple[str, ...]` | 5 terms of the trained topic | `InvalidInputError` for unknown id |
| `DriftDetector` | `compare(self, texts: Sequence[str], body_sha256: str, created_at: str) -> DriftReport` | §4.5 | `InvalidInputError` |
| `MetricsStore` | `record(self, route: str, latency_ms: float, decisions: Sequence[Decision]) -> None` | Thread-safe; keeps the last 1000 latencies | — |
| `MetricsStore` | `record_drift(self, report: DriftReport) -> None` | Replaces the last drift report | — |
| `MetricsStore` | `snapshot(self) -> MetricsSnapshot` | Percentiles by nearest rank over the buffer; `None` when empty | — |

v1 adapters (constructor signatures; objects from the bundle are typed `object` and narrowed inside the adapter):

| Adapter | Module | Constructor |
|---|---|---|
| `TrustedModelStore` | `api/adapters/model_store.py` | `(models_dir: Path)`; verifies and loads on construction (SEC-14) |
| `SklearnPolarityModel` | `api/adapters/sklearn_models.py` | `(pipeline: object, conformal: object, confidence_level: float)` |
| `SklearnAspectModel` | `api/adapters/sklearn_models.py` | `(pipeline: object, thresholds: tuple[float, ...])` |
| `OcclusionExplainer` | `api/adapters/explainer.py` | `(model: PolarityModel)`; delta = `p_top(text) - p_top(text without that word)` per distinct word (`\w+`, lowercase) |
| `SpacyAnonymizer` | `api/adapters/anonymizer.py` | `(model_name: str = "es_core_news_sm")`; load failure → `AnonymizerUnavailableError` |
| `CentroidSummarizer` | `api/adapters/text_analysis.py` | `(vectorizer: object)`; splits on `[.!?]+(?=\s\|$)`, ranks by cosine to the mean vector |
| `KMeansTopicModel` | `api/adapters/text_analysis.py` | `(vectorizer: object, kmeans: object, terms: tuple[tuple[str, ...], ...])` |
| `ReferenceDriftDetector` | `api/adapters/monitoring.py` | `(reference: Mapping[str, object], vocabulary: frozenset[str])` |
| `InMemoryMetricsStore` | `api/adapters/monitoring.py` | `()`; uses one `threading.Lock` |

## 4. Domain functions

### 4.1 Decision agent — `api/domain/decision.py`

`DecisionCosts(error_cost: float, review_cost: float, review_if_set_not_singleton: bool)`: both costs finite and
`> 0`. `DecisionResult(decision: Decision, reason: DecisionReason, label: Polarity)`.
`decide(probabilities: ClassProbabilities, conformal_set: ConformalSet, costs: DecisionCosts) -> DecisionResult`.
`label = probabilities.top()`. Rules in order, first match wins:

1. `conformal_set.labels` empty → `REVIEW`, `EMPTY_SET`.
2. `len(labels) > 1` and `review_if_set_not_singleton` → `REVIEW`, `SET_NOT_SINGLETON`.
3. `label not in labels` → `REVIEW`, `LABEL_OUTSIDE_SET`.
4. `(1 - probabilities.of(label)) * error_cost > review_cost + 1e-12` → `REVIEW`, `EXPECTED_COST`.
5. Otherwise `CLASSIFY`, `CONFIDENT`.

With the defaults (5.0, 1.0, true) rule 4 classifies when `p_top >= 0.8`. Test vectors (defaults unless stated):

| p (neg, neu, pos) | set | Result |
|---|---|---|
| (0.05, 0.10, 0.85) | {positive} | classify, confident, positive (cost 0.75 ≤ 1.0) |
| (0.15, 0.25, 0.60) | {positive} | review, expected_cost, positive (cost 2.0 > 1.0) |
| (0.10, 0.10, 0.80) | {positive} | classify, confident (cost 0.9999999999999998) |
| (0.45, 0.40, 0.15) | {negative, neutral} | review, set_not_singleton, negative |
| (0.30, 0.40, 0.30) | {} | review, empty_set, neutral |
| (0.10, 0.82, 0.08) | {negative} | review, label_outside_set, neutral |
| (0.02, 0.90, 0.08), flag false | {neutral, positive} | classify, confident, neutral (cost 0.5) |

### 4.2 Clauses and aspect sentiment — `api/domain/clauses.py`

`split_clauses(text: str) -> tuple[str, ...]`:
1. Split on `[.!?;]+(?=\s|$)`.
2. Split each piece on the case-insensitive regex `\b(?:pero|aunque|sin embargo|no obstante|mientras que)\b`
   (connector dropped).
3. Strip each piece of whitespace and of `,;:` at both ends; drop pieces shorter than 3 characters.
4. If nothing remains, return `(text.strip(),)`.

Vector: `"El contenido fue claro, pero los parciales fueron difíciles. Sin embargo, buen horario."` →
`("El contenido fue claro", "los parciales fueron difíciles", "buen horario")`.

`aspect_sentiments(clauses: Sequence[ClauseAnalysis]) -> tuple[AspectSentiment, ...]`: for each group in
`ASPECT_ORDER`, candidates are clauses whose `aspects.present` contains it; none → group omitted; otherwise pick the
candidate with the highest `aspects.score(group)` (tie → lowest index) and emit `AspectSentiment(group,
clause.probabilities.top(), score, index)`. Vector: clause 0 present {content} score 0.9, probabilities top
positive; clause 1 present {content, assessment} scores 0.6 and 0.8, top negative → `(content, positive, 0.9, 0)`,
`(assessment, negative, 0.8, 1)`.

### 4.3 Priority rule — `api/domain/priority.py`

Constants `MIN_SUPPORT: int = 5`. `rank_priorities(cells: Sequence[AspectCell], comment_count: int) ->
tuple[PriorityEntry, ...]` (`comment_count >= 1`). For each cell with `mentions >= 1`:
`prevalence = mentions / comment_count`; `smoothed_negative_share = (negative + 1) / (mentions + 2)`;
`score = prevalence * smoothed_negative_share`; `low_support = mentions < MIN_SUPPORT`. Sort by `score` descending,
tie → `ASPECT_ORDER`; `rank` from 1. Floats are not rounded in the domain (JSON rounds to 4 decimals).

Vector, `comment_count = 100`:

| Cell (mentions, negative) | prevalence | smoothed share | score | rank | low_support |
|---|---|---|---|---|---|
| content (40, 10) | 0.40 | 11/42 = 0.261905 | 0.104762 | 1 | false |
| assessment (10, 8) | 0.10 | 9/12 = 0.75 | 0.075 | 2 | false |
| platform (2, 2) | 0.02 | 3/4 = 0.75 | 0.015 | 3 | true |
| materials (0, 0) | — | — | omitted | — | — |

### 4.4 Safety — `api/domain/safety.py` (standard library only)

- `resolve_within(base: Path, candidate: Path) -> Path`: `root = base.resolve(strict=True)`;
  `target = (root / candidate).resolve(strict=False)`; `target.is_relative_to(root)` false →
  `UnsafePathError("path escapes base")`; returns `target`. Vectors: `(tmp, Path("v001/manifest.json"))` →
  `tmp/v001/manifest.json`; `(tmp, Path("../x"))` and `(tmp, Path("/etc/passwd"))` → `UnsafePathError`.
- Patterns (compiled module constants): `EMAIL_PATTERN = r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,}"`;
  `PHONE_PATTERN = r"\+?\(?\d[\d\s().-]{5,}\d"` replaced only when the match holds ≥ 7 digits and contains a
  separator (space, `-`, `.`, `(`, `)`, `+`), or holds more than 10 digits with no word character (`\w`) right before or
  after it; `ID_PATTERN = r"\b\d{6,10}\b"`.
- `mask_contact_data(text: str) -> str`: applies, in order, email → `"[EMAIL]"`, phone → `"[PHONE]"`,
  id → `"[ID]"`. Vector: `"Escribir a ana.gomez@uni.edu.co o al 300 123 4567, código 20231045"` →
  `"Escribir a [EMAIL] o al [PHONE], código [ID]"`.
- `redact(text: str) -> str` → `f"<redacted len={len(text)} sha={sha256(text.encode()).hexdigest()[:8]}>"`.
  Vector: `"Juan Pérez"` → `"<redacted len=10 sha=090fd624>"`.
- `class RedactingFilter(logging.Filter)`: `filter(self, record: logging.LogRecord) -> bool` sets
  `record.msg = mask_contact_data(record.getMessage())`, `record.args = None`; when `record.exc_info` is set it
  stores `mask_contact_data(logging.Formatter().formatException(record.exc_info))` in `record.exc_text` and sets
  `record.exc_info = None`; returns `True`.

`SpacyAnonymizer.mask` = `mask_contact_data` first, then each spaCy entity with label `"PER"` → `"[PERSON]"`.

### 4.5 Drift statistics (implemented in `ReferenceDriftDetector`)

Length bins: `bisect_right(reference["length_edges"], len(text))` gives a bin `0..9` (9 interior edges). Batch share
per bin, floored at `1e-4`. `length_psi = Σ (a_i - e_i) * ln(a_i / e_i)` with `e_i = reference["length_shares"][i]`.
`oov_rate` = share of lowercase tokens matching `(?u)\b\w\w+\b` that are not in `vocabulary`. `drifted =
length_psi > 0.25 or oov_rate > reference_oov_rate + 0.10`. Vector: `e = 0.1 × 10`, `a = (0.3, 0.1 × 7, 0, 0)` →
`length_psi = 1.599892` (rounded to 6 decimals).

## 5. Use cases — `api/application/`

| Class | Module | Constructor | Method |
|---|---|---|---|
| `AnalyzeComment` | `analyze.py` | `(polarity: PolarityModel, aspects: AspectModel, explainer: Explainer, costs: DecisionCosts, influence_count: int = 5)` | `execute(self, comment: Comment) -> CommentAnalysis` |
| `AnalyzeBatch` | `analyze.py` | `(polarity: PolarityModel, aspects: AspectModel, anonymizer: Anonymizer, costs: DecisionCosts)` | `execute(self, comments: Sequence[Comment]) -> tuple[CommentAnalysis, ...]` |
| `BuildCourseReport` | `course_report.py` | `(anonymizer: Anonymizer, summarizer: Summarizer, topics: TopicModel, quote_count: int = 3)` | `execute(self, comments: Sequence[Comment], analyses: Sequence[CommentAnalysis]) -> tuple[CourseReport, ...]` |

`AnalyzeComment`: probabilities and set of the full text → `decide` → `split_clauses` → `predict_proba` and
`detect` on all clauses in one call each → `aspect_sentiments` → `explain(text, influence_count)`. The returned
`comment.text` is the caller's own text, unmasked (SEC-02).
`AnalyzeBatch`: same per comment, with one `predict_proba`, one `predict_set` call over all comments and one
`predict_proba` and one `detect` call over all clauses; `influences = ()`; `comment.text` replaced by
`anonymizer.mask(text)` (SEC-02).
`BuildCourseReport`: `comments[i]` and `analyses[i]` are paired (same length, else `InvalidInputError`); groups by
`course` (`None` → `"unknown"`), sorted by course ascending. Polarity counts and `review_count` from the decisions;
aspect cells from `analyses[i].aspects`; `rank_priorities`; topics: `assign` on the original texts, one
`TopicSummary` per topic present (sorted by size descending, then id) with `terms(topic)` and
`quote = mask(summarize(topic texts, 1)[0])`; `quotes = mask` of each `summarize(course texts, quote_count)`.

## 6. HTTP API (`api/main.py`)

Every response carries header `X-Request-ID` (uuid4 hex, 32 characters, generated per request; an incoming value is
ignored). Error body: `{"error": "<code>", "message": "<client message from §2>", "request_id": "<id>"}`. JSON floats
are rounded to 4 decimals. CSV bodies: `Content-Type: text/csv` (any `charset` parameter), body size checked on
`Content-Length` and while reading (`limits.max_upload_bytes`, 2,097,152), strict UTF-8 with optional BOM, required
columns `feedback` and `curso` (others ignored), rows equal to the header row dropped, 1 to 5,000 data rows, every
`feedback` 1 to 2,000 characters after strip (SEC-01, SEC-11).

| Method and path | Request | 200 response | Errors |
|---|---|---|---|
| `GET /health` | — | `{"status": "ok", "model_version": "v001"}` | — |
| `GET /model` | — | `ModelInfo` fields in snake_case | 503 |
| `POST /predict` | `application/json` `{"text": "..."}` | `PredictResponse` | 415, 422, 503, 500 |
| `POST /predict-batch` | `text/csv` body | `BatchResponse` | 413, 415, 422, 503, 500 |
| `POST /drift` | `text/csv` body | `DriftReport` fields; also stored in `MetricsStore` | 413, 415, 422, 500 |
| `GET /metrics` | — | `MetricsResponse` | — |
| `GET /` | — | `web/index.html` (static mount, ADR-004) | 404 |

`PredictResponse` example:

```json
{"model_version": "v001", "text": "El contenido fue claro, pero los parciales fueron difíciles.",
 "predicted": "neutral", "probabilities": {"negative": 0.31, "neutral": 0.52, "positive": 0.17},
 "conformal_set": ["negative", "neutral"], "confidence_level": 0.9,
 "decision": "review", "reason": "set_not_singleton",
 "aspects": [{"group": "content", "polarity": "positive", "score": 0.91},
             {"group": "assessment", "polarity": "negative", "score": 0.77}],
 "influences": [{"word": "difíciles", "delta": 0.14}, {"word": "claro", "delta": -0.09}]}
```

`BatchResponse`: `{"model_version": "v001", "row_count": 2, "decision_counts": {"classify": 1, "review": 1},
"rows": [Row, ...], "courses": [CourseReportJson, ...]}`. `Row` = `{"row": 1, "course": "Bases de datos", "text":
"<masked>", "predicted", "probabilities", "conformal_set", "decision", "reason", "aspects"}` with the
`PredictResponse` shapes; `row` is the 1-based data row after dropping repeated headers. `conformal_set` lists labels
in `POLARITY_ORDER`. `CourseReportJson`:

```json
{"course": "Bases de datos", "comment_count": 70, "review_count": 12,
 "polarity_counts": {"negative": 20, "neutral": 30, "positive": 20},
 "aspects": [{"group": "content", "mentions": 40, "negative": 10, "neutral": 5, "positive": 25,
              "negative_share": 0.25}],
 "priorities": [{"rank": 1, "group": "content", "mentions": 40, "negative": 10, "prevalence": 0.4,
                 "smoothed_negative_share": 0.2619, "score": 0.1048, "low_support": false}],
 "topics": [{"topic": 0, "size": 30, "terms": ["contenido", "claro", "curso", "temas", "clase"],
             "quote": "<masked sentence>"}],
 "quotes": ["<masked sentence>", "<masked sentence>", "<masked sentence>"]}
```

`aspects` always has 9 entries (`negative_share` is `null` when `mentions` is 0).
`MetricsResponse`: `{"request_count": 10, "latency_ms": {"p50": 12.5, "p95": 40.1}, "decisions": {"classify": 7,
"review": 3}, "abstention_rate": 0.3, "last_drift": null}`. Latency and decisions are recorded for `/predict` and
`/predict-batch` only. Pydantic models live in `api/adapters/http_schemas.py`; request models use
`extra="forbid"`; FastAPI `RequestValidationError` maps to 422 `invalid_input`.

## 7. Configuration — `config/app.json`

```json
{"costs": {"error_cost": 5.0, "review_cost": 1.0, "review_if_set_not_singleton": true},
 "conformal": {"alpha": 0.1},
 "limits": {"max_text_chars": 2000, "max_upload_bytes": 2097152, "max_upload_rows": 5000},
 "models_dir": "models"}
```

`api/adapters/settings.py`: `load_settings(path: Path) -> AppSettings` (pydantic, `extra="forbid"`, frozen).
Validation: costs finite `> 0`; `0 < alpha < 1`; limits integers `>= 1` and `max_text_chars <= 2000`,
`max_upload_bytes <= 2097152`, `max_upload_rows <= 5000` (SEC-11 ceilings); `models_dir` relative, resolved with
`resolve_within(repo_root, ...)`. Any failure → `ConfigError`. At startup `1 - alpha` MUST equal the manifest
`confidence_level` within 1e-9, else `ConfigError`. `ml.train` reads `conformal.alpha` with `json` only.

## 8. `ml` modules

No `__init__.py`; every CLI module has `main(argv: Sequence[str] | None = None) -> int` and starts with
`os.umask(0o077)` (SEC-04). Seed 42 everywhere. Text arguments are `Sequence[str]`; `y` is `np.ndarray` of int
(class index in `POLARITY_ORDER`).

| Module | Public API |
|---|---|
| `ml.schemas` | `TypedDict`s `EmbeddingInfo`, `ManifestMetrics`, `SmokeCheck`, `SplitInfo` as defined in spec 007; constants `RAW_COLUMNS`, `POLARITY_RAW_MAP`, `ASPECT_LABEL_TO_GROUP`, `CLEAN_COLUMNS`, `SEED = 42`, `BUNDLE_SCHEMA_VERSION = 1`; `TypedDict`s `Manifest`, `Registry`, `Report`, `ReferenceStats` mirroring §9 |
| `ml.data` | `MAX_INPUT_BYTES = 2_097_152`; `validate_input_file(path: Path, base: Path) -> Path` (SEC-11); `dataset_files(dataset_dir: Path) -> tuple[Path, ...]` (`*.csv` top level, sorted by name); `dataset_sha256(files: Sequence[Path]) -> str`; `normalize_text(text: str) -> str`; `normalize_polarity(raw: str) -> Polarity`; `parse_aspects(raw: str) -> dict[AspectGroup, Polarity]`; `load_dataset(dataset_dir: Path) -> pd.DataFrame` |
| `ml.split` | `template_groups(texts: Sequence[str]) -> np.ndarray`; `cv_splitter() -> StratifiedGroupKFold` (5 folds, shuffle, 42); `grouped_split(y: np.ndarray, groups: np.ndarray) -> tuple[np.ndarray, np.ndarray]` (train and test row indices, first fold) |
| `ml.representations` | `EMBEDDING_MODEL_NAME`, `EMBEDDING_REVISION` (values in `CONTEXT.md`); `REPRESENTATIONS = ("tfidf", "tfidf_svd", "embeddings")`; `build_representation(name: str) -> TransformerMixin`; `class EmbeddingTransformer(BaseEstimator, TransformerMixin)` with `__init__(self, model_name: str, revision: str)`, `fit` no-op, `transform` → L2-normalized `float32` (n, 384), model loaded lazily with `local_files_only=True` and not pickled; `download(model_name: str, revision: str) -> None`; `main` (`--download`) |
| `ml.selection` | `CLASSIFIERS` (8 names: `dummy`, `logistic_regression`, `linear_svm`, `naive_bayes`, `random_forest`, `extra_trees`, `knn`, `sgd_log_loss`); `build_pipeline(representation: str, classifier: str) -> Pipeline` (steps `"features"`, `"classifier"`); `SelectionResult` (frozen dataclass: `representation`, `classifier`, `best_params`, `cv_macro_f1_mean`, `cv_macro_f1_std`, `pipeline` fitted, `selection` tuple of one dict per representation × classifier); the winner MUST expose `predict_proba` (`linear_svm` is a raw `LinearSVC` and never wins); `naive_bayes` is `ComplementNB` on `tfidf` and `GaussianNB` on dense representations; `select_model(texts, y, groups) -> SelectionResult` (`GridSearchCV`, `scoring="f1_macro"`, `cv=cv_splitter()`, best mean, tie → lower std, then name) |
| `ml.evaluation` | `evaluate(pipeline: Pipeline, texts, y) -> dict[str, object]` (keys `accuracy`, `macro_precision`, `macro_recall`, `macro_f1`, `per_class`, `confusion_matrix` 3×3 in `POLARITY_ORDER`); `per_file_macro_f1(pipeline: Pipeline, texts, y, source_files: Sequence[str]) -> dict[str, float]`; `risk_coverage(probabilities: np.ndarray, y: np.ndarray) -> list[tuple[float, float]]` |
| `ml.conformal` | `fit_cross_conformal(pipeline: Pipeline, texts, y, groups, confidence_level: float) -> CrossConformalClassifier` (ADR-002); `conformal_report(model, texts, y) -> dict[str, float]` (`empirical_coverage`, `mean_set_size`, `singleton_rate`, `empty_rate`) |
| `ml.aspects` | `aspect_targets(frame: pd.DataFrame) -> np.ndarray` (n, 9) int; `fit_aspect_model(texts, Y, groups) -> tuple[Pipeline, tuple[float, ...]]` (TF-IDF word 1-2 + `OneVsRestClassifier(LogisticRegression(class_weight="balanced", max_iter=1000))`; per-group threshold maximizing out-of-fold F1 over 0.10..0.90 step 0.05); `aspect_report(...) -> dict[str, object]` |
| `ml.topics` | `fit_topics(texts) -> tuple[TfidfVectorizer, KMeans, tuple[tuple[str, ...], ...]]` (word TF-IDF `min_df=5`; k in 4..10 by silhouette; `n_init=10`; 5 top centroid terms per topic) |
| `ml.artifact` | `next_version(models_dir: Path) -> str`; `write_version(models_dir: Path, bundle: dict[str, object], manifest: Manifest, report: Report, reference: ReferenceStats) -> Path`; `load_verified(models_dir: Path, version: str) -> dict[str, object]`; `activate(models_dir: Path, version: str) -> None`; `rollback(models_dir: Path) -> str`; `SMOKE_TEXTS` (3 hand-written synthetic comments); `main` (`activate vNNN`, `rollback`, `verify vNNN`) |
| `ml.train` | `main` (`--dataset Dataset --models models --config config/app.json`): clean → split → select → evaluate → conformal → aspects → topics → write version → activate |
| `ml.gold` | `main` (`sample --n 100` writes `gold/sheet_a.csv`, `gold/sheet_b.csv`; `agreement` reads both, writes `gold/agreement.json` with Cohen's kappa) |

## 9. Artifact files

### 9.1 `models/vNNN/bundle.joblib` (dict, `joblib.dump`)

Keys: `schema_version` (int 1), `class_order` (`("negative", "neutral", "positive")`), `aspect_order` (9 group
values), `polarity_pipeline` (selected `Pipeline` refit on train), `conformal_classifier`
(`CrossConformalClassifier`), `aspect_pipeline` (`Pipeline`), `aspect_thresholds` (tuple of 9 floats),
`topic_vectorizer` (`TfidfVectorizer`), `topic_kmeans` (`KMeans`), `topic_terms` (tuple of tuples of str). The
drift vocabulary is `topic_vectorizer.vocabulary_` keys. No embedding weights (ADR-003).

### 9.2 `models/vNNN/manifest.json`

```json
{"version": "v001", "created_at": "2026-11-10T12:00:00Z", "bundle_sha256": "<64 hex>",
 "dataset_sha256": "<64 hex>", "python_version": "3.12.14",
 "library_versions": {"scikit-learn": "1.9.1", "numpy": "2.5.4", "joblib": "1.6.0", "mapie": "1.6.0",
   "scipy": "1.18.1", "pandas": "3.1.1", "sentence-transformers": "6.2.0", "torch": "2.15.0+cpu", "spacy": "3.8.18"},
 "embedding": {"model_name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
   "revision": "e8f8c211226b894fcb81acc59f3b34ba3efd5f42"},
 "polarity_model": "logistic_regression", "representation": "tfidf", "best_params": {"classifier__C": 1.0},
 "confidence_level": 0.9, "seed": 42, "metrics": {"test_macro_f1": 0.61, "empirical_coverage": 0.9},
 "smoke": {"texts": ["<SMOKE_TEXTS[0]>", "<SMOKE_TEXTS[1]>", "<SMOKE_TEXTS[2]>"],
   "probabilities": [[0.1, 0.2, 0.7], [0.6, 0.3, 0.1], [0.3, 0.5, 0.2]]}}
```

SEC-14 compares `scikit-learn`, `numpy`, `joblib`, `mapie` with `importlib.metadata.version`. `verify` recomputes
smoke probabilities and requires `abs` difference ≤ 1e-9.

### 9.3 `models/registry.json`

`{"active": "v002", "history": ["v001", "v002"]}`. `activate(v)`: `v` directory MUST exist, append `v`, set
`active`. `rollback()`: `len(history) >= 2` else `ModelUnavailableError`; pop last; `active = history[-1]`. Written
atomically (temporary file in `models/` then `os.replace`).

### 9.4 `models/vNNN/report.json`

Keys: `selection` (list of `{"representation", "classifier", "best_params", "cv_macro_f1_mean",
"cv_macro_f1_std"}`), `test` (`evaluate` output), `per_file_macro_f1` (`{"<file name>": float}`), `conformal`
(`conformal_report`), `risk_coverage` (list of `[coverage, risk]`), `aspects` (per-group precision, recall, F1,
threshold), `topics` (list of `{"topic", "size", "terms"}`), `split` (`{"train_rows", "test_rows", "groups"}`),
`test_row_keys` (list of `row_key`). It holds no comment text and no quotes (SEC-02).

### 9.5 `models/vNNN/reference_stats.json`

`{"length_edges": [9 ints, train character-length deciles], "length_shares": [10 floats],
"reference_oov_rate": float (test rows against the train vocabulary), "class_shares": [3 floats, train labels]}`.

## 10. Dataset — `Dataset/*.csv`

Files: `feedback_curso_universitario.csv` (193 data rows), `feedback_curso_universitario2.csv` (405),
`feedback_curso_universitario3.csv` (20); total 618. Each starts with a UTF-8 BOM (read with `encoding="utf-8-sig"`)
and repeats the header as a data row (file 3 repeats it twice, at data positions 0 and 8); drop every row whose `id` equals `"id"`. Columns, in order:
`id,curso,feedback,polaridad_basica,grano_fino,emocion,aspectos,semestre`. `id` is not unique (file 3 has 7
repeated ids). `grano_fino` and `emocion` are dropped. `semestre` values: `2023-1`, `2023-2`, `2024-1`, `2024-2`.
`curso` has 7 values, kept verbatim (including `Sistemas opertativos`). No emoji appears (verified: no character
above U+2000).

Cleaning rules (`ml.data`):
1. `normalize_text`: Unicode NFC, every whitespace run → one space, strip. No stopword removal (intensifiers such
   as `muy` and `bastante` stay).
2. `normalize_polarity`: lowercase, remove `[`, `]`, `'`, `"` and spaces, then map `negativo` → negative,
   `neutral` → neutral, `positivo`/`positiva`/`posicion` → positive; other values → `DatasetError`. Raw values
   seen: `neutral`, `negativo`, `['negativo']`, `positivo`, `['positivo']`, `['neutral']`, `positiva`,
   `["['positivo']"]`, `['posicion']`. Result: negative 205, neutral 259, positive 154.
3. `parse_aspects`: `json.loads` of `aspectos` (every row parses as JSON); list of
   `{"aspecto": str, "sentimiento": "positivo" | "negativo" | "neutral"}`; unknown label → `DatasetError`. A group
   repeated in one row with one polarity keeps it; with conflicting polarities → neutral (7 cases).
4. `row_key = f"{file name}:{n}"`, `n` = 1-based data row in that file after dropping the header row.
5. Clean frame columns (`CLEAN_COLUMNS`): `row_key`, `source_file`, `source_id` (int), `course`, `semester`, `text`,
   `polarity` (value string), then `aspect_<group>` for the 9 groups in `ASPECT_ORDER` (value `""` when absent,
   else the polarity value).
6. `dataset_sha256`: SHA-256 over, for each file sorted by name, `file name + "\n"` then the file bytes. Value on
   2026-11-05: `5e3ac133828878229457420245bd2d674fdfe985e5a13632bf97b35bdbf2f666`.

Rows per group after rule 3: content 361, assessment 94, feedback 76, methodology_clarity 71, materials 66,
organization_schedule 59, platform 48, communication_climate 38, workload_pace 35; 60 rows have no aspect.

`ASPECT_LABEL_TO_GROUP` (22 labels, exact strings):

| Group | Original labels |
|---|---|
| `content` | `contenidos`, `Contenido y pertinencia`, `cantidad de temasrepaso al inicio del curso` |
| `assessment` | `parciales`, `dificultad de las preguntas en los parciales`, `Diseño de la evaluación y criterios` |
| `feedback` | `retroalimentación de los examenes`, `Retroalimentación recibida`, `comentarios del profesor` |
| `methodology_clarity` | `metodología del profesor`, `Actividades y metodología`, `Claridad de exposición` |
| `materials` | `material de clase`, `diseño de las diapositivas` |
| `organization_schedule` | `organización del curso y su planeación`, `horario` |
| `platform` | `disponibilidad de los recursos en el aula digital`, `Soporte técnico y plataforma` |
| `communication_climate` | `respuesta oportuna a los correos`, `Clima de aula e interacción` |
| `workload_pace` | `carga_académica`, `Ritmo y carga de trabajo` |
