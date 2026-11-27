#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

fail() {
  echo "CLEAN ENV FAIL: $1" >&2
  exit 1
}

[ -z "$(git status --porcelain --untracked-files=no)" ] || fail "commit or stash tracked changes first"
[ -f models/registry.json ] || fail "no trained model; run .venv/bin/python -m ml.train"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
mkdir "$WORK/repo"
git archive --format=tar HEAD | tar -x -C "$WORK/repo"
mkdir -p "$WORK/repo/models"
cp -a models/. "$WORK/repo/models/"

cd "$WORK/repo"
uv venv --python 3.12 --seed .venv
[ "$(.venv/bin/python --version)" = "Python 3.12.14" ] || fail "expected Python 3.12.14"
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/pip check
.venv/bin/pytest -q -m "not integration"

active="$(.venv/bin/python -c 'import json, pathlib; print(json.loads(pathlib.Path("models/registry.json").read_text(encoding="utf-8"))["active"])')"
HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m ml.artifact verify "$active"

echo "CLEAN ENV OK"
