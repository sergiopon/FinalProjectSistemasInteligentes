# 019 - Adapters text: anonymizer, summarizer and topics
Riesgo: alto

## Objective

SEC-02 requires every comment text returned in batch rows, quotes, summaries and course reports to pass through the
`Anonymizer` port, and the API to refuse to start when the anonymizer cannot load. The course report
(`docs/contracts.md` §5) also needs a `Summarizer` and a `TopicModel`. No adapter implements these ports. This spec
creates `SpacyAnonymizer` (`api/adapters/anonymizer.py`), which reuses `mask_contact_data` from
`api/domain/safety.py` and masks spaCy `PER` entities, plus `CentroidSummarizer` and `KMeansTopicModel`
(`api/adapters/text_analysis.py`) over the bundle keys `topic_vectorizer`, `topic_kmeans` and `topic_terms`
(contract §9.1). Measured limitation of `es_core_news_sm` 3.8.0 (pins of `CONTEXT.md`): in
`"La profesora María Fernanda López respondió tarde los correos."` the name is labeled `MISC`, so it stays unmasked.

## Depends on

001 (`scripts/security_grep.sh`, `tests/architecture`, used by the Definition of Done); 003 (domain safety helpers);
006 (ports).

## Governing files

- `ARCHITECTURE.md` §2, §4, §6 (≤ 20 statements per function, ≤ 300 lines per module, `mypy --strict`, `raise ...
  from e`, no mutable global state).
- `security-rules.md` SEC-02 (masks and startup failure), SEC-05 (no comment text in logs), SEC-16 (spaCy loads from
  the installed package, no network), SEC-17 (model from the pinned URL in `requirements.txt`), SEC-21.
- `docs/contracts.md` §2 (`AnonymizerUnavailableError`, `InferenceError`, `InvalidInputError`,
  `ModelIntegrityError`), §3, §4.4, §9.1.

## Files to create/modify

1. `api/adapters/anonymizer.py` (new). Reference pattern: `api/adapters/model_store.py` (spec 017).
2. `api/adapters/text_analysis.py` (new). Same reference pattern.
3. `tests/unit/adapters/test_anonymizer.py` (new).
4. `tests/unit/adapters/test_text_analysis.py` (new).

No existing test changes expectation.

## External dependencies

None new (spacy `==3.8.18`, `es_core_news_sm` 3.8.0, scikit-learn `==1.9.1`, numpy `==2.5.4` from `CONTEXT.md`).

## Interfaces and types

Module `api/adapters/anonymizer.py`:

- Constants: `DEFAULT_MODEL: str = "es_core_news_sm"`, `PERSON_LABEL: str = "PER"`, `PERSON_MASK: str = "[PERSON]"`,
  `EXCLUDED_PIPES: tuple[str, ...] = ("parser", "lemmatizer", "morphologizer", "attribute_ruler")`.
- `class SpacyAnonymizer` (implements `Anonymizer`):
  - `__init__(self, model_name: str = DEFAULT_MODEL) -> None`; attributes `_nlp: spacy.language.Language`,
    `_lock: threading.Lock`.
  - `mask(self, text: str) -> str`

Module `api/adapters/text_analysis.py`:

- Constants: `SENTENCE_SPLIT: re.Pattern[str] = re.compile(r"[.!?]+(?=\s|$)")`, `MAX_TEXTS: int = 5000`,
  `MIN_K: int = 1`, `MAX_K: int = 10`, `TERMS_PER_TOPIC: int = 5`.
- `class CentroidSummarizer` (implements `Summarizer`): `__init__(self, vectorizer: object) -> None`;
  `summarize(self, texts: Sequence[str], k: int) -> tuple[str, ...]`.
- `class KMeansTopicModel` (implements `TopicModel`): `__init__(self, vectorizer: object, kmeans: object, terms:
  tuple[tuple[str, ...], ...]) -> None`; `assign(self, texts: Sequence[str]) -> tuple[int, ...]`;
  `terms(self, topic: int) -> tuple[str, ...]`.
