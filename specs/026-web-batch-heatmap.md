# 026 - Web batch upload and heatmap
Riesgo: alto

## Objective
Program directors need to see, per course, which aspects draw negative comments (`docs/analysis.md` §6, unit 9
and the §3 interface row). `POST /predict-batch` (spec 024) returns that report, but the page (spec 025) only analyzes one comment.
This spec adds the "Batch upload" tab: the browser reads a CSV file and sends it as a raw `text/csv` body (SEC-01),
then shows a summary, the course × aspect heatmap of negative share, and per course the priority ranking, the topics
and the anonymized quotes. It also publishes the batch to spec 027 through a `"batch-loaded"` event. Risk is high:
the page renders masked comment text and course names coming from an uploaded file.

## Depends on
024 (`Implemented`) and 025 (shell, `web/common.js`; `specs/README.md` lists 024 only, see the delivery report).

## Governing files
- `ARCHITECTURE.md` §5, §6 (English text; functions ≤ 20 statements; files ≤ 300 lines). ADR-004.
- `security-rules.md` SEC-01 (raw `text/csv` body, no multipart), SEC-02 (rows, quotes and topics arrive masked;
  the page never shows unmasked batch text), SEC-03 (nothing persisted here), SEC-06 (the file name is shown in the
  page only and never sent), SEC-11 (2 MB limit), SEC-16, SEC-21.
- `DESIGN.md` §2 (heatmap steps), §4 ("CSV upload dropzone", "Heatmap", "Priority ranking"), §5, §6.
  `docs/contracts.md` §4.3 (`MIN_SUPPORT = 5`), §6 (`BatchResponse`, `CourseReportJson`).

## Files to create/modify
1. `web/index.html` (modify): second tab and its panel.
2. `web/styles.css` (modify): dropzone, heatmap, legend, course sections.
3. `web/app.js` (modify): `initBatch(document.getElementById("panel-batch"))` after `initSingle`.
4. `web/batch.js` (new): upload flow. Same structure as `web/single.js` (spec 025).
5. `web/report.js` (new): pure render functions for the batch result.
No Python file and no existing test changes (ADR-004, no JavaScript runner).

## External dependencies
None new. Browser APIs: `File.arrayBuffer()`, `crypto.subtle.digest("SHA-256", buffer)` (available in secure
contexts; `http://127.0.0.1` and `http://localhost` are secure contexts and SEC-16 binds the server to
`127.0.0.1`), `DataTransfer.files`, `HTMLInputElement.click()`.

## Interfaces and types
`web/report.js` (exports only these):
- `MIN_SUPPORT = 5`; `HEAT_CLASSES = ["heat-0", "heat-1", "heat-2", "heat-3", "heat-4"]` (literal strings, so
  `ai-slop/unused-css` sees them).
- `heatStep(share: number | null): number | null`.
- `countText(count: number, singular: string, plural: string): string` →
  `` `${count.toLocaleString("en-US")} ${count === 1 ? singular : plural}` ``.
- `renderSummary(response: object): HTMLElement`; `renderHeatmap(courses: object[]): HTMLElement`;
  `renderCourse(course: object): HTMLElement`.

`web/batch.js` (exports only these):
- `MAX_UPLOAD_BYTES = 2097152` (`config/app.json` `limits.max_upload_bytes`).
- `checkFile(file: File): string | null` (message, or `null` when the file may be sent).
- `sha256Hex(buffer: ArrayBuffer): Promise<string>` (64 lowercase hex characters).
- `initBatch(panel: HTMLElement): void`.
- Event contract for spec 027: `"batch-loaded"` dispatched on `document`, `detail = { batchId: string, response:
  object }`, `batchId = sha256Hex(body)`, `response` the parsed `BatchResponse`.

