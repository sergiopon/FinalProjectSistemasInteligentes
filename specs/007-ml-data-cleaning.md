# 007 - ML data cleaning
Riesgo: alto

## Objective

The three course CSV files (`Dataset/*.csv`, 618 data rows) carry a UTF-8 BOM, repeated header rows (one in each of
files 1 and 2, two in file 3, at raw data positions 0 and 8), 9 raw spellings of 3 polarity classes and 22 aspect
labels that collapse into 9 groups (`docs/contracts.md` §10). Every later `ml` spec (008 to 015, 029) and the
adapter `validate_texts` (spec 018, `ml.data.normalize_text`) assume one clean frame and one text normalization.
When this spec is done, `ml/schemas.py` holds the shared constants and `TypedDict`s of `docs/contracts.md` §8 and
§9, and `ml/data.py` validates input files (SEC-11), hashes the dataset and returns the clean frame of §10.

Measured on 2026-11-07 with pandas 3.1.1 on the real `Dataset/`: rows per file 193, 405, 20; polarity negative 205,
neutral 259, positive 154; aspect rows content 361, assessment 94, feedback 76, methodology_clarity 71, materials
66, organization_schedule 59, platform 48, communication_climate 38, workload_pace 35; 60 rows without aspect; 7
rows with a group repeated with conflicting sentiment; 1 text changed by `normalize_text`
(`feedback_curso_universitario3.csv:5`, it holds `"\n"`); text length 49 to 774 characters, at least 6 words;
`dataset_sha256` `5e3ac133828878229457420245bd2d674fdfe985e5a13632bf97b35bdbf2f666`.

## Depends on

001 (`scripts/gate.sh`, `scripts/security_grep.sh`, `tests/architecture/`), 002 (`api/domain/entities.py`: `Polarity`,
`AspectGroup`, `ASPECT_ORDER`; `api/domain/errors.py`: `DatasetError`, `InvalidInputError`), 003 (index dependency;
`api/domain/safety.py` is not imported here).

## Governing files

- `ARCHITECTURE.md` §2 rule 4 (`ml` imports only `api.domain`, other `ml` modules and third parties), §3 step 1,
  §6 (≤ 20 statements, ≤ 6 arguments, complexity ≤ 8, ≤ 8 branches, modules ≤ 300 lines except `ml/schemas.py`,
  `mypy --strict`, `pathlib.Path`, custom exceptions only, no `print`, no `assert` in production code, no mutable
  global state).
- `security-rules.md` SEC-05 (no comment text or file names in logs), SEC-09 (synthetic unit fixtures; integration
  tests read `Dataset/`), SEC-11 (input file checks), SEC-13 (`json` only).
- `docs/contracts.md` §1.1, §2 (`DatasetError`, CLI exit 2), §8 (`ml.schemas`, `ml.data`), §9, §10.

## Files to create/modify

1. `ml/schemas.py` (new). No `ml` module exists yet; reference pattern for layout: `api/domain/entities.py` (spec 002).
2. `ml/data.py` (new). Same reference pattern. Budget ≤ 300 lines (§6 limit).
3. `tests/unit/ml/test_data.py` (new): schemas, `normalize_text`, `normalize_polarity`, `parse_aspects`.
4. `tests/unit/ml/test_data_files.py` (new): `validate_input_file`, `dataset_files`, `dataset_sha256`, `load_dataset`.
5. `tests/integration/test_data_dataset.py` (new; module-level `pytestmark = pytest.mark.integration`). No existing
   test changes expectation.

## External dependencies

None new (`pandas==3.1.1`, spec 000). Verified at this pin: `pd.read_csv(path, dtype=str, keep_default_na=False,
encoding="utf-8-sig")` strips the BOM from the first header and keeps empty cells as `""`; invalid UTF-8 raises
`UnicodeDecodeError`, a 0-byte file `pandas.errors.EmptyDataError`, an unterminated quote
`pandas.errors.ParserError`. On CPython 3.12.14 `Path.resolve(strict=True)` raises `FileNotFoundError` for a missing
path and `RuntimeError` for a symlink loop.

## Interfaces and types

`ml/schemas.py` (`Final` constants; mappings wrapped in `types.MappingProxyType`):
- `SEED: Final[int] = 42`; `BUNDLE_SCHEMA_VERSION: Final[int] = 1`.
- `RAW_COLUMNS: Final[tuple[str, ...]] = ("id", "curso", "feedback", "polaridad_basica", "grano_fino", "emocion",
  "aspectos", "semestre")`.
