# 000 - Tooling and pins
Riesgo: alto

## Objective

The repository has no tooling yet: no `pyproject.toml`, no requirements files, no `.gitignore` and no
`config/app.json`. SEC-18 requires every direct and transitive dependency pinned with `==`, SEC-10 requires six
ignored paths, and `ARCHITECTURE.md` §6 fixes size limits that the linter must enforce. When this spec is done the
project has exact pins (75 runtime, 44 development, 103 distinct), tool configuration for ruff, mypy and pytest that
encodes `ARCHITECTURE.md` §6, the ignore rules of SEC-10 and the configuration file of `docs/contracts.md` §7. A
fresh `.venv` installs with exit code 0.

## Depends on

None.

## Governing files

- `ARCHITECTURE.md` §5 (folders), §6 (names, size, types, docstrings, errors, logging, imports), §7 (configuration).
- `security-rules.md` SEC-10, SEC-17, SEC-18, SEC-19.
- `ADR-005` (Python 3.12, `==` pins, CPU torch index, namespace packages).
- `docs/contracts.md` §7 (content of `config/app.json`).

## Files to create/modify

1. `pyproject.toml` (new)
2. `requirements.txt` (new)
3. `requirements-dev.txt` (new)
4. `.gitignore` (new)
5. `config/app.json` (new)

No reference file of the same kind exists in the repository. No existing test changes.

## External dependencies

Development machine: `uv` 0.12.19 (`uv --version` prints `uv 0.12.19`) and the uv-managed CPython 3.12.14. Python
packages: the pins below, no others.

## Interfaces and types

### `pyproject.toml` (exact tables and keys, in this order)

| Table | Key = value |
|---|---|
| `[project]` | `name = "from-comment-to-action"`, `version = "0.1.0"`, `requires-python = "==3.12.*"` |
| `[tool.ruff]` | `target-version = "py312"`, `line-length = 100` |
| `[tool.ruff.lint]` | `select = ["E", "W", "F", "I", "N", "UP", "B", "C90", "PLR", "BLE", "S", "T20", "D", "TID"]`, `ignore = ["D107", "N803", "N806"]` |
| `[tool.ruff.lint.per-file-ignores]` | `"tests/**" = ["D", "S101", "S603", "S607", "PLR2004"]`, `"scripts/**" = ["T201"]`, `"api/main.py" = ["BLE001"]`, `"ml/train.py" = ["T201", "BLE001"]`, `"ml/artifact.py" = ["T201", "BLE001"]`, `"ml/gold.py" = ["T201", "BLE001"]`, `"ml/gold_eval.py" = ["T201", "BLE001"]`, `"ml/representations.py" = ["T201", "BLE001"]` |
| `[tool.ruff.lint.pydocstyle]` | `convention = "google"` |
| `[tool.ruff.lint.isort]` | `required-imports = ["from __future__ import annotations"]` |
| `[tool.ruff.lint.flake8-tidy-imports]` | `ban-relative-imports = "all"` |
| `[tool.ruff.lint.mccabe]` | `max-complexity = 8` |
| `[tool.ruff.lint.pylint]` | `max-statements = 20`, `max-args = 6`, `max-branches = 8` |
| `[tool.mypy]` | `python_version = "3.12"`, `strict = true`, `explicit_package_bases = true` |
| `[[tool.mypy.overrides]]` | `module = ["sklearn.*", "pandas.*", "scipy.*", "joblib.*", "mapie.*"]`, `ignore_missing_imports = true` |
| `[tool.pytest.ini_options]` | `pythonpath = ["."]`, `addopts = "--import-mode=importlib"`, `testpaths = ["tests"]`, `markers = ["integration: needs the trained bundle and the embedding cache"]` |

`pyproject.toml` carries exactly five TOML comments, each on its own line directly above the key it explains, with this
literal text and no other comment in the file:
1. Above `ignore` in `[tool.ruff.lint]`: `# D107: Google style documents constructor arguments in the class
   docstring. N803, N806: ARCHITECTURE.md section 6 allows X for feature matrices.` (one line)