`web/index.html` additions: in the tablist after `#tab-single`, `<button role="tab" id="tab-batch"
aria-controls="panel-batch" aria-selected="false" tabindex="-1">Batch upload</button>`; after `#panel-single`,
`<section role="tabpanel" id="panel-batch" aria-labelledby="tab-batch" hidden>` holding, in order: `<h2>Analyze a
CSV file</h2>`; `<p class="empty" id="batch-empty">Upload a CSV file to see the course heatmap.</p>`; `<div
class="dropzone" id="dropzone">` with `<p>Drop a CSV file here or choose a file</p>`, `<button type="button"
id="choose-file">Choose file</button>`, `<input type="file" id="file-input" accept=".csv,text/csv" hidden>` and
`<p class="hint">UTF-8 CSV with columns feedback and curso, up to 2 MB and 5,000 rows</p>`; `<p id="file-status"
aria-live="polite">No file selected.</p>`; `<p id="file-error" class="field-error" role="alert"></p>`; `<button
type="button" id="analyze-file" class="primary" disabled>Analyze file</button>`; `<div id="batch-loading"
class="loading-bar" hidden></div>`; `<div id="batch-errors"></div>`; `<div id="batch-result" aria-live="polite"
aria-busy="false"></div>`. The intro paragraph of spec 025 is unchanged.

`web/styles.css` additions: `.dropzone` 1 px dashed `--control-border`, padding `var(--sp-6)`; `.is-dragover`
border color `--accent`; `.hint` `--text-muted`, `--fs-sm`; `.field-error` `--error`; `.table-scroll` `overflow-x:
auto`; `.heatmap` `border-collapse: collapse`, cells padding `var(--sp-2)`, `td` centered, header cells
`--surface`; `.heat-0` `#EFF3FB`, `.heat-1` `#C6D4EC`, `.heat-2` `#8EAAD8` with `--text` text; `.heat-3` `#3A6BB3`,
`.heat-4` `#1D4E89` with `#FFFFFF` text (ratios 13.27, 9.86, 6.25, 5.34, 8.39, rechecked); `.heat-none` `--bg`
background, `--text-muted` text (6.46); `.cell-share` block, weight 600; `.cell-count` block, `--fs-sm`;
`.low-support` italic; `.legend` flex row with wrap and gap `var(--sp-2)`; `.swatch` padding 2 px 8 px, 1 px
`--control-border` border; `.course` top margin `var(--sp-8)`; `blockquote` `--surface` background, padding
`var(--sp-3)`, no colored left border.

## Expected behavior
1. `heatStep(share)`: `null` → `null`; `pct = Math.round(share * 100)`; `pct < 20` → 0, `< 40` → 1, `< 60` → 2,
   `< 80` → 3, otherwise 4. The printed percent and the color use the same rounded `pct`.
2. `checkFile(file)`: `file.name.toLowerCase()` not ending in `".csv"` → `"Choose a file whose name ends in
   .csv."`; `file.size > 2097152` → `"This file is over 2 MB. Choose a file of 2 MB or less."`; otherwise `null`.
   Rows, columns and UTF-8 are checked by the server only.
3. File selection (`#file-input` `change`, or a `drop` on `#dropzone` taking `dataTransfer.files[0]`): message =
   `checkFile(file)`; a message → `#file-error` text = message, selected file cleared, `#file-status` `"No file
   selected."`; `null` → `#file-error` emptied, `#file-status` `"Selected: <file.name> (<countText(file.size,
   "byte", "bytes")>)"`. `#analyze-file.disabled` = no selected file. `#choose-file` click → `#file-input.click()`.
4. Drag: `dragenter` and `dragover` on `#dropzone` call `preventDefault()` and add `is-dragover`; `dragleave` and
   `drop` remove it. `dragover` and `drop` on `window` call `preventDefault()`, so a missed drop does not navigate
   away and lose the batch held in memory.
5. `#analyze-file` click: `clearError(#batch-errors)`; `setBusy(button, #batch-result, #batch-loading, true)`;
   `buffer = await file.arrayBuffer()` (a `DOMException` → `showError` with `ApiError("The file could not be read.
   Choose it again.", null)`); `response = await postBody("/predict-batch", buffer, "text/csv; charset=utf-8")`
   (the bytes are sent unchanged, BOM included; the file name is not sent); `batchId = await sha256Hex(buffer)`;
   render step 6; dispatch `"batch-loaded"`. `ApiError` → `showError(#batch-errors, error)`, previous result kept.
   Finally `setBusy(..., false)` and `#analyze-file.disabled` = no selected file.
