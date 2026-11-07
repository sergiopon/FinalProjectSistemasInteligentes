# 016 - Adapters settings and logging
Riesgo: alto

## Objective

The service has no validated configuration and no log setup. Without them an invalid `config/app.json` would start the
service with unsafe limits, and log records would reach handlers without `RedactingFilter` (uvicorn ships two
handlers, one of them on stderr, measured on uvicorn 0.54.0), which breaks SEC-05. After this spec:
`load_settings` validates `config/app.json` with pydantic and stops on any violation with `ConfigError`, and
`configure_logging` routes every record of the root logger and of the uvicorn loggers to one stdout handler that
carries `RedactingFilter` and writes `key=value` lines in UTC.

## Depends on

000 (`config/app.json`, `pyproject.toml`); 001 (`scripts/security_grep.sh`, `tests/architecture`, used by the
Definition of Done); 002 (`api/domain/errors.py`: `ConfigError`, `UnsafePathError`); 003 (`api/domain/safety.py`:
`resolve_within`, `RedactingFilter`, `mask_contact_data`).

## Governing files

- `ARCHITECTURE.md` §2 (adapters layer; configuration and logging handler setup live in `api.adapters`), §6
  (size limits, types, errors, logging: one logger per module, `key=value`, `RedactingFilter` on every handler,
  `log_config.py` only builds stdout handlers), §7 (single file `config/app.json`, invalid file stops the process).
- `security-rules.md` SEC-05 (stdout only, no file handler, filter on every handler), SEC-11 (HTTP ceilings 2,000
  characters, 2 MB, 5,000 rows), SEC-12 (`resolve_within`), SEC-13 (configuration read with `json`), SEC-21.
- `docs/contracts.md` §2 (`ConfigError`, code `internal_error`, startup exit 1), §4.4 (`RedactingFilter`), §7.

## Files to create/modify

1. `api/adapters/settings.py` (new)
2. `api/adapters/log_config.py` (new)
3. `tests/unit/adapters/test_settings.py` (new)
4. `tests/unit/adapters/test_log_config.py` (new)

`config/app.json` already exists (created by spec 000 with the content of `docs/contracts.md` §7); this spec does
not modify it.

Reference pattern: no adapter exists yet; the module layout (docstring, `from __future__ import annotations`,
imports, constants, classes, functions) follows `api/domain/safety.py` from spec 003.

## External dependencies

None new. Uses `pydantic==2.14.3` (`BaseModel`, `ConfigDict`, `Field`, `ValidationError`, `field_validator`), pinned
in `requirements.txt` by spec 000. pydantic ships type information: no type suppression is allowed in this spec.

## Interfaces and types

`api/adapters/settings.py`:

- `REPO_ROOT: Path = Path(__file__).resolve().parents[2]` (the repository root: `api/adapters/settings.py` → `api/`
  → root).
- Every model below sets `model_config = ConfigDict(extra="forbid", frozen=True)`.
- `class CostSettings(BaseModel)`: `error_cost: float` and `review_cost: float`, each
  `Field(gt=0, allow_inf_nan=False, strict=True)`; `review_if_set_not_singleton: bool` with `Field(strict=True)`.
- `class ConformalSettings(BaseModel)`: `alpha: float` with `Field(gt=0, lt=1, allow_inf_nan=False, strict=True)`.
- `class LimitSettings(BaseModel)`: `max_text_chars: int` with `Field(ge=1, le=2000, strict=True)`;
  `max_upload_bytes: int` with `Field(ge=1, le=2097152, strict=True)`; `max_upload_rows: int` with
  `Field(ge=1, le=5000, strict=True)`.
- `class AppSettings(BaseModel)`: `costs: CostSettings`, `conformal: ConformalSettings`, `limits: LimitSettings`,
  `models_dir: Path` (lax: a JSON string becomes a `Path`). Validator
  `@field_validator("models_dir")` `@classmethod` `_models_dir_inside_repo(cls, value: Path) -> Path`.
