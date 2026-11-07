#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
.venv/bin/ruff format --check .
.venv/bin/ruff check .
.venv/bin/mypy --strict api ml tests
.venv/bin/pytest -q tests/architecture
.venv/bin/pytest -q -m "not integration" --cov=api --cov=ml --cov-report=term-missing --cov-fail-under=80
bash scripts/security_grep.sh
.venv/bin/pip-audit -r requirements.txt --disable-pip --no-deps
echo "GATE OK"
