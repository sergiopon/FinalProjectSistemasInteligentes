# 027 - Web review queue and export
Riesgo: alto

## Objective
The decision agent sends doubtful comments to human review (ADR-002), but nobody sees them yet: the batch view
(spec 026) shows only counts. This spec adds the "Review queue" tab: it lists the batch rows whose `decision` is
`"review"`, lets a person accept the predicted class or relabel it, keeps those decisions only in the browser's
`localStorage` (SEC-03, README of spec 030 "Review decisions stay in your browser's local storage"), and exports the
queue as a CSV built in the browser with formula-injection prefixing (SEC-07). Risk is high: personal-data retention
rules, untrusted text in a spreadsheet file, and stored state that must hold no comment text.

## Depends on
026 (`Implemented`): `"batch-loaded"` event; 025: `web/common.js` (`el`, `REASON_TEXT`, `POLARITY_ORDER`,
`"tab-shown"`).

## Governing files
- `ARCHITECTURE.md` §5, §6 (English text; functions ≤ 20 statements; files ≤ 300 lines). ADR-002, ADR-004 item 4.
- `security-rules.md` SEC-02 (the queue shows and exports only the masked `text` of batch rows), SEC-03 (decisions
  only in `localStorage`; the API receives none), SEC-07 (prefix `'`), SEC-12 spirit (export file name fixed, not
  derived from input), SEC-16, SEC-21.
- `DESIGN.md` §4 ("Review queue table", "Review badge" reasons), §5 (empty state "No comments need review."), §6.
  `docs/contracts.md` §1.1 (`Polarity`, `DecisionReason` values), §6 (`Row` fields).

## Files to create/modify
1. `web/index.html` (modify): third tab and its panel.
2. `web/styles.css` (modify): queue table, line clamp, text button, `.visually-hidden`.
3. `web/app.js` (modify): `initReview(document.getElementById("panel-review"))` after `initBatch`.
4. `web/review.js` (new): queue view and storage. Same structure as `web/batch.js` (spec 026).
5. `web/export.js` (new): pure CSV functions and the download.
No Python file and no existing test changes (ADR-004, no JavaScript runner).

## External dependencies
None new. Browser APIs: `localStorage` (`getItem` and `setItem` may throw a `DOMException`), `Blob`,
`URL.createObjectURL`, `URL.revokeObjectURL`, `HTMLAnchorElement.download`.

## Interfaces and types
`web/export.js` (exports only these):
- `FORMULA_PREFIXES = ["=", "+", "-", "@", "\t", "\r"]`; `EXPORT_FILE_NAME = "review-queue.csv"`;
  `EXPORT_HEADER = ["row", "course", "comment", "predicted", "prediction_set", "reason", "review_action",
  "final_label"]`.
- `escapeCell(value: string): string`; `buildQueueCsv(rows: object[], decisions: object): string`;
  `downloadCsv(text: string, fileName: string): void`.

`web/review.js` (exports only these):
- `STORAGE_PREFIX = "review-decisions:"`; `ACTIONS = ["accept", "relabel"]`.
- `queueRows(response: object): object[]`; `loadDecisions(batchId: string): { decisions: object, readable:
  boolean }`; `saveDecisions(batchId: string, decisions: object): boolean`; `initReview(panel: HTMLElement): void`.
- `decisions` shape: `{ "<row>": { action: "accept" | "relabel", label: "negative" | "neutral" | "positive" } }`.
  Stored value = `JSON.stringify(decisions)` under key `STORAGE_PREFIX + batchId`. Vector: key
  `"review-decisions:" + "a".repeat(64)`, value `{"3":{"action":"relabel","label":"positive"}}`. The stored value
  MUST NOT hold comment text, course names or any other field of the response.

