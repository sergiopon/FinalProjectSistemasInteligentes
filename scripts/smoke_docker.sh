#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
BASE_URL="http://127.0.0.1:8000"
HEALTH_ATTEMPTS=60
HEALTH_INTERVAL_S=2
SAMPLE_TEXT="El contenido del curso fue claro y ordenado."

fail() {
  echo "SMOKE FAIL: $1" >&2
  exit 1
}

[ -n "$(docker compose ps -q api)" ] || fail "api container is not running"
[ "$(docker compose port api 8000)" = "127.0.0.1:8000" ] || fail "port 8000 is not bound to 127.0.0.1 only"
[ "$(docker compose exec -T api id -u)" = "$(id -u)" ] || fail "container uid differs from host uid (export UID before docker compose up)"
for flag in HF_HUB_OFFLINE TRANSFORMERS_OFFLINE; do
  [ "$(docker compose exec -T api printenv "$flag")" = "1" ] || fail "offline flags missing"
done

healthy=0
for _ in $(seq 1 "$HEALTH_ATTEMPTS"); do
  if answer="$(curl -fsS "$BASE_URL/health" 2>/dev/null)" && [[ "$answer" == *'"status":"ok"'* ]]; then
    healthy=1
    break
  fi
  sleep "$HEALTH_INTERVAL_S"
done
[ "$healthy" = "1" ] || fail "/health did not answer within 120 s"

reply="$(curl -sS -w '\n%{http_code}' -X POST "$BASE_URL/predict" \
  -H 'Content-Type: application/json' -d "{\"text\":\"$SAMPLE_TEXT\"}")"
status="${reply##*$'\n'}"
body="${reply%$'\n'*}"
{ [ "$status" = "200" ] && [[ "$body" == *'"model_version"'* ]]; } || fail "/predict returned $status"

reply="$(curl -sS -w '\n%{http_code}' -X POST "$BASE_URL/predict" \
  -H 'Content-Type: application/json' -d '{"text":"   "}')"
status="${reply##*$'\n'}"
[ "$status" = "422" ] || fail "blank text returned $status"

echo "SMOKE OK"
