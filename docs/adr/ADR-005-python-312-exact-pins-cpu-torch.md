# ADR-005 — Python 3.12, exact pins and CPU-only torch

Status: Accepted (2026-11-05)

## Context

SEC-18 requires every direct and transitive dependency pinned with `==`. The system host has Python 3.14; the
scientific stack has the widest wheel coverage on 3.12. Default PyPI torch wheels for Linux pull CUDA packages that
the CPU-only service never uses.

## Decision

1. The project runs on CPython 3.12 (3.12.14 at the time of writing), created with
   `uv venv --python 3.12 --seed .venv`; `pyproject.toml` sets `requires-python = "==3.12.*"` and ruff
   `target-version = "py312"`.
2. Pins are resolved with `uv pip compile --python 3.12` and written as exact `==` lines to `requirements.txt`
   (runtime) and `requirements-dev.txt` (development); `CONTEXT.md` lists the main pins.
3. torch is installed as `torch==2.15.0+cpu` from `--extra-index-url https://download.pytorch.org/whl/cpu`.
4. Packages are namespace packages with no `__init__.py`.

## Consequences

- pip-audit reports torch as "not found on PyPI and could not be audited"; torch advisories are checked by hand at
  each pin change.
- The `--extra-index-url https://download.pytorch.org/whl/cpu` line is the single allowed non-`==` line in
  `requirements.txt`; the SEC-18 grep in `security-rules.md` §8 admits exactly that line (owner decision 2026-11-05).
- Upgrading any pin means recompiling both files and retraining (ADR-003).
