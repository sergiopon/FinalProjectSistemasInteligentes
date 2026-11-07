# 006 - Ports
Riesgo: alto

## Objective

Use cases MUST depend on abstractions, not on scikit-learn, MAPIE, spaCy or joblib (`ARCHITECTURE.md` §2 rule 2,
§4). No port exists yet. This spec creates the 9 ports of `docs/contracts.md` §3 as `typing.Protocol` classes in
three modules of `api/ports/`, each method documented with **Preconditions**, **Postconditions** and **Raises**.
After this spec, adapters (specs 017 to 020) implement these Protocols and use cases (specs 022 and 023) receive
them through their constructors. The ports hold no behavior; the tests are structural.

## Depends on

001 (`scripts/gate.sh`, `scripts/security_grep.sh`, `tests/architecture/`); 002 (`api/domain/entities.py`,
`api/domain/reports.py`, `api/domain/errors.py`).

## Governing files

- `ARCHITECTURE.md` §2 (ports import only `api.domain` and the standard library; rules 2 and 3), §4 (port list),
  §6 (port names end in their role; Google-style docstrings; ports document Preconditions, Postconditions and
  Raises; `mypy --strict`; `from __future__ import annotations`; modules ≤ 300 lines; absolute imports).
- `docs/contracts.md` §1 (entity names), §2 (error names), §3 (binding: files, methods, signatures, postconditions,
  raises, "not `runtime_checkable`"), §4.4 and §4.5 (referenced by `Anonymizer` and `DriftDetector`), §9.1.
- `security-rules.md` SEC-02 (the `Anonymizer` port masks persons, emails, phones and ids).

## Files to create/modify

1. `api/ports/models.py` (new): `ModelStore`, `PolarityModel`, `AspectModel`, `Explainer`.
2. `api/ports/text.py` (new): `Anonymizer`, `Summarizer`, `TopicModel`.
3. `api/ports/monitoring.py` (new): `DriftDetector`, `MetricsStore`.
4. `tests/unit/ports/test_ports_structure.py` (new): tests 1 to 4 of "Acceptance tests", `PORTS`, the method map and
   the signature table.
5. `tests/unit/ports/test_ports_fakes.py` (new): tests 5 to 7 and the 9 fakes. Two files keep each one under 300
   lines (spec 001, `test_size_limits`).

Pattern reference: no module exists yet in `api/ports/`; module header and docstring layout follow
`api/domain/entities.py` (spec 002); test layout follows `tests/unit/domain/test_entities.py` (spec 002). No
`__init__.py` is created (namespace packages, `CONTEXT.md` Structure). No existing test changes expectation.

## External dependencies

None new. Standard library: `typing.Protocol`, `collections.abc.Mapping`, `collections.abc.Sequence`, `inspect`
(tests only).

## Interfaces and types

Every module starts with a module docstring, then `from __future__ import annotations`, then module-level imports:

- `models.py`: `from collections.abc import Mapping, Sequence`; `from typing import Protocol`; from
  `api.domain.entities`: `AspectScores`, `ClassProbabilities`, `ConformalSet`, `WordInfluence`; from
  `api.domain.reports`: `ModelInfo`.
- `text.py`: `from collections.abc import Sequence`; `from typing import Protocol`.
- `monitoring.py`: `from collections.abc import Sequence`; `from typing import Protocol`; from
  `api.domain.entities`: `Decision`; from `api.domain.reports`: `DriftReport`, `MetricsSnapshot`.

Each port is `class <Name>(Protocol):` with a one-line class docstring (the responsibility of `ARCHITECTURE.md` §4)
and exactly the methods below, in this order. No decorator, no attribute, no `__init__`, no default argument. Each
method body is its docstring followed by `...`. `str(inspect.signature(Port.method))` MUST equal the string shown:

| Port | Method | `inspect.signature` string |
|---|---|---|
| `ModelStore` | `info` | `(self) -> 'ModelInfo'` |
| `ModelStore` | `bundle` | `(self) -> 'Mapping[str, object]'` |
| `PolarityModel` | `predict_proba` | `(self, texts: 'Sequence[str]') -> 'tuple[ClassProbabilities, ...]'` |
| `PolarityModel` | `predict_set` | `(self, texts: 'Sequence[str]') -> 'tuple[ConformalSet, ...]'` |
| `AspectModel` | `detect` | `(self, texts: 'Sequence[str]') -> 'tuple[AspectScores, ...]'` |
| `Explainer` | `explain` | `(self, text: 'str', top_k: 'int') -> 'tuple[WordInfluence, ...]'` |
| `Anonymizer` | `mask` | `(self, text: 'str') -> 'str'` |
| `Summarizer` | `summarize` | `(self, texts: 'Sequence[str]', k: 'int') -> 'tuple[str, ...]'` |
| `TopicModel` | `assign` | `(self, texts: 'Sequence[str]') -> 'tuple[int, ...]'` |
| `TopicModel` | `terms` | `(self, topic: 'int') -> 'tuple[str, ...]'` |
| `DriftDetector` | `compare` | `(self, texts: 'Sequence[str]', body_sha256: 'str', created_at: 'str') -> 'DriftReport'` |
| `MetricsStore` | `record` | `(self, route: 'str', latency_ms: 'float', decisions: 'Sequence[Decision]') -> 'None'` |
| `MetricsStore` | `record_drift` | `(self, report: 'DriftReport') -> 'None'` |
| `MetricsStore` | `snapshot` | `(self) -> 'MetricsSnapshot'` |