- `def load_settings(path: Path) -> AppSettings`.

Measured with pydantic 2.14.3: with `strict=True` a float field accepts the JSON integer `1` (becomes `1.0`) and
rejects `"5"` and `true`; an int field rejects `2000.0` and `true`; a bool field rejects `1` and `"true"`;
`allow_inf_nan=False` rejects `Infinity` and `NaN` (which `json.loads` accepts); assigning an attribute of a frozen
model raises `ValidationError` of type `frozen_instance`.

`api/adapters/log_config.py`:

- `LOG_FORMAT: str = "time=%(asctime)s level=%(levelname)s logger=%(name)s %(message)s"`
- `DATE_FORMAT: str = "%Y-%m-%dT%H:%M:%SZ"`
- `UVICORN_LOGGERS: tuple[str, ...] = ("uvicorn", "uvicorn.error", "uvicorn.access")`
- `def build_stdout_handler() -> logging.Handler`
- `def configure_logging(level: int = logging.INFO) -> None`

## Expected behavior

`_models_dir_inside_repo(value)`:
1. `value.is_absolute()` → raise `ValueError("models_dir must be relative")`.
2. Return `resolve_within(REPO_ROOT, value)`; an `UnsafePathError` is caught and re-raised as
   `ValueError("models_dir escapes the repository")` with `from` the original error.

`load_settings(path)`:
1. `raw = path.read_text(encoding="utf-8")`. `OSError` or `UnicodeDecodeError` → raise
   `ConfigError("config file unreadable")` from the original error.
2. `document = json.loads(raw)`. `json.JSONDecodeError` → raise `ConfigError("config file is not valid JSON")` from
   the original error.
3. `AppSettings.model_validate(document)`. `ValidationError` → raise `ConfigError("config invalid: " + locations)`
   from the original error, where `locations` joins with `","` each error's `loc` joined with `"."`; an empty `loc`
   is written `"<root>"`. The order is the order of the fields: `costs`, `conformal`, `limits`, `models_dir` and, inside
   a model, the order in which its fields are declared above (pydantic reports errors in that order).
4. Return the `AppSettings` instance; `models_dir` holds the absolute resolved path.

No value of the file appears in any `ConfigError` detail. `load_settings` logs nothing. The check that `1 - alpha`
equals the manifest `confidence_level` within 1e-9 runs at startup in `api/main.py` (spec 024), not here.

`build_stdout_handler()`:
1. `formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)`; `formatter.converter = time.gmtime` (UTC timestamps).
2. `handler = logging.StreamHandler(sys.stdout)`; `handler.setFormatter(formatter)`;
   `handler.addFilter(RedactingFilter())`.
3. Return `handler`.

`configure_logging(level)`:
1. `logging.basicConfig(handlers=[build_stdout_handler()], level=level, force=True)` (replaces every root handler).
2. For each name in `UVICORN_LOGGERS`: `logging.getLogger(name).handlers.clear()` and `propagate = True`, so uvicorn
   records reach the root handler only.
3. Returns `None`. Calling it twice leaves exactly 1 root handler.

The module `log_config.py` creates no `FileHandler`, never references `sys.stderr` and never calls `print`.
Every function in both modules has at most 20 statements; each module stays under 120 lines.

## Edge cases and error handling

