# 001 - Gate and dependency rule
Riesgo: alto

## Objective

`CONTEXT.md` defines the `Gate` (8 ordered steps) and `ARCHITECTURE.md` §2 rule 6 requires
`tests/architecture/test_dependencies.py`, but both are missing. When this spec is done: `bash scripts/gate.sh` runs
the 8 steps and stops at the first failure; `bash scripts/security_grep.sh` runs every automatable check of
`security-rules.md` §8; architecture tests enforce the layer rule, the no-`__init__.py` rule (ADR-005) and the module
and class size limits of `ARCHITECTURE.md` §6.

## Depends on

000.

## Governing files

- `ARCHITECTURE.md` §2 (table and rules 1 to 4, 6), §6 (size: modules ≤ 300 lines except
  `api/adapters/http_schemas.py` and `ml/schemas.py`, classes ≤ 150 lines; logging: no `print`).
- `security-rules.md` §8 commands for SEC-01, SEC-04, SEC-05, SEC-10, SEC-13, SEC-14, SEC-15, SEC-16, SEC-17, SEC-18,
  SEC-22.
- `ADR-005` rule 4 (no `__init__.py`). `CONTEXT.md` "Gate" (exact commands and order).

## Files to create/modify

1. `scripts/gate.sh` (new)
2. `scripts/security_grep.sh` (new)
3. `tests/architecture/test_dependencies.py` (new)
4. `tests/architecture/test_size_limits.py` (new)
5. `tests/architecture/test_security_grep.py` (new)

No reference file of the same layer exists yet. No existing test changes.

## External dependencies

None new. Bash, GNU grep and the standard library modules `ast`, `pathlib`, `subprocess`, `sys`, `shutil`.

## Interfaces and types

### `scripts/gate.sh`

First line `#!/usr/bin/env bash`, then `set -euo pipefail`, then `cd "$(dirname "$0")/.."`, then exactly the 8
commands of `CONTEXT.md` "Gate", one per line, in order: `.venv/bin/ruff format --check .`;
`.venv/bin/ruff check .`; `.venv/bin/mypy --strict api ml tests`; `.venv/bin/pytest -q tests/architecture`;
`.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing --cov-fail-under=80`;
`bash scripts/security_grep.sh`; `.venv/bin/pip-audit -r requirements.txt --disable-pip --no-deps`;
`echo "GATE OK"`. No other command.

### `scripts/security_grep.sh`

Usage `bash scripts/security_grep.sh [ROOT]`. `ROOT` defaults to the parent directory of the script. Shebang
`#!/usr/bin/env bash`, `set -uo pipefail` (no `-e`: grep exits 1 on no match), `cd` into `ROOT` (exit 2 if it
fails). Every check runs, in the order of the table below; each failure prints to stdout the line `SECURITY FAIL
<ID>: <message>` followed by the matching lines, if any, and sets the final exit code to 1. The stderr of every
`grep` is discarded (`2>/dev/null`), except in SEC-18, where it is merged into the output. On success the script prints nothing and exits 0. A directory
among `api`, `ml`, `scripts`, `web` that does not exist is left out of every scan; a check whose directory list ends up
empty is skipped. Every `grep -r` uses `--include="*.py"`, except SEC-22 (it uses only `--include="*.js" --include="*.html"`);
SEC-13 adds `--include="*.sh" --exclude=security_grep.sh`, because the script holds the patterns itself.

