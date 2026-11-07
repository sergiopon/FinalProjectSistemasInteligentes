# 024 - API composition root and routes
Riesgo: alto

## Objective
The adapters (specs 016 to 021) and use cases (specs 022, 023) exist but nothing serves them. This spec creates the
composition root `api/main.py` (process hardening, offline flags, wiring, request id, error mapping, the single
generic exception handler, static mount of `web/`) and `api/routes.py` (the 6 JSON routes of `docs/contracts.md`
§6). Both modules MUST stay ≤ 300 lines (`ARCHITECTURE.md` §6), which is why the routes live in their own module.
After this spec, `.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000` serves the API.

## Depends on
017, 018, 019, 020, 021, 022, 023 (`Implemented`). The startup check of the Definition of Done also needs a trained
bundle (spec 014, `python -m ml.train`).

## Governing files
- `ARCHITECTURE.md` §2 (entry layer imports everything; nobody imports `api.main`; rule 5 manual injection), §3
  steps 6 and 7, §6 (≤ 20 statements per function, ≤ 6 arguments, ≤ 300 lines per module, generic `except` only in
  the global handler of `api/main.py`, `logging.getLogger(__name__)`, `key=value` logs, no `print`), §7.
- `security-rules.md` SEC-01, SEC-02, SEC-03, SEC-04, SEC-05, SEC-06, SEC-11, SEC-16, SEC-21, SEC-22.
- `docs/contracts.md` §2 (codes, statuses, client messages), §3 (adapters), §5, §6, §7, §9.1, §9.5. ADR-003, ADR-004.

## Files to create/modify
1. `api/main.py` (new). No entry module exists yet; structure fixed below.
2. `api/routes.py` (new). Entry-layer module imported only by `api/main.py`.
3. `tests/fixtures/fake_ports.py` (modify): add `FakeDriftDetector`, `RaisingPolarityModel`, `make_services`.
4. `tests/unit/test_main.py` (new).
5. `tests/unit/test_routes.py` (new).

## External dependencies
None new. Verified at the pins of `CONTEXT.md` (fastapi 0.162.0, starlette 1.10.0, uvicorn 0.54.0, pydantic
2.14.3, httpx 0.28.1, Python 3.12.14): `@app.middleware("http")` catches exceptions that no handler handled;
`StaticFiles(directory=..., html=True, check_dir=False)` mounted at `"/"` after the router serves `index.html` at
`/`, its 404 and 405 reach the app's `StarletteHTTPException` handler, and a missing directory raises `RuntimeError`
at request time; a lifespan startup exception makes uvicorn log `"Application startup failed. Exiting."` and exit
with code 3; `BaseModel.model_validate_json` raises `pydantic.ValidationError` for invalid JSON and extra fields.

## Interfaces and types
Names consumed from earlier specs (not all in `docs/contracts.md`; the implementer checks each against the
implemented code first and, on any mismatch, stops and reports it without adapting):

| Spec | Name |
|---|---|
| 016 | `api.adapters.settings.load_settings(path: Path) -> AppSettings`; fields `costs.error_cost`, `costs.review_cost`, `costs.review_if_set_not_singleton`, `conformal.alpha`, `limits.max_text_chars`, `limits.max_upload_bytes`, `limits.max_upload_rows`, `models_dir: Path` (absolute); `api.adapters.log_config.configure_logging() -> None` |
| 017-020 | Adapter constructors of `docs/contracts.md` §3; `api.adapters.monitoring.utc_now_iso() -> str` (UTC, `%Y-%m-%dT%H:%M:%SZ`) |
| 021 | `api.adapters.csv_reader.read_limited_body(chunks: AsyncIterator[bytes], content_length: str \| None, max_bytes: int) -> bytes` (async; `PayloadTooLargeError`); `api.adapters.csv_reader.parse_comments_csv(body: bytes, max_rows: int, max_text_chars: int) -> tuple[Comment, ...]` (`CsvFormatError`, `InvalidInputError`); `api.adapters.http_schemas`: `PredictRequest` (`text`), `PredictResponse.from_analysis(analysis, model_version)`, `BatchResponse.from_results(model_version, analyses, reports)`, `ModelInfoResponse.from_info(info)`, `DriftResponse.from_report(report)`, `MetricsResponse.from_snapshot(snapshot)` |

`api/routes.py`:
- `@dataclass(frozen=True, slots=True) class Services:` fields `model_info: ModelInfo`, `analyze_comment:
  AnalyzeComment`, `analyze_batch: AnalyzeBatch`, `course_report: BuildCourseReport`, `drift: DriftDetector`,
  `metrics: MetricsStore`, `max_upload_bytes: int`, `max_upload_rows: int`, `max_text_chars: int`, `clock:
  Callable[[], str]`.
