# From comment to action

Final project for the Emerging Technologies course. The service reads Spanish course-evaluation comments and returns
a polarity, a conformal prediction set and a decision: classify the comment or send it to a person for review.

The project is built spec by spec. Each spec in `specs/` has one owner, one branch (`feature/NNN-slug`) and is
merged into `main` with `git merge --no-ff` once its dependencies are integrated.

## Team split

[Team split diagram](https://claude.ai/artifact/Pcs8ByvfPx34G7LvdD6UvJ) shows one lane per person, who waits on
whom, and the critical path. The link is private: ask Sergio for access.

| Person | Area | Specs |
|---|---|---|
| Sergio Ponce | Tooling, Gate, domain, ports, benchmark and final README | 000 to 006, 030 |
| Andres Acosta | ML: cleaning, split, embeddings, model selection, conformal, gold set and its evaluation | 007 to 011, 015, 029 |
| Jose David Ruano | ML aspects, artifact registry, train CLI, adapters for settings, store, sklearn and text | 012 to 014, 016 to 019 |
| Felipe Moncada | Monitoring, HTTP and CSV, application, API, web UI and Docker | 020 to 028 |

Critical path: 000, 002, 003, 007, 008 and 009, 010, 011, 013, 017, 018, 024, 025, 026, 027.

## Progress

<!-- progress:start -->
_Updated 2026-11-09 from `specs/README.md`._

Implemented: **12 of 31** specs.

| # | Spec | Owner | Status |
|---|---|---|---|
| 000 | [Tooling and pins](specs/000-tooling-and-pins.md) | Sergio Ponce | Implemented |
| 001 | [Gate and dependency rule](specs/001-gate-and-dependency-rule.md) | Sergio Ponce | Implemented |
| 002 | [Domain errors and entities](specs/002-domain-errors-entities.md) | Sergio Ponce | Implemented |
| 003 | [Domain safety helpers](specs/003-domain-safety.md) | Sergio Ponce | Implemented |
| 004 | [Domain decision agent](specs/004-domain-decision-agent.md) | Sergio Ponce | Implemented |
| 005 | [Domain clauses and priority](specs/005-domain-clauses-priority.md) | Sergio Ponce | Implemented |
| 006 | [Ports](specs/006-ports.md) | Sergio Ponce | Implemented |
| 007 | [ML data cleaning](specs/007-ml-data-cleaning.md) | Andres Acosta | Implemented |
| 008 | [ML grouped split](specs/008-ml-grouped-split.md) | Andres Acosta | Implemented |
| 009 | [ML representations](specs/009-ml-representations.md) | Andres Acosta | Implemented |
| 010 | [ML model selection](specs/010-ml-model-selection.md) | Andres Acosta | Implemented |
| 011 | [ML conformal](specs/011-ml-conformal.md) | Andres Acosta | Implemented |
| 012 | [ML aspects and topics](specs/012-ml-aspects.md) | Jose David Ruano | To draft |
| 013 | [ML artifact and registry](specs/013-ml-artifact-registry.md) | Jose David Ruano | To draft |
| 014 | [ML train CLI](specs/014-ml-train-cli.md) | Jose David Ruano | To draft |
| 015 | [ML gold set and agreement](specs/015-ml-gold-agreement.md) | Andres Acosta | To draft |
| 016 | [Adapters settings and logging](specs/016-adapters-settings-logging.md) | Jose David Ruano | To draft |
| 017 | [Adapters model store](specs/017-adapters-model-store.md) | Jose David Ruano | To draft |
| 018 | [Adapters scikit-learn models](specs/018-adapters-sklearn-models.md) | Jose David Ruano | To draft |
| 019 | [Adapters text](specs/019-adapters-text.md) | Jose David Ruano | To draft |
| 020 | [Adapters monitoring](specs/020-adapters-monitoring.md) | Felipe Moncada | To draft |
| 021 | [Adapters HTTP schemas and CSV](specs/021-adapters-http-csv.md) | Felipe Moncada | To draft |
| 022 | [Application analyze](specs/022-application-analyze.md) | Felipe Moncada | To draft |
| 023 | [Application course report](specs/023-application-course-report.md) | Felipe Moncada | To draft |
| 024 | [API main and routes](specs/024-api-main-routes.md) | Felipe Moncada | To draft |
| 025 | [Web single comment](specs/025-web-single-comment.md) | Felipe Moncada | To draft |
| 026 | [Web batch and heatmap](specs/026-web-batch-heatmap.md) | Felipe Moncada | To draft |
| 027 | [Web review queue and export](specs/027-web-review-queue-export.md) | Felipe Moncada | To draft |
| 028 | [Docker and clean environment](specs/028-docker-clean-env.md) | Felipe Moncada | To draft |
| 029 | [ML gold-set evaluation](specs/029-ml-gold-evaluation.md) | Andres Acosta | To draft |
| 030 | [Benchmark and README](specs/030-benchmark-readme.md) | Sergio Ponce | To draft |
<!-- progress:end -->

To update it, change the status of the spec in `specs/README.md`, run `bash scripts/update_progress.sh`, and commit
both files together. A spec is `Ready` once its review is done and `Implemented` once it is merged into `main` with
the Gate green.

## Where things live

- `CONTRIBUTING.md`: the workflow every teammate follows. Read it before your first spec.
- `ARCHITECTURE.md` and `security-rules.md`: rules every spec follows.
- `CONTEXT.md`: stack, pinned versions and commands, including the Gate.
- `docs/contracts.md`: contracts shared by all specs. `docs/adr/`: architecture decisions.
- `specs/`: one file per change, index in `specs/README.md`.
