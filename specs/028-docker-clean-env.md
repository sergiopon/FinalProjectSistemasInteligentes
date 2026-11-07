# 028 - Docker and clean environment
Riesgo: alto

## Objective

The guide asks to load the model in a clean environment and to deploy the service (`docs/analysis.md` §1, unit 7:
"Same predictions in a clean environment"). `CONTEXT.md` lists `docker compose up --build`,
`bash scripts/smoke_docker.sh` and `bash scripts/verify_clean_env.sh`, and `README.md` (spec 030) promises that
Compose publishes port 8000 on `127.0.0.1` only and that the container runs with the user's id. None of these files
exists. After this spec: the image installs the pinned runtime set and the pinned embedding revision at build time,
the container runs offline as the host user and binds the host port on `127.0.0.1` only (SEC-04, SEC-16), the
smoke script checks a running container, and the clean-environment script rebuilds a fresh venv from the committed
tree, runs the unit tests and re-verifies the active bundle's smoke predictions.

## Depends on

024 (`api.main:app`). The runtime checks of the Definition of Done also need a trained bundle (spec 014) and
`ml.representations --download` (spec 009).

## Governing files

- `ARCHITECTURE.md` §5 (`Dockerfile`, `docker-compose.yml` at the root; `scripts/smoke_docker.sh`,
  `scripts/verify_clean_env.sh`), §7 (`models_dir` `"models"`, resolved under the repository root `/app`).
- `security-rules.md` SEC-03 (nothing persisted: models mounted read-only), SEC-04 (`user: "${UID:-1000}"`),
  SEC-05, SEC-08 (no `.env`, bundle or `.git` in the build context), SEC-10, SEC-13 (no `eval(`, `exec(`,
  `pickle`, `shell=True` in `scripts/`), SEC-14 (the bundle is loaded from `models/` by `TrustedModelStore`),
  SEC-16 (offline flags in the Dockerfile; `0.0.0.0` only inside the container; `127.0.0.1:8000:8000`), SEC-17,
  SEC-18 (image installs `requirements.txt` only).
- ADR-003 (the container never trains), ADR-005. `CONTEXT.md` "Commands" (Docker, Clean environment).

## Files to create/modify

1. `Dockerfile` (new). No file of this kind exists; content fixed below.
2. `docker-compose.yml` (new).
3. `.dockerignore` (new).
4. `scripts/smoke_docker.sh` (new). Same header as `scripts/gate.sh` (spec 001).
5. `scripts/verify_clean_env.sh` (new). Same header as `scripts/gate.sh`.

No existing test changes expectation.

## External dependencies

- Base image `python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e`
  (index digest read with `docker buildx imagetools inspect` on 2026-11-07). Docker 29.9.2, Compose v5.6.1, uv
  0.12.19 on the host. No new Python package.
- Verified on 2026-11-07 by building that base with the 77-line `requirements.txt` of spec 000 (SHA-256
  `216c0cbafc05811e644be5760d015bdf95398196d89583027ac26bd3889afac7`): `pip install -r requirements.txt` exits 0
  (torch `2.15.0+cpu` from the CPU index line, `es_core_news_sm` from its URL); a Hugging Face download with
  `os.umask(0o077)` leaves files `0600` owned by root, unreadable for uid 1000 until `chmod -R a+rX`; after it,
  `--user 1000 --network none --cap-drop ALL --security-opt no-new-privileges:true --read-only --tmpfs /tmp` with
  `HF_HOME=/opt/hf` and both offline flags loads the pinned revision with `local_files_only=True`, encodes to
  `(1, 384) float32`, and loads `es_core_news_sm`; without `--tmpfs /tmp` it fails with `FileNotFoundError: No
  usable temporary directory found`. `HOME` is `/` for uid 1000. Python reports `3.12.14`.
- Verified with Compose v5.6.1: with `UID` not exported (bash does not export it), `user: "${UID:-1000}"` resolves
  to `"1000"`; `docker compose port api 8000` prints `127.0.0.1:8000` for `"127.0.0.1:8000:8000"`; a `0700` bind
  mount owned by uid 1000 is readable through `:ro` by `user: "1000"`. uvicorn 0.54.0 inserts `--app-dir` (default
  `""`, the working directory) at `sys.path[0]`, so `api.main:app` imports from `/app`.
- An allowlist `.dockerignore` (`*` then `!dir/`) sends only the listed paths; a missing listed directory is not an
  error (verified with `docker build`).

## Interfaces and types

`.dockerignore`, exactly these 7 lines: `*`, `!requirements.txt`, `!api/`, `!ml/`, `!web/`, `!config/`,
`**/__pycache__`.

`Dockerfile`, exactly these instructions in this order (one per line, no others, no comments):
1. `FROM python:3.12.14-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e`
2. `ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 HF_HOME=/opt/hf`
3. `WORKDIR /app`
4. `COPY requirements.txt ./`
5. `RUN pip install -r requirements.txt`
6. `COPY . .`
7. `RUN python -m ml.representations --download && chmod -R a+rX /opt/hf`
8. `ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1`
9. `USER 1000`
10. `EXPOSE 8000`
11. `CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]`

