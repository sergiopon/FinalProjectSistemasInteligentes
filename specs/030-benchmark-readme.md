# 030 - Benchmark and README
Riesgo: alto

## Objective

The guide asks to measure inference time and document security and quality (`docs/analysis.md` §1); there is no
benchmark script and `README.md` has no usage guide. This spec adds `scripts/benchmark.py` (p50 and p95 latency of `POST /predict` and
`POST /predict-batch` through the in-process app with the active bundle) and the usage sections of `README.md`.

## Depends on

024 (`api.main.app`, routes). Contracts used: `docs/contracts.md` §2, §6, §8. Commands: `CONTEXT.md` "Commands".

## Governing files

- `ARCHITECTURE.md` §5 (`scripts/benchmark.py`, `README.md` at the root), §6 (≤ 20 statements per function, ≤ 300
  lines per module, `mypy --strict`, `print` allowed in `scripts/`, only `AppError` subclasses raised).
- `security-rules.md` SEC-02, SEC-03, SEC-05, SEC-08, SEC-09 (synthetic benchmark texts), SEC-14, SEC-16 (no
  socket opened), SEC-21. ADR-001, ADR-002, ADR-003, ADR-004.

## Files to create/modify

1. `scripts/benchmark.py` (new; no Python module exists in `scripts/` yet, layout per `ARCHITECTURE.md` §6).
2. `tests/unit/scripts/test_benchmark.py` (new). 3. `README.md` (modify: it already holds the team split and the progress block). No existing test changes expectation.

## External dependencies

None new. Verified at fastapi `==0.162.0`, starlette `==1.10.0`, httpx `==0.28.1`: `with TestClient(app) as
client:` runs lifespan startup before the first request; `client.post(path, content=bytes, headers={"Content-Type":
"text/csv"})` sends the raw body; importing `fastapi.testclient` emits a `StarletteDeprecationWarning` (not an error).

## Interfaces and types

Module `scripts/benchmark.py`, run as `.venv/bin/python -m scripts.benchmark` from the repository root (namespace
package, `CONTEXT.md` "Structure"). Starts with `from __future__ import annotations`.

Constants:
- `PREDICT_RUNS: int = 100`, `BATCH_RUNS: int = 20`, `BATCH_ROWS: int = 100`, `WARMUP_RUNS: int = 3`
- `BATCH_COURSE: str = "Curso de prueba"`
- `SAMPLE_COMMENTS: tuple[str, ...]`, exactly these 5 synthetic strings, in order: `"El contenido del curso fue
  claro y ordenado."`, `"Los parciales fueron muy difíciles para el tiempo disponible."`, `"La plataforma se cayó
  varias veces durante las entregas."`, `"El profesor respondió los correos a tiempo."`, `"La carga de trabajo fue
  alta pero el material ayudó."`

Functions (no others):
- `percentile(values: Sequence[float], percent: float) -> float`
- `batch_body(rows: int) -> bytes`
- `measure(client: TestClient, path: str, body: bytes, content_type: str, runs: int) -> tuple[float, ...]`
- `summarize(latencies: Sequence[float]) -> dict[str, float | int]` (keys `runs`, `p50_ms`, `p95_ms`)
- `run_benchmark(client: TestClient) -> dict[str, object]`
- `load_app() -> FastAPI`
- `main() -> int`

Errors: `InvalidInputError` and `InferenceError` from `api.domain.errors`.

## Expected behavior

1. `percentile(values, percent)`: nearest rank. `n = len(values)`; result = `sorted(values)[ceil(percent / 100 *
   n) - 1]`. Vectors: `1.0..20.0` (20 values) → p50 `10.0`, p95 `19.0`; `(3.0, 1.0, 2.0)` → p50 `2.0`, p95 `3.0`;
   `(7.5,)` → `7.5` for both.
