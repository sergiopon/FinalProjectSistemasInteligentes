# ADR-004 — Static web UI served by FastAPI

Status: Accepted (2026-11-05)

## Context

The guide asks for an interface that accepts a single comment or a CSV upload. The product needs a course × aspect
heatmap and a review queue. The system runs locally with no network at runtime (SEC-16) and one Python process.

## Decision

1. `web/` holds plain HTML, CSS and ES modules, mounted by `api/main.py` with FastAPI `StaticFiles` at `/`; the API
   routes keep their paths (`docs/contracts.md` §6).
2. No chart library and no vendored third-party code: bars are drawn with CSS and the heatmap is an HTML table
   (`DESIGN.md`). No CDN is requested at runtime.
3. No build step, no Node toolchain, no framework. Visual rules: `DESIGN.md`.
4. Every response carries the security headers of SEC-22, set by `api/main.py`; `web/` uses no HTML-string sinks.
5. Review decisions live only in the browser `localStorage` (SEC-03); the review-queue CSV export is built in the
   browser with formula-injection prefixing (SEC-07).

## Consequences

- No Streamlit process; the same uvicorn process serves UI and API.
- The UI has no automated browser tests in the `Gate`; `aislop scan` and manual checks cover it.
- The web directory has no third-party code, so there is nothing to pin or audit on the client side.
- A strict Content-Security-Policy is possible because `web/` has no inline script and no inline style.