2. Above `"api/main.py"` in `[tool.ruff.lint.per-file-ignores]`: `# api/main.py and the four ml command-line modules:
   ARCHITECTURE.md section 6 allows a generic catch (and print in ml main()) only there.` (one line)
3. Above `"tests/**"` in the same table: `# tests use assert, literal expected values and subprocess with list
   arguments.` (one line)
4. Above `[[tool.mypy.overrides]]`: `# These five packages ship no py.typed marker at the pinned versions (checked on
   2026-11-05); numpy, torch, spacy, sentence_transformers, fastapi, pydantic, starlette, uvicorn and httpx ship one
   and are type-checked.` (one line)
5. Above `[tool.pytest.ini_options]`: `# pytest runs from the repository root; integration tests are outside the
   Gate.` (one line)

There is no `[build-system]` table: the project is not installed as a package.

### `config/app.json`

The value below (`docs/contracts.md` §7), written as `json.dumps(value, indent=2)` produces it plus one final newline:
`{"costs": {"error_cost": 5.0, "review_cost": 1.0, "review_if_set_not_singleton": true}, "conformal": {"alpha":
0.1}, "limits": {"max_text_chars": 2000, "max_upload_bytes": 2097152, "max_upload_rows": 5000}, "models_dir":
"models"}`.

## Expected behavior

1. Runtime pins. Run, from the repository root (network needed):
   `printf '%s\n' scikit-learn==1.9.1 numpy==2.5.4 joblib==1.6.0 mapie==1.6.0 scipy==1.18.1 pandas==3.1.1
   spacy==3.8.18 sentence-transformers==6.2.0 torch==2.15.0+cpu fastapi==0.162.0 uvicorn==0.54.0 pydantic==2.14.3
   | uv pip compile --python 3.12 - --index-strategy unsafe-best-match --extra-index-url
   https://download.pytorch.org/whl/cpu --no-header --no-annotate --exclude-newer 2026-11-06T00:00:00Z -q`
   (one shell line). The output is 75 lines of `name==version`, sorted by name.
2. Write `requirements.txt` with exactly 77 lines: line 1 `--extra-index-url https://download.pytorch.org/whl/cpu`;
   lines 2 to 76 the 75 lines of step 1 unchanged; line 77
   `es_core_news_sm @ https://github.com/explosion/spacy-models/releases/download/es_core_news_sm-3.8.0/es_core_news_sm-3.8.0-py3-none-any.whl#sha256=e451a83d6df79b87e9eed0cb553f03e99e36a3bab18a7b79f0dcfd1fdf875e12`.
   The file ends with one newline. Its SHA-256 is
   `216c0cbafc05811e644be5760d015bdf95398196d89583027ac26bd3889afac7`.
3. Development pins. Run
   `printf '%s\n' ruff==0.17.4 mypy==2.4.1 pytest==9.2.0 pytest-cov==7.1.0 httpx==0.28.1 pip-audit==2.10.1 |
   uv pip compile --python 3.12 - --no-header --no-annotate --exclude-newer 2026-11-06T00:00:00Z -q` and write its
   44 output lines unchanged to `requirements-dev.txt` (final newline). SHA-256:
   `9b7810cb5133efbe5f0fd81c4d7eab795acb71cfa4a495a3b0a2326d3708642c`. The 16 packages present in both files
   (`anyio`, `certifi`, `charset-normalizer`, `filelock`, `h11`, `httpcore`, `httpx`, `idna`, `markdown-it-py`,
   `mdurl`, `packaging`, `pygments`, `requests`, `rich`, `typing-extensions`, `urllib3`) carry the same version in
   both files.
4. Write `.gitignore` with these 13 lines in this order: `# SEC-10`, `data/`, `reports/`,
   `models/v*/bundle.joblib`, `.venv/`, `__pycache__/`, `.env`, an empty line, `# Tool caches`, `.mypy_cache/`,
   `.ruff_cache/`, `.pytest_cache/`, `.coverage`. The file ends with one newline.