- `services_of(request: Request) -> Services`: `request.app.state.services` narrowed with `isinstance`; missing or
  other type → `ModelUnavailableError("services not loaded")`.
- `media_type(request: Request) -> str`: `content-type` header before the first `;`, stripped, lowercase; `""`
  when absent.
- Endpoints (all `async def`, argument `request: Request` only): `health` → `dict[str, str]`; `model` →
  `ModelInfoResponse`; `predict` → `PredictResponse`; `predict_batch` → `BatchResponse`; `drift` →
  `DriftResponse`; `metrics` → `MetricsResponse`.
- `build_router() -> APIRouter`: registers with `add_api_route` exactly `GET /health`, `GET /model`, `POST
  /predict`, `POST /predict-batch`, `POST /drift`, `GET /metrics`. No module-level router object.

`api/main.py`:
- Statement order (top of file): module docstring; `from __future__ import annotations`; `import os`;
  `os.umask(0o077)`; `os.environ["HF_HUB_OFFLINE"] = "1"`; `os.environ["TRANSFORMERS_OFFLINE"] = "1"`; then every
  other import, each with `# noqa: E402` (the only suppression this spec authorizes).
- Constants: `REPO_ROOT: Path = Path(__file__).resolve().parent.parent`; `CONFIG_PATH: Path = REPO_ROOT / "config"
  / "app.json"`; `WEB_DIR: Path = REPO_ROOT / "web"`; `ALPHA_TOLERANCE: float = 1e-9`; `LOGGER =
  logging.getLogger(__name__)`; `CLIENT_ERRORS: Mapping[str, tuple[int, str]]` = `types.MappingProxyType` of
  `internal_error` (500, `"Internal error."`), `invalid_input` (422, `"The request is invalid."`), `invalid_csv`
  (422, `"The CSV file is invalid."`), `payload_too_large` (413, `"The upload exceeds the size limit."`),
  `unsupported_media_type` (415, `"Unsupported content type."`), `not_found` (404, `"Resource not found."`),
  `model_unavailable` (503, `"The model is not available."`), `method_not_allowed` (405, `"Method not
  allowed."`).
- `SECURITY_HEADERS: Mapping[str, str]` = `types.MappingProxyType` of exactly the 5 headers of `security-rules.md`
  SEC-22: `Content-Security-Policy` (`"default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self';
  connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"`), `X-Content-Type-Options`
  (`"nosniff"`), `Referrer-Policy` (`"no-referrer"`), `Cross-Origin-Resource-Policy` (`"same-origin"`),
  `Cache-Control` (`"no-store"`).
- `apply_security_headers(response: Response) -> None`: sets each `SECURITY_HEADERS` item on `response.headers`.
- `error_response(code: str, request_id: str) -> JSONResponse`: status and message from `CLIENT_ERRORS`; body
  `{"error": code, "message": message, "request_id": request_id}`.
- `load_services(config_path: Path = CONFIG_PATH) -> Services`; helpers `_float_tuple(value: object, key: str) ->
  tuple[float, ...]`, `_terms_tuple(value: object) -> tuple[tuple[str, ...], ...]`, `_vocabulary(vectorizer:
  object) -> frozenset[str]`, `_read_reference(models_dir: Path, version: str) -> dict[str, object]`.
- `build_app(factory: Callable[[], Services], web_dir: Path = WEB_DIR) -> FastAPI`.
- `app: FastAPI = build_app(load_services)` (module level; importing the module loads no model).

## Expected behavior
`load_services(config_path)` (runs inside the lifespan, so failures stop startup):
1. `configure_logging()`; `settings = load_settings(config_path)`; `store = TrustedModelStore(settings.models_dir)`;
   `info = store.info()`; `bundle = store.bundle()`.
2. `abs((1 - settings.conformal.alpha) - info.confidence_level) > 1e-9` → `ConfigError("alpha does not match the
   model confidence level")`.
3. Builds `SklearnPolarityModel(bundle["polarity_pipeline"], bundle["conformal_classifier"],
   info.confidence_level)`, `SklearnAspectModel(bundle["aspect_pipeline"], _float_tuple(bundle["aspect_thresholds"],
   "aspect_thresholds"))`, `OcclusionExplainer(polarity)`, `SpacyAnonymizer()`,
   `CentroidSummarizer(bundle["topic_vectorizer"])`, `KMeansTopicModel(bundle["topic_vectorizer"],
   bundle["topic_kmeans"], _terms_tuple(bundle["topic_terms"]))`, `ReferenceDriftDetector(_read_reference(...),
   _vocabulary(bundle["topic_vectorizer"]))`, `InMemoryMetricsStore()`, `DecisionCosts(...)` from `settings.costs`,
   the three use cases with default `influence_count` and `quote_count`, `clock = utc_now_iso`.