- `POLARITY_RAW_MAP: Final[Mapping[str, Polarity]]`: `"negativo"` → `NEGATIVE`, `"neutral"` → `NEUTRAL`,
  `"positivo"`, `"positiva"`, `"posicion"` → `POSITIVE` (5 keys).
- `ASPECT_LABEL_TO_GROUP: Final[Mapping[str, AspectGroup]]`: the 22 exact labels of `docs/contracts.md` §10.
- `CLEAN_COLUMNS: Final[tuple[str, ...]] = ("row_key", "source_file", "source_id", "course", "semester", "text",
  "polarity", *(f"aspect_{g.value}" for g in ASPECT_ORDER))` (16 names).
- `TypedDict`s (all keys required): `EmbeddingInfo` (`model_name: str`, `revision: str`); `ManifestMetrics`
  (`test_macro_f1: float`, `empirical_coverage: float`); `SmokeCheck` (`texts: list[str]`, `probabilities:
  list[list[float]]`); `Manifest` (`version`, `created_at`, `bundle_sha256`, `dataset_sha256`, `python_version`:
  `str`; `library_versions: dict[str, str]`; `embedding: EmbeddingInfo`; `polarity_model: str`; `representation:
  str`; `best_params: dict[str, object]`; `confidence_level: float`; `seed: int`; `metrics: ManifestMetrics`;
  `smoke: SmokeCheck`); `Registry` (`active: str`, `history: list[str]`); `SplitInfo` (`train_rows`, `test_rows`,
  `groups`: `int`); `Report` (`selection: list[dict[str, object]]`, `test: dict[str, object]`, `per_file_macro_f1:
  dict[str, float]`, `conformal: dict[str, float]`, `risk_coverage: list[tuple[float, float]]`, `aspects: dict[str,
  object]`, `topics: list[dict[str, object]]`, `split: SplitInfo`, `test_row_keys: list[str]`); `ReferenceStats`
  (`length_edges: list[int]`, `length_shares: list[float]`, `reference_oov_rate: float`, `class_shares:
  list[float]`).

`ml/data.py`:
- `MAX_INPUT_BYTES: Final[int] = 2_097_152`.
- `validate_input_file(path: Path, base: Path) -> Path`
- `dataset_files(dataset_dir: Path) -> tuple[Path, ...]`
- `dataset_sha256(files: Sequence[Path]) -> str`
- `normalize_text(text: str) -> str`
- `normalize_polarity(raw: str) -> Polarity`
- `parse_aspects(raw: str) -> dict[AspectGroup, Polarity]`
- `load_dataset(dataset_dir: Path) -> pd.DataFrame`
- Private helpers (names start with `_`) keep every function within the §6 limits.

## Expected behavior

`validate_input_file(path, base)` (SEC-11), checks in this order, first failure raises:
1. `path.suffix.lower() != ".csv"` → extension error.
2. `path.is_symlink()` → symlink error.
3. `resolved = path.resolve(strict=True)`; `OSError` or `RuntimeError` → not-found error, raised `from` it.
4. `root = base.resolve(strict=True)` (same exceptions → base error); `not resolved.is_relative_to(root)` →
   outside error.
5. `not resolved.is_file()` → regular-file error (directories, FIFOs and devices).
6. `resolved.stat().st_size > MAX_INPUT_BYTES` → size error. Returns `resolved`. The file is parsed by its caller.

`dataset_files(dataset_dir)`: the entries of `dataset_dir.iterdir()` (top level only) whose `suffix.lower()` is
`".csv"`, sorted by `name`, each passed through `validate_input_file(entry, dataset_dir)`; returns the resolved
paths. `Dataset/__MACOSX/` is a directory without that suffix and is skipped. `OSError` from `iterdir` → missing-dir
error; zero entries → no-files error.

`dataset_sha256(files)`: one `hashlib.sha256`; for each file sorted by `name`: update with
`name.encode("utf-8") + b"\n"`, then with the file bytes. Returns lowercase hex.

`normalize_text(text)`: `unicodedata.normalize("NFC", text)`, then `re.sub(r"\s+", " ", ...)`, then `strip()`.
Case, punctuation, accents and stopwords stay (`"muy"`, `"bastante"` kept).

`normalize_polarity(raw)`: `re.sub(r"[\[\]'\" ]", "", raw.lower())` looked up in `POLARITY_RAW_MAP`; missing key →
unknown-polarity error.