`docker-compose.yml`, exactly one service `api` with these keys in this order: `build: .`; `image:
from-comment-to-action:0.1.0`; `user: "${UID:-1000}"`; `ports: ["127.0.0.1:8000:8000"]`; `volumes:
["./models:/app/models:ro"]`; `read_only: true`; `tmpfs: ["/tmp"]`; `cap_drop: [ALL]`; `security_opt:
["no-new-privileges:true"]`. No `version` key, no `environment`, no `network_mode`, no other service.

Scripts: first line `#!/usr/bin/env bash`, second `set -euo pipefail`, third `cd "$(dirname "$0")/.."`. Every
failure prints one line to stderr starting `SMOKE FAIL: ` (smoke) or `CLEAN ENV FAIL: ` (clean environment) and
exits 1. Constants in `smoke_docker.sh`: `BASE_URL="http://127.0.0.1:8000"`, `HEALTH_ATTEMPTS=60`,
`HEALTH_INTERVAL_S=2`, `SAMPLE_TEXT="El contenido del curso fue claro y ordenado."` (synthetic, spec 030
`SAMPLE_COMMENTS[0]`).

## Expected behavior

Build and run: `docker compose up --build` builds the image (network only here, SEC-16), installs the runtime pins
(not `requirements-dev.txt`), downloads the embedding revision through `ml.representations` into `/opt/hf` and
makes it world-readable, then starts uvicorn as the host uid on `0.0.0.0:8000` inside the container, published as
`127.0.0.1:8000` on the host. `api.main` reads `/app/config/app.json` and `/app/models` (the host `models/`
directory, read-only); a missing or unverified bundle makes startup fail (uvicorn exit 3, spec 024) and the
container stops. The container writes only to the `/tmp` tmpfs.

`scripts/smoke_docker.sh` (run from another terminal while the container runs), steps in order:
1. `docker compose ps -q api` empty → `SMOKE FAIL: api container is not running`.
2. `docker compose port api 8000` not equal to `127.0.0.1:8000` → `SMOKE FAIL: port 8000 is not bound to
   127.0.0.1 only`.
3. `docker compose exec -T api id -u` not equal to `id -u` → `SMOKE FAIL: container uid differs from host uid
   (export UID before docker compose up)`.
4. `docker compose exec -T api printenv HF_HUB_OFFLINE` and `... TRANSFORMERS_OFFLINE`, each not `1` →
   `SMOKE FAIL: offline flags missing`.
5. Up to `HEALTH_ATTEMPTS` calls of `curl -fsS "$BASE_URL/health"`, `sleep "$HEALTH_INTERVAL_S"` between failed
   ones; the first answer must contain `"status":"ok"`. No success → `SMOKE FAIL: /health did not answer within
   120 s`.
6. `POST /predict` with `Content-Type: application/json` and body `{"text":"<SAMPLE_TEXT>"}`, one `curl -sS -w
   '\n%{http_code}'` call held in a shell variable (last line = status, the rest = body): status `200` and body
   containing `"model_version"`, else `SMOKE FAIL: /predict returned <status>`.
7. `POST /predict` with body `{"text":"   "}`: status `422`, else `SMOKE FAIL: blank text returned <status>`.
8. Prints `SMOKE OK` to stdout; exit 0. Nothing is written to disk.

`scripts/verify_clean_env.sh`, steps in order:
1. `git status --porcelain --untracked-files=no` non-empty → `CLEAN ENV FAIL: commit or stash tracked changes
   first`.
2. `models/registry.json` not a regular file → `CLEAN ENV FAIL: no trained model; run .venv/bin/python -m
   ml.train`.
3. `WORK="$(mktemp -d)"`; `trap 'rm -rf "$WORK"' EXIT`; `mkdir "$WORK/repo"`; `git archive --format=tar HEAD |
   tar -x -C "$WORK/repo"` (committed files only: no `.venv`, no caches); `mkdir -p "$WORK/repo/models"`;
   `cp -a models/. "$WORK/repo/models/"` (adds the untracked `bundle.joblib` files, modes kept).
4. In `$WORK/repo`: `uv venv --python 3.12 --seed .venv`; `.venv/bin/python --version` not `Python 3.12.14` →
   `CLEAN ENV FAIL: expected Python 3.12.14`; `.venv/bin/pip install -r requirements.txt -r
   requirements-dev.txt`; `.venv/bin/pip check`.
5. `.venv/bin/pytest -q -m "not integration"`.
6. `active` = `.venv/bin/python -c` printing `json.loads(Path("models/registry.json").read_text(encoding="utf-8"))
   ["active"]` (SEC-13: `json`); `HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 .venv/bin/python -m ml.artifact verify
   "$active"` (hash, versions and smoke probabilities within 1e-9, spec 013).
