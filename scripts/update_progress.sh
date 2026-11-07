#!/usr/bin/env bash
# Rebuilds the progress block of README.md from the status column of specs/README.md.
# Usage: bash scripts/update_progress.sh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
index="$root/specs/README.md"
readme="$root/README.md"

block="$(awk -F'|' '
  function owner(n) {
    if (n <= 6 || n == 30) return "Sergio Ponce"
    if ((n >= 7 && n <= 11) || n == 15 || n == 29) return "Andres Acosta"
    if (n == 12 || n == 13 || n == 14 || (n >= 16 && n <= 19)) return "Jose David Ruano"
    return "Felipe Moncada"
  }
  function trim(s) { gsub(/^ +| +$/, "", s); return s }
  /^\| [0-9][0-9][0-9] \|/ {
    id = trim($2); title = trim($3); status = trim($5)
    sub(/\]\(/, "](specs/", title)
    total++
    if (status == "Implemented") done++
    rows = rows "| " id " | " title " | " owner(id + 0) " | " status " |\n"
  }
  END {
    printf "Implemented: **%d of %d** specs.\n\n", done, total
    printf "| # | Spec | Owner | Status |\n|---|---|---|---|\n%s", rows
  }' "$index")"

BLOCK="$block" DAY="$(date +%F)" awk '
  /<!-- progress:start -->/ { print; print "_Updated " ENVIRON["DAY"] " from `specs/README.md`._\n"; print ENVIRON["BLOCK"]; skip = 1; next }
  /<!-- progress:end -->/ { skip = 0 }
  !skip { print }
' "$readme" > "$readme.tmp"
mv "$readme.tmp" "$readme"