| ID | Scan | Fails when | `<message>` |
|---|---|---|---|
| SEC-01 | `grep -rnE "UploadFile\|NamedTemporaryFile\|SpooledTemporaryFile"` over `api` | output non-empty | `upload or temporary file in api/` |
| SEC-04 | files: `api/main.py` if it exists, plus the output of `grep -rl "^def main("` over `ml` | a listed file lacks `os.umask(0o077)` | `os.umask(0o077) missing in <file>` (one line per file) |
| SEC-05 | `grep -rnE "FileHandler\|print\("` over `api` | output non-empty | `file handler or print in api/` |
| SEC-10 | `grep -qxF -- <line> .gitignore` for each of `data/`, `reports/`, `models/v*/bundle.joblib`, `.venv/`, `__pycache__/`, `.env` | a line is absent or `.gitignore` is missing | `.gitignore lacks <line>` (one line per missing entry) |
| SEC-13 | `grep -rnE "yaml\.load\|pickle\|eval\(\|exec\(\|shell=True"` over `api`, `ml`, `scripts` | output non-empty | `forbidden construct` |
| SEC-14 | `grep -rl "joblib\.load"` over `api`, `ml`, filtered by `grep -vxE "api/adapters/model_store\.py\|ml/artifact\.py"` | output non-empty | `joblib.load outside the two allowed files` |
| SEC-15 | `grep -rnE "torch\.load\|pickle\.load"` over `api`, `ml` | output non-empty | `torch.load or pickle.load used` |
| SEC-16 | `api/main.py`, only if it exists | it lacks `HF_HUB_OFFLINE` or lacks `TRANSFORMERS_OFFLINE` | `offline flags missing in api/main.py` |
| SEC-17 | `grep -c "^es_core_news_sm @ https://" requirements.txt` | result is not `1` or the file is missing | `spaCy model URL not pinned in requirements.txt` |
| SEC-18 | `grep -vnE "^\s*(#\|$\|.*==\|.*@ https://\|--extra-index-url https://download\.pytorch\.org/whl/cpu$)" requirements.txt requirements-dev.txt` (stderr merged) | output non-empty | `unpinned requirement line` |
| SEC-22 | `grep -rnE "innerHTML\|outerHTML\|insertAdjacentHTML\|document\.write\|eval\(\|new Function\|setAttribute\(.style\|<script>\|style=\| on[a-z]+=" --include="*.js" --include="*.html"` over `web` | output non-empty | `forbidden construct in web/` |

(`\|` in the table stands for the regex alternation `|`.)

### `tests/architecture/test_dependencies.py`

- `REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]`
- `def module_layer(relative_path: Path) -> str | None`: `api/domain/**` → `"domain"`, `api/ports/**` →
  `"ports"`, `api/application/**` → `"application"`, `api/adapters/**` → `"adapters"`, `api/main.py` → `"main"`,
  `ml/**` → `"ml"`; any other path → `None`.
- `def imported_modules(path: Path) -> tuple[str, ...]`: parses with `ast.parse`, walks every node (imports under
  `if TYPE_CHECKING:` count). `import a.b` → `"a.b"` per alias; `from a.b import c` → `"a.b"`; a relative import →
  `"." * level + (module or "")`.
- `def is_allowed(layer: str, module: str) -> bool` with `within(module, package)` meaning `module == package` or
  `module.startswith(package + ".")`, and `stdlib` meaning `module.split(".")[0] in sys.stdlib_module_names`:

| Layer | Allowed |
|---|---|
| any | never a module starting with `.`; never `within(module, "api.main")` |
| `domain` | `stdlib` or `within(module, "api.domain")` |
| `ports` | `stdlib` or within `api.domain` or `api.ports` |
| `application` | `stdlib` or within `api.domain`, `api.ports` or `api.application` |
| `adapters`, `main` | everything else |
| `ml` | everything except within `api.ports`, `api.application`, `api.adapters` |

- `def dependency_violations(root: Path) -> tuple[str, ...]`: every `*.py` under `root/api` and `root/ml` (`rglob`,
  sorted by path), each disallowed import as `f"{relative_path}: {layer} must not import {module}"`, with
  `relative_path` in POSIX form relative to `root`. A file whose `module_layer` is `None` is skipped (no violation).

### `tests/architecture/test_size_limits.py`

Test files do not import each other; each defines its own `REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]`
(also `test_security_grep.py`).

- Constants: `MAX_MODULE_LINES: Final = 300`, `MAX_CLASS_LINES: Final = 150`,
  `MODULE_LINE_EXEMPTIONS: Final = frozenset({"api/adapters/http_schemas.py", "ml/schemas.py"})`,
  `SCANNED_DIRS: Final = ("api", "ml", "tests", "scripts")`.
- `def size_violations(root: Path) -> tuple[str, ...]`: for every `*.py` under the scanned directories that exist
  (sorted): `n = len(text.splitlines())`; `n > 300` and the POSIX relative path not exempt →
  `f"{relative_path}: {n} lines > 300"`; every `ast.ClassDef` with `(end_lineno or lineno) - lineno + 1 > 150` (`end_lineno` is `int | None` in the type stubs) →
  `f"{relative_path}:{lineno}: class {name} has {count} lines > 150"`.

## Expected behavior

1. `bash scripts/gate.sh` runs the 8 steps; the first failing step ends the script with that step's exit code; when
   all pass the last line is `GATE OK` and the exit code is 0.
2. `bash scripts/security_grep.sh` on the repository after specs 000 and 001 prints nothing and exits 0.
3. The architecture tests read files only; they never import project modules, so they pass with `api/` and `ml/`
   absent.

## Edge cases and error handling

