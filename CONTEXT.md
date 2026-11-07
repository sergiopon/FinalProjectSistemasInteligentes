# Context — FinalProjectTecEmergentes ("From comment to action")

## Stack

- Python 3.12 (`cpython-3.12.14`, installed by uv) on Linux; the virtual environment is `.venv` (ADR-005).
- Training (`ml/`): scikit-learn, MAPIE (cross-conformal classification), pandas, numpy, scipy, joblib,
  sentence-transformers on CPU-only torch, spaCy with `es_core_news_sm`.
- Service (`api/`): FastAPI on uvicorn, pydantic settings and HTTP schemas; static web UI in `web/` (ADR-004).
- Development tools: ruff (lint and format), mypy `--strict`, pytest with pytest-cov, httpx (FastAPI test client),
  pip-audit.
- Contracts shared by every spec: `docs/contracts.md`. Web UI design: `DESIGN.md`.

## Pinned versions

Resolved on 2026-11-05 with `uv pip compile --python 3.12` (uv 0.12.19), PyPI plus the PyTorch CPU index
`https://download.pytorch.org/whl/cpu`. The full `requirements.txt` (75 pins) and `requirements-dev.txt` are created by
spec 000; runtime and development resolutions were checked together (103 pins, no conflict).

| Package | Pin | File | Notes |
|---|---|---|---|
| scikit-learn | `==1.9.1` | requirements.txt | Checked in manifest (SEC-14) |
| numpy | `==2.5.4` | requirements.txt | Checked in manifest (SEC-14) |
| joblib | `==1.6.0` | requirements.txt | Checked in manifest (SEC-14) |
| mapie | `==1.6.0` | requirements.txt | Checked in manifest (SEC-14). API verified by import: `mapie.classification.CrossConformalClassifier(estimator, confidence_level=0.9, conformity_score="lac", cv=StratifiedGroupKFold(...), random_state=42)`, `.fit_conformalize(X, y, groups=groups)`, `.predict_set(X, agg_scores="mean") -> (y_pred (n,), y_set (n, 3, 1) bool)`. It has no `predict_proba`. |
| scipy | `==1.18.1` | requirements.txt | |
| pandas | `==3.1.1` | requirements.txt | |
| spacy | `==3.8.18` | requirements.txt | |
| es_core_news_sm | `3.8.0` | requirements.txt | Line: `es_core_news_sm @ https://github.com/explosion/spacy-models/releases/download/es_core_news_sm-3.8.0/es_core_news_sm-3.8.0-py3-none-any.whl#sha256=e451a83d6df79b87e9eed0cb553f03e99e36a3bab18a7b79f0dcfd1fdf875e12` (URL returns 200, 12,884,212 bytes; `compatibility.json` lists 3.8.0 for spaCy 3.8) |
| sentence-transformers | `==6.2.0` | requirements.txt | |
| torch | `==2.15.0+cpu` | requirements.txt | Needs the line `--extra-index-url https://download.pytorch.org/whl/cpu`; pip-audit skips it ("not found on PyPI") |
| transformers | `==5.22.1` | requirements.txt | Transitive |
| huggingface-hub | `==2.4.0` | requirements.txt | Transitive |
| fastapi | `==0.162.0` | requirements.txt | starlette `==1.10.0` transitive |
| uvicorn | `==0.54.0` | requirements.txt | |
| pydantic | `==2.14.3` | requirements.txt | pydantic-core `==2.50.4` transitive |
| ruff | `==0.17.4` | requirements-dev.txt | |
| mypy | `==2.4.1` | requirements-dev.txt | |
| pytest | `==9.2.0` | requirements-dev.txt | |
| pytest-cov | `==7.1.0` | requirements-dev.txt | |
| httpx | `==0.28.1` | requirements-dev.txt | Also transitive in runtime |
| pip-audit | `==2.10.1` | requirements-dev.txt | |