4. Returns `Services`; logs `"startup model_version=<version>"` at `INFO`.
- `_float_tuple`: value not a `tuple` or any item not a `float` → `ModelIntegrityError(f"bundle key {key} has an
  invalid type")`. `_terms_tuple`: same check for a tuple of tuples of `str`, key `topic_terms`. `_vocabulary`:
  `getattr(vectorizer, "vocabulary_", None)` not a `dict` → `ModelIntegrityError("topic vectorizer has no
  vocabulary")`; returns its keys as `str`. `_read_reference`: `resolve_within(models_dir, Path(version) /
  "reference_stats.json")`, read UTF-8, `json.loads`; `OSError` or `json.JSONDecodeError` →
  `ModelIntegrityError("reference stats unreadable")` raised `from` the cause; not a `dict` →
  `ModelIntegrityError("reference stats are not an object")`.

`build_app(factory, web_dir)`:
1. Lifespan: `app.state.services = factory()`; no `try` (an exception aborts startup, uvicorn exits with code 3).
2. Middleware `request_context` (the global exception handler): `request_id = uuid.uuid4().hex` stored in
   `request.state.request_id` (incoming `X-Request-ID` ignored); `await call_next(request)` inside `try`; `except
   Exception` → `LOGGER.exception("unhandled_error request_id=%s route=%s", request_id, request.url.path)` and
   `error_response("internal_error", request_id)`. Sets header `X-Request-ID` and calls `apply_security_headers` on every response, including the 500 built in the
   `except` branch and the static files; logs `"request
   request_id=%s route=%s status=%d duration_ms=%.1f"` at `INFO` (`time.perf_counter`, monotonic, not wall time).
3. `AppError` handler → `error_response(exc.code, request_id)`; logs `"app_error request_id=%s code=%s detail=%s"`
   at `WARNING` for status < 500 and `ERROR` otherwise (`detail` never holds comment text, contracts §2).
4. `RequestValidationError` handler → `invalid_input`. `StarletteHTTPException` handler → 404 → `not_found`, 405 →
   `method_not_allowed`, any other status → `internal_error`.
5. `FastAPI(lifespan=..., docs_url=None, redoc_url=None, openapi_url=None)` (no interactive docs: their page loads
   scripts from a CDN, SEC-16). `app.include_router(build_router())`, then `app.mount("/", StaticFiles(directory=web_dir, html=True,
   check_dir=False), name="web")`.

Routes (`services = services_of(request)`; `version = services.model_info.version`):
1. `GET /health` → `{"status": "ok", "model_version": version}`. `GET /model` →
   `ModelInfoResponse.from_info(services.model_info)`. `GET /metrics` →
   `MetricsResponse.from_snapshot(services.metrics.snapshot())`.
2. `POST /predict`: `start = time.perf_counter()`; `media_type != "application/json"` →
   `UnsupportedMediaTypeError("predict expects application/json")`; `PredictRequest.model_validate_json(await
   request.body())`, `pydantic.ValidationError` → `InvalidInputError("predict body failed validation")` raised
   `from` it; `analysis = services.analyze_comment.execute(Comment(text=payload.text))`;
   `services.metrics.record("/predict", elapsed_ms, (analysis.decision.decision,))`; returns
   `PredictResponse.from_analysis(analysis, version)`.
3. `POST /predict-batch`: `media_type != "text/csv"` → `UnsupportedMediaTypeError("expected text/csv")`; `body =
   await read_limited_body(request.stream(), request.headers.get("content-length"), services.max_upload_bytes)`;
   `comments = parse_comments_csv(body, services.max_upload_rows, services.max_text_chars)`; `analyses =
   analyze_batch.execute(comments)`; `reports = course_report.execute(comments, analyses)` (original texts; masked
   inside, SEC-02); `metrics.record("/predict-batch", elapsed_ms, decisions)`; logs `"batch request_id=%s
   rows=%d"`; returns `BatchResponse.from_results(version, analyses, reports)`.
4. `POST /drift`: same media check and body read; `report = drift.compare(tuple(c.text for c in comments),
   hashlib.sha256(body).hexdigest(), services.clock())`; `metrics.record_drift(report)`; returns
   `DriftResponse.from_report(report)`. No latency record.
