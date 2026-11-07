# 003 - Domain safety helpers
Riesgo: alto

## Objective

SEC-05 forbids comment text, emails, phone numbers and ids in logs, and SEC-12 requires every output path to stay
inside its base directory. Adapters and `ml` need one shared, standard-library implementation of both
(`ARCHITECTURE.md` §2). When this spec is done `api/domain/safety.py` provides `resolve_within`, `redact`,
`mask_contact_data` and `RedactingFilter` with the exact behavior of `docs/contracts.md` §4.4, and the error classes
of spec 002 get their own tests.

## Depends on

002.

## Governing files

- `security-rules.md` SEC-02 (mask emails, phones with 7 or more digits, ids of 6 to 10 digits), SEC-05 (`redact()`
  and `RedactingFilter` on every handler), SEC-12 (`resolve_within`, `UnsafePathError`), SEC-21 (tracebacks pass
  through `RedactingFilter`).
- `ARCHITECTURE.md` §2 rule 1 (standard library only), §6 (logging, errors, size limits, `pathlib.Path`).
- `docs/contracts.md` §2 (`UnsafePathError`), §4.4 (this module).

## Files to create/modify

1. `api/domain/safety.py` (new); same module conventions as `api/domain/entities.py`.
2. `tests/unit/domain/test_safety.py` (new); same structure as `tests/unit/domain/test_entities.py`.
3. `tests/unit/domain/test_errors.py` (new); same structure as `tests/unit/domain/test_entities.py`.

No existing test changes.

## External dependencies

None new (standard library: `hashlib`, `logging`, `re`, `pathlib`, `typing`).

## Interfaces and types

Module constants (compiled with `re.compile`, no flags):
- `EMAIL_PATTERN: Final[re.Pattern[str]]` = `r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"`
- `PHONE_PATTERN: Final[re.Pattern[str]]` = `r"\+?\(?\d[\d\s().-]{5,}\d"`
- `ID_PATTERN: Final[re.Pattern[str]]` = `r"\b\d{6,10}\b"`
- `MIN_PHONE_DIGITS: Final[int] = 7`, `MAX_UNSEPARATED_DIGITS: Final[int] = 10`
- `EMAIL_MASK: Final = "[EMAIL]"`, `PHONE_MASK: Final = "[PHONE]"`, `ID_MASK: Final = "[ID]"`

Functions and class:
- `def resolve_within(base: Path, candidate: Path) -> Path`
- `def mask_contact_data(text: str) -> str`
- `def redact(text: str) -> str`
- `def _mask_phone(match: re.Match[str]) -> str` (private, used by `mask_contact_data`)
- `class RedactingFilter(logging.Filter)` with `def filter(self, record: logging.LogRecord) -> bool`

## Expected behavior

`resolve_within(base, candidate)`:
1. `root = base.resolve(strict=True)`. An `OSError` (including `FileNotFoundError`), a `RuntimeError` (symlink loop
   in Python 3.12) or a `ValueError` (embedded NUL character) → `UnsafePathError("base cannot be resolved")`,
   raised `from` the original error.
2. `target = (root / candidate).resolve(strict=False)`. An `OSError`, a `RuntimeError` or a `ValueError` →
   `UnsafePathError("path cannot be resolved")`, raised `from` the original error.
3. `target.is_relative_to(root)` false → `UnsafePathError("path escapes base")`.
4. Returns `target` (absolute, symlinks resolved). The function creates no file or directory.

`mask_contact_data(text)`:
1. `EMAIL_PATTERN.sub(EMAIL_MASK, text)`.
2. `PHONE_PATTERN.sub(_mask_phone, ...)`. `_mask_phone`: with `digits` = number of characters of the match for
   which `str.isdecimal()` is true, returns `PHONE_MASK` when `digits >= MIN_PHONE_DIGITS` and (`digits <
   len(match)`, meaning the match holds a separator from whitespace, `(`, `)`, `.`, `-`, `+`, or `digits >
   MAX_UNSEPARATED_DIGITS`); otherwise returns the matched text unchanged.
3. `ID_PATTERN.sub(ID_MASK, ...)`; returns the result. A text without matches is returned equal to the input.

`redact(text)` returns `f"<redacted len={len(text)} sha={hashlib.sha256(text.encode()).hexdigest()[:8]}>"`
(`len` counts characters; the hash is over UTF-8 bytes).

`RedactingFilter.filter(record)`:
1. `record.msg = mask_contact_data(record.getMessage())`; `record.args = None`.
2. If `record.exc_info` is truthy: `record.exc_text =
   mask_contact_data(logging.Formatter().formatException(record.exc_info))`; `record.exc_info = None`.
3. Returns `True` (the filter never drops a record). `record.stack_info` is left unchanged.

## Edge cases and error handling