6. Render: `#batch-empty` gets `hidden`; `#batch-result.replaceChildren(renderSummary(response),
   renderHeatmap(response.courses), ...response.courses.map(renderCourse))`.
7. `renderSummary`: `<p>` `"<countText(row_count, "comment", "comments")> analyzed: <classify> classified, <review>
   sent to review. Model <model_version>."` (counts from `decision_counts`, formatted with `toLocaleString("en-US")`).
8. `renderHeatmap(courses)`: `<section>` with `<h3>Negative share by course and aspect</h3>`; `<p
   class="caption">Each cell shows the share of mentions with negative sentiment and the number of mentions.</p>`;
   `<ul class="legend">` with five `<li><span class="swatch heat-N">` texts `"0 to 19 %"`, `"20 to 39 %"`, `"40 to
   59 %"`, `"60 to 79 %"`, `"80 to 100 %"`, one `<span class="swatch heat-none">No mentions</span>` and one
   `<li><em>Count in italics</em>: Fewer than 5 mentions</li>`; then `<div class="table-scroll" role="region"
   aria-label="Heatmap table, scrolls sideways" tabindex="0">` with `<table class="heatmap">`: header row `<th
   scope="col">Course</th>` and the 9 `ASPECT_NAMES` in `ASPECT_ORDER`; one row per course, in response order, with
   `<th scope="row">` the course name and 9 `<td>` matched by `group`.
9. Cell: `mentions === 0` → class `heat-none`, text `"No mentions"`. Otherwise class `HEAT_CLASSES[heatStep(
   negative_share)]`, `<span class="cell-share num">formatPercent(negative_share)</span>` and `<span
   class="cell-count num">countText(mentions, "mention", "mentions")</span>`, the count span also `low-support`
   when `mentions < MIN_SUPPORT`.
10. `renderCourse(course)`: `<section class="course">` with `<h3>` course name; `<p>` `"<countText(comment_count,
    "comment", "comments")>, <review_count> sent to review. Polarity: <negative> negative, <neutral> neutral,
    <positive> positive."`; `<h4>What to fix first</h4>`; `<p class="caption">Ranked by how often an aspect is
    mentioned times its smoothed negative share.</p>`; `<ol class="priorities">` one `<li>` per priority in order:
    `"<ASPECT_NAMES[group]>, score <formatScore(score)> (<countText(mentions, "mention", "mentions")>, <negative>
    negative)"`, with `", fewer than 5 mentions"` before the closing parenthesis when `low_support`; `<h4>Topics</h4>`
    and a `<ul>` with one `<li>` per topic: `"<terms joined by ", "> (<countText(size, "comment", "comments")>)"`
    followed by `<blockquote>` with `quote`; `<h4>Representative comments</h4>`, `<p class="caption">Names, emails,
    phone numbers and id numbers are masked.</p>` and one `<blockquote>` per `quotes` item.
11. Empty lists: no priorities → `<p>No aspect was mentioned in this course.</p>`; no topics → `<p>No topics were
    found for this course.</p>`; no quotes → `<p>No representative comments for this course.</p>`.
12. Every API string (course, terms, quote, model version) enters the DOM as text only (`el`, `append`,
    `textContent`). Nothing is stored in the browser (SEC-03).

## Edge cases and error handling
| Input | Result |
|---|---|
| `notes.txt` | `#file-error` `"Choose a file whose name ends in .csv."`; button disabled |
| `DATOS.CSV` | Accepted (lowercase comparison) |
| File of 2,097,153 bytes | `#file-error` `"This file is over 2 MB. Choose a file of 2 MB or less."` |
| File of exactly 2,097,152 bytes | Accepted by the page; the server decides |
| Server 422 `invalid_csv` | Banner `"The CSV file is invalid."` and `"Request id: <id>"` |
| Server 413 | Banner `"The upload exceeds the size limit."` and its request id |
| File deleted after selection | Banner `"The file could not be read. Choose it again."`, no request id line |
| Course `<i>Redes</i>`, comment `<b>hola</b>` | Shown as literal text |
| `negative_share` 0.1999 | `"20 %"`, class `heat-1` |
| Second upload | Result replaced; a new `"batch-loaded"` event |
| Course with 0 priorities, 0 topics, 0 quotes | The three empty sentences of step 11 |
If an existing test fails because of this change, the implementer does not modify it: they report its name and the
reason.

