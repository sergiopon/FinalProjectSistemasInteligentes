# From comment to action

This project reads Spanish course-evaluation comments and returns, for each one, a polarity (negative, neutral or
positive), the probability of each class, a conformal prediction set and a decision: classify the comment or send
it to a person for review. It also scores 9 aspect groups and builds a report per course with an aspect heatmap, a
priority ranking, topics and anonymized quotes. Everything runs on your machine: one FastAPI process on
`127.0.0.1` serves the API and a static web page.

## Requirements

Linux, [uv](https://docs.astral.sh/uv/), and Docker with the Compose plugin if you want the container. uv installs
Python 3.12.14. The network is needed only to install packages, download the embedding model and build the image.

## Install

```bash
uv venv --python 3.12 --seed .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m ml.representations --download
```

The last command downloads `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` at the revision pinned in
`CONTEXT.md`. After it, nothing else goes to the network.

## Train a model

```bash
.venv/bin/python -m ml.train
.venv/bin/python -m ml.artifact verify v001
```

Training reads `Dataset/`, writes `models/v001/` and makes it the active version in `models/registry.json`. The
service never trains. `.venv/bin/python -m ml.artifact rollback` returns to the previous version and
`.venv/bin/python -m ml.artifact activate v001` selects one by name.

## Check the model against people

```bash
.venv/bin/python -m ml.gold sample
.venv/bin/python -m ml.gold agreement
.venv/bin/python -m ml.gold_eval
```

`sample` writes `gold/sheet_a.csv` and `gold/sheet_b.csv` with the same comments. Two people label them without
seeing each other's sheet. `agreement` writes Cohen's kappa to `gold/agreement.json`, and `ml.gold_eval` compares
the active model with the rows where both people agree, in `reports/gold_eval.json`.

## Run the service

```bash
.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/> for the web page.

| Route | What it does |
|---|---|
| `GET /health` | Status and active model version |
| `GET /model` | Metadata and test metrics of the active model |
| `POST /predict` | Analyzes one comment sent as JSON `{"text": "..."}` |
| `POST /predict-batch` | Analyzes a CSV body (`text/csv`) with columns `feedback` and `curso` |
| `POST /drift` | Compares a CSV body with the training data |
| `GET /metrics` | Latency p50 and p95, decision counts and the last drift report |

## Run with Docker

Train a model first (it is read from `models/`). Run `export UID` if your shell does not export it, then
`docker compose up --build`, and `bash scripts/smoke_docker.sh` to check it. Compose publishes port 8000 on
`127.0.0.1` only, and the container runs with your user id.

## Measure inference time

`.venv/bin/python -m scripts.benchmark` loads the active model in the same process, sends 3 warm-up requests per route, then 100 requests to
`/predict` and 20 requests of 100 rows to `/predict-batch`. It prints p50 and p95 latency in milliseconds as JSON.
No socket is opened, so the times leave out network cost.

## Limitations

- The data is synthetic. The 618 comments in `Dataset/` come from templates ("El curso fue bastante..." opens 61
  of them), so these results say little about real student comments.
- The labels are noisy. The overall polarity matches the sentiment of the comment's own aspects in about half of
  the rows, and "neutral" often marks a mixed comment. A TF-IDF baseline reached macro-F1 0.62 in 5-fold
  cross-validation, which is probably near the ceiling these labels allow. This is why the service abstains and
  sends doubtful comments to review.
- Aspect labels are incomplete: of 55 comments that mention "diapositiva", 31 carry that aspect. Metrics against
  these labels count some correct predictions as errors; the gold set gives a cleaner measure.
- Groups are templates, not authors. The dataset has no author column, so the train and test split keeps clusters
  of near-identical comments on one side (`docs/adr/ADR-001-grouped-split-by-template-clusters.md`). Two comments
  by the same person can still fall on both sides.
- Deployment is local. The service listens on `127.0.0.1` and has no login, so do not expose it on a network.

## Security and ethics

- Comments can contain names. Every comment the API returns in batch rows, quotes, summaries and course reports is
  anonymized first: person names, emails, phone numbers and id numbers are masked. If the anonymizer cannot load,
  the service does not start. `/predict` returns your own text unchanged.
- The service stores nothing. Uploads are read in memory; predictions, counters and the last drift report are lost
  on restart. Review decisions stay in your browser's local storage.
- Logs go to stdout and never hold comment text or upload file names.
- The service loads a model only from `models/`, and only when the SHA-256 of the bundle and the versions of
  scikit-learn, numpy, joblib and mapie match its manifest. A mismatch stops the process.
- While it runs, the service makes no network calls. Every response carries a strict Content-Security-Policy and
  other browser security headers, and the web page builds its content without HTML strings.
- A predicted label is a suggestion. Comments the model is unsure about go to a review queue, and the gold set,
  labeled by two people, is what the model is measured against.
- Do not send real student comments, logs, uploads or model files to external services.

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

Implemented: **25 of 31** specs.

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
| 012 | [ML aspects and topics](specs/012-ml-aspects.md) | Jose David Ruano | Implemented |
| 013 | [ML artifact and registry](specs/013-ml-artifact-registry.md) | Jose David Ruano | Implemented |
| 014 | [ML train CLI](specs/014-ml-train-cli.md) | Jose David Ruano | Implemented |
| 015 | [ML gold set and agreement](specs/015-ml-gold-agreement.md) | Andres Acosta | To draft |
| 016 | [Adapters settings and logging](specs/016-adapters-settings-logging.md) | Jose David Ruano | Implemented |
| 017 | [Adapters model store](specs/017-adapters-model-store.md) | Jose David Ruano | Implemented |
| 018 | [Adapters scikit-learn models](specs/018-adapters-sklearn-models.md) | Jose David Ruano | Implemented |
| 019 | [Adapters text](specs/019-adapters-text.md) | Jose David Ruano | Implemented |
| 020 | [Adapters monitoring](specs/020-adapters-monitoring.md) | Felipe Moncada | Implemented |
| 021 | [Adapters HTTP schemas and CSV](specs/021-adapters-http-csv.md) | Felipe Moncada | Implemented |
| 022 | [Application analyze](specs/022-application-analyze.md) | Felipe Moncada | Implemented |
| 023 | [Application course report](specs/023-application-course-report.md) | Felipe Moncada | Implemented |
| 024 | [API main and routes](specs/024-api-main-routes.md) | Felipe Moncada | Implemented |
| 025 | [Web single comment](specs/025-web-single-comment.md) | Felipe Moncada | To draft |
| 026 | [Web batch and heatmap](specs/026-web-batch-heatmap.md) | Felipe Moncada | To draft |
| 027 | [Web review queue and export](specs/027-web-review-queue-export.md) | Felipe Moncada | To draft |
| 028 | [Docker and clean environment](specs/028-docker-clean-env.md) | Felipe Moncada | To draft |
| 029 | [ML gold-set evaluation](specs/029-ml-gold-evaluation.md) | Andres Acosta | To draft |
| 030 | [Benchmark and README](specs/030-benchmark-readme.md) | Sergio Ponce | Implemented |
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