- The module imports only the standard library and `api.domain.errors`; it never logs (it is used inside logging).
- `resolve_within` with `candidate = Path(".")` returns `root` itself.
- An absolute `candidate` replaces `root` in `root / candidate`; it passes only if it lies inside `root`.
- A symlink inside `root` that points outside makes `target` escape → `UnsafePathError("path escapes base")`.
- `RedactingFilter` applied twice to the same record gives the same `msg` as applied once (masks do not re-match).
- `exc_info == (None, None, None)` (from `exc_info=True` outside an exception) is truthy: `exc_text` becomes
  `"NoneType: None"`.
- A message containing `%` after masking is safe: `args` is `None`, so `getMessage()` does not format again.
- A `candidate` holding a NUL character (`Path("a\x00b")`) → `UnsafePathError("path cannot be resolved")`;
  `__cause__` is a `ValueError`.
- A record whose `getMessage()` raises `TypeError` or `ValueError` (for example message `"x %d"` with args
  `("a",)`): the exception propagates unchanged out of `filter`; the filter does not catch it.
- `redact("\ud800")` (lone surrogate): `UnicodeEncodeError` propagates; callers pass validated text.

## Acceptance tests (prose)

`tests/unit/domain/test_safety.py` (`tmp` is pytest `tmp_path`; symlinks made with `Path.symlink_to`):
- `test_resolve_within_inside`: `(tmp, Path("v001/manifest.json"))` → `tmp.resolve() / "v001/manifest.json"`.
- `test_resolve_within_normalizes_dots`: `(tmp, Path("v001/../v002/x.json"))` → `tmp.resolve() / "v002/x.json"`.
- `test_resolve_within_dot_returns_base`: `(tmp, Path("."))` → `tmp.resolve()`.
- `test_resolve_within_parent_escape`: `(tmp, Path("../x"))` → `UnsafePathError`, `detail == "path escapes base"`.
- `test_resolve_within_absolute_escape`: `(tmp, Path("/etc/passwd"))` → `UnsafePathError`, `"path escapes base"`.
- `test_resolve_within_symlink_escape`: `tmp/link` → `/etc`; `(tmp, Path("link/passwd"))` → `"path escapes base"`.
- `test_resolve_within_symlink_loop`: `tmp/loop` → `tmp/loop`; `(tmp, Path("loop/x"))` → `UnsafePathError`,
  `"path cannot be resolved"`, `__cause__` is a `RuntimeError`.
- `test_resolve_within_missing_base`: `(tmp / "missing", Path("a"))` → `UnsafePathError`, `"base cannot be
  resolved"`, `__cause__` is a `FileNotFoundError`.
- `test_resolve_within_creates_nothing`: after `(tmp, Path("new/dir/file.json"))`, `tmp / "new"` does not exist.
- `test_resolve_within_absolute_inside`: `(tmp, tmp.resolve() / "a.json")` → `tmp.resolve() / "a.json"`.
- `test_resolve_within_null_byte`: `(tmp, Path("a\x00b"))` → `UnsafePathError`, `detail == "path cannot be
  resolved"`, `__cause__` is a `ValueError`.
- `test_resolve_within_base_symlink_loop`: `tmp/loop` → `tmp/loop`; `(tmp / "loop", Path("a"))` →
  `UnsafePathError`, `detail == "base cannot be resolved"`, `__cause__` is a `RuntimeError`.
- `test_mask_contact_data_vectors` (parametrized, input → output):
  - `"Escribir a ana.gomez@uni.edu.co o al 300 123 4567, código 20231045"` →
    `"Escribir a [EMAIL] o al [PHONE], código [ID]"`
  - `"Llamar al +57 (300) 123-4567 hoy"` → `"Llamar al [PHONE] hoy"`
  - `"Fax 601\t2345678"` → `"Fax [PHONE]"`
  - `"Número 573001234567"` (12 digits, no separator) → `"Número [PHONE]"`
  - `"Llamar al 3001234567"` (10 digits, no separator) → `"Llamar al [ID]"`
  - `"Juan.Perez99@correo.com"` → `"[EMAIL]"`
  - `"Código 12345"` → unchanged; `"Tel 123 456"` (6 digits) → unchanged;
    `"Semestres 2023-1 y 2023-2"` → unchanged; `"Sin datos de contacto."` → unchanged.
- `test_redact_vectors`: `"Juan Pérez"` → `"<redacted len=10 sha=090fd624>"`; `""` →
  `"<redacted len=0 sha=e3b0c442>"`; `"El curso fue bastante bueno"` → `"<redacted len=27 sha=c489921e>"`.
- `test_redacting_filter_masks_message_and_args`: `logging.LogRecord("t", logging.INFO, "f", 1, "contact %s row=%d",
  ("ana@uni.edu.co", 3), None)` → `filter` returns `True`, `msg == "contact [EMAIL] row=3"`, `args is None`.
