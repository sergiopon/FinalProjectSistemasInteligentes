#!/usr/bin/env bash
# Runs the automatable checks of security-rules.md section 8.
# Usage: bash scripts/security_grep.sh [ROOT]
set -uo pipefail

ROOT="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ROOT" 2>/dev/null || exit 2

status=0
DIRS=()

# Fills DIRS with the given directories that exist; fails when none does.
pick_dirs() {
  DIRS=()
  local dir
  for dir in "$@"; do
    [ -d "$dir" ] && DIRS+=("$dir")
  done
  [ "${#DIRS[@]}" -gt 0 ]
}

fail() {
  echo "SECURITY FAIL $1: $2"
  [ -n "${3:-}" ] && echo "$3"
  status=1
}

report() {
  [ -n "$3" ] && fail "$1" "$2" "$3"
}

pick_dirs api && report SEC-01 "upload or temporary file in api/" \
  "$(grep -rnE "UploadFile|NamedTemporaryFile|SpooledTemporaryFile" --include="*.py" "${DIRS[@]}" 2>/dev/null)"

entry_files=()
[ -f api/main.py ] && entry_files+=(api/main.py)
if pick_dirs ml; then
  while IFS= read -r file; do
    entry_files+=("$file")
  done < <(grep -rl "^def main(" --include="*.py" ml 2>/dev/null)
fi
for file in "${entry_files[@]}"; do
  grep -qF "os.umask(0o077)" "$file" 2>/dev/null || fail SEC-04 "os.umask(0o077) missing in $file"
done

pick_dirs api && report SEC-05 "file handler or print in api/" \
  "$(grep -rnE "FileHandler|print\(" --include="*.py" "${DIRS[@]}" 2>/dev/null)"

for entry in "data/" "reports/" "models/v*/bundle.joblib" ".venv/" "__pycache__/" ".env"; do
  grep -qxF -- "$entry" .gitignore 2>/dev/null || fail SEC-10 ".gitignore lacks $entry"
done

pick_dirs api ml scripts && report SEC-13 "forbidden construct" \
  "$(grep -rnE "yaml\.load|pickle|eval\(|exec\(|shell=True" --include="*.py" --include="*.sh" --exclude=security_grep.sh "${DIRS[@]}" 2>/dev/null)"

pick_dirs api ml && report SEC-14 "joblib.load outside the two allowed files" \
  "$(grep -rl "joblib\.load" --include="*.py" "${DIRS[@]}" 2>/dev/null | grep -vxE "api/adapters/model_store\.py|ml/artifact\.py")"

pick_dirs api ml && report SEC-15 "torch.load or pickle.load used" \
  "$(grep -rnE "torch\.load|pickle\.load" --include="*.py" "${DIRS[@]}" 2>/dev/null)"

if [ -f api/main.py ]; then
  grep -q "HF_HUB_OFFLINE" api/main.py && grep -q "TRANSFORMERS_OFFLINE" api/main.py ||
    fail SEC-16 "offline flags missing in api/main.py"
fi

[ "$(grep -c "^es_core_news_sm @ https://" requirements.txt 2>/dev/null)" = "1" ] ||
  fail SEC-17 "spaCy model URL not pinned in requirements.txt"

report SEC-18 "unpinned requirement line" \
  "$(grep -vnE '^\s*(#|$|.*==|.*@ https://|--extra-index-url https://download\.pytorch\.org/whl/cpu$)' requirements.txt requirements-dev.txt 2>&1)"

pick_dirs web && report SEC-22 "forbidden construct in web/" \
  "$(grep -rnE "innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function|setAttribute\(.style|<script>|style=| on[a-z]+=" --include="*.js" --include="*.html" "${DIRS[@]}" 2>/dev/null)"

exit "$status"