| Input | Result |
|---|---|
| Path does not exist, or is a directory | `ConfigError`, detail `"config file unreadable"` |
| File bytes `b"\xff\xfe"` | `ConfigError`, detail `"config file unreadable"` |
| File text `{"costs": ` | `ConfigError`, detail `"config file is not valid JSON"` |
| Document `[1]` | `ConfigError`, detail `"config invalid: <root>"` |
| `"error_cost": Infinity`, `NaN`, `0.0`, `-1.0`, `"5"` or `true` | `ConfigError`, detail `"config invalid: costs.error_cost"` |
| `"review_if_set_not_singleton": 1` | `ConfigError`, detail `"config invalid: costs.review_if_set_not_singleton"` |
| `"alpha": 0.0` or `1.0` | `ConfigError`, detail `"config invalid: conformal.alpha"` |
| `"max_text_chars": 2001`, `0` or `2000.0` | `ConfigError`, detail `"config invalid: limits.max_text_chars"` |
| `"max_upload_bytes": 2097153` | `ConfigError`, detail `"config invalid: limits.max_upload_bytes"` |
| `"max_upload_rows": 5001` | `ConfigError`, detail `"config invalid: limits.max_upload_rows"` |
| `"models_dir": "/srv/models"` or `"../outside"` | `ConfigError`, detail `"config invalid: models_dir"` |
| Extra top-level key `"debug": true` | `ConfigError`, detail `"config invalid: debug"` |
| Missing section `"conformal"` | `ConfigError`, detail `"config invalid: conformal"` |
| Assignment to an attribute of a loaded `AppSettings` | `pydantic.ValidationError` (frozen) |
| Log message holding `ana.gomez@uni.edu.co` | Output line holds `[EMAIL]` and not the address |
| Exception traceback holding `ana@x.com` | Traceback lines printed with `[EMAIL]` |

No existing test changes expectation. If an existing test not listed here fails because of this change, the
implementer does not modify it: they report its name and the reason.

## Acceptance tests (prose)

`tests/unit/adapters/test_settings.py` (every case writes a synthetic file under pytest `tmp_path`, except the first):
- `test_load_settings_reads_versioned_config`: `load_settings(REPO_ROOT / "config" / "app.json")` returns
  `costs.error_cost == 5.0`, `costs.review_cost == 1.0`, `costs.review_if_set_not_singleton is True`,
  `conformal.alpha == 0.1`, `limits.max_text_chars == 2000`, `limits.max_upload_bytes == 2097152`,
  `limits.max_upload_rows == 5000`, `models_dir == REPO_ROOT / "models"`.
- `test_load_settings_accepts_integer_cost`: the §7 document with `"review_cost": 1` loads with `review_cost == 1.0`.
- `test_load_settings_rejects_missing_file`: path `tmp_path / "absent.json"` → `ConfigError`, detail
  `"config file unreadable"`.
- `test_load_settings_rejects_directory_path`: `load_settings(tmp_path)` (a directory) → `ConfigError`, detail
  `"config file unreadable"`.
- `test_load_settings_rejects_non_utf8`: bytes `b"\xff\xfe"` → detail `"config file unreadable"`.
- `test_load_settings_rejects_invalid_json`: text `{"costs": ` → detail `"config file is not valid JSON"`.
- `test_load_settings_rejects_non_object`: text `[1]` → detail `"config invalid: <root>"`.
- `test_load_settings_rejects_bad_error_cost`: parametrized over the JSON literals `Infinity`, `NaN`, `0.0`, `-1.0`,
  `"5"`, `true` → detail `"config invalid: costs.error_cost"` for each of the 6.
- `test_load_settings_rejects_non_bool_flag`: `"review_if_set_not_singleton": 1` → detail
  `"config invalid: costs.review_if_set_not_singleton"`.
- `test_load_settings_rejects_alpha_bounds`: parametrized `0.0`, `1.0` → `"config invalid: conformal.alpha"`.
- `test_load_settings_rejects_limit_ceilings`: parametrized (`max_text_chars`, `2001`), (`max_text_chars`, `0`),
  (`max_text_chars`, `2000.0`), (`max_upload_bytes`, `2097153`), (`max_upload_rows`, `5001`) → detail
  `"config invalid: limits.<field>"`.
- `test_load_settings_rejects_absolute_models_dir`: `"/srv/models"` → `"config invalid: models_dir"`.
- `test_load_settings_rejects_escaping_models_dir`: `"../outside"` → `"config invalid: models_dir"`.
- `test_load_settings_joins_multiple_locations`: the §7 document with `"error_cost": 0.0`, `"alpha": 1.0` and
  `"max_upload_rows": 5001` → detail `"config invalid: costs.error_cost,conformal.alpha,limits.max_upload_rows"`.