The body stays in memory (SEC-01); nothing is written to disk (SEC-03); no log holds text or file names (SEC-05,
SEC-06).

## Edge cases and error handling
| Input | Result |
|---|---|
| `POST /predict` with `Content-Type: text/plain` | 415 `unsupported_media_type` |
| Body `{bad`, `{"text": "a", "x": 1}`, `{"text": "   "}` | 422 `invalid_input`, `"The request is invalid."` |
| CSV `Content-Length` above `max_upload_bytes` | 413 `payload_too_large` |
| CSV without column `curso` | 422 `invalid_csv`, `"The CSV file is invalid."` |
| Unknown path `/nope` | 404 `not_found`; `DELETE /predict` → 405 `method_not_allowed` |
| Port raises `RuntimeError("Ana Gómez ana@uni.edu.co")` | 500 `internal_error`, `"Internal error."`; traceback logged once by `api.main` |
| Port raises `InferenceError` | 500 `internal_error` |
| Factory raises `ModelIntegrityError` | Startup aborts (uvicorn exit code 3) |
| `web_dir` missing | `GET /` → 500 `internal_error` |

If an existing test not listed here fails because of this change, the implementer does not modify it: they report
its name and the reason. `fastapi.testclient` prints `StarletteDeprecationWarning` with httpx 0.28.1; it is not
filtered here.

## Acceptance tests (prose)
`tests/fixtures/fake_ports.py` additions: `FakeDriftDetector` (`compare` returns `DriftReport(body_sha256,
len(texts), 0.0, 0.0, 0.0, False, created_at)` and records calls); `RaisingPolarityModel(error: Exception)` (both
methods raise `error`); `make_services(polarity: PolarityModel | None = None, max_upload_bytes: int = 2097152) ->
Services` with `ModelInfo("v001", "2026-11-05T12:00:00Z", "0" * 64, "logistic_regression", "tfidf", 0.9, 0.61,
0.9)`, spec 022 and 023 fakes (topic map empty, terms `{0: ("curso", "clase", "tema", "contenido", "horario")}`),
`InMemoryMetricsStore()`, `FakeDriftDetector()`, limits 5000 and 2000, clock `"2026-11-05T12:00:00Z"`. Clients are
`TestClient(build_app(lambda: services, tmp_path / "web"))` used as context manager; `tmp_path / "web" /
"index.html"` holds `"<p>synthetic</p>"`. `CSV = "﻿id,curso,feedback\nid,curso,feedback\n1,Redes,Ana dio buen
contenido.\n2,Redes,Buen curso.\n"` encoded UTF-8, header `text/csv; charset=utf-8`.

`tests/unit/test_main.py`:
1. `test_main_umask_and_offline_first` — `ast.parse` of `api/main.py`: statements 0 to 5 are the docstring, the
   `__future__` import, `import os`, `os.umask(0o077)`, `HF_HUB_OFFLINE`, `TRANSFORMERS_OFFLINE` assignments to
   `"1"`; no other import before statement 6.
2. `test_main_offline_env_set` — after `import api.main`, both variables equal `"1"`.
3. `test_main_request_id_header` — 2 `GET /health` with `X-Request-ID: abc`: each header matches `^[0-9a-f]{32}$`,
   differs from `abc` and from the other.
4. `test_main_app_error_mapping` — parametrized over `InvalidInputError` (422), `CsvFormatError` (422
   `invalid_csv`), `PayloadTooLargeError` (413), `UnsupportedMediaTypeError` (415), `NotFoundError` (404),
   `ModelUnavailableError` (503), `InferenceError` (500 `internal_error`), `UnsafePathError` (500), raised by
   `RaisingPolarityModel` on `POST /predict {"text": "Buen curso."}`: status, `error`, `message` per `CLIENT_ERRORS`,
   `request_id` equals the header.
5. `test_main_unhandled_error_generic` — `RuntimeError("Ana Gómez ana@uni.edu.co")`: 500 body exactly `{"error":
   "internal_error", "message": "Internal error.", "request_id": <header>}`; body has no `"Ana"`, `"Traceback"`,
   `"RuntimeError"`; `caplog` holds 1 `ERROR` record of logger `api.main` starting `"unhandled_error request_id="`.
6. `test_main_not_found_and_method` — `GET /nope` → 404 `not_found`; `DELETE /predict` → 405
   `method_not_allowed`, message `"Method not allowed."`.
7. `test_main_static_index` — `GET /` → 200, text `"<p>synthetic</p>"`.
7b. `test_main_security_headers` — `GET /`, `GET /health`, `GET /nope` (404) and a `RuntimeError` 500 each carry the 5
    headers of `SECURITY_HEADERS` with exactly those values; `GET /docs` and `GET /openapi.json` → 404 `not_found`.
