# 020 - Adapters monitoring: metrics store and drift detector
Riesgo: alto

## Objective

The guide asks to measure inference time and monitor data drift. `GET /metrics` and `POST /drift`
(`docs/contracts.md` §6) need the `MetricsStore` and `DriftDetector` ports, and no adapter implements them. This spec
creates `InMemoryMetricsStore` (thread-safe counters and a 1000-latency ring buffer, nearest-rank p50/p95) and
`ReferenceDriftDetector` (Population Stability Index over 10 length bins plus out-of-vocabulary rate, compared with
`models/vNNN/reference_stats.json`) in `api/adapters/monitoring.py`. Everything stays in memory and is lost on
restart (SEC-03).

## Depends on

006 (ports).

## Governing files

- `ARCHITECTURE.md` §2, §4, §6 (≤ 20 statements per function, ≤ 300 lines per module, no mutable global state,
  `mypy --strict`).
- `security-rules.md` SEC-03 (no persistence), SEC-05 (no comment text in logs), SEC-06 (only the body SHA-256 in
  the drift report), SEC-13.
- `docs/contracts.md` §1.2 (`DriftReport`, `MetricsSnapshot`), §2, §3, §4.5, §9.5.

## Files to create/modify

1. `api/adapters/monitoring.py` (new). Reference pattern: `api/adapters/model_store.py` (spec 017).
2. `tests/unit/adapters/test_monitoring_metrics.py` (new).
3. `tests/unit/adapters/test_monitoring_drift.py` (new).

No existing test changes expectation.

## External dependencies

None new (standard library only: `bisect`, `collections.deque`, `logging`, `math`, `re`, `threading`).

## Interfaces and types

Module `api/adapters/monitoring.py`:

- Constants: `LATENCY_BUFFER_SIZE: int = 1000`, `BIN_COUNT: int = 10`, `EDGE_COUNT: int = 9`,
  `SHARE_FLOOR: float = 1e-4`, `PSI_THRESHOLD: float = 0.25`, `OOV_MARGIN: float = 0.10`,
  `SHARE_SUM_TOLERANCE: float = 1e-6`, `MAX_TEXTS: int = 5000`,
  `TOKEN_PATTERN: re.Pattern[str] = re.compile(r"(?u)\b\w\w+\b")`.
- `class InMemoryMetricsStore` (implements `MetricsStore`):
  - `__init__(self) -> None`; attributes `_lock: threading.Lock`, `_latencies: deque[float]` (`maxlen=1000`),
    `_request_count: int`, `_classify_count: int`, `_review_count: int`, `_last_drift: DriftReport | None`.
  - `record(self, route: str, latency_ms: float, decisions: Sequence[Decision]) -> None`
  - `record_drift(self, report: DriftReport) -> None`
  - `snapshot(self) -> MetricsSnapshot`
- `nearest_rank(sorted_values: Sequence[float], percent: int) -> float`: module function.
- `class ReferenceDriftDetector` (implements `DriftDetector`):
  - `__init__(self, reference: Mapping[str, object], vocabulary: frozenset[str]) -> None`; attributes
    `_edges: tuple[int, ...]`, `_shares: tuple[float, ...]`, `_reference_oov_rate: float`,
    `_vocabulary: frozenset[str]`.
  - `compare(self, texts: Sequence[str], body_sha256: str, created_at: str) -> DriftReport`
  - Private helpers `_length_psi(self, texts: Sequence[str]) -> float` and
    `_oov_rate(self, texts: Sequence[str]) -> float`.

Google-style docstrings on every public item. No `# type: ignore`, no `# noqa`.

## Expected behavior

`nearest_rank(sorted_values, percent)`: `n = len(sorted_values)` (`n >= 1`, `percent` in `1..100`);
`rank = ceil(percent * n / 100)` computed with integers (`-(-percent * n // 100)`); returns
`sorted_values[rank - 1]`.

`InMemoryMetricsStore.record(route, latency_ms, decisions)`:
1. `math.isfinite(latency_ms)` false or `latency_ms < 0.0` →
   `InvalidInputError("latency must be a finite non-negative number")`; nothing is recorded.
2. Under `_lock`: `_request_count += 1`; append `latency_ms` to `_latencies` (the oldest value drops when 1000 are
   held); add the number of `Decision.CLASSIFY` items to `_classify_count` and of `Decision.REVIEW` to
   `_review_count`.
3. Logs at `DEBUG`: `"metrics_recorded route=%s latency_ms=%.1f decisions=%d"` with `route`, `latency_ms`,
   `len(decisions)`.