2. `batch_body(rows)`: header `feedback,curso` then `rows` data rows, row `i` (0-based) =
   `SAMPLE_COMMENTS[i % 5]`, `BATCH_COURSE`; written with `csv.writer(..., lineterminator="\n")`, encoded UTF-8
   without BOM. Vector: `batch_body(2)` → `b"feedback,curso\nEl contenido del curso fue claro y ordenado.,Curso de
   prueba\nLos parciales fueron muy dif\xc3\xadciles para el tiempo disponible.,Curso de prueba\n"`.
3. `measure(...)`: `runs` sequential `client.post(path, content=body, headers={"Content-Type": content_type})`;
   each latency = `(time.perf_counter() after - before) * 1000.0` in ms; returns them in order.
4. `summarize(latencies)`: `{"runs": len, "p50_ms": round(percentile(l, 50), 2), "p95_ms": round(percentile(l,
   95), 2)}`. Vector: `(1.0, 2.0, 10.006)` → `{"runs": 3, "p50_ms": 2.0, "p95_ms": 10.01}`.
5. `run_benchmark(client)`:
   1. `GET /health`; `model_version` = the JSON field `model_version`.
   2. Predict body = `json.dumps({"text": SAMPLE_COMMENTS[0]}).encode()`, content type `"application/json"`; batch
      body = `batch_body(BATCH_ROWS)`, content type `"text/csv"`.
   3. Warm-up: `measure` with `WARMUP_RUNS` on each route, results discarded.
   4. Returns `{"model_version": <str>, "predict": summarize(measure(..., PREDICT_RUNS)), "predict_batch":
      {**summarize(measure(..., BATCH_RUNS)), "rows": BATCH_ROWS}}`.
6. `load_app()`: returns `importlib.import_module("api.main").app`, so importing `scripts.benchmark` in unit tests
   does not build the app or load the bundle (ruff `PLC0415` flags a function-level `import`).
7. `main()`: `with TestClient(load_app()) as client:` → `run_benchmark`; prints `json.dumps(result,
   sort_keys=True)` as the last line of stdout (API logs also go to stdout, SEC-05); returns 0. `AppError` →
   prints `f"benchmark failed: {error.code}"` to stderr and returns 2. The module ends with
   `if __name__ == "__main__": raise SystemExit(main())`.
8. `README.md` keeps, unchanged, the `## Team split` and `## Progress` sections (including the
   `<!-- progress:start -->` and `<!-- progress:end -->` markers) and the `## Where things live` section; they move
   to the end of the file, after the block below. The rest of the file is exactly the block below (outer `~~~~`
   fence not included). Copy rules applied: no em
   dash, no claim or number without a source in `docs/analysis.md`, `ARCHITECTURE.md` or `security-rules.md`.

~~~~markdown
# From comment to action

This project reads Spanish course-evaluation comments and returns, for each one, a polarity (negative, neutral or
positive), the probability of each class, a conformal prediction set and a decision: classify the comment or send
it to a person for review. It also scores 9 aspect groups and builds a report per course with an aspect heatmap, a
priority ranking, topics and anonymized quotes. Everything runs on your machine: one FastAPI process on
`127.0.0.1` serves the API and a static web page.

## Requirements

