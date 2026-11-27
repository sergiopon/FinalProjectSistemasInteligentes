# Project analysis: requirements, dataset diagnosis and product decision

Date: 2026-11-05. Deadline: 2026-11-23.

Sources: `docs/curso/CL12_26102026.pdf` (official guide), `docs/curso/01_Program.pdf` (program), `docs/curso/0b-Scheduling.pdf` (schedule), and the three
CSV files in `Dataset/`. Slides 7 and 8 of the guide are empty (title only).

## 1. Requirements

### Mandatory (guide `docs/curso/CL12_26102026.pdf`)

| Part | Requirement |
|---|---|
| AI | Explore the CSV: columns, labels, missing values, duplicates, quality. |
| AI | Define the task and preprocess: normalize text, handle emojis and intensifiers. |
| AI | Stratified 80/20 train/test split, no information leakage, **grouped by author**. |
| AI | Compare **TF-IDF vs. semantic embeddings**, fitted on train only. |
| AI | `DummyClassifier` reference; compare **Logistic Regression, Linear SVM, Naive Bayes, Random Forest**. |
| AI | `Pipeline` + `GridSearchCV`/`RandomizedSearchCV`, stratified CV, selection by **macro-F1**. |
| AI | Test evaluation: accuracy, precision, recall, macro-F1, confusion matrix. |
| Product | Select the best model; record metrics, parameters and dataset version. |
| Product | Save the full `Pipeline` with joblib; record Python and dependency versions. |
| Product | Load it in a clean environment; test empty texts, errors and ambiguous comments. |
| Product | **FastAPI or Flask API** returning the predicted class and per-class probabilities. |
| Product | Interface (Streamlit or web app) accepting a single comment or a **CSV upload**. |
| Product | Measure inference time, security and quality. **Deploy on a server or cloud** and monitor data drift. |
| Product | Do not retrain on startup; load only trusted joblib files; keep scikit-learn versions aligned; model versioning and rollback. |
| Product | If **nine aspects** are predicted, a structured output with one prediction per aspect. |
| Ethics | LLMs act as methodological assistants; automatic labels need human validation; anonymize comments before sending them to external services. |
| Article | Template of the journal *Ingeniería y Universidad* (see below). |

### Article format (from the journal's submission page; the guide only links it)

- At most 5,400 words including references. Published in English.
- Word file, Times New Roman 12 pt, single spacing, single column.
- Sections: Title, Abstract, Keywords (at least 3), Introduction, Materials and Methods, Results, Conclusions, References.
- Structured abstract of at most 200 words. IEEE citation style.

### Optional or left to the team

- The classification target: polarity, aspects or both. Step 2 says "task definition" and leaves it open.
- The embedding model and the interface stack.

### Not in the guide

- Transformer fine-tuning, LLMs inside the product, per-teacher analysis, any minimum metric threshold.
- The program only weights the grade: the final project presentation is 20 %.

### Conflicts with the project constraints

- The guide asks for server or cloud deployment; the project must run locally without a server.
- The guide asks to group by author; the dataset has no author column.

## 2. Dataset diagnosis

### Verified facts

- 618 rows. Each CSV has a repeated header row and a UTF-8 BOM.
- No empty texts, no exact duplicates. Median length is 44 words.
- `polaridad_basica` has 9 raw values that normalize to 3 classes: negative 205, neutral 259, positive 154.
- `grano_fino`: 99 % equal 3. `emocion`: 98.7 % neutral. Both are useless as labels.
- Baseline (5-fold CV, TF-IDF): Logistic Regression macro-F1 0.62, Linear SVM 0.61, Complement NB 0.59, Dummy 0.20.

### New findings

1. **The global label agrees with the sentiment of its own aspects in only about 50 % of rows.**
   - "Neutral" behaves as "mixed": 142 neutral rows have mostly positive aspects.
   - 0.62 is probably close to the ceiling the label noise allows. Squeezing models will pay off little.
2. **Aspect labels are precise but incomplete.**
   - When an aspect is labeled, its keyword appears in the text 75 % to 90 % of the time. Exception: `carga_académica`, 9 of 18.
   - Recall is poor: of 55 texts mentioning "diapositiva", only 31 carry that aspect.
   - Consequence: evaluating against these labels penalizes correct predictions.
3. **Drift between files.** Per-file macro-F1 is 0.64 on one file and 0.50 on another: different generators or annotators.
4. **Texts are synthetic and templated.** "El curso fue bastante…" appears 61 times.
5. **The 22 aspect names collapse into 9 groups**, matching the guide's "nine aspects":

| Group | Original labels | Mentions |
|---|---|---|
| Content | contenidos, Contenido y pertinencia, cantidad de temas y repaso | 365 |
| Assessment | parciales, dificultad de las preguntas en los parciales, Diseño de la evaluación y criterios | 99 |
| Feedback | retroalimentación de los examenes, Retroalimentación recibida, comentarios del profesor | 78 |
| Methodology and clarity | metodología del profesor, Actividades y metodología, Claridad de exposición | 72 |
| Materials | material de clase, diseño de las diapositivas | 67 |
| Organization and schedule | organización del curso y su planeación, horario | 60 |
| Platform | disponibilidad de los recursos en el aula digital, Soporte técnico y plataforma | 50 |
| Communication and climate | respuesta oportuna a los correos, Clima de aula e interacción | 38 |
| Workload and pace | carga_académica, Ritmo y carga de trabajo | 35 |

### What the dataset can answer

- Coarse polarity.
- Which aspects a comment mentions and with what sentiment.
- Aspect distribution per course (about 70 to 145 comments per course).