- Until `api/` and `ml/` each hold one `.py` file (specs 002 and 007), Gate step 3 exits 2 (mypy prints
  `ml: error: Duplicate module named "__main__" (also at "api")` while both directories are missing,
  `ml: error: Cannot read file: No such file or directory` when only `ml` is missing, and
  `There are no .py[i] files in directory 'api'` for an empty directory; the exit code is 2 in all three cases), and step 5 fails with `Coverage failure: total of 0 is less than fail-under=80` while no module
  under `api/` is tested. This is expected; the DoD checks each step separately.
- `security_grep.sh` with `ROOT` holding no `api`, `ml` or `scripts` directory runs SEC-10, SEC-17 and SEC-18 only.
- A missing `requirements-dev.txt` makes SEC-18 fail (grep's `No such file or directory` message is the output).
- Binary files and `__pycache__` are never matched (`--include` filters).
- `from api import domain` inside `api/domain` is a violation (`api` is not within `api.domain`): imports name the
  full module.
- A file that `ast.parse` cannot parse makes the test fail with the `SyntaxError` (not caught).

## Acceptance tests (prose)

Synthetic trees are written under `tmp_path`; file bodies are one-line strings given here.

`test_dependencies.py`:
- `test_dependencies_repository_has_no_violations`: `dependency_violations(REPO_ROOT)` → `()`.
- `test_dependencies_no_init_files`: no `__init__.py` under `REPO_ROOT` `api`, `ml`, `tests`, `scripts`.
- `test_dependencies_domain_rejects_third_party`: `api/domain/bad.py` = `import numpy` →
  `("api/domain/bad.py: domain must not import numpy",)`.
- `test_dependencies_domain_allows_stdlib_and_domain`: `api/domain/ok.py` = `import re` plus
  `from api.domain.errors import AppError` → `()`.
- `test_dependencies_type_checking_import_counted`: `api/domain/tc.py` = `from typing import TYPE_CHECKING`, then
  `if TYPE_CHECKING:` with `import numpy` → `("api/domain/tc.py: domain must not import numpy",)`.
- `test_dependencies_relative_import_rejected`: `api/domain/rel.py` = `from . import errors` →
  `("api/domain/rel.py: domain must not import .",)`.
- `test_dependencies_ports_rejects_adapters`: `api/ports/bad.py` = `from api.adapters.settings import load_settings`
  → `("api/ports/bad.py: ports must not import api.adapters.settings",)`.
- `test_dependencies_application_rejects_ml`: `api/application/bad.py` = `import ml.data` →
  `("api/application/bad.py: application must not import ml.data",)`.
- `test_dependencies_nobody_imports_main`: `api/adapters/bad.py` = `from api.main import app` →
  `("api/adapters/bad.py: adapters must not import api.main",)`.
- `test_dependencies_ml_rejects_application`: `ml/bad.py` = `from api.application.analyze import AnalyzeComment` →
  `("ml/bad.py: ml must not import api.application.analyze",)`.
- `test_dependencies_ml_allows_domain_and_third_party`: `ml/ok.py` = `from api.domain.entities import Polarity` plus
  `import sklearn` → `()`.
- `test_dependencies_bare_api_import_rejected`: `api/domain/pkg.py` = `from api import domain` →
  `("api/domain/pkg.py: domain must not import api",)`.
- `test_dependencies_syntax_error_propagates`: `api/domain/broken.py` = `def (` → `pytest.raises(SyntaxError)` around
  `dependency_violations(tree)`.

`test_size_limits.py`:
- `test_size_limits_repository_within_limits`: `size_violations(REPO_ROOT)` → `()`.
- `test_size_limits_module_301_lines_rejected`: `api/domain/long.py` = 301 lines `X = 1` →
  `("api/domain/long.py: 301 lines > 300",)`.
- `test_size_limits_module_300_lines_accepted`: 300 such lines → `()`.
- `test_size_limits_exempt_module_accepted`: `ml/schemas.py` with 301 lines → `()`.
- `test_size_limits_class_151_lines_rejected`: `api/domain/big.py` = line `class Big:` plus 150 lines `    a = 1` →
  `("api/domain/big.py:1: class Big has 151 lines > 150",)`.
- `test_size_limits_class_150_lines_accepted`: `class Big:` plus 149 lines → `()`.

`test_security_grep.py` (runs `subprocess.run(["bash", str(REPO_ROOT / "scripts/security_grep.sh"), str(tree)],
capture_output=True, text=True, check=False)`; the base tree holds copies of the repository `.gitignore`,
`requirements.txt` and `requirements-dev.txt`):
- `test_security_grep_clean_tree_passes`: base tree plus `api/domain/ok.py` = `X = 1` → exit 0, stdout `""`.
- `test_security_grep_empty_tree_passes`: base tree only → exit 0, stdout `""`.
- `test_security_grep_detects_violation` (parametrized; each case: planted path, body, expected stdout prefix; exit
  1): `api/adapters/up.py` `from fastapi import UploadFile` → `SECURITY FAIL SEC-01`; `ml/train.py`
  `def main() -> int:` → `SECURITY FAIL SEC-04: os.umask(0o077) missing in ml/train.py`; `api/adapters/log.py`
  `handler = logging.FileHandler("x.log")` → `SECURITY FAIL SEC-05`; `api/adapters/out.py` `print("x")` →
  `SECURITY FAIL SEC-05`; `ml/io.py` `import pickle` → `SECURITY FAIL SEC-13`; `scripts/run.py` `value = eval("1")` →
  `SECURITY FAIL SEC-13`; `api/adapters/other.py` `bundle = joblib.load(path)` → `SECURITY FAIL SEC-14`;
  `ml/emb.py` `weights = torch.load(path)` → `SECURITY FAIL SEC-15`; `api/main.py` `os.umask(0o077)` →
  `SECURITY FAIL SEC-16`; `web/app.js` `node.innerHTML = text;` → `SECURITY FAIL SEC-22: forbidden construct in web/`.
- `test_security_grep_allows_model_store`: `api/adapters/model_store.py` = `bundle = joblib.load(path)` → exit 0.
- `test_security_grep_gitignore_entry_missing`: `.gitignore` without the `.env` line → exit 1, stdout contains
  `SECURITY FAIL SEC-10: .gitignore lacks .env`.
- `test_security_grep_spacy_url_missing`: `requirements.txt` without its `es_core_news_sm` line → stdout contains
  `SECURITY FAIL SEC-17`.
- `test_security_grep_unpinned_line`: `requirements-dev.txt` with an added line `ruff>=0.17` → stdout contains
  `SECURITY FAIL SEC-18`.
- `test_security_grep_missing_dev_requirements`: base tree without `requirements-dev.txt` → exit 1, stdout contains
  `SECURITY FAIL SEC-18`.
- `test_security_grep_ignores_non_matching_files`: base tree plus `api/adapters/note.txt` = `import pickle` and
  `api/__pycache__/x.pyc` = `eval(` → exit 0, stdout `""`.
- `test_security_grep_missing_root_exits_2`: `ROOT` = `tmp_path / "nope"` → exit 2.

## Out of scope

- `scripts/verify_clean_env.sh`, `scripts/benchmark.py`, `scripts/smoke_docker.sh` (specs 028 and 030).
- Checks of `security-rules.md` §8 that need judgment (SEC-02, 03, 06, 07, 08, 09, 11, 12, 20, 21) and the "first
  instruction" order of SEC-04 and SEC-16.
- Changing `CONTEXT.md`, `pyproject.toml` or the rectors. Ruff rule S404 for the `subprocess` import in tests is
  handled by spec 000 (`tests/**` ignore list).

## Definition of Done

- [ ] Architecture tests: `.venv/bin/pytest -q tests/architecture` prints `38 passed`, exit code 0 (13 in
  `test_dependencies.py`, 6 in `test_size_limits.py`, 19 in `test_security_grep.py`).
- [ ] Full suite: `.venv/bin/pytest -q -m "not integration"` prints `38 passed`, exit code 0.
- [ ] Linter: `.venv/bin/ruff check .` prints `All checks passed!`.
- [ ] Formatter: `.venv/bin/ruff format --check .` exits 0.
- [ ] Type checker: `.venv/bin/mypy --strict tests` prints `Success: no issues found in 3 source files` (`api` and
  `ml` hold no module yet).
- [ ] No new suppressions: `grep -rn "noqa\|type: ignore" --include="*.py" --exclude-dir=.venv .` prints nothing.
- [ ] Coverage: not applicable: this spec adds no module under `api/` or `ml/`.
- [ ] Security grep: `bash scripts/security_grep.sh; echo $?` prints only `0`.
- [ ] Gate order: `grep -c "^\.venv/bin/\|^bash scripts/security_grep.sh$\|^echo \"GATE OK\"$" scripts/gate.sh`
  prints `8`; `head -2 scripts/gate.sh` prints `#!/usr/bin/env bash` and `set -euo pipefail`.
- [ ] Gate stop: `bash scripts/gate.sh > /dev/null 2>&1; echo $?` prints `2` (mypy, step 3; expected until
  `api/` and `ml/` hold modules; the full Gate prints `GATE OK` once specs 002 and 007 are implemented).
