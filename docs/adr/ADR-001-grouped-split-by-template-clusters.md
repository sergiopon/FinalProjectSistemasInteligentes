# ADR-001 — Grouped split by template clusters

Status: Accepted (2026-11-05)

## Context

The course guide (`docs/curso/CL12_26102026.pdf`) asks for a stratified 80/20 split grouped by author, with no information
leakage. The dataset (`Dataset/*.csv`, 618 rows) has no author column. The texts are synthetic and templated
(`docs/analysis.md` §2), so near-duplicate comments in both train and test would inflate test metrics.

## Decision

1. `ml.split` groups comments by template: TF-IDF with `analyzer="char_wb"`, `ngram_range=(3, 5)` fitted on the
   cleaned texts, a precomputed cosine-distance matrix, and `AgglomerativeClustering(n_clusters=None,
   metric="precomputed", linkage="average", distance_threshold=0.7)`. The cluster label is the group id.
2. The 80/20 split is the first fold of `StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)` on the
   polarity labels and the group ids.
3. Every later cross-validation (model selection, cross-conformal, aspect thresholds) uses
   `StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42)` on train rows with the same group ids.
4. The article documents that groups are template clusters, not authors.

## Consequences

- No template cluster appears in both train and test (acceptance test of spec 008).
- The clustering is fitted on all rows; it is a grouping device, not a model feature, and it is not saved in the bundle.
- Measured on 2026-11-05 with scikit-learn 1.9.1: distance threshold 0.4 gives 614 clusters for 618 rows (largest 3);
  0.7 gives 380 clusters (largest 8); 0.8 gives 131 (largest 36). At 0.4 the grouping changes almost no row, so the owner fixed 0.7
  on 2026-11-05. Any further change of the threshold is a new ADR that supersedes this one.