### What it cannot answer

- Anything per teacher or per author: there are no such columns.
- Time trends: 2024-2 has 13 rows from a single course, and course × semester cells hold about 25 rows.
- Emotion or intensity.
- Generalization to real comments, because the texts are synthetic.

### Split strategy

Without an author column, group by near-duplicate (template) clusters and document the limitation in the article.

## 3. Product ideas

| | A. Triage with abstention | B. Aspect action map | C. Label auditor | D. Writing coach |
|---|---|---|---|---|
| User | Evaluation office or program director | Teacher and program director | Model and data maintainer | Student |
| Problem | Review thousands of comments without blindly trusting a 0.62 model | Go from "62 % negative" to "what to fix first in this course" | Dirty labels make the model learn noise | Vague comments that nobody can act on |
| AI (midterm 3) | Mandatory pipeline plus conformal prediction: a class set with guaranteed coverage (e.g. 90 %), abstains when unsure | Mandatory pipeline plus a 9-aspect multi-label classifier with per-aspect sentiment | Mandatory pipeline plus confident learning: flags likely mislabels from CV probabilities | Live polarity and aspects plus a specificity score |
| Interface (final project) | Human review queue and a coverage-precision curve with a slider | CSV upload, course × aspect heatmap, priority ranking, representative quotes | Relabeling screen with before/after F1 | Editor with real-time hints |
| Novelty | Uncertainty is the product; targets the guide's actionability gap | Answers "nine aspects" and "actionability" directly | Data-centric AI; fulfills "human validation" | Intervenes at the source, while writing |
| Main risk | Low: calibration with about 120 rows is noisy | Incomplete aspect labels, few rows per group | Circular evaluation if the test set is also relabeled | No specificity label: requires annotation from scratch |
| Effort | S | M | M | M/L |
| Fits deadline | Yes | Yes | Yes | Tight |

Discarded: topic discovery by clustering. With templated synthetic texts the clusters would be trivial.

## 4. Decision matrix

Scale 1 to 5. The first row is the weight of each criterion.

| | Guide compliance | Innovation | Viability with this dataset | Time | Interface showcase | **Total** |
|---|---|---|---|---|---|---|
| Weight | 0.30 | 0.20 | 0.25 | 0.15 | 0.10 | |
| A. Triage | 4 | 4 | 5 | 5 | 3 | **4.30** |
| B. Aspects | 5 | 4 | 3 | 3 | 5 | **4.00** |
| C. Auditor | 4 | 4 | 4 | 4 | 3 | 3.90 |
| D. Coach | 3 | 5 | 2 | 3 | 4 | 3.25 |

## 5. Open questions

1. **Deployment.** Does the professor accept a FastAPI service on `localhost` as "deployment"? If not, the architecture changes.
2. **Article.** Is it due with midterm 3, with the final project or both? Must it be in English and at most 5,400 words?
3. **Task.** Must polarity be the main task, or are aspects acceptable as the main task?
4. **Gold set.** Can the team hand-label about 100 comments with two annotators and report Cohen's kappa (about 3 hours)? Without it, no metric against these noisy labels is trustworthy.
5. **Team.** How many people and how many hours per week? 18 days remain until 2026-11-23.

## 6. Provisional recommendation: A as the core, B as the visible value

Assumptions: localhost deployment is accepted, the task is free, the gold set is feasible, and the team has 2 or 3 people.

Rationale:

- A meets the guide and is cheap.
- A turns the dataset's weakness (noise, a 0.62 ceiling) into the product's argument: the system knows when it does not know.
- B gives the showcase interface and answers the guide's "nine aspects" and actionability gap literally.

### Units ready to become specs

| # | Unit | Part | Acceptance criterion |
|---|---|---|---|
| 1 | Cleaning: drop repeated headers, normalize polarity, map aspects to 9 groups, version the dataset by hash | AI | Reproducible counts: 618 rows, 3 classes, 9 groups |
| 2 | Split grouped by template cluster, stratified 80/20 | AI | No cluster appears in both train and test |
| 3 | Polarity pipeline: Dummy, LR, SVM, NB and RF, each with TF-IDF and with multilingual embeddings; grid search by macro-F1 | AI | Full metrics table and confusion matrix |
| 4 | Gold set of about 100 comments with kappa | AI | Noise ceiling reported |
| 5 | Conformal prediction and abstention on the best model | AI | Empirical test coverage of at least 90 % within tolerance; risk-coverage curve |
| 6 | 9-aspect multi-label model plus per-aspect sentiment, with structured JSON output | AI | Per-aspect F1, also measured against the gold set |
| 7 | Artifact: joblib, manifest (versions, dataset hash, metrics), verified loading and rollback | AI and product | Same predictions in a clean environment; empty input returns a controlled error |
| 8 | Local API with `/predict` and `/predict-batch` (CSV) | Product | Returns class, probabilities, conformal set and aspects |
| 9 | Interface: single comment, CSV upload, course × aspect heatmap, review queue for abstentions | Product | Works with the 3 CSV files |

### Deliberately out of scope

- Transformer fine-tuning: not worth it with 618 noisy rows.
- `grano_fino` and `emocion`.
- Per-teacher or per-author analysis and time trends: the data does not support them.
- LLMs inside the product, because of anonymization and external dependency.
- Cloud deployment and authentication.
- The writing coach (D) and topic clustering.
- The label auditor (C) appears only as error analysis in the article, not as a screen.

### Unverified

- The journal's Word template was not opened.
- Embeddings were not benchmarked.
- Conformal coverage with about 120 calibration rows is still to be shown in unit 5.