(Strings verified with CPython 3.12.14 and `from __future__ import annotations`.)

## Expected behavior

1. Each method docstring is Google style: a one-line summary, a blank line, then the sections `Preconditions:`,
   `Postconditions:` and `Raises:` in this order, each with the indented text below. `TEXTS` stands for the
   sentence "`texts` holds 1 to 5000 items and every item is non-empty after `strip()`." Text rule: a cell holds one or
   more sentences separated by one space; a `;` inside a cell ends a sentence, and each part is written as its own
   sentence starting with a capital letter and ending with a period; a line longer than 100 characters is broken at
   the last space before column 100 and continues with the same indentation. Final text of the two mixed cells:
   `summarize` Preconditions "`texts` holds 1 to 5000 items and every item is non-empty after `strip()`. `k` is in
   1..10."; `compare` Preconditions "`texts` holds 1 to 5000 items and every item is non-empty after `strip()`.
   `body_sha256` is 64 lowercase hex characters. `created_at` is ISO 8601 UTC ending in `Z`."
2. Section texts:

| Method | Preconditions | Postconditions | Raises |
|---|---|---|---|
| `info` | None. | The `ModelInfo` of the active version, already verified. | `ModelUnavailableError`: no verified active version. |
| `bundle` | None. | The verified bundle dictionary with the keys of docs/contracts.md §9.1. | `ModelUnavailableError`: no verified active version. |
| `predict_proba` | TEXTS | One `ClassProbabilities` per text, same length and order as `texts`. | `InferenceError`: the model fails. |
| `predict_set` | TEXTS | One `ConformalSet` per text, same length and order; `confidence_level` equals the manifest value. | `InferenceError`: the model fails. |
| `detect` | TEXTS | One `AspectScores` per text, same order; `present` holds the groups whose score is >= the bundle threshold of that group. | `InferenceError`: the model fails. |
| `explain` | `text` is non-empty after `strip()`; `top_k` is in 1..20. | At most `top_k` items sorted by `abs(delta)` descending, then `word` ascending. | `InferenceError`: the model fails. |
| `mask` | `text` is a `str`. | Emails, phones, ids and person entities masked as in docs/contracts.md §4.4; a text without matches is returned unchanged. | `AnonymizerUnavailableError`: the language model is not loaded. |
| `summarize` | TEXTS; `k` is in 1..10. | At most `k` distinct sentences taken from `texts`, most representative first. | `InferenceError`: the vectorizer fails. |
| `assign` | TEXTS | One topic id in `0..n_topics-1` per text, same order. | `InferenceError`: the model fails. |
| `terms` | `topic` is an `int`. | The 5 terms of the trained topic. | `InvalidInputError`: `topic` is not a trained topic id. |
| `compare` | TEXTS; `body_sha256` is 64 lowercase hex characters; `created_at` is ISO 8601 UTC ending in `Z`. | A `DriftReport` for `texts` computed as in docs/contracts.md §4.5. | `InvalidInputError`: an argument violates a precondition. |
| `record` | `route` is `"/predict"` or `"/predict-batch"`; `latency_ms` is finite and >= 0.0. | Latency and decisions stored; thread-safe; the buffer keeps the last 1000 latencies. | No exception. |
| `record_drift` | `report` is a valid `DriftReport`. | `report` replaces the last drift report; thread-safe. | No exception. |
| `snapshot` | None. | Percentiles by nearest rank over the latency buffer; `p50_ms` and `p95_ms` are `None` when it is empty. | No exception. |

3. Docstring layout, applied to every method (indentation 4 spaces per level, every line ≤ 100 characters; the
   module docstring and class docstring are one line each, between triple quotes on one line; a section text
   longer than the limit wraps onto a second line with the same indentation):

   ```
   """<summary ending in a period>

   Preconditions:
       <text>

   Postconditions:
       <text>

   Raises:
       <text>
   """
   ```

   Exact one-line texts (all end in a period):