8. `test_main_static_missing_dir` — `web_dir = tmp_path / "absent"`: `GET /` → 500 `internal_error`.
9. `test_main_startup_failure` — factory raising `ModelIntegrityError("hash mismatch")`: entering `TestClient`
   raises `ModelIntegrityError`.
10. `test_main_float_tuple` — `(0.5, 0.25)` returned; `[0.5]` and `(0.5, "x")` raise `ModelIntegrityError` with
    detail `"bundle key aspect_thresholds has an invalid type"`.
11. `test_main_terms_tuple` — `(("a", "b"),)` returned; `(("a", 1),)` raises `ModelIntegrityError`.
12. `test_main_vocabulary` — `SimpleNamespace(vocabulary_={"curso": 0})` → `frozenset({"curso"})`; `object()` raises.
13. `test_main_read_reference` — `tmp/v001/reference_stats.json` with `{"length_edges": []}` → that dict; `[1]` →
    `"reference stats are not an object"`; `{bad` and a missing file → `"reference stats unreadable"`.

`tests/unit/test_routes.py`:
14. `test_routes_health` — `{"status": "ok", "model_version": "v001"}`.
15. `test_routes_model` — 200, `version == "v001"`, keys equal the `ModelInfo` field names.
16. `test_routes_predict` — polarity of spec 022 `C1`: 200, `text` equals the input, `predicted == "neutral"`,
    `decision == "review"`, `reason == "set_not_singleton"`, `conformal_set == ["negative", "neutral"]`.
17. `test_routes_predict_rejects` — `text/plain` → 415; `{bad`, extra field, blank text → 422 `invalid_input`.
18. `test_routes_predict_batch` — `CSV`: 200, `row_count == 2`, `rows[0]["text"] == "[PERSON] dio buen
    contenido."`, `rows[0]["row"] == 1`, `courses[0]["course"] == "Redes"`, 9 aspect entries.
19. `test_routes_predict_batch_rejects` — `max_upload_bytes = 64` with `CSV` → 413; `text/plain` → 415;
    `"curso,texto\nRedes,hola\n"` → 422 `invalid_csv`.
20. `test_routes_drift` — `CSV`: `body_sha256` equals `hashlib.sha256` of the bytes, `created_at ==
    "2026-11-05T12:00:00Z"`, `row_count == 2`; then `GET /metrics` has `last_drift` not null.
21. `test_routes_metrics_records` — after 1 `/predict`, 1 `/predict-batch` (2 rows) and 1 `/drift`:
    `request_count == 2`, `decisions == {"classify": 3, "review": 0}`.
22. `test_routes_logs_hold_no_text` — `POST /predict {"text": "Ana Gómez secreto"}`: no `caplog` message contains
    `"Ana"` or `"secreto"`.

## Out of scope
Running use cases in a thread pool (one local user; calls run in the event loop); the `web/` files (specs 025 to
027); authentication; Docker (spec 028); schema rounding and CSV parsing rules (spec 021).

## Definition of Done
- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0; `.venv/bin/pytest -q tests/unit/test_main.py tests/unit/test_routes.py` → `30 passed`.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed`; `wc -l api/main.py api/routes.py` → each ≤ 300.
- [ ] `grep -nE "# noqa|# type: ignore" api/main.py api/routes.py tests/unit/test_main.py tests/unit/test_routes.py tests/fixtures/fake_ports.py | grep -vE "^api/main.py:[0-9]+:.*# noqa: E402$"` → no output.
- [ ] `grep -rnE "except Exception|except:" api/` → exactly 1 line, in `api/main.py`.
- [ ] `grep -rn "UploadFile\|NamedTemporaryFile\|SpooledTemporaryFile" api/` → no output (SEC-01).
- [ ] `grep -rn "FileHandler\|print(" api/` → no output (SEC-05); `grep -rn "os.umask(0o077)" api/main.py` → 1 line (SEC-04).
- [ ] `grep -rnE "^(from|import) api\.main" api/ ml/ tests/` → only `tests/unit/` lines.
- [ ] `.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing` → lines for `api/main.py` and `api/routes.py` ≥ 80 %.
- [ ] After `.venv/bin/python -m ml.train`: `.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000` started in background, `curl -s http://127.0.0.1:8000/health` → `{"status":"ok","model_version":"v001"}`; `ss -ltn` lists `127.0.0.1:8000` and no `0.0.0.0:8000`; server stopped afterwards.
- [ ] `bash scripts/gate.sh` → last line `GATE OK`, exit code 0.