`record_drift(report)`: under `_lock`, `_last_drift = report`.

`snapshot()`: under `_lock`, copies the state; `p50_ms = nearest_rank(sorted(latencies), 50)` and
`p95_ms = nearest_rank(sorted(latencies), 95)`, both `None` when the buffer is empty; returns
`MetricsSnapshot(request_count, p50_ms, p95_ms, classify_count, review_count, last_drift)`. `abstention_rate` is the
domain property of `MetricsSnapshot`.

`ReferenceDriftDetector.__init__(reference, vocabulary)`, each failure →
`ModelIntegrityError("reference stats are invalid")`:
1. `reference["length_edges"]` is a `list` of 9 `int` (not `bool`), non-decreasing.
2. `reference["length_shares"]` is a `list` of 10 `int` or `float` (not `bool`), each in `(0.0, 1.0]`, with
   `abs(sum - 1.0) <= 1e-6`.
3. `reference["reference_oov_rate"]` is an `int` or `float` (not `bool`) in `[0.0, 1.0]`.
4. A missing key is a failure. `class_shares` and other keys are ignored. `vocabulary` is stored as given.

`compare(texts, body_sha256, created_at)`:
1. `len(texts)` outside `1..5000` → `InvalidInputError("texts must hold 1 to 5000 items")`.
2. `length_psi = _length_psi(texts)`: bin of a text = `bisect.bisect_right(edges, len(text))` (0..9);
   `a_i = max(count_i / len(texts), 1e-4)`; `e_i = shares[i]`; `length_psi = Σ_{i=0..9} (a_i - e_i) · ln(a_i / e_i)`.
3. `oov_rate = _oov_rate(texts)`: tokens = `TOKEN_PATTERN.findall(text.lower())` over every text;
   `oov_rate = (tokens not in vocabulary) / (all tokens)`; `0.0` when there are no tokens.
4. `drifted = length_psi > 0.25 or oov_rate > reference_oov_rate + 0.10`.
5. Returns `DriftReport(body_sha256=body_sha256, row_count=len(texts), length_psi=length_psi, oov_rate=oov_rate,
   reference_oov_rate=reference_oov_rate, drifted=drifted, created_at=created_at)`; the entity raises
   `InvalidInputError` for a `body_sha256` that is not 64 lowercase hex or a `created_at` not ending in `Z`.
6. Logs at `INFO`: `"drift_compared rows=%d length_psi=%.6f oov_rate=%.6f drifted=%s"`.

Statistic choice: PSI on character-length bins (thresholds: > 0.25 is a major shift, the standard PSI band) and an
OOV margin of 0.10 over the reference rate; no Kolmogorov-Smirnov test is computed. The module never opens, writes
or serializes anything (SEC-03); the composition root (spec 024) reads `reference_stats.json` with `json` and passes
the mapping.

## Edge cases and error handling

| Input | Result |
|---|---|
| `record("/predict", -1.0, [])`, `float("nan")`, `float("inf")` | `InvalidInputError("latency must be a finite non-negative number")`, counters unchanged |
| `record("/predict", 5.0, [])` | `request_count + 1`, decision counters unchanged |
| 1001 records | buffer keeps the last 1000; `request_count` 1001 |
| `snapshot()` before any record | `request_count 0`, `p50_ms None`, `p95_ms None`, `last_drift None`, `abstention_rate None` |
| 8 threads × 1000 `record` calls | `request_count 8000`, no lost update |
| reference without `length_edges`, with 8 edges, decreasing edges, a share `0.0`, shares summing to 0.9, `True` as a value, OOV rate 1.5 | `ModelIntegrityError("reference stats are invalid")` |
| `compare([], ...)` or 5001 texts | `InvalidInputError("texts must hold 1 to 5000 items")` |
| texts with no token (`["a b"]`) | `oov_rate 0.0` |
| `body_sha256 "XYZ"` | `InvalidInputError` from `DriftReport` |

Log lines never hold comment text (SEC-05). If an existing test not listed in this spec fails because of this
change, the implementer does not modify it: they report its name and the reason.

## Acceptance tests (prose)

Reference fixture `uniform`: `{"length_edges": [10, 20, 30, 40, 50, 60, 70, 80, 90], "length_shares": [0.1] * 10,
"reference_oov_rate": 0.2, "class_shares": [0.33, 0.42, 0.25]}`. `SHA = "a" * 64`, `NOW = "2026-11-10T12:00:00Z"`.
Floats compare with `abs` difference ≤ 1e-6. Values computed with Python 3.12.

`tests/unit/adapters/test_monitoring_metrics.py`:

