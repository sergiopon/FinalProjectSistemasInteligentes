# DESIGN — Web UI

Status: Approved (2026-11-07).

Audience: staff of a university evaluation office and program directors. Tone: sober and institutional. The UI is
plain HTML, CSS and ES modules in `web/` (ADR-004). All user-facing text is English (`ARCHITECTURE.md` §6); the
comments being analyzed are Spanish and are shown as data, never translated.

## 1. Principles

- Neutral palette plus one accent color (`--accent`). Status colors (error) appear only in error states.
- No gradients, no shadows deeper than `--shadow-1`, no emoji, no decorative icons, no animation except a 150 ms
  opacity transition and the loading indicator.
- Information first: numbers and labels are always written as text; color never carries meaning alone.
- One page with three views selected by tabs: "Single comment", "Batch upload", "Review queue".

## 2. Color tokens and contrast (WCAG 2.2 AA)

| Token | Hex | Use |
|---|---|---|
| `--bg` | `#FFFFFF` | Page background |
| `--surface` | `#F5F7FA` | Cards, table header |
| `--text` | `#1F2933` | Body text |
| `--text-muted` | `#52606D` | Secondary text, captions |
| `--border` | `#CBD2D9` | Decorative dividers only |
| `--control-border` | `#7B8794` | Inputs, buttons, bar track outline, neutral bars |
| `--accent` | `#1D4E89` | Primary button, links, focus ring, predicted-class bar, active tab |
| `--badge-bg` | `#E4E7EB` | Review badge background |
| `--error` | `#B42318` | Error text and error border |
| `--error-bg` | `#FEF3F2` | Error banner background |

Ratios computed with the WCAG relative-luminance formula:

| Foreground / background | Ratio | Requirement |
|---|---|---|
| `#1F2933` / `#FFFFFF` | 14.76 | Text 4.5 |
| `#1F2933` / `#F5F7FA` | 13.75 | Text 4.5 |
| `#52606D` / `#FFFFFF` | 6.46 | Text 4.5 |
| `#52606D` / `#F5F7FA` | 6.02 | Text 4.5 |
| `#1D4E89` / `#FFFFFF` (links, accent text) | 8.39 | Text 4.5 |
| `#FFFFFF` / `#1D4E89` (button label) | 8.39 | Text 4.5 |
| `#1D4E89` / `#F5F7FA` | 7.82 | Text 4.5 |
| `#1F2933` / `#E4E7EB` (badge) | 11.89 | Text 4.5 |
| `#B42318` / `#FFFFFF` | 6.57 | Text 4.5 |
| `#B42318` / `#FEF3F2` | 6.05 | Text 4.5 |
| `#7B8794` / `#FFFFFF` (control borders, bars) | 3.66 | Non-text 3.0 |
| `#CBD2D9` / `#FFFFFF` | 1.53 | Decorative only; never the only boundary of a control |

## 3. Typography and spacing

- Font stack: `system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`; numbers use
  `font-variant-numeric: tabular-nums`.
- Sizes (rem, base 16 px): `--fs-sm` 0.875, `--fs-base` 1, `--fs-lg` 1.25, `--fs-xl` 1.5. Line height 1.5 for body,
  1.25 for headings. Weights 400 and 600 only.
- Spacing scale (px): `--sp-1` 4, `--sp-2` 8, `--sp-3` 12, `--sp-4` 16, `--sp-6` 24, `--sp-8` 32, `--sp-12` 48.
- Layout: content column max width 1120 px, side padding `--sp-4`; cards padding `--sp-6`; radius 4 px;
  `--shadow-1` = `0 1px 2px rgba(31, 41, 51, 0.08)`.
- Breakpoint 720 px: below it, two-column areas stack and tables scroll horizontally inside their container.

## 4. Components

- **Comment input**: `<label>` "Comment" above a `<textarea>` of 6 rows, border `--control-border`, live counter
  "N / 2000 characters" in `--text-muted`; the primary button "Analyze" is disabled when the trimmed text is empty or
  longer than 2000 characters.