- `test_redacting_filter_idempotent`: applying `filter` a second time leaves `msg == "contact [EMAIL] row=3"`.
- `test_redacting_filter_masks_traceback`: a record built with `sys.exc_info()` of `ValueError("id 1234567")` →
  last line of `exc_text` is `"ValueError: id [ID]"`, `"1234567" not in exc_text`, `exc_info is None`.
- `test_redacting_filter_on_handler_message`: logger `"tests.safety.message"` (`propagate = False`) with a
  `logging.StreamHandler` on its own `io.StringIO`, formatter `"%(message)s"`, and the filter added with
  `handler.addFilter(...)` (on the handler, not on the logger); `logger.error("contact %s", "ana@uni.edu.co")`
  writes `"contact [EMAIL]\n"`. The handler is removed in a `finally` block.
- `test_redacting_filter_on_handler_exception`: logger `"tests.safety.exception"` built the same way with its own
  stream; `logger.exception("failed row=%d", 3)` inside `except ValueError` for `ValueError("id 1234567")` writes a
  first line `"failed row=3"` and a last line `"ValueError: id [ID]"`, and the stream never holds `"1234567"`. The
  handler is removed in a `finally` block.
- `test_redacting_filter_percent_in_message`: `logging.LogRecord("t", logging.INFO, "f", 1, "rate 100%% for %s",
  ("ana@uni.edu.co",), None)` → after `filter`, `msg == "rate 100% for [EMAIL]"` and `getMessage() == "rate 100% for
  [EMAIL]"`.
- `test_redacting_filter_bad_args_propagates`: `logging.LogRecord("t", logging.INFO, "f", 1, "x %d", ("a",), None)`
  → `filter` raises `TypeError`.
- `test_redact_lone_surrogate_raises`: `redact("\ud800")` raises `UnicodeEncodeError`.
- `test_redacting_filter_empty_exc_info`: record with `exc_info=(None, None, None)` → `exc_text == "NoneType:
  None"`.

`tests/unit/domain/test_errors.py`:
- `test_errors_codes` (parametrized, class → `code`): `AppError` `internal_error`, `InvalidInputError`
  `invalid_input`, `CsvFormatError` `invalid_csv`, `PayloadTooLargeError` `payload_too_large`,
  `UnsupportedMediaTypeError` `unsupported_media_type`, `NotFoundError` `not_found`, `ModelUnavailableError`
  `model_unavailable`, `ModelIntegrityError` `model_unavailable`, `ConfigError`, `AnonymizerUnavailableError`,
  `InferenceError`, `UnsafePathError`, `DatasetError` `internal_error`.
- `test_errors_hierarchy`: `CsvFormatError` subclasses `InvalidInputError`; `ModelIntegrityError` subclasses
  `ModelUnavailableError`; all 13 classes subclass `AppError`; `AppError` subclasses `Exception`.
- `test_errors_detail`: `UnsafePathError("path escapes base")` has `.detail == "path escapes base"` and
  `str(error) == "path escapes base"`.

## Out of scope

- `SpacyAnonymizer` and person-name masking (spec 019); attaching the filter to handlers (spec 016).
- Validating input files (SEC-11, spec 007) and creating directories with mode 0700 (SEC-04).
- Changing the patterns or masks of `docs/contracts.md` §4.4.

## Definition of Done

- [ ] Tests: `.venv/bin/pytest -q -m "not integration"` prints `N passed`, exit code 0;
  `.venv/bin/pytest -q tests/unit/domain/test_safety.py tests/unit/domain/test_errors.py` prints `47 passed` (32 in
  `test_safety.py`, 15 in `test_errors.py`).
- [ ] Linter: `.venv/bin/ruff check .` prints `All checks passed!`; formatter: `.venv/bin/ruff format --check .`
  exits 0.
- [ ] Architecture and size: `.venv/bin/pytest -q tests/architecture` prints `N passed`, exit code 0.
- [ ] Type checker: `.venv/bin/mypy --strict api tests` prints `Success: no issues found in N source files` (`ml`
  holds no module until spec 007).
- [ ] No new suppressions: `grep -rn "noqa\|type: ignore" --include="*.py" --exclude-dir=.venv .` prints nothing.
- [ ] Coverage: `.venv/bin/pytest -q -m "not integration" --cov=api --cov-report=term-missing` shows ≥ 80 % for
  `api/domain/safety.py` and `api/domain/errors.py`.
- [ ] No logging inside the module: `grep -n "getLogger\|print(" api/domain/safety.py` prints nothing.
- [ ] Security grep: `bash scripts/security_grep.sh` prints nothing, exit code 0.