Linux, [uv](https://docs.astral.sh/uv/), and Docker with the Compose plugin if you want the container. uv installs
Python 3.12.14. The network is needed only to install packages, download the embedding model and build the image.

## Install

```bash
uv venv --python 3.12 --seed .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m ml.representations --download
```

The last command downloads `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` at the revision pinned in
`CONTEXT.md`. After it, nothing else goes to the network.

## Train a model

```bash
.venv/bin/python -m ml.train
.venv/bin/python -m ml.artifact verify v001
```

Training reads `Dataset/`, writes `models/v001/` and makes it the active version in `models/registry.json`. The
service never trains. `.venv/bin/python -m ml.artifact rollback` returns to the previous version and
`.venv/bin/python -m ml.artifact activate v001` selects one by name.

## Check the model against people

```bash
.venv/bin/python -m ml.gold sample
.venv/bin/python -m ml.gold agreement
.venv/bin/python -m ml.gold_eval
```

`sample` writes `gold/sheet_a.csv` and `gold/sheet_b.csv` with the same comments. Two people label them without
seeing each other's sheet. `agreement` writes Cohen's kappa to `gold/agreement.json`, and `ml.gold_eval` compares
the active model with the rows where both people agree, in `reports/gold_eval.json`.

## Run the service

```bash
.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/> for the web page.

| Route | What it does |
|---|---|
| `GET /health` | Status and active model version |
| `GET /model` | Metadata and test metrics of the active model |
| `POST /predict` | Analyzes one comment sent as JSON `{"text": "..."}` |
| `POST /predict-batch` | Analyzes a CSV body (`text/csv`) with columns `feedback` and `curso` |
| `POST /drift` | Compares a CSV body with the training data |
| `GET /metrics` | Latency p50 and p95, decision counts and the last drift report |

## Run with Docker

Train a model first (it is read from `models/`). Run `export UID` if your shell does not export it, then
`docker compose up --build`, and `bash scripts/smoke_docker.sh` to check it. Compose publishes port 8000 on
`127.0.0.1` only, and the container runs with your user id.

## Measure inference time

`.venv/bin/python -m scripts.benchmark` loads the active model in the same process, sends 3 warm-up requests per route, then 100 requests to
`/predict` and 20 requests of 100 rows to `/predict-batch`. It prints p50 and p95 latency in milliseconds as JSON.
No socket is opened, so the times leave out network cost.

## Limitations

- The data is synthetic. The 618 comments in `Dataset/` come from templates ("El curso fue bastante..." opens 61
  of them), so these results say little about real student comments.
- The labels are noisy. The overall polarity matches the sentiment of the comment's own aspects in about half of
  the rows, and "neutral" often marks a mixed comment. A TF-IDF baseline reached macro-F1 0.62 in 5-fold
  cross-validation, which is probably near the ceiling these labels allow. This is why the service abstains and
  sends doubtful comments to review.
- Aspect labels are incomplete: of 55 comments that mention "diapositiva", 31 carry that aspect. Metrics against
  these labels count some correct predictions as errors; the gold set gives a cleaner measure.
- Groups are templates, not authors. The dataset has no author column, so the train and test split keeps clusters
  of near-identical comments on one side (`docs/adr/ADR-001-grouped-split-by-template-clusters.md`). Two comments
  by the same person can still fall on both sides.
- Deployment is local. The service listens on `127.0.0.1` and has no login, so do not expose it on a network.

## Security and ethics

- Comments can contain names. Every comment the API returns in batch rows, quotes, summaries and course reports is
  anonymized first: person names, emails, phone numbers and id numbers are masked. If the anonymizer cannot load,
  the service does not start. `/predict` returns your own text unchanged.
- The service stores nothing. Uploads are read in memory; predictions, counters and the last drift report are lost
  on restart. Review decisions stay in your browser's local storage.
- Logs go to stdout and never hold comment text or upload file names.
- The service loads a model only from `models/`, and only when the SHA-256 of the bundle and the versions of
  scikit-learn, numpy, joblib and mapie match its manifest. A mismatch stops the process.
- While it runs, the service makes no network calls. Every response carries a strict Content-Security-Policy and
  other browser security headers, and the web page builds its content without HTML strings.
- A predicted label is a suggestion. Comments the model is unsure about go to a review queue, and the gold set,
  labeled by two people, is what the model is measured against.
- Do not send real student comments, logs, uploads or model files to external services.
~~~~

## Edge cases and error handling

| Input | Result |
|---|---|
| `percentile` with empty `values` | `InvalidInputError("no latencies")` |
| `percentile` with `percent <= 0` or `> 100` | `InvalidInputError("percent out of range")` |
| `batch_body` with `rows < 1` or `rows > 5000` | `InvalidInputError("rows out of range")` |
| `measure` with `runs < 1` | `InvalidInputError("runs out of range")` |
| Any status other than 200 (health, warm-up, measured) | `InferenceError(f"benchmark request failed status={status}")`; `main` prints `"benchmark failed: internal_error"` to stderr, returns 2 |
| App startup fails (no active bundle, integrity error) | the startup exception propagates; the process exits non-zero with the traceback from Python |

If an existing test not listed here fails because of this change, the implementer does not modify it: report it with
its name and the reason.

## Acceptance tests (prose)

All in `tests/unit/scripts/test_benchmark.py`. A stub FastAPI app built in the test (never `api.main`) has
`GET /health` → `{"status": "ok", "model_version": "v009"}`, `POST /predict` and `POST /predict-batch` → 200 `{}`,
and counts calls and the received `Content-Type` per route.

- `test_percentile_nearest_rank`: the three vectors of behavior step 1.
- `test_percentile_rejects_empty`: `()` → `InvalidInputError`. `test_percentile_rejects_out_of_range`: `percent`
  0 and 101 → `InvalidInputError` each.
- `test_batch_body_vector`: `batch_body(2)` equals the bytes of behavior step 2.
- `test_batch_body_wraps_comments`: `batch_body(6)` has 7 lines; line 7 is the first comment again.
- `test_batch_body_rejects_row_limits`: 0 and 5001 → `InvalidInputError` each; 5000 → 5001 lines.
- `test_measure_one_latency_per_run`: `runs=4` on `/predict` → 4 floats, each `>= 0.0`; stub counted 4 calls.
- `test_measure_rejects_zero_runs`: `runs=0` → `InvalidInputError`. `test_measure_rejects_non_200`: stub
  `/predict` returns 503 → `InferenceError`.
- `test_summarize_vector`: `(1.0, 2.0, 10.006)` → `{"runs": 3, "p50_ms": 2.0, "p95_ms": 10.01}`.
- `test_run_benchmark_shape_and_counts`: result keys `model_version` (`"v009"`), `predict` (`runs` 100),
  `predict_batch` (`runs` 20, `rows` 100); stub counted 103 `/predict` and 23 `/predict-batch` calls; batch calls
  carried `text/csv`, predict calls `application/json`.
- `test_main_prints_json_last_line`: `monkeypatch.setattr` on `scripts.benchmark.load_app` returning the stub; exit
  0; last stdout line parses with `json.loads` and has `model_version` `"v009"`.
- `test_main_returns_2_on_failure`: stub `/health` returns 503 → exit 2, stderr
  `"benchmark failed: internal_error\n"`.

## Out of scope

Load tests over a real socket, concurrency, recording results in `/metrics` or in files, numbers inside
`README.md`, the article, `CONTEXT.md` (its "Commands" table gains no row here), Docker files (spec 028).

## Definition of Done

- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files` (follows the test's
      import of `scripts.benchmark`). `.venv/bin/pytest -q tests/architecture` → `N passed`.
- [ ] `grep -n "noqa\|type: ignore" scripts/benchmark.py tests/unit/scripts/test_benchmark.py` → no output.
- [ ] Coverage: not applicable to `scripts/` (the coverage command measures `api` and `ml` only); the Gate's
      `--cov-fail-under=80` still passes.
- [ ] `grep -n "^import api\.main\|^from api\.main" scripts/benchmark.py tests/unit/scripts/test_benchmark.py` → no
      output.
- [ ] `grep -nP "\x{2014}|\x{2013}" README.md` → no output (no em or en dash).
- [ ] `grep -niE "seamless|powerful|revolutionary|cutting.edge|next.generation|effortless|unlock|elevate" README.md`
      → no output.
- [ ] With a trained active bundle and the embedding cache: `.venv/bin/python -m scripts.benchmark` → exit 0; last
      stdout line is JSON with keys `model_version`, `predict`, `predict_batch`.
- [ ] `bash scripts/security_grep.sh` → no output, exit 0. `bash scripts/gate.sh` → last line `GATE OK`.