`parse_aspects(raw)`:
1. `json.loads(raw)`; `json.JSONDecodeError` → invalid-JSON error `from` it; result not a `list` → not-a-list error.
2. Each item MUST be a `dict` whose `"aspecto"` and `"sentimiento"` values are `str` (else malformed-entry error);
   `"aspecto"` is looked up in `ASPECT_LABEL_TO_GROUP` (else unknown-label error); `"sentimiento"` in the private map
   `"negativo"` → `NEGATIVE`, `"neutral"` → `NEUTRAL`, `"positivo"` → `POSITIVE` (else unknown-sentiment error).
3. Per group, the set of sentiments seen: one value → that value; two or more → `Polarity.NEUTRAL`.
4. Returns a new `dict` holding only the groups present, keys in `ASPECT_ORDER`.

`load_dataset(dataset_dir)`:
1. `files = dataset_files(dataset_dir)`.
2. Per file: `pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")`; `UnicodeDecodeError`,
   `pandas.errors.ParserError` or `pandas.errors.EmptyDataError` → unparseable error `from` it.
   `list(frame.columns) != list(RAW_COLUMNS)` → columns error.
3. Rows whose `id` equals `"id"` are dropped (every repeated header, wherever it appears); the remaining rows are
   numbered `n = 1, 2, ...` in file order.
4. Per row: `row_key = f"{path.name}:{n}"`; `source_file = path.name`; `source_id = int(id)` (`ValueError` → id
   error); `course = curso` and `semester = semestre` verbatim; `text = normalize_text(feedback)` (`""` → empty-text
   error); `polarity = normalize_polarity(polaridad_basica).value`; for each group `g` in `ASPECT_ORDER`,
   `aspect_<g.value>` = the value of `parse_aspects(aspectos)[g]` when present, else `""`. `grano_fino` and
   `emocion` are dropped.
5. Rows of all files concatenated in file order; zero rows → no-rows error. Returns a new `pd.DataFrame` with columns
   `CLEAN_COLUMNS` in that order, a `RangeIndex`, `source_id` of dtype `int64`.
6. Logs `INFO` `"dataset_loaded files=%d rows=%d"`. No log line holds text, file names or paths (SEC-05).

## Edge cases and error handling

Every error is `DatasetError` (`api/domain/errors.py`) with this exact `detail` (no input data in it):

| Condition | Detail |
|---|---|
| suffix not `.csv` (`a.txt`) | `"input file must have the .csv extension"` |
| `path` is a symlink | `"input file must not be a symlink"` |
| `path` missing, or a loop in a parent component (`base/l1/x.csv`, `l1` ↔ `l2`) | `"input file not found"` |
| `base` missing | `"input base directory not found"` |
| resolved file outside `base` (`base/../x.csv`) | `"input file is outside its base directory"` |
| directory or FIFO named `x.csv` | `"input file must be a regular file"` |
| size 2,097,153 bytes | `"input file exceeds 2097152 bytes"` (2,097,152 bytes is accepted) |
| `dataset_dir` missing | `"dataset directory not found"` |
| no `.csv` entry | `"no CSV files in dataset directory"` |
| undecodable, unterminated or 0-byte CSV | `"dataset file is not a parseable CSV"` |
| header differs from `RAW_COLUMNS` | `"dataset columns do not match"` |
| `id` `"x1"` | `"dataset id is not an integer"` |
| `feedback` `"   "` | `"dataset text is empty"` |
| only header rows in every file | `"dataset has no rows"` |
| polarity `"mixto"` or `""` | `"unknown polarity label"` |
| `aspectos` `"[{"` | `"aspect list is not valid JSON"` |
| `aspectos` `"{}"` | `"aspect list must be a JSON list"` |
| item `{"aspecto": "horario"}` or `"x"` (inside a list) | `"aspect entry is malformed"` |
| label `"comida"` | `"unknown aspect label"` |
| sentiment `"positiva"` | `"unknown aspect sentiment"` |

Uppercase `A.CSV` is accepted. `dataset_sha256` of an empty sequence returns the SHA-256 of no bytes
(`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`); callers pass `dataset_files` output, never
empty. If an existing test not listed here fails because of this change, the implementer does NOT modify it: report
its name and the reason.

## Acceptance tests (prose)