`web/index.html` additions: `<button role="tab" id="tab-review" aria-controls="panel-review" aria-selected="false"
tabindex="-1">Review queue</button>` after `#tab-batch`; after `#panel-batch`, `<section role="tabpanel"
id="panel-review" aria-labelledby="tab-review" hidden>` holding: `<h2>Review queue</h2>`; `<p class="empty"
id="review-empty">Upload a CSV file in Batch upload to fill the review queue.</p>`; `<p id="review-summary"
hidden></p>`; `<p id="review-notice" class="field-error" role="alert"></p>`; `<button type="button"
id="export-csv" class="primary" disabled>Export CSV</button>`; `<p class="caption">Decisions are saved in this
browser only. Export the queue to share them.</p>`; `<div id="review-table"></div>`.

`web/styles.css` additions: `.queue` same cell rules as `.heatmap` without colors, comment column `min-width:
16rem`, cells top-aligned; `.clamp` = `display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3;
line-clamp: 3; overflow: hidden`; `.link-button` = no background, `--accent` text, underline, `min-height: 44px`;
`.decision-actions` flex row with wrap and gap `var(--sp-2)`; `.visually-hidden` = clip pattern (1 px, `overflow:
hidden`, `clip-path: inset(50%)`, `white-space: nowrap`, `position: absolute`).

## Expected behavior
1. `escapeCell(value)`: when `value` starts with one of `FORMULA_PREFIXES`, `value = "'" + value`; then every `"`
   becomes `""` and the result is wrapped in `"`. Every cell, header included, goes through it.
2. `buildQueueCsv(rows, decisions)`: `"﻿"` + the header line + one line per row in order; cells joined by `,`,
   lines ended by `"\r\n"`. Row cells: `String(row)`; `course ?? ""`; `text`; `predicted`; `conformal_set` joined
   by `"|"`; `reason`; `decisions[row]?.action ?? ""`; `decisions[row]?.label ?? ""`.
3. `downloadCsv(text, fileName)`: `Blob([text], { type: "text/csv;charset=utf-8" })`; object URL; a temporary `<a
   href download>` built with `el`, appended to `body`, clicked, removed; `URL.revokeObjectURL` in a
   `setTimeout(..., 0)`.
4. `queueRows(response)` = `response.rows` filtered to `decision === "review"`, response order kept.
5. `loadDecisions(batchId)`: `getItem(STORAGE_PREFIX + batchId)`; `null` → `{ decisions: {}, readable: true }`. A
   `DOMException` from `getItem` or a `SyntaxError` from `JSON.parse` → `{ decisions: {}, readable: false }`.
   Parsed value not a plain object → same as unreadable. Entries are kept only when the key matches `^[0-9]+$`,
   `action` is in `ACTIONS` and `label` is in `POLARITY_ORDER`; others are dropped.
6. `saveDecisions(batchId, decisions)`: `setItem(...)`; a `DOMException` → returns `false`; otherwise `true`.
7. `initReview(panel)` listens to `"batch-loaded"`: state = `{ batchId, rows: queueRows(response), decisions }`
   from `loadDecisions(batchId)`; `#review-notice` = `"Saved decisions for this file could not be read and were
   ignored."` when `readable` is `false`, else empty; then render (step 8). A later `"batch-loaded"` replaces the
   state.
8. Render: `#review-empty` hidden. Zero rows → `#review-summary` `"No comments need review."`, `#review-table`
   emptied, `#export-csv` disabled. Otherwise `#review-summary` `"<countText(n, "comment needs", "comments need")>
   review. <d> decided."` (`d` = rows with a decision; `countText` from `web/report.js`), `#export-csv` enabled, and
   `#review-table.replaceChildren(wrapper)`: `<div class="table-scroll" role="region" aria-label="Review queue table,
   scrolls sideways" tabindex="0">` with `<table class="queue">`, header cells Row, Course, Comment, Predicted, Set,
   Reason, Decision (`scope="col"`), one row per queue row.