5. Write `pyproject.toml` with the tables above and `config/app.json` with the JSON above.
6. Virtual environment (the commands of `CONTEXT.md`, documented there; no new file):
   `uv venv --python 3.12 --seed .venv`, then `.venv/bin/pip install -r requirements.txt -r requirements-dev.txt`.
   The environment then holds 104 distributions (the 103 distinct pins plus `es_core_news_sm`); `pip freeze --all`
   lists all 104 (plain `pip freeze` skips only `pip` and lists 103 lines, `setuptools` included).
7. Package skeleton: `api/`, `ml/`, `tests/` and `scripts/` are namespace packages (PEP 420). No `__init__.py` is
   created anywhere. Directories are not pre-created: git tracks no empty directory, and each directory appears with
   its first module in the spec that creates it.

## Edge cases and error handling

- If step 1 or step 3 produces any line that differs from the expected SHA-256 result, the implementer stops and
  reports the `diff` against the expected file; the pins are not edited by hand.
- `pip-audit` skips two entries by design: `torch` ("Dependency not found on PyPI and could not be audited: torch
  (2.15.0+cpu)", ADR-005) and `es-core-news-sm` ("URL requirements cannot be pinned to a specific package
  version"). Both skips are expected; the command still prints `No known vulnerabilities found` and exits 0.
- `requirements.txt` holds exactly two lines without `==`: the `--extra-index-url` line and the `@ https://` line;
  the SEC-18 grep admits both.
- `models/v001/manifest.json`, `models/registry.json`, `Dataset/*.csv` and `config/app.json` MUST stay tracked
  (not ignored).
- With no `.py` file yet, `.venv/bin/mypy --strict api ml tests` exits with a non-zero code and
  `.venv/bin/pytest` exits 5 and prints the line `PytestConfigWarning: No files were found in testpaths` and the
  final line `1 warning in <t>s`; both are expected at this spec.

## Acceptance tests (prose)

No Python test is added: this spec creates configuration only. Each check below is a shell command with its result.

- `test_pins_runtime_hash`: `sha256sum requirements.txt` prints
  `216c0cbafc05811e644be5760d015bdf95398196d89583027ac26bd3889afac7`.
- `test_pins_dev_hash`: `sha256sum requirements-dev.txt` prints
  `9b7810cb5133efbe5f0fd81c4d7eab795acb71cfa4a495a3b0a2326d3708642c`.
- `test_pins_counts`: `grep -c "==" requirements.txt requirements-dev.txt` prints `requirements.txt:75` and
  `requirements-dev.txt:44`.
- `test_pins_manifest_libraries`: `grep -E "^(scikit-learn|numpy|joblib|mapie|torch)==" requirements.txt` prints
  `joblib==1.6.0`, `mapie==1.6.0`, `numpy==2.5.4`, `scikit-learn==1.9.1`, `torch==2.15.0+cpu`.
- `test_gitignore_sec10`: `grep -cxF -e 'data/' -e 'reports/' -e 'models/v*/bundle.joblib' -e '.venv/' -e
  '__pycache__/' -e '.env' .gitignore` prints `6`.
- `test_gitignore_hash`: `sha256sum .gitignore` prints
  `891a9d673f2e18669ce319cff5a11b20392da49cf568ce81aa6d3fe403d7b3ff`.
- `test_pyproject_values`: `.venv/bin/python -c "import tomllib; d = tomllib.load(open('pyproject.toml', 'rb')); r =
  d['tool']['ruff']; l = r['lint']; assert r['line-length'] == 100 and r['target-version'] == 'py312'; assert
  l['mccabe']['max-complexity'] == 8 and l['pylint'] == {'max-statements': 20, 'max-args': 6, 'max-branches': 8};
  assert l['ignore'] == ['D107', 'N803', 'N806'] and l['pydocstyle']['convention'] == 'google'; assert
  l['per-file-ignores']['tests/**'] == ['D', 'S101', 'S603', 'S607', 'PLR2004'] and
  l['per-file-ignores']['api/main.py'] == ['BLE001']; assert d['tool']['mypy']['strict'] is True; assert
  d['tool']['pytest']['ini_options']['testpaths'] == ['tests']; print('PYPROJECT OK')"` prints `PYPROJECT OK`.
  `grep -c "^#" pyproject.toml` prints `5`.
- `test_gitignore_bundle_ignored`: `git check-ignore -q models/v001/bundle.joblib` exits 0.
- `test_gitignore_manifest_tracked`: `git check-ignore -q models/v001/manifest.json` exits 1; the same for
  `models/registry.json` and `config/app.json`.
- `test_config_parses`: `.venv/bin/python -m json.tool config/app.json` exits 0 and prints the 4 top-level keys
  `costs`, `conformal`, `limits`, `models_dir`.
- `test_pins_non_pinned_lines`: `grep -vc "==" requirements.txt` prints `2`; `grep -vc "==" requirements-dev.txt`
  prints `0`.
- `test_gitignore_dataset_tracked`: `git check-ignore -q Dataset/feedback_curso_universitario.csv` exits 1; the same
  for `Dataset/feedback_curso_universitario2.csv` and `Dataset/feedback_curso_universitario3.csv`.
- `test_config_hash`: `sha256sum config/app.json` prints
  `a5e52bec86b15e15067d1d4ca66f79d1eb2d0c8450dc16a9c8ef531e8a9508e0`.
- `test_venv_python`: `.venv/bin/python --version` prints `Python 3.12.14`.
- `test_venv_consistent`: `.venv/bin/pip check` prints `No broken requirements found.`; `.venv/bin/pip freeze --all |
  wc -l` prints `104`.
- `test_tools_versions`: `.venv/bin/ruff --version` prints `ruff 0.17.4`; `.venv/bin/mypy --version` starts with
  `mypy 2.4.1`; `.venv/bin/pytest --version` prints `pytest 9.2.0`.
- `test_no_init_files`: `find . -name __init__.py -not -path "./.venv/*"` prints nothing.

## Out of scope

- `README.md` (spec 030), `Dockerfile` and `docker-compose.yml` (spec 028), `scripts/gate.sh` and
  `scripts/security_grep.sh` (spec 001).
- Any Python module, test or directory placeholder file.
- Hash-pinning (`--require-hashes`) of the requirements files.
- Editing `CONTEXT.md`, the rectors or `docs/contracts.md`.

## Definition of Done

- [ ] All checks of "Acceptance tests (prose)" give their stated result.
- [ ] Install: `.venv/bin/pip install -r requirements.txt -r requirements-dev.txt` exits 0.
- [ ] Tests: not applicable at this spec (`.venv/bin/pytest -q -m "not integration"` exits 5, prints the
  `PytestConfigWarning` line `No files were found in testpaths` and the final line `1 warning in <t>s`; this warning
  is expected at this spec).
- [ ] Linter: `.venv/bin/ruff check .` prints `All checks passed!` with no warning line about the configuration.
- [ ] Formatter: `.venv/bin/ruff format --check .` exits 0.
- [ ] Type checker: not applicable at this spec (no `.py` file); `.venv/bin/mypy --version` prints `mypy 2.4.1
  (compiled: yes)`.
- [ ] No new suppressions: `grep -rn "noqa\|type: ignore" --include="*.py" --exclude-dir=.venv .` prints nothing.
- [ ] Coverage: not applicable: this spec adds no Python code.
- [ ] SEC-18: `grep -vnE "^\s*(#|$|.*==|.*@ https://|--extra-index-url https://download\.pytorch\.org/whl/cpu$)"
  requirements.txt requirements-dev.txt` prints nothing.
- [ ] SEC-19: `.venv/bin/pip-audit -r requirements.txt --disable-pip --no-deps` prints `No known vulnerabilities
  found` and exits 0 (network).
- [ ] SEC-17: `grep -c "^es_core_news_sm @ https://" requirements.txt` prints `1`.