Unit fixtures are synthetic and written under `tmp_path`. `SYN` = a file `synthetic.csv` written in UTF-8 with
`"\ufeff"` first, then 4 records (5 physical lines): the header `RAW_COLUMNS` joined by `,`; the same header again;
`7,Bases de datos,"Las clases  fueron\nclaras y útiles.",['positivo'],3,neutral,"[{""aspecto"": ""contenidos"",
""sentimiento"": ""positivo""}]",2023-1`; `7,Bases de datos,Los parciales fueron muy difíciles para
todos.,negativo,3,neutral,"[{""aspecto"": ""parciales"", ""sentimiento"": ""negativo""}, {""aspecto"":
""horario"", ""sentimiento"": ""neutral""}]",2024-2`. The `\n` in the first data row is a real line feed character
inside the quoted field.

`tests/unit/ml/test_data.py`:
1. `test_schemas_constants`: `SEED == 42`, `BUNDLE_SCHEMA_VERSION == 1`, `RAW_COLUMNS` and `CLEAN_COLUMNS` equal the
   tuples above (16 names, last `"aspect_workload_pace"`), `len(ASPECT_LABEL_TO_GROUP) == 22`,
   `ASPECT_LABEL_TO_GROUP["cantidad de temasrepaso al inicio del curso"] is AspectGroup.CONTENT`,
   `ASPECT_LABEL_TO_GROUP["carga_académica"] is AspectGroup.WORKLOAD_PACE`, every group has ≥ 2 labels.
2. `test_schemas_mappings_are_read_only`: item assignment on `typing.cast("dict[str, Polarity]", POLARITY_RAW_MAP)` raises `TypeError` (the cast keeps
   `mypy --strict` clean without a suppression).
3. `test_normalize_text_collapses_whitespace`: `"  El curso\n fue\tbueno  "` → `"El curso fue bueno"`;
   `"muy bueno"` → `"muy bueno"`.
4. `test_normalize_text_applies_nfc`: `"Me gusto\u0301"` (9 characters) → `"Me gust\u00f3"` (8 characters).
5. `test_normalize_text_keeps_case_and_intensifiers`: `"Muy MUY bastante bueno!"` unchanged.
6. `test_normalize_polarity_raw_values` (parametrized): `"neutral"`, `"['neutral']"` → `NEUTRAL`; `"negativo"`,
   `"['negativo']"` → `NEGATIVE`; `"positivo"`, `"['positivo']"`, `"positiva"`, `"[\"['positivo']\"]"`,
   `"['posicion']"`, `" Positivo "` → `POSITIVE`.
7. `test_normalize_polarity_rejects_unknown`: `"mixto"` and `""` → `"unknown polarity label"`.
8. `test_parse_aspects_maps_groups`: `[{"aspecto": "horario", "sentimiento": "neutral"}, {"aspecto": "contenidos",
   "sentimiento": "positivo"}, {"aspecto": "Contenido y pertinencia", "sentimiento": "positivo"}]` →
   `{CONTENT: POSITIVE, ORGANIZATION_SCHEDULE: NEUTRAL}` with keys in that order.
9. `test_parse_aspects_conflict_becomes_neutral`: `parciales` `negativo` plus `Diseño de la evaluación y criterios`
   `positivo` → `{ASSESSMENT: NEUTRAL}`.
10. `test_parse_aspects_empty_list`: `"[]"` → `{}`.
11. `test_parse_aspects_rejects_bad_input` (parametrized, raw input → detail): `[{` → `"aspect list is not valid JSON"`;
    `{}` → `"aspect list must be a JSON list"`; `[{"aspecto": "horario"}]` and `["x"]` → `"aspect entry is malformed"`;
    `[{"aspecto": "comida", "sentimiento": "neutral"}]` → `"unknown aspect label"`; `[{"aspecto": "horario",
    "sentimiento": "positiva"}]` → `"unknown aspect sentiment"`.

`tests/unit/ml/test_data_files.py`:
1. `test_validate_input_file_returns_resolved_path`: `base/a.csv` → `(base / "a.csv").resolve()`; `base/A.CSV`
   accepted.
2. `test_validate_input_file_rejects_extension`, `_rejects_symlink` (`link.csv` → `a.csv`), `_rejects_missing`,
   `_rejects_symlink_loop` (`base/l1` → `l2`, `base/l2` → `l1`, path `base/l1/x.csv`), `_rejects_missing_base`
   (`tmp_path/a.csv` exists, `base = tmp_path/"nope"` not created), `_rejects_outside_base` (`base / ".." / "out.csv"` existing), `_rejects_directory`
   (`d.csv/`), `_rejects_fifo` (`os.mkfifo`), `_rejects_oversize` (2,097,153 bytes), `_accepts_size_limit`
   (2,097,152 bytes): each with its detail of the edge-case table.