- Private module functions (each ≤ 20 statements): `_check_texts(texts: Sequence[str]) -> None`;
  `_check_vectorizer(vectorizer: object) -> None` (raises `ModelIntegrityError("topic vectorizer is invalid")`, used by
  both classes); `_split_sentences(texts: Sequence[str]) -> tuple[str, ...]` (step 2 of `summarize`);
  `_centroid_cosines(vectorizer: object, sentences: Sequence[str]) -> tuple[float, ...]` (step 4 of `summarize`,
  including the `InferenceError("summarizer failed")` wrapping); `_check_terms(terms: tuple[tuple[str, ...], ...],
  n_clusters: int) -> None` (step 3 of `KMeansTopicModel.__init__`).

Narrowing: `isinstance(vectorizer, sklearn.feature_extraction.text.TfidfVectorizer)` and
`isinstance(kmeans, sklearn.cluster.KMeans)`. Untyped imports follow the mypy configuration of `pyproject.toml`
(spec 000); this spec adds no `# type: ignore` and no `# noqa`. Google-style docstrings on every public item.

## Expected behavior

`SpacyAnonymizer.__init__(model_name)`:
1. `self._nlp = spacy.load(model_name, exclude=EXCLUDED_PIPES)`; `OSError`, `ImportError` or `ValueError` →
   `AnonymizerUnavailableError("spaCy model failed to load")` raised `from` the cause.
2. `"ner" not in self._nlp.pipe_names` → `AnonymizerUnavailableError("spaCy model has no ner component")`.
3. Creates `self._lock = threading.Lock()`.

`SpacyAnonymizer.mask(text)`:
1. `masked = mask_contact_data(text)` (`api/domain/safety.py`, contract §4.4: email → `"[EMAIL]"`, phone →
   `"[PHONE]"`, id → `"[ID]"`).
2. Under `self._lock`: `doc = self._nlp(masked)`; `ValueError` → `AnonymizerUnavailableError("anonymizer failed")`
   raised `from` the cause.
3. Every entity of `doc.ents` with `label_ == "PER"` is replaced in `masked` by `"[PERSON]"`, using
   `start_char`/`end_char`, from the last entity to the first. Other labels are kept.
4. Returns the result; a text with no match is returned unchanged (`""` → `""`).

`CentroidSummarizer.__init__(vectorizer)`: not a `TfidfVectorizer`, or no attribute `vocabulary_` (unfitted) →
`ModelIntegrityError("topic vectorizer is invalid")`.

`CentroidSummarizer.summarize(texts, k)`:
1. `_check_texts(texts)`; `k` outside `1..10` → `InvalidInputError("k must be between 1 and 10")`.
2. Sentences: for each text in order, split with `SENTENCE_SPLIT`, strip each piece, drop `""` pieces and pieces
   whose exact string (case-sensitive, after strip) equals an earlier piece (first occurrence kept).
3. No sentence left → `()`.
4. `V = vectorizer.transform(sentences)`; `m` = mean of the rows of `V`. `cos_i = (V_i · m) / (‖V_i‖ · ‖m‖)`,
   `0.0` when `‖V_i‖` or `‖m‖` is `0.0`. `ValueError` or `AttributeError` from the library →
   `InferenceError("summarizer failed")` raised `from` the cause.
5. Sort by `cos_i` descending, tie → lower sentence index; return the first `k` sentences as `tuple[str, ...]`.

`KMeansTopicModel.__init__(vectorizer, kmeans, terms)`:
1. Vectorizer check as above → `ModelIntegrityError("topic vectorizer is invalid")`.
2. `kmeans` not a `KMeans` or without attribute `cluster_centers_` → `ModelIntegrityError("topic kmeans is
   invalid")`.
3. `len(terms) != kmeans.n_clusters`, or any tuple with length other than 5, or any term `""` →
   `ModelIntegrityError("topic terms are invalid")`.