| Item | Docstring |
|---|---|
| module `models.py` | `Ports for the trained models: store, polarity, aspects and explainer.` |
| module `text.py` | `Ports for text processing: anonymizer, summarizer and topic model.` |
| module `monitoring.py` | `Ports for monitoring: drift detection and metrics.` |
| `ModelStore` | `Gives access to the verified active model bundle.` |
| `PolarityModel` | `Predicts polarity probabilities and conformal prediction sets.` |
| `AspectModel` | `Detects the aspect groups mentioned in a text.` |
| `Explainer` | `Explains a polarity prediction with word influences.` |
| `Anonymizer` | `Masks personal data in a text.` |
| `Summarizer` | `Picks the most representative sentences of a set of texts.` |
| `TopicModel` | `Assigns texts to topics and names the topics.` |
| `DriftDetector` | `Compares an upload with the training reference.` |
| `MetricsStore` | `Keeps request latency, decision counts and the last drift report.` |
| `info` | `Return the metadata of the active model.` |
| `bundle` | `Return the verified bundle dictionary.` |
| `predict_proba` | `Return class probabilities for each text.` |
| `predict_set` | `Return the conformal set for each text.` |
| `detect` | `Return aspect scores for each text.` |
| `explain` | `Return the most influential words of a text.` |
| `mask` | `Return the text with personal data masked.` |
| `summarize` | `Return up to k representative sentences.` |
| `assign` | `Return the topic id of each text.` |
| `terms` | `Return the terms that describe a topic.` |
| `compare` | `Compare an upload with the training reference.` |
| `record` | `Record the latency and decisions of one request.` |
| `record_drift` | `Replace the last drift report.` |
| `snapshot` | `Return the current metrics.` |

4. Module and class docstrings do not contain the strings `Preconditions:`, `Postconditions:`, `Raises:` or
   `runtime_checkable`.
5. The ports import nothing from `api.adapters`, `api.application`, `api.main` or `ml`, and define no function,
   constant or class other than the 9 ports.

## Edge cases and error handling

| Case | Result |
|---|---|
| `isinstance(object(), <any port>)` | `TypeError` whose message contains `"runtime_checkable"` (Protocol is not runtime checkable) |
| A fake whose method signature differs from the port | Not committed. Verified once by hand with a throwaway fake in `/tmp/bad_polarity.py` (outside the repository): `class BadPolarity` with `def predict_proba(self, texts: list[str]) -> tuple[ClassProbabilities, ...]` and `def predict_set(self, texts: Sequence[str]) -> tuple[ConformalSet, ...]`, used as `model: PolarityModel = BadPolarity()`. Command `MYPYPATH=. .venv/bin/mypy --strict /tmp/bad_polarity.py` prints a line containing `Incompatible types in assignment (expression has type "BadPolarity", variable has type "PolarityModel")`; the implementer copies that line into the report, not into the repository |
| A port gains a method not listed in the table | `test_port_exposes_exactly_contract_methods` fails |

The ports raise nothing themselves: Preconditions are enforced by callers and adapters, not by the Protocols. If a
test not listed in this spec fails because of this change, the implementer does not modify it: the implementer
reports its name and the reason.

## Acceptance tests (prose)

Tests 1 to 4 live in `tests/unit/ports/test_ports_structure.py`; tests 5 to 7 in `tests/unit/ports/test_ports_fakes.py`.
A module constant `PORTS: tuple[type, ...]` in the first file lists the 9 ports in the order of `docs/contracts.md`
§3; a module constant maps each port to its expected method names. Each fake method repeats the parameter names,
parameter types and return type of its row in the signature table (`texts`, `k`, `top_k`, `topic`, `body_sha256`,
`created_at`, `route`, `latency_ms`, `decisions`, `report`) without default values.
The fake instances are named `store`, `polarity`, `aspects`, `explainer`, `anonymizer`, `summarizer`, `topics` and `detector`, each annotated with its port; test 7 also uses `store: MetricsStore`.

1. `test_port_is_not_runtime_checkable`: parametrized over the 9 ports; `isinstance(object(), port)` raises
   `TypeError` matching `"runtime_checkable"`.
2. `test_port_exposes_exactly_contract_methods`: parametrized over the 9 ports; the set of names in `vars(port)`
   whose value is a function (`inspect.isfunction`) and whose name does not start with `_` equals the methods of
   the table (`ModelStore` → `{"info", "bundle"}`, `PolarityModel` → `{"predict_proba", "predict_set"}`,
   `AspectModel` → `{"detect"}`, `Explainer` → `{"explain"}`, `Anonymizer` → `{"mask"}`, `Summarizer` →
   `{"summarize"}`, `TopicModel` → `{"assign", "terms"}`, `DriftDetector` → `{"compare"}`, `MetricsStore` →
   `{"record", "record_drift", "snapshot"}`).