3. `test_dataset_files_sorted_top_level`: `b.csv`, `a.csv`, `notes.txt`, `__MACOSX/c.csv` → `(a.csv, b.csv)`.
4. `test_dataset_files_rejects_missing_and_empty`: missing directory → `"dataset directory not found"`; only
   `notes.txt` → `"no CSV files in dataset directory"`.
5. `test_dataset_sha256_vector`: `a.csv` = `b"x\n"`, `b.csv` = `b"y\n"`, passed as `[b, a]` →
   `"393bea311dcb44194f89bc26c627e0dd485632584b5b827ca0bacbb4d2f723f3"`.
6. `test_load_dataset_builds_clean_frame`: `SYN` → 2 rows; columns `CLEAN_COLUMNS`; `row_key`
   `["synthetic.csv:1", "synthetic.csv:2"]`; `source_id` `[7, 7]` dtype `int64`; `text[0] == "Las clases fueron
   claras y útiles."`; `polarity` `["positive", "negative"]`; row 0 `aspect_content == "positive"`; row 1
   `aspect_assessment == "negative"`, `aspect_organization_schedule == "neutral"`; the other 15 aspect cells `""`.
7. `test_load_dataset_orders_files_by_name`: `b.csv` and `a.csv` copies of `SYN` → first `row_key` `"a.csv:1"`.
8. `test_load_dataset_rejects_bad_files` (parametrized): bytes `b"id,curso\n1,\xff\n"`, a 0-byte file, header
   without `semestre`, header-only file, `id` `x1`, `feedback` `"   "` → each detail of the edge-case table.
9. `test_load_dataset_logs_no_text`: with `caplog` at `INFO`, the record `"dataset_loaded files=1 rows=2"` and no
   record containing `"clases"` or `"synthetic"`.

`tests/integration/test_data_dataset.py` (real `Dataset/`, SEC-09 exception):
1. `test_dataset_counts`: `load_dataset(Path("Dataset"))` → 618 rows; per `source_file` 193, 405, 20; polarity
   counts `{"negative": 205, "neutral": 259, "positive": 154}`; non-empty `aspect_<g>` counts `[361, 94, 76, 71, 66,
   59, 48, 38, 35]` in `ASPECT_ORDER`; 60 rows with all 9 aspect cells `""`; `row_key` unique.
2. `test_dataset_values`: 7 courses including `"Sistemas opertativos"`; semesters `{"2023-1", "2023-2", "2024-1",
   "2024-2"}`; row `feedback_curso_universitario3.csv:8` has `source_id == 1` (repeated id after the second header);
   `feedback_curso_universitario3.csv:5` text starts with `"Estimado estudiante, Recuerda"` and holds no `"\n"`;
   every text equals `normalize_text` of itself.
3. `test_dataset_sha256_value`: `dataset_sha256(dataset_files(Path("Dataset")))` →
   `"5e3ac133828878229457420245bd2d674fdfe985e5a13632bf97b35bdbf2f666"`.

## Out of scope

- Splitting, grouping and features (specs 008, 009); the training CLI (spec 014); reading `gold/` sheets (spec 015).
- Emoji handling: no character above U+2000 appears in `Dataset/` (`docs/contracts.md` §10). Stopword removal,
  lemmatization, spelling fixes (`"opertativos"` stays), use of `grano_fino` and `emocion`.

## Definition of Done

- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/pytest -q -m integration tests/integration/test_data_dataset.py` → `3 passed`, exit code 0.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed`.
- [ ] `grep -nE "# noqa|# type: ignore" ml/schemas.py ml/data.py tests/unit/ml/test_data.py tests/unit/ml/test_data_files.py tests/integration/test_data_dataset.py` → no output.
- [ ] `.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing` → `ml/data.py` and
      `ml/schemas.py` each ≥ 80 % line coverage.
- [ ] `grep -nE "pickle|eval\(|exec\(|yaml|print\(" ml/schemas.py ml/data.py` → no output; `wc -l < ml/data.py` ≤ 300.
- [ ] `bash scripts/security_grep.sh` → no output, exit code 0.
- [ ] `bash scripts/gate.sh` → last line `GATE OK`, exit code 0.