1. `test_nearest_rank_vectors`: `[1.0 .. 20.0]` → p50 `10.0`, p95 `19.0`; `[10.0, 20.0, 30.0]` → p50 `20.0`, p95
   `30.0`; `[7.0]` → `7.0` for both.
2. `test_metrics_snapshot_empty`: new store → `MetricsSnapshot(0, None, None, 0, 0, None)`.
3. `test_metrics_counts_decisions`: `record("/predict-batch", 12.5, [CLASSIFY] * 7 + [REVIEW] * 3)` →
   `classify_count 7`, `review_count 3`, `abstention_rate 0.3`, `request_count 1`, p50 and p95 `12.5`.
4. `test_metrics_buffer_keeps_last_1000`: latencies `1.0 .. 1001.0` → `request_count 1001`, p50 `501.0`, p95
   `951.0`.
5. `test_metrics_rejects_invalid_latency`: `-1.0`, `nan`, `inf` → `InvalidInputError`; snapshot unchanged.
6. `test_metrics_record_is_thread_safe`: 8 `threading.Thread`, each 1000 × `record("/predict", 1.0, [CLASSIFY])` →
   `request_count 8000`, `classify_count 8000`.
7. `test_metrics_record_drift_replaces_last`: two reports recorded → `last_drift` is the second.
8. `test_metrics_logs_without_text`: `caplog` at `DEBUG` after `record("/predict", 3.0, [REVIEW])` holds
   `"metrics_recorded route=/predict latency_ms=3.0 decisions=1"`.

`tests/unit/adapters/test_monitoring_drift.py`:

9. `test_drift_contract_vector`: texts = 3 × `"a" * 5` plus `"b" * L` for `L` in 15, 25, 35, 45, 55, 65, 75 (bin
   shares `0.3, 0.1 × 7, 0, 0`), vocabulary `frozenset()` → `length_psi 1.599892`, `drifted True`, `row_count 10`.
10. `test_drift_one_text_per_bin_has_zero_psi`: `"c" * L` for `L` in 5, 15, …, 95 (10 texts), vocabulary
    `frozenset({"c" * L for those L})` → `length_psi 0.0`, `oov_rate 0.0`, `drifted False`.
11. `test_drift_bin_edges_use_bisect_right`: texts `"d" * 9`, `"d" * 10`, `"d" * 90` (bin counts 1 in bins 0, 1
    and 9) → `length_psi 5.673374`.
12. `test_drift_single_bin_batch`: 4 × `"x" * 50` → `length_psi 8.283089`, `drifted True`.
13. `test_drift_oov_rate_and_margin`: reference `length_shares [0.0001, 0.9991] + [0.0001] * 8`,
    `reference_oov_rate 0.4`, vocabulary `{"curso", "claro", "profesor"}`, texts `["El curso fue claro",
    "profesor nuevo"]` (lengths 18 and 14, both bin 1) → `oov_rate 0.5`, `length_psi` 8.103647e-07 (abs difference ≤ 1e-12),
    `drifted False` (`0.5 > 0.4 + 0.10` is false); with `reference_oov_rate 0.39` → `drifted True`.
14. `test_drift_no_tokens_gives_zero_oov`: `["a b"]` → `oov_rate 0.0`.
15. `test_drift_rejects_invalid_reference`: each invalid reference of the edge-case table →
    `ModelIntegrityError`.
16. `test_drift_rejects_invalid_texts_count`: `[]` and 5001 texts → `InvalidInputError`.
17. `test_drift_rejects_invalid_sha`: `body_sha256 "XYZ"` → `InvalidInputError`.
18. `test_drift_report_fields`: test 9 report has `body_sha256 SHA`, `created_at NOW`, `reference_oov_rate 0.2`.

## Out of scope

- Reading `reference_stats.json` and building the vocabulary from `topic_vectorizer.vocabulary_` (spec 024), the
  routes `/metrics` and `/drift` (spec 024), computing reference statistics at training time (spec 013).
- Persistence, per-route metrics, time windows, alerting.

## Definition of Done

- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed`.
- [ ] `grep -nE "noqa|type: ignore" api/adapters/monitoring.py tests/unit/adapters/test_monitoring_metrics.py tests/unit/adapters/test_monitoring_drift.py`
      → no output.
- [ ] `grep -nE "open\(|\.write|json\.dump|joblib|pickle|pathlib|sqlite" api/adapters/monitoring.py` → no output
      (SEC-03).
- [ ] `.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing` → row
      `api/adapters/monitoring.py` ≥ 80 %.
- [ ] `bash scripts/gate.sh` → last line `GATE OK`, exit code 0.