- `test_load_settings_rejects_extra_key`: extra `"debug": true` → `"config invalid: debug"`.
- `test_load_settings_rejects_missing_section`: no `"conformal"` key → `"config invalid: conformal"`.
- `test_app_settings_is_frozen`: assigning `settings.models_dir = Path("x")` raises `pydantic.ValidationError`.

`tests/unit/adapters/test_log_config.py` (an autouse fixture saves root handlers and level and the handlers and
`propagate` of the 3 uvicorn loggers before each test and restores them after; handlers are built inside the test so
pytest `capsys` captures `sys.stdout`):
- `test_build_stdout_handler_writes_key_value_line`: a `logging.Logger("api.test")` with the handler logs at INFO
  `"event=startup version=%s"` with arg `"v001"`; captured stdout is one line matching
  `^time=\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z level=INFO logger=api.test event=startup version=v001$`; stderr is
  empty.
- `test_build_stdout_handler_has_redacting_filter`: `any(isinstance(f, RedactingFilter) for f in handler.filters)`
  is true.
- `test_build_stdout_handler_masks_contact_data`: logging `"contact=%s"` with `"ana.gomez@uni.edu.co"` prints a line
  ending in `contact=[EMAIL]`; `"ana.gomez"` is not in stdout.
- `test_build_stdout_handler_masks_traceback`: inside `except ValueError` of `ValueError("bad ana@x.com")`,
  `logger.exception("event=failed")` prints a line containing `ValueError: bad [EMAIL]`; `"ana@x.com"` is not in
  stdout.
- `test_build_stdout_handler_uses_utc`: a `logging.LogRecord` (name `"api.test"`, level INFO, msg `"event=x"`) with
  `created` set to `0.0`, formatted by `handler.formatter`, starts with `"time=1970-01-01T00:00:00Z "`.
- `test_configure_logging_replaces_root_handlers`: after two calls of `configure_logging(logging.DEBUG)`, the root
  logger has exactly 1 handler, it holds a `RedactingFilter`, and the root level is `logging.DEBUG`.
- `test_configure_logging_routes_uvicorn_loggers`: after adding a `logging.StreamHandler(sys.stderr)` to
  `"uvicorn"` and setting `propagate = False`, `configure_logging()` leaves each of the 3 uvicorn loggers with 0
  handlers and `propagate is True`.

## Out of scope

- The `1 - alpha` versus manifest `confidence_level` check and the process exit on `ConfigError` (spec 024).
- `RedactingFilter` and `resolve_within` themselves (spec 003). Logging setup of `ml` entry points (`ml` MUST NOT
  import `api.adapters`, `ARCHITECTURE.md` §2 rule 4).
- Any other configuration source (environment variables, profiles, command-line flags).

## Definition of Done

- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0.
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] `.venv/bin/pytest -q tests/architecture` → `N passed` (dependency rule and size limits).
- [ ] `grep -rnE "# noqa|# type: ignore" api/adapters/settings.py api/adapters/log_config.py tests/unit/adapters/test_settings.py tests/unit/adapters/test_log_config.py` → no output.
- [ ] `.venv/bin/pytest -q tests/unit/adapters/test_settings.py tests/unit/adapters/test_log_config.py --cov=api/adapters --cov-report=term-missing`
      → the rows of `api/adapters/settings.py` and `api/adapters/log_config.py` show Cover ≥ 80 %.
- [ ] `grep -rn "FileHandler\|print(" api/` → no output (SEC-05).
- [ ] `grep -n "stderr" api/adapters/log_config.py` → no output.
- [ ] `grep -c "RedactingFilter" api/adapters/log_config.py` → a number ≥ 2 (import and `addFilter`).
- [ ] `bash scripts/security_grep.sh` → no output, exit code 0.
- [ ] `.venv/bin/python -c "from pathlib import Path; from api.adapters.settings import load_settings; print(load_settings(Path('config/app.json')).conformal.alpha)"` → `0.1`.