9. Cells: Row `row` (class `num`); Course `course`, or `"No course"` when `null`; Comment `<p class="clamp"
   id="comment-<row>">` with `text` and `<button type="button" class="link-button" aria-expanded="false"
   aria-controls="comment-<row>" hidden>Show more</button>`; Predicted `predicted`; Set labels joined by `", "`, or
   `"no class"` when empty; Reason `REASON_TEXT[reason]`; Decision: `<p id="status-<row>">` status text, then `<div
   class="decision-actions">` with `<button type="button" aria-label="Accept row <row> as <predicted>">Accept</button>`,
   `<label class="visually-hidden" for="relabel-<row>">New class for row <row></label>`, `<select
   id="relabel-<row>">` with the 3 `POLARITY_ORDER` options (selected = the saved `label` of a `relabel`, otherwise
   `predicted`) and `<button type="button" aria-label="Relabel row <row>">Relabel</button>`.
10. Status text: no decision → `"Pending"`; `accept` → `"Accepted as <label>"`; `relabel` → `"Relabeled as
    <label>"`.
11. Accept click → `decisions[row] = { action: "accept", label: predicted }`; Relabel click → `{ action: "relabel",
    label: select.value }`. Then status and summary update; `saveDecisions` returning `false` sets `#review-notice`
    to `"Your browser could not save this decision. Export the queue to keep it."` and the decision stays in memory
    and in the export.
12. "Show more": click toggles class `clamp` on the paragraph, `aria-expanded`, and the label `"Show more"` /
    `"Show less"`. `refreshToggles()` sets `hidden` on each collapsed toggle when `p.scrollHeight <= p.clientHeight +
    1`; it runs after render when `#panel-review` is visible, on `"tab-shown"` with `panelId === "panel-review"`, and
    on `window` `resize`. Text is never clipped without a visible toggle.
13. `#export-csv` click → `downloadCsv(buildQueueCsv(state.rows, state.decisions), EXPORT_FILE_NAME)`. The export
    holds the masked `text` only (SEC-02); nothing is sent to the server (SEC-03).

## Edge cases and error handling
| Input | Result |
|---|---|
| `escapeCell("=SUM(A1)")` | `"'=SUM(A1)"` (with the outer quotes) |
| `escapeCell("+57 300")`, `("-1")`, `("@user")` | `"'+57 300"`, `"'-1"`, `"'@user"` |
| `escapeCell("\tx")`, `("\rx")` | `"'\tx"`, `"'\rx"` |
| `escapeCell(" =x")` | `" =x"` (no prefix: first character is a space) |
| `escapeCell('dijo "hola", bien')` | `"dijo ""hola"", bien"` |
| `escapeCell("")`, `("Buen curso")` | `""`, `"Buen curso"` |
| Stored value `{bad` | Notice "Saved decisions for this file could not be read and were ignored."; all rows Pending |
| Stored `{"3":{"action":"accept","label":"neutral"},"x":{"action":"delete","label":"neutral"}}` | Only row 3 kept |
| `setItem` throws `QuotaExceededError` | Notice "Your browser could not save this decision. Export the queue to keep it." |
| Zero review rows | "No comments need review."; Export disabled |
| No batch yet | "Upload a CSV file in Batch upload to fill the review queue."; Export disabled |
| Same file uploaded again | Same `batchId`; saved decisions restored |
| Comment `<script>alert(1)</script>` | Literal text in the cell and in the CSV |
Errors other than `DOMException` and `SyntaxError` are rethrown. If an existing test fails because of this change,
the implementer does not modify it: they report its name and the reason.

## Acceptance tests (prose)
No automated test is added (ADR-004). Manual checks in a desktop browser with the server running. `SYN` is this
synthetic event, dispatched from the console with `document.dispatchEvent(new CustomEvent("batch-loaded", {detail:
SYN}))`: `batchId` `"a".repeat(64)`; `response.rows` = row 3 (`course` `"Redes"`, `text` `"=1+1 [PERSON]
explicó"`, `predicted` `"neutral"`, `conformal_set` `["negative", "neutral"]`, `decision` `"review"`, `reason`
`"set_not_singleton"`), row 5 (same fields, `decision` `"classify"`, `reason` `"confident"`) and row 7 (`course`
`null`, `text` `'Dijo "bien"'`, `predicted` `"positive"`, `conformal_set` `[]`, `decision` `"review"`, `reason`
`"empty_set"`).
1. `test_escape_cell_vectors`: console on `/export.js`: the 10 `escapeCell` rows of the edge-case table.
2. `test_build_queue_csv_vector`: `buildQueueCsv` with rows 3 and 7 of `SYN` and `{"3": {action: "relabel", label:
   "positive"}}` equals `"﻿\"row\",\"course\",\"comment\",\"predicted\",\"prediction_set\",\"reason\",
   \"review_action\",\"final_label\"\r\n\"3\",\"Redes\",\"'=1+1 [PERSON] explicó\",\"neutral\",\"negative|neutral\",
   \"set_not_singleton\",\"relabel\",\"positive\"\r\n\"7\",\"\",\"Dijo \"\"bien\"\"\",\"positive\",\"\",
   \"empty_set\",\"\",\"\"\r\n"` (one string; line breaks here are for layout only).