`KMeansTopicModel.assign(texts)`: `_check_texts(texts)`; `labels = kmeans.predict(vectorizer.transform(list(texts)))`
(`ValueError` → `InferenceError("topic assignment failed")` from the cause); returns `tuple(int(v) for v in
labels)`.

`KMeansTopicModel.terms(topic)`: `0 <= topic < len(terms)` → `terms[topic]`; otherwise
`InvalidInputError("unknown topic id")`.

`_check_texts(texts)`: `len(texts)` outside `1..5000` → `InvalidInputError("texts must hold 1 to 5000 items")`; a
text with `t.strip() == ""` → `InvalidInputError("texts must be non-empty after strip")`.

No module logs comment text; both modules log nothing.

## Edge cases and error handling

| Input | Result |
|---|---|
| `SpacyAnonymizer("xx_missing_model")` | `AnonymizerUnavailableError("spaCy model failed to load")`, cause `OSError` (spaCy `[E050]`) |
| `spacy.load` returns a pipeline without `ner` | `AnonymizerUnavailableError("spaCy model has no ner component")` |
| `mask("")` | `""` |
| `[EMAIL]` labeled `ORG`, `[PHONE]` labeled `MISC` by spaCy (measured) | kept, only `PER` is replaced |
| `summarize` with `k` 0 or 11 | `InvalidInputError("k must be between 1 and 10")` |
| `summarize(["!!!"], 1)` | `()` |
| every sentence without known words | cosine `0.0` for all, order of appearance |
| unfitted `TfidfVectorizer` | `ModelIntegrityError("topic vectorizer is invalid")` |
| 4 term tuples for a 3-cluster `KMeans`, or a tuple of 4 terms | `ModelIntegrityError("topic terms are invalid")` |
| `terms(-1)` or `terms(3)` with 3 topics | `InvalidInputError("unknown topic id")` |
| `texts == []`, 5001 texts, or a blank text | `InvalidInputError` with the `_check_texts` messages |

The composition root (spec 024) builds `SpacyAnonymizer()` before serving; the `AnonymizerUnavailableError` it
raises stops startup (SEC-02, contract §2). If an existing test not listed in this spec fails because of this change,
the implementer does not modify it: they report its name and the reason.

## Acceptance tests (prose)

`tests/unit/adapters/test_anonymizer.py` uses the real installed `es_core_news_sm` (pip package, no network); one
module-scoped pytest fixture builds `SpacyAnonymizer()` once. Outputs below were measured with the pins of
`CONTEXT.md`.

1. `test_anonymizer_masks_contact_data`: `"Escribir a ana.gomez@uni.edu.co o al 300 123 4567, código 20231045"` →
   `"Escribir a [EMAIL] o al [PHONE], código [ID]"`.
2. `test_anonymizer_masks_person`: `"El profesor Juan Pérez explica muy bien."` →
   `"El profesor [PERSON] explica muy bien."`.
3. `test_anonymizer_masks_person_and_email`: `"Le escribí a Carlos Ramírez a carlos.ramirez@correo.com y no
   contestó."` → `"Le escribí a [PERSON] a [EMAIL] y no contestó."`.
4. `test_anonymizer_masks_two_people`: `"Juan Pérez y Ana Gómez llegaron tarde."` →
   `"[PERSON] y [PERSON] llegaron tarde."`.
5. `test_anonymizer_masks_ids_without_separators`: `"Mi código es 1234567 y mi celular es 3001234567."` →
   `"Mi código es [ID] y mi celular es [ID]."`.
6. `test_anonymizer_keeps_text_without_matches`: `"El contenido fue claro, pero los parciales fueron difíciles."` →
   the same string.
7. `test_anonymizer_empty_text`: `""` → `""`.
8. `test_anonymizer_missing_model_fails`: `SpacyAnonymizer("xx_missing_model")` → `AnonymizerUnavailableError` whose
   `__cause__` is an `OSError`.
9. `test_anonymizer_without_ner_fails`: pytest `monkeypatch` replaces `spacy.load` with a function returning
   `spacy.blank("es")` → `AnonymizerUnavailableError` with detail `"spaCy model has no ner component"`.