## Acceptance tests (prose)
No automated test is added (ADR-004). Manual checks with the server of `CONTEXT.md` "Serve" and a trained bundle;
CSV files are synthetic or from `Dataset/` (SEC-09) and created in a temporary folder outside the repository:
1. `test_heat_step_vectors`: console `(await import("/report.js")).heatStep` on `null`, 0, 0.1949, 0.1999, 0.25,
   0.4, 0.5999, 0.6, 0.79, 0.8, 1 → `null`, 0, 0, 1, 1, 2, 3, 3, 3, 4, 4.
2. `test_count_text`: `countText(1, "mention", "mentions")` → `"1 mention"`; `countText(5000, "comment",
   "comments")` → `"5,000 comments"`; `countText(0, "byte", "bytes")` → `"0 bytes"`.
3. `test_check_file`: console `checkFile(new File(["x"], "notes.txt"))` → the extension message;
   `checkFile(new File([new Uint8Array(2097153)], "a.csv"))` → the size message; `new File(["x"], "DATOS.CSV")` →
   `null`.
4. `test_upload_dataset_file`: choose `Dataset/feedback_curso_universitario3.csv`: summary starts `"20 comments
   analyzed:"`, one heatmap row per distinct `curso` of the file, 9 aspect columns, legend above the table, each
   course section lists priorities, topics and quotes, no quote shows an email or a 7-digit number.
5. `test_drop_upload`: drag the same file onto the dropzone: border turns `--accent` during the drag; same result.
6. `test_batch_event`: before uploading, console `document.addEventListener("batch-loaded", e =>
   window.lastBatch = e.detail)`; after the upload `lastBatch.batchId` equals the `sha256sum` of the file and
   `lastBatch.response.row_count` is 20.
7. `test_invalid_csv`: `bad.csv` with `curso,texto\nRedes,hola\n` → banner `"The CSV file is invalid."` with a
   32-hex request id.
8. `test_client_limits`: `notes.txt` and a 2,097,153-byte `big.csv` (`truncate -s 2097153 big.csv`) show the two
   field messages and send no request (Network panel).
9. `test_markup_literal`: CSV `feedback,curso\n<b>hola</b> buen curso,<i>Redes</i>\n`: no bold or italic element
   created; the course reads `<i>Redes</i>`.
10. `test_keyboard_and_loading`: Tab reaches "Choose file" (Enter opens the picker), then "Analyze file"; arrow keys
    switch tabs; with "Slow 3G" the button reads `"Analyzing…"` and `aria-busy="true"` is set.
11. `test_mobile`: 320 px viewport: the page has no horizontal scroll, the heatmap scrolls inside its region, and
    the region receives a visible focus ring.

## Out of scope
The review queue and export (spec 027); `POST /drift` and `GET /metrics` in the page; sorting or filtering the
heatmap; charts; any Python change.

## Definition of Done
- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0 (no test changes expectation).
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0;
      `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] Coverage: not applicable: the coverage command measures `api` and `ml` only; the `Gate` threshold still passes.
- [ ] `aislop scan web` → last result line contains `Clean run` and `no issues`; `aislop ci web` → exit code 0; no
      rule disabled, no `aislop-ignore` comment.
- [ ] `grep -rnE "innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function|setAttribute\(.style" web/`
      → no output. `grep -rnE "https?://" web/` → no output. `grep -rn "console\." web/` → no output.
- [ ] `grep -rnE "localStorage|sessionStorage|indexedDB|document\.cookie|FormData|multipart" web/` → no output.
- [ ] `grep -rnP "\x{2014}|\x{2013}" web/` → no output. `grep -c '"heat-4"' web/report.js` → `1`.
- [ ] `wc -l web/*.js web/*.css web/index.html` → each ≤ 300 lines; every function ≤ 20 statements.
- [ ] The 11 manual checks above recorded as passed. `bash scripts/gate.sh` → last line `GATE OK`, exit code 0.