- **Result card**: predicted class as text ("Predicted: neutral"), decision line ("Decision: classify" or the review
  badge with its reason in words), conformal set as text ("Prediction set at 90 %: negative, neutral").
- **Probability bars**: one row per class in the order negative, neutral, positive; label left, bar track 100 %
  width with a 1 px `--control-border` outline, fill `--control-border` for other classes and `--accent` for the
  predicted class, value right as "52 %". Each row is `role="img"` with an `aria-label` that states class and value.
- **Review badge**: text "Needs review", `--badge-bg` background, `--text` color, 1 px `--control-border` border, radius
  4 px, padding 2 px 8 px. Reasons in words: `empty_set` "No class reached the confidence level",
  `set_not_singleton` "More than one class is plausible", `label_outside_set` "Top class is outside the prediction
  set", `expected_cost` "Confidence below the review threshold".
- **Aspect list**: rows "Group name: polarity (score 0.91)"; group display names: Content, Assessment, Feedback,
  Methodology and clarity, Materials, Organization and schedule, Platform, Communication and climate,
  Workload and pace.
- **CSV upload dropzone**: dashed 1 px `--control-border` box, text "Drop a CSV file here or choose a file", a visible
  "Choose file" button (keyboard reachable), hint "UTF-8 CSV with columns feedback and curso, up to 2 MB and 5,000
  rows". The file is read in the browser and sent as a raw `text/csv` body (SEC-01).
- **Heatmap** (course × aspect, value = negative share): HTML `<table>`; sequential single-hue scale, colorblind-safe
  because it varies in lightness only. Every cell prints its value ("25 %") and mention count; cells with 0
  mentions show "—" on `--bg`. Steps by negative share:

| Share | Background | Text | Ratio |
|---|---|---|---|
| 0 to < 20 % | `#EFF3FB` | `#1F2933` | 13.27 |
| 20 to < 40 % | `#C6D4EC` | `#1F2933` | 9.86 |
| 40 to < 60 % | `#8EAAD8` | `#1F2933` | 6.25 |
| 60 to < 80 % | `#3A6BB3` | `#FFFFFF` | 5.34 |
| 80 to 100 % | `#1D4E89` | `#FFFFFF` | 8.39 |

  A legend with the five steps sits above the table. Cells with `low_support` show the count in italics with the
  caption "Fewer than 5 mentions".
- **Priority ranking**: ordered list per course, "1. Content — score 0.10 (40 mentions, 10 negative)".
- **Review queue table**: columns Row, Course, Comment (masked text, 3 lines then "Show more"), Predicted, Set,
  Reason, Decision; the Decision column has two buttons "Accept" and "Relabel" with a class `<select>`. Decisions are
  saved in `localStorage` (SEC-03). Button "Export CSV" downloads the queue with formula-injection prefixing (SEC-07).
- **Tabs**: `role="tablist"`; the active tab has a 2 px `--accent` bottom border and `aria-selected="true"`.

## 5. States

- **Empty**: each view shows one sentence of guidance in `--text-muted` ("Paste a comment and select Analyze.",
  "Upload a CSV file to see the course heatmap.", "No comments need review.").
- **Loading**: the triggering button is disabled and its label becomes "Analyzing…"; a 2 px `--accent` bar
  indeterminate indicator above the card; `aria-busy="true"` on the result region.
- **Error**: banner with `--error-bg` background, 1 px `--error` border, `--error` title "The request failed" and the
  server `message` plus "Request id: <id>" in `--text`; the banner has `role="alert"`. No stack traces or raw
  responses are shown.

## 6. Accessibility and interaction

- Keyboard: every control reachable by Tab in reading order; tabs move with arrow keys; visible focus ring 2 px
  solid `--accent` with 2 px offset on every focusable element.
- Tap targets ≥ 44 × 44 px. Text resizes to 200 % without loss of content.
- `prefers-reduced-motion: reduce` removes the transition and the moving loading bar (static bar instead).