3. `test_port_method_signature`: parametrized over the 14 rows of the signature table; `str(inspect.signature(
   getattr(port, method)))` equals the string of the row.
4. `test_port_method_documents_contract`: parametrized over the 14 methods; `inspect.getdoc` of the method contains
   `"Preconditions:"`, `"Postconditions:"` and `"Raises:"`, at increasing positions.
5. `test_model_port_fakes_conform`: fakes, defined in the test module with full annotations and no base class:
   `FakeModelStore.info` returns `ModelInfo("v001", "2026-11-10T12:00:00Z", "0" * 64, "logistic_regression",
   "tfidf", 0.9, 0.61, 0.9)`, `.bundle` returns `{"schema_version": 1}`; `FakePolarityModel.predict_proba` returns
   `ClassProbabilities(0.2, 0.3, 0.5)` per text, `.predict_set` returns `ConformalSet(frozenset({Polarity.POSITIVE}),
   0.9)` per text; `FakeAspectModel.detect` returns `AspectScores((0.0,) * 9, frozenset())` per text;
   `FakeExplainer.explain` returns `(WordInfluence("claro", 0.1),)[:top_k]`. Each fake is assigned to a variable
   annotated with its port (`store: ModelStore = FakeModelStore()`). Assertions: `store.info().version == "v001"`;
   `store.bundle()["schema_version"] == 1`; `len(polarity.predict_proba(["uno", "dos"])) == 2`;
   `polarity.predict_set(["uno"])[0].labels == frozenset({Polarity.POSITIVE})`; `len(aspects.detect(["uno"])) ==
   1`; `explainer.explain("muy claro", 1) == (WordInfluence("claro", 0.1),)`.
6. `test_text_port_fakes_conform`: `FakeAnonymizer.mask` returns `text`; `FakeSummarizer.summarize` returns
   `tuple(texts[:k])`; `FakeTopicModel.assign` returns `(0,) * len(texts)`, `.terms` returns
   `("a", "b", "c", "d", "e")`. Assertions: `mask("Ana") == "Ana"`; `summarize(["a b c", "d e f"], 1) ==
   ("a b c",)`; `assign(["x y", "z w"]) == (0, 0)`; `len(terms(0)) == 5`.
7. `test_monitoring_port_fakes_conform`: `FakeDriftDetector.compare` returns `DriftReport(body_sha256, len(texts),
   0.0, 0.0, 0.0, False, created_at)`; `FakeMetricsStore.record` and `.record_drift` have return type `None`, `.snapshot`
   returns `MetricsSnapshot(0, None, None, 0, 0, None)`. Variables: `store: MetricsStore`, `detector: DriftDetector`, and
   `report = detector.compare(["texto uno"], "0" * 64, "2026-11-10T12:00:00Z")`. Assertions: `report.row_count == 1`; `store.record("/predict", 12.5, [Decision.CLASSIFY])` and `store.record_drift(report)` are called
   as statements and their result is not used or asserted; `snapshot().request_count == 0`.

Conformance of the fakes is proved by `mypy --strict` on `tests/` (the Gate type-check step), not at runtime.

## Out of scope

- Every adapter (specs 017 to 020) and every use case (specs 022 and 023).
- Enforcing preconditions at runtime.
- Shared fakes under `tests/fixtures/` for later specs.
- Any change to `api/domain/` or `docs/contracts.md`.

## Definition of Done

- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/pytest -q tests/unit/ports` → `49 passed` (9 + 9 + 14 + 14 + 3), exit code 0.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`.
- [ ] `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api tests` → `Success: no issues found in N source files` (`ml` holds no module until
      spec 007).
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed`.
- [ ] `.venv/bin/pytest -q -m "not integration" --cov=api --cov-report=term-missing` → the rows of the
      three `api/ports/` modules show ≥ 80 % (method bodies of docstring plus `...` measured 100 % with
      coverage 7.17.2).
- [ ] `grep -rnE "# noqa|# type: ignore" api/ports/ tests/unit/ports/` → no output.
- [ ] `grep -rn "runtime_checkable" api/ports/` → no output.
- [ ] `grep -rnE "^\s*(from|import) (api\.(adapters|application|main)|ml)\b" api/ports/` → no output.
- [ ] `grep -c "Postconditions:" api/ports/models.py api/ports/text.py api/ports/monitoring.py` →
      `api/ports/models.py:6`, `api/ports/text.py:4`, `api/ports/monitoring.py:4`.
- [ ] `find api/ports -name "__init__.py"` → no output.
- [ ] `bash scripts/security_grep.sh` → no output, exit code 0.
- [ ] `bash scripts/gate.sh` is not run in this spec: its `mypy` step needs a module in `ml/` (spec 007, see
      `specs/001` edge cases). Each Gate step runs through the separate commands above.
