# Specs index

| # | Spec | Depends on | Status |
|---|---|---|---|
| 000 | [Tooling and pins](000-tooling-and-pins.md) | None | Implemented |
| 001 | [Gate and dependency rule](001-gate-and-dependency-rule.md) | 000 | Implemented |
| 002 | [Domain errors and entities](002-domain-errors-entities.md) | 000, 001 | Implemented |
| 003 | [Domain safety helpers](003-domain-safety.md) | 001, 002 | Implemented |
| 004 | [Domain decision agent](004-domain-decision-agent.md) | 001, 002 | Implemented |
| 005 | [Domain clauses and priority](005-domain-clauses-priority.md) | 001, 002 | Implemented |
| 006 | [Ports](006-ports.md) | 001, 002 | Implemented |
| 007 | [ML data cleaning](007-ml-data-cleaning.md) | 002, 003 | To draft |
| 008 | [ML grouped split](008-ml-grouped-split.md) | 007 | To draft |
| 009 | [ML representations](009-ml-representations.md) | 007 | To draft |
| 010 | [ML model selection](010-ml-model-selection.md) | 008, 009 | To draft |
| 011 | [ML conformal](011-ml-conformal.md) | 010 | To draft |
| 012 | [ML aspects and topics](012-ml-aspects.md) | 008, 009 | To draft |
| 013 | [ML artifact and registry](013-ml-artifact-registry.md) | 003, 010, 011, 012 | To draft |
| 014 | [ML train CLI](014-ml-train-cli.md) | 013 | To draft |
| 015 | [ML gold set and agreement](015-ml-gold-agreement.md) | 007 | To draft |
| 016 | [Adapters settings and logging](016-adapters-settings-logging.md) | 003 | To draft |
| 017 | [Adapters model store](017-adapters-model-store.md) | 006, 013, 016 | To draft |
| 018 | [Adapters scikit-learn models](018-adapters-sklearn-models.md) | 006, 017 | To draft |
| 019 | [Adapters text](019-adapters-text.md) | 003, 006 | To draft |
| 020 | [Adapters monitoring](020-adapters-monitoring.md) | 006 | To draft |
| 021 | [Adapters HTTP schemas and CSV](021-adapters-http-csv.md) | 016 | To draft |
| 022 | [Application analyze](022-application-analyze.md) | 004, 005, 006 | To draft |
| 023 | [Application course report](023-application-course-report.md) | 022 | To draft |
| 024 | [API main and routes](024-api-main-routes.md) | 017, 018, 019, 020, 021, 022, 023 | To draft |
| 025 | [Web single comment](025-web-single-comment.md) | 024 | To draft |
| 026 | [Web batch and heatmap](026-web-batch-heatmap.md) | 024, 025 | To draft |
| 027 | [Web review queue and export](027-web-review-queue-export.md) | 025, 026 | To draft |
| 028 | [Docker and clean environment](028-docker-clean-env.md) | 024 | To draft |
| 029 | [ML gold-set evaluation](029-ml-gold-evaluation.md) | 013, 015 | To draft |
| 030 | [Benchmark and README](030-benchmark-readme.md) | 024 | To draft |

## Corrections

| Date | Spec | Change | Reason |
|---|---|---|---|
| 2026-11-07 | 002 | `CommentAnalysis` moves from `api/domain/entities.py` to `api/domain/decision.py` in `docs/contracts.md` §1.1 | its `decision` field needs `DecisionResult`, and `entities.py` cannot import `decision.py` |
| 2026-11-07 | 002, 003, 006 | `Depends on` of the index lists 001 as well | the Definition of Done of each spec uses `tests/architecture` and `scripts/security_grep.sh` from spec 001 |
| 2026-11-07 | 001 | `imported_modules` also emits `api.<name>` for `from api import <name>`; 2 tests added (38 to 40) | the form `from api import adapters` evaded `ARCHITECTURE.md` §2 rules 3 and 4 |
| 2026-11-07 | 003 | `EMAIL_PATTERN` bounds its local part to 64 and its domain to 255 characters (also in `docs/contracts.md` §4.4); the word-boundary condition of `PHONE_PATTERN` moves into `_mask_phone` for matches without separator; 5 tests added (49 to 54) | the email pattern took quadratic time on long tokens (7.6 s for 100000 characters) and the phone pattern masked digit runs inside hex request ids; the lookbehind and boundary variants left adjacent emails and glued phones unmasked |
| 2026-11-07 | 005 | `_SENTENCE_BOUNDARY` becomes `(?<![.!?;])[.!?;]++(?=\s|$)`; `_STRIP_CHARS` adds the Unicode spaces `str.isspace()` accepts (both also in `docs/contracts.md` §4.2); 2 tests added (18 to 20) | a comment ending in no-break spaces produced a blank clause that made `ClauseAnalysis` raise; a 2000-character punctuation run took 38 ms in the sentence regex |
| 2026-11-07 | 006 | line-break rule of the port docstrings reads "last space that keeps the line at 100 characters or fewer (greedy fill)" | the old wording ("before column 100") contradicted "every line ≤ 100 characters" and gave a one-word third line for `compare` |