7. Prints `CLEAN ENV OK`; exit 0. The `EXIT` trap deletes `$WORK` on success and on failure. A failing command of
   steps 4 to 6 ends the script with that command's exit code (`set -e`) after its own output.

## Edge cases and error handling

| Condition | Result |
|---|---|
| No `models/registry.json` on the host at `docker compose up` | container exits (startup failure, spec 024); smoke step 1 or 5 fails |
| Host uid not 1000 and `UID` not exported | container runs as 1000, cannot read the `0700` models directory, startup fails; smoke step 3 names the fix |
| `web/` absent at build | image builds (allowlist), `GET /` returns 500 (spec 024); smoke does not call `/` |
| `requirements.txt` changed after a bundle was trained | `ModelIntegrityError` at startup (SEC-14); retrain on the host |
| Tracked file modified | `verify_clean_env.sh` step 1 fails, exit 1 |
| Embedding cache missing on the host and the active model uses embeddings | step 6 fails (offline load) |
| `docker` or `curl` missing | the shell's `command not found`, exit 127 |

If an existing test not listed here fails because of this change, the implementer does NOT modify it: report its
name and the reason.

## Acceptance tests (prose)

No Python test is added (configuration and shell only). Each check is a command with its result:
- `test_compose_config_valid`: `docker compose config --quiet` → exit 0.
- `test_compose_user_and_port`: `docker compose config` (with `UID` not exported) contains `user: "1000"`,
  `host_ip: 127.0.0.1`, `target: 8000`, `published: "8000"`, `read_only: true`, `- ALL` under `cap_drop`, and
  `read_only: true` under the `models` bind volume.
- `test_compose_no_wildcard_host`: `grep -c "0.0.0.0" docker-compose.yml` → `0`.
- `test_dockerfile_offline_after_download`: `grep -n "HF_HUB_OFFLINE" Dockerfile` → exactly 1 line, after the
  line holding `ml.representations --download`.
- `test_dockerignore_allowlist`: `head -1 .dockerignore` → `*`; `grep -c "^!" .dockerignore` → `5`.
- `test_image_cache_readable`: after the build, `docker run --rm --entrypoint find from-comment-to-action:0.1.0
  /opt/hf -type f ! -perm -o=r` → no output; `docker run --rm --entrypoint id from-comment-to-action:0.1.0 -u` →
  `1000`.
- `test_image_has_no_secrets_or_bundles`: `docker run --rm --entrypoint sh from-comment-to-action:0.1.0 -c 'ls -a
  /app'` lists no `.env`, `.git`, `.venv`, `models`, `Dataset`, `tests`.
- `test_smoke_passes`: after `.venv/bin/python -m ml.train` and `docker compose up --build -d`,
  `bash scripts/smoke_docker.sh` → last line `SMOKE OK`, exit 0; `ss -ltn` lists `127.0.0.1:8000` and no
  `0.0.0.0:8000`; then `docker compose down`.
- `test_smoke_detects_stopped_container`: after `docker compose down`, `bash scripts/smoke_docker.sh` → exit 1,
  stderr `SMOKE FAIL: api container is not running`.
- `test_clean_env_passes`: with a clean tracked tree and a trained `models/`, `bash scripts/verify_clean_env.sh` →
  last line `CLEAN ENV OK`, exit 0; no `tmp.*` directory created by it remains in `${TMPDIR:-/tmp}`.
- `test_clean_env_rejects_dirty_tree`: after appending one line to `README.md` (reverted afterwards with
  `git checkout -- README.md`), the script → exit 1, stderr `CLEAN ENV FAIL: commit or stash tracked changes first`.
- `test_scripts_syntax`: `bash -n scripts/smoke_docker.sh scripts/verify_clean_env.sh` → exit 0.

## Out of scope

Training inside the image (ADR-003); a registry push or any remote deployment; a Compose `healthcheck`; HTTPS or
authentication; changing `README.md` (spec 030), `CONTEXT.md` or the Gate (the Docker checks need the network and
stay outside it); `requirements-dev.txt` in the image.

## Definition of Done

- [ ] All checks of "Acceptance tests (prose)" give their stated result.
- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0 (no Python file changes).
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0.
- [ ] `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] No new suppressions: no Python file is added or changed (`git diff --stat -- '*.py'` → empty).
- [ ] Coverage: not applicable: this spec adds no module under `api/` or `ml/`.
- [ ] `grep -nE "yaml\.load|pickle|eval\(|exec\(|shell=True" scripts/smoke_docker.sh scripts/verify_clean_env.sh`
      → no output.
- [ ] `head -3 scripts/smoke_docker.sh scripts/verify_clean_env.sh` → each `#!/usr/bin/env bash`,
      `set -euo pipefail`, `cd "$(dirname "$0")/.."`.
- [ ] `bash scripts/security_grep.sh` → no output, exit 0; `bash scripts/gate.sh` → last line `GATE OK`.