3. `test_queue_from_event`: dispatch `SYN`: 2 table rows (3 and 7), summary `"2 comments need review. 0
   decided."`, row 7 Course `"No course"`, Set `"no class"`, Reason `"No class reached the confidence level"`.
4. `test_decisions_saved_and_restored`: relabel row 3 to positive, accept row 7: statuses `"Relabeled as
   positive"` and `"Accepted as positive"`, summary `"2 decided."`; the Application panel shows one key
   `review-decisions:aaaa…` whose value has only row numbers, `action` and `label`; reload and dispatch `SYN`
   again → both statuses restored.
5. `test_export_file`: Export CSV downloads `review-queue.csv`; its bytes equal the string of check 2 with row 7
   filled as `"accept","positive"`.
6. `test_load_filters_and_corrupt`: set the key to the two stored values of the edge-case table, dispatch `SYN`
   each time → notice and all Pending; then only row 3 restored.
7. `test_storage_failure`: console `Storage.prototype.setItem = () => { throw new DOMException("full",
   "QuotaExceededError"); }`, click Accept → quota notice, status updated, export still holds the decision.
8. `test_empty_states`: fresh page → no-batch sentence, Export disabled; dispatch `SYN` with `rows: []` → "No
   comments need review.", Export disabled.
9. `test_real_batch`: upload `Dataset/feedback_curso_universitario3.csv` in Batch upload: queue size equals
   `decision_counts.review`; every comment is masked text.
10. `test_show_more_and_keyboard`: a 600-character comment in `SYN` row 3: "Show more" visible, Enter expands and
    the label becomes "Show less"; a 20-character comment has no toggle; Tab reaches Accept, the select and Relabel
    of each row in order; switching tabs with arrow keys works.
11. `test_mobile`: 320 px viewport: page without horizontal scroll, table scrolls inside its region, buttons ≥ 44
    × 44 px.

## Out of scope
Sending decisions to the API; deleting stored decisions of old batches (each key holds at most 5,000 short entries);
editing the comment text; importing a CSV of decisions; any Python change.

## Definition of Done
- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0 (no test changes expectation).
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0;
      `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] Coverage: not applicable: the coverage command measures `api` and `ml` only; the `Gate` threshold still passes.
- [ ] `aislop scan web` → last result line contains `Clean run` and `no issues`; `aislop ci web` → exit code 0; no
      rule disabled, no `aislop-ignore` comment.
- [ ] `grep -rnE "innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function|setAttribute\(.style" web/`
      → no output. `grep -rnE "https?://" web/` → no output. `grep -rn "console\." web/` → no output.
- [ ] `grep -rln "localStorage" web/` → only `web/review.js`; `grep -rnE "sessionStorage|indexedDB|document\.cookie"
      web/` → no output (SEC-03).
- [ ] `grep -c 'EXPORT_FILE_NAME = "review-queue.csv"' web/export.js` → `1` (SEC-12 spirit).
- [ ] `grep -rnP "\x{2014}|\x{2013}" web/` → no output.
- [ ] `wc -l web/*.js web/*.css web/index.html` → each ≤ 300 lines; every function ≤ 20 statements.
- [ ] The 11 manual checks above recorded as passed. `bash scripts/gate.sh` → last line `GATE OK`, exit code 0.