Embedding model (SEC-17): `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, revision
`e8f8c211226b894fcb81acc59f3b34ba3efd5f42` (Hugging Face API, `lastModified` 2026-01-28), license apache-2.0, 384
dimensions, mean pooling, `max_seq_length` 128 tokens, `model.safetensors` 470,641,600 bytes.

PENDING TO VALIDATE: an `import sentence_transformers` and one `encode` call at these pins (torch was resolved, not
installed); `pip-audit -r requirements.txt` without `--disable-pip --no-deps` (it installs the full set into a
temporary environment).

## Commands

All commands run from the repository root; every Python tool runs from `.venv/bin/`.

| Purpose | Command | Expected result |
|---|---|---|
| Create venv | `uv venv --python 3.12 --seed .venv` | `.venv/bin/python --version` prints `Python 3.12.14` |
| Install | `.venv/bin/pip install -r requirements.txt -r requirements-dev.txt` | Exit code 0 |
| Download embeddings | `.venv/bin/python -m ml.representations --download` | Model cached at the pinned revision (network) |
| Tests | `.venv/bin/pytest -q -m "not integration"` | `N passed`, exit code 0 |
| Integration tests | `.venv/bin/pytest -q -m integration` | `N passed` (needs a trained bundle and the embedding cache) |
| Coverage | `.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing` | `TOTAL` line ≥ 80 % |
| Linter | `.venv/bin/ruff check .` | `All checks passed!` |
| Formatter | `.venv/bin/ruff format --check .` | Exit code 0 (fix with `.venv/bin/ruff format .`) |
| Type checker | `.venv/bin/mypy --strict api ml tests` | `Success: no issues found in N source files` |
| Architecture test | `.venv/bin/pytest -q tests/architecture` | `N passed` |
| Security grep | `bash scripts/security_grep.sh` | No output, exit code 0 |
| Audit | `.venv/bin/pip-audit -r requirements.txt --disable-pip --no-deps` | `No known vulnerabilities found` |
| Gate | `bash scripts/gate.sh` | Last line `GATE OK`, exit code 0 |
| Train | `.venv/bin/python -m ml.train` | New `models/vNNN/` and `models/registry.json` updated |
| Activate / rollback | `.venv/bin/python -m ml.artifact activate v001` / `.venv/bin/python -m ml.artifact rollback` | Registry `active` changes |
| Verify bundle | `.venv/bin/python -m ml.artifact verify v001` | Exit code 0 |
| Gold set | `.venv/bin/python -m ml.gold sample` / `.venv/bin/python -m ml.gold agreement` | `gold/` files written |
| Serve | `.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000` | `GET /health` returns 200 |
| Clean environment | `bash scripts/verify_clean_env.sh` | Exit code 0 |
| Docker | `docker compose up --build` then `bash scripts/smoke_docker.sh` | Exit code 0 |

`Gate` (`scripts/gate.sh`, `set -euo pipefail`, stops at the first failure) runs, in this order:
1. `.venv/bin/ruff format --check .`
2. `.venv/bin/ruff check .`
3. `.venv/bin/mypy --strict api ml tests`
4. `.venv/bin/pytest -q tests/architecture` (dependency rule and size limits)
5. `.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing --cov-fail-under=80`
6. `bash scripts/security_grep.sh` (the `grep` commands of `security-rules.md` §8)
7. `.venv/bin/pip-audit -r requirements.txt --disable-pip --no-deps` (network)
8. `echo "GATE OK"`

## Structure

- Layers, packages and the dependency rule: `ARCHITECTURE.md` §2; folders: `ARCHITECTURE.md` §5.
- No `__init__.py` files: `api/`, `ml/` and `tests/` are namespace packages (PEP 420). `pyproject.toml` sets pytest
  `pythonpath = ["."]` and `addopts = "--import-mode=importlib"`, and mypy `explicit_package_bases = true`.
- Tests mirror the source: `tests/unit/domain/test_entities.py` tests `api/domain/entities.py`.
- `Dataset/`: three course CSV files read by `ml` and integration tests; `Dataset/__MACOSX/` is ignored (only
  `Dataset/*.csv` at the top level is read).
- `specs/`: one spec per change, index in `specs/README.md`.

## Environment

- No `.env` and no API keys. Configuration: `config/app.json` (`docs/contracts.md` §7).
- Network only for install, `ml.representations --download`, `pip-audit` and the Docker build (SEC-16).
- Embedding cache: the Hugging Face default (`~/.cache/huggingface`); `HF_HOME` overrides it.
- Tests need no network and no downloaded model, except tests marked `integration` (marker registered in
  `pyproject.toml`), which need the trained bundle and the embedding cache and are outside the `Gate`.
- Branches: one spec per `feature/NNN-slug` branch, merged into `main` with `git merge --no-ff`.
