# 025 - Web single comment
Riesgo: alto

## Objective
The API (spec 024) serves `web/` at `/`, but the folder does not exist, so `GET /` returns 500. This spec creates
the page shell (header, tabs, error banner, loading bar), the shared browser helpers and the "Single comment" view
that calls `POST /predict` and shows the predicted class, the decision, the conformal set, the class probabilities,
the aspects and the most influential words. Specs 026 and 027 add the other two tabs to the same shell. Risk is high
because the page renders text from the API (XSS surface) and sets the page's Content Security Policy.

## Depends on
024 (`Implemented`): routes and static mount of `docs/contracts.md` §6. A trained active bundle is needed only for
the manual checks of the Definition of Done.

## Governing files
- `ARCHITECTURE.md` §5 (`web/`), §6 (English user-facing text; functions ≤ 20 statements, ≤ 6 arguments; modules
  ≤ 300 lines, applied here to `.js` files). ADR-004 (plain HTML, CSS and ES modules, no build step, no CDN).
- `security-rules.md` SEC-02 (only `/predict` returns the caller's own text), SEC-03 (this view persists nothing),
  SEC-16 (no request leaves the page's origin), SEC-21 (the page shows only `message` and `request_id`).
- `DESIGN.md` §1 to §6 (tokens, typography, components "Comment input", "Result card", "Probability bars",
  "Review badge", "Aspect list", "Tabs", states, accessibility). `docs/contracts.md` §1.1 (enum values), §6.

## Files to create/modify
1. `web/index.html` (new). No HTML file exists yet; structure fixed below.
2. `web/styles.css` (new).
3. `web/common.js` (new): helpers shared by specs 025 to 027.
4. `web/single.js` (new): the "Single comment" view.
5. `web/app.js` (new): entry module.
No Python file and no existing test changes. ADR-004 puts no browser test in the `Gate` and the project has no
JavaScript runner (no Node toolchain), so the checks are the greps, `aislop` and the manual list of the Definition
of Done.

## External dependencies
None new. No chart library: `DESIGN.md` draws bars with CSS and the heatmap (spec 026) as an HTML table. Browser APIs
used: `fetch`, `Node.append`, `Node.replaceChildren`, `CustomEvent`, CSSOM `element.style.width` (CSSOM writes are
not blocked by the `style-src 'self'` directive; `style` attributes in markup are).

## Interfaces and types
`web/common.js` (ES module; exports only these):
- `POLARITY_ORDER = ["negative", "neutral", "positive"]`; `ASPECT_ORDER` = the 9 `AspectGroup` values in contract
  order; `ASPECT_NAMES` maps them to `"Content"`, `"Assessment"`, `"Feedback"`, `"Methodology and clarity"`,
  `"Materials"`, `"Organization and schedule"`, `"Platform"`, `"Communication and climate"`, `"Workload and pace"`;
  `REASON_TEXT` maps `empty_set` → `"No class reached the confidence level"`, `set_not_singleton` → `"More than
  one class is plausible"`, `label_outside_set` → `"Top class is outside the prediction set"`, `expected_cost` →
  `"Confidence below the review threshold"`. All four frozen with `Object.freeze`.
- `formatPercent(value: number): string` → `` `${Math.round(value * 100)} %` ``.
- `formatScore(value: number): string` → `value.toFixed(2)`.
- `el(tag: string, attributes: object = {}, children: Array<Node | string> = []): HTMLElement`: each attribute
  through `setAttribute`, children through `append` (strings become text nodes).
- `class ApiError extends Error` with constructor `(message: string, requestId: string | null)` and field
  `requestId`.
- `postJson(path: string, payload: object): Promise<object>` and `postBody(path: string, body: ArrayBuffer,
  contentType: string): Promise<object>`; both use the private `request(path, init)`.
- `showError(slot: HTMLElement, error: ApiError): void`; `clearError(slot: HTMLElement): void`.
- `setBusy(button: HTMLButtonElement, region: HTMLElement, bar: HTMLElement, busy: boolean): void`.
- `initTabs(tablist: HTMLElement): void`. Event contract for spec 027: `"tab-shown"` dispatched on `document` with
  `detail = { panelId: string }`.

`web/single.js`: exports `textLength(value: string): number` and `initSingle(panel: HTMLElement): void`.
Constant `MAX_TEXT_CHARS = 2000` (`config/app.json` `limits.max_text_chars`).
`web/app.js`: no exports.

`web/index.html` (`<!doctype html>`, `<html lang="en">`), in order:
1. `<head>`: `<meta charset="utf-8">`; `<meta name="viewport" content="width=device-width, initial-scale=1">`;
   `<title>From comment to action</title>`; `<link rel="stylesheet" href="styles.css">`;
   `<script type="module" src="app.js"></script>`. No inline script, no inline style, no `style` attribute.
2. `<header>`: `<h1>From comment to action</h1>` and `<p class="intro">Analyze Spanish course-evaluation comments.
   Each result shows the likely polarity, the classes the model cannot rule out, and whether a person should review
   the comment. The service stores nothing you enter.</p>`.
3. `<main>`: `<div role="tablist" aria-label="Views">` with one `<button role="tab" id="tab-single"
   aria-controls="panel-single" aria-selected="true" tabindex="0">Single comment</button>`.
4. `<section role="tabpanel" id="panel-single" aria-labelledby="tab-single">` holding: `<h2>Analyze one
   comment</h2>`; `<p class="empty" id="single-empty">Paste a comment and select Analyze.</p>`; `<label
   for="comment-text">Comment</label>`; `<textarea id="comment-text" rows="6" aria-describedby="comment-counter">`;
   `<p id="comment-counter" class="counter">0 / 2000 characters</p>`; `<button type="button" id="analyze-button"
   class="primary" disabled>Analyze</button>`; `<div id="single-loading" class="loading-bar" hidden></div>`;
   `<div id="single-errors"></div>`; `<div id="single-result" aria-live="polite" aria-busy="false"></div>`.

`web/styles.css`: `:root` holds every `DESIGN.md` §2 token, `--fs-*`, `--sp-*`, `--shadow-1` and
`color-scheme: light` (`DESIGN.md` defines one light theme). Rules: body font stack and line heights of §3;
`.num` and every table cell use `font-variant-numeric: tabular-nums`; content column `max-width: 1120px`, side
padding `var(--sp-4)`; buttons, tabs, `select` and the file button `min-height: 44px`, `min-width: 44px`;
`.primary` = `--accent` background, `#FFFFFF` text; `.primary:disabled` = `--surface` background, `--text-muted`
text, 1 px `--control-border` border (6.02:1); secondary buttons = `--bg` background, `--accent` text, 1 px
`--control-border` border; `:focus-visible` = `outline: 2px solid var(--accent); outline-offset: 2px` (no
`outline: none` anywhere); `.badge` per "Review badge"; `.banner` per "Error" state; `.loading-bar` 2 px `--accent`
with a 1.5 s linear loop moving a 30 % wide segment, replaced by a static full-width bar under
`prefers-reduced-motion: reduce`, which also removes the 150 ms opacity transition; below `max-width: 720px`
two-column areas stack. Every class the CSS defines is written literally in `index.html` or a `.js` file (rule
`ai-slop/unused-css`).

## Expected behavior
1. `app.js` on load: `initTabs(document.querySelector('[role="tablist"]'))`, then
   `initSingle(document.getElementById("panel-single"))`. Specs 026 and 027 append their `init*` calls here.
2. `initTabs`: tabs are the `[role="tab"]` children. Activating a tab sets `aria-selected="true"` and `tabindex="0"`
   on it, `"false"` and `"-1"` on the others, `hidden` on every other `aria-controls` panel, removes `hidden` from its
   own, then dispatches `"tab-shown"`. Click activates. `ArrowRight` and `ArrowLeft` move to the next and previous
   tab with wrap-around, `Home` and `End` to the first and last; each activates and focuses the tab.
3. `textLength(value)` = number of code points of `value.trim()` (`[...value.trim()].length`), matching Python
   `len(text.strip())` for the text the API validates.
4. On every `input` event of `#comment-text`: `n = textLength(value)`; counter text `"<n> / 2000 characters"`; when
   `n > 2000` the counter text is `"<n> / 2000 characters. Shorten the comment to 2000 characters."` and gets
   class `over-limit` (`--error` color; the words carry the meaning); `#analyze-button.disabled = n === 0 || n >
   2000`.
5. Click on `#analyze-button`: `clearError(#single-errors)`; `setBusy(button, #single-result, #single-loading,
   true)`; `postJson("/predict", { text: textarea.value })` (raw value; the API strips); on success render step 7,
   on `ApiError` `showError(#single-errors, error)` and keep the previous result; finally `setBusy(..., false)` and
   recompute step 4.
6. `setBusy(true)`: stores the label in `button.dataset.label`, sets `disabled`, label `"Analyzing…"` (U+2026),
   `aria-busy="true"` on the region, removes `hidden` from the bar. `setBusy(false)` restores the label, sets
   `aria-busy="false"`, hides the bar, sets `disabled = false`.
7. Render (`#single-result.replaceChildren(card)`; `#single-empty` gets `hidden`). Card `<article class="card">`:
   1. `<h3>Result</h3>`; `<p>Predicted: <predicted></p>`.
   2. `decision === "classify"` → `<p>Decision: classify</p>`; `"review"` → `<p>Decision: ` + `<span
      class="badge">Needs review</span>` + ` <REASON_TEXT[reason]></p>`.
   3. `<p>Prediction set at <formatPercent(confidence_level)>: <labels joined by ", "></p>`; an empty
      `conformal_set` prints `no class`.
   4. `<h4>Class probabilities</h4>`; one row per class of `POLARITY_ORDER`: `<div class="prob-row">` with
      `<span class="prob-label">` class name, `<span class="prob-track">` holding the fill `<span>`, and `<span
      class="prob-value num">` `formatPercent(p)`; fill `style.width = "<Math.round(p * 100)>%"`; class `fill-predicted` (`--accent`) for
      `predicted`, `fill-other` (`--control-border`) otherwise; row `role="img"`, `aria-label="<class>
      <formatPercent(p)>"`.
   5. `<h4>Aspects</h4>`; `<ul>` of `"<ASPECT_NAMES[group]>: <polarity> (score <formatScore(score)>)"`; empty
      `aspects` → `<p>No aspect detected in this comment.</p>`.
   6. `<h4>Words that changed the prediction most</h4>`; `<ul>` of `"<word>: <sign><formatScore(abs(delta))>"`,
      sign `"+"` for `delta >= 0`, `"-"` otherwise; then `<p class="caption">Each value is the drop in the
      probability of the predicted class when the word is removed. A negative value means the word pulled against
      it.</p>`; empty `influences` → `<p>No single word changed the prediction.</p>`.
   7. `<p class="caption">Model <model_version></p>`.
8. `request`: `fetch(path, init)`; a `TypeError` from `fetch` → `ApiError("The server did not respond. Check that the
   service is running.", null)`. Non-2xx with a JSON body whose `message` is a string → `ApiError(body.message,
   body.request_id ?? header "X-Request-ID" ?? null)`. Any other non-2xx, or a 2xx body that is not JSON →
   `ApiError("The server returned an unexpected response.", header "X-Request-ID" ?? null)`. 2xx → parsed JSON.
9. `showError(slot, error)`: `slot.replaceChildren(banner)`; banner `<div class="banner" role="alert">` with
   `<p class="banner-title">The request failed</p>`, `<p>` holding `error.message`, and `<p>Request id:
   <requestId></p>` only when `requestId` is not `null`. `clearError` empties the slot.
10. All API text reaches the DOM only through `el`, `textContent` or `append` of strings. Nothing is written to
    `localStorage`, `sessionStorage`, cookies or IndexedDB (SEC-03).

## Edge cases and error handling
| Input | Result |
|---|---|
| Textarea empty or only spaces | Button disabled; counter `"0 / 2000 characters"` |
| 2000 code points | Button enabled |
| 2001 code points | Button disabled; over-limit counter text |
| `"😀"` | `textLength` 1 (code points, not UTF-16 units) |
| Server stopped | Banner `"The server did not respond. Check that the service is running."`, no request id line |
| 422 `{"error": "invalid_input", "message": "The request is invalid.", "request_id": "ab12"}` | Banner with that message and `"Request id: ab12"` |
| 503 `model_unavailable` | Banner `"The model is not available."` and its request id |
| 500 with a non-JSON body | Banner `"The server returned an unexpected response."` plus the `X-Request-ID` value |
| Response text holding `<img src=x onerror=alert(1)>` | Rendered as literal text; no element created |
| Double click on Analyze | Second click ignored (button disabled while busy) |
`fetch` errors other than `TypeError` are rethrown, not swallowed. If an existing test fails because of this change,
the implementer does not modify it: they report its name and the reason.

## Acceptance tests (prose)
No automated test is added (ADR-004, no JavaScript runner). Each item is checked by hand in a desktop browser with
the server of `CONTEXT.md` "Serve" running a trained bundle, and the result is recorded in the delivery report:
1. `test_page_loads_clean`: open `http://127.0.0.1:8000/`: title "From comment to action", 0 console errors, 0 CSP
   violations, the Network panel lists requests to `127.0.0.1:8000` only.
2. `test_counter_limits`: type `"  hola  "` → `"4 / 2000 characters"`, button enabled; paste 2001 `"a"` →
   over-limit text, button disabled; clear → `"0 / 2000 characters"`, button disabled.
3. `test_counter_code_points`: devtools console: `(await import("/single.js")).textLength("😀")` → `1`;
   `textLength("ñandú")` → `5`.
4. `test_format_helpers`: console on `/common.js`: `formatPercent(0.52)` → `"52 %"`, `formatPercent(0.9)` →
   `"90 %"`, `formatPercent(0)` → `"0 %"`, `formatPercent(1)` → `"100 %"`; `formatScore(0.91)` → `"0.91"`,
   `formatScore(0.1048)` → `"0.10"`.
5. `test_review_result`: analyze `"El contenido fue claro, pero los parciales fueron difíciles."`: card shows
   `"Predicted: "`, a decision line, the prediction-set line with `"90 %"`, 3 bars in order negative, neutral,
   positive with the predicted one in `--accent`, aspects and words lists, `"Model v001"`.
6. `test_loading_state`: devtools throttling "Slow 3G": while waiting the button reads `"Analyzing…"` and is
   disabled, the bar is visible and `#single-result` has `aria-busy="true"`.
7. `test_error_banners`: stop the server and analyze → no-response banner without a request id line; restart; in
   the console `(await import("/common.js")).postJson("/predict", {text: " "})` rejects with an `ApiError` whose
   `message` is `"The request is invalid."` and whose `requestId` matches `^[0-9a-f]{32}$`.
8. `test_xss_literal`: analyze `<img src=x onerror=alert(1)>`: no alert, the Elements panel shows no `img`.
9. `test_keyboard`: Tab reaches tab, textarea, button in that order with a visible 2 px ring; Enter and Space
   activate the button; `ArrowRight` on the tab keeps focus on the only tab.
10. `test_mobile_and_zoom`: 320 px wide viewport: no horizontal page scroll, controls ≥ 44 × 44 px; 200 % zoom at
    1280 px: no clipped text.

## Out of scope
Batch upload and heatmap (spec 026); review queue and export (spec 027); any Python change (the response security headers of SEC-22 belong to spec 024); a dark theme; translations; a chart library.

## Definition of Done
- [ ] `.venv/bin/pytest -q -m "not integration"` → `N passed`, exit code 0 (no test changes expectation).
- [ ] `.venv/bin/ruff check .` → `All checks passed!`; `.venv/bin/ruff format --check .` → exit code 0;
      `.venv/bin/mypy --strict api ml tests` → `Success: no issues found in N source files`.
- [ ] Coverage: not applicable: the coverage command measures `api` and `ml` only; the `Gate` threshold still passes.
- [ ] `aislop scan web` → last result line contains `Clean run` and `no issues`; `aislop ci web` → exit code 0. No
      rule disabled and no `aislop-ignore` comment added. A `formatting` finding is fixed with `aislop fix --safe`.
- [ ] `grep -rnE "innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function|setAttribute\(.style" web/`
      → no output.
- [ ] `grep -rnE "https?://" web/` → no output (no CDN, SEC-16). `grep -rn "console\." web/` → no output.
- [ ] `grep -rnE "localStorage|sessionStorage|indexedDB|document\.cookie" web/` → no output (SEC-03).
- [ ] `grep -rnP "\x{2014}|\x{2013}" web/` → no output (no em or en dash).
- [ ] `grep -nE "<script>|style=|Content-Security-Policy" web/index.html` → no output (the policy is the SEC-22
      response header of spec 024).
- [ ] `wc -l web/*.js web/*.css web/index.html` → each file ≤ 300 lines; every function ≤ 20 statements.
- [ ] With a trained bundle: `curl -s -o /dev/null -w "%{http_code} %{content_type}" http://127.0.0.1:8000/app.js`
      → output starts with `200 text/javascript`; the 10 manual checks above recorded as passed.
- [ ] `bash scripts/gate.sh` → last line `GATE OK`, exit code 0.