`tests/unit/adapters/test_text_analysis.py` fixture: `corpus = ["el profesor explica claro", "el profesor explica
bien", "los parciales fueron difíciles", "los parciales fueron largos", "el horario fue cómodo", "el horario fue
tarde"]`; `vectorizer = TfidfVectorizer().fit(corpus)`; `kmeans = KMeans(n_clusters=3, n_init=10,
random_state=42).fit(vectorizer.transform(corpus))` (measured `labels_` = `[2, 2, 0, 0, 1, 1]`); `terms` = 3 tuples of
5 non-empty strings.

10. `test_summarizer_ranks_by_centroid_cosine`: texts `["El profesor explica claro. Los parciales fueron
    difíciles!", "El profesor explica claro y bien. El horario fue cómodo."]`, `k=3` → `("El profesor explica
    claro", "El profesor explica claro y bien", "El horario fue cómodo")` (cosines 0.797544, 0.789893, 0.499105;
    `"Los parciales fueron difíciles"` 0.401864).
11. `test_summarizer_unknown_words_keep_order`: `["zzz qqq. www."]`, `k=2` → `("zzz qqq", "www")`.
12. `test_summarizer_drops_duplicates`: `["El horario fue cómodo", "El horario fue cómodo... ¿Por qué?"]`, `k=5` →
    `("El horario fue cómodo", "¿Por qué")`.
13. `test_summarizer_punctuation_only_returns_empty`: `["!!!"]`, `k=1` → `()`.
14. `test_summarizer_rejects_k_out_of_range`: `k=0` and `k=11` → `InvalidInputError`.
15. `test_summarizer_rejects_invalid_texts`: `[]`, 5001 texts `"a b"`, and `["ok", "  "]` → `InvalidInputError`.
16. `test_summarizer_rejects_unfitted_vectorizer`: `TfidfVectorizer()` and `"x"` → `ModelIntegrityError`.
17. `test_topics_assign_matches_training_labels`: `["el profesor explica", "el horario fue cómodo"]` → `(2, 1)`,
    each a Python `int`.
18. `test_topics_terms_returns_tuple`: `terms(0)` → `terms[0]`; `terms(3)` and `terms(-1)` → `InvalidInputError`.
19. `test_topics_rejects_invalid_terms`: 4 tuples, and 3 tuples where one has 4 terms → `ModelIntegrityError`;
    `kmeans="x"` → `ModelIntegrityError`.
20. `test_topics_assign_rejects_empty_sequence`: `[]` → `InvalidInputError`.

## Out of scope

- `mask_contact_data` and its patterns (spec 003), fitting topics (spec 012), course report assembly (spec 023),
  startup exit handling (spec 024).
- Improving person recall beyond the `PER` label of `es_core_news_sm` (see Objective), batching with `nlp.pipe`,
  Unicode normalization of inputs.

## Definition of Done

- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed`.
- [ ] `grep -nE "noqa|type: ignore" api/adapters/anonymizer.py api/adapters/text_analysis.py tests/unit/adapters/test_anonymizer.py tests/unit/adapters/test_text_analysis.py`
      → no output.
- [ ] `grep -n "mask_contact_data" api/adapters/anonymizer.py` → exactly 2 matching lines (one import line from
      `api.domain.safety` and one call; the name MUST NOT appear in docstrings or comments); `grep -nE "EMAIL_PATTERN|PHONE_PATTERN|ID_PATTERN|re\.compile" api/adapters/anonymizer.py` → no output
      (patterns are reused, not copied).
- [ ] `grep -nE "logging|print\(" api/adapters/anonymizer.py api/adapters/text_analysis.py` → no output (SEC-05; the words
      `logging` and `print(` MUST NOT appear in docstrings or comments of those two files).
- [ ] `.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing` → rows
      `api/adapters/anonymizer.py` and `api/adapters/text_analysis.py` each ≥ 80 %.
- [ ] `bash scripts/gate.sh` → last line `GATE OK`, exit code 0.
