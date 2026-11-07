# ADR-002 — Cross-conformal sets and expected-utility abstention

Status: Accepted (2026-11-05)

## Context

The best baseline reaches macro-F1 0.62 and the global label agrees with its own aspects in about 50 % of rows
(`docs/analysis.md` §2). The product must say when it does not know. About 124 test rows are too few for a separate
calibration split.

## Decision

1. `ml.conformal` wraps the selected (unfitted) pipeline in
   `mapie.classification.CrossConformalClassifier(confidence_level=1 - alpha, conformity_score="lac",
   cv=StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=42), random_state=42)` and calls
   `fit_conformalize(X_train, y_train, groups=groups_train)`. Sets come from `predict_set(X, agg_scores="mean")`.
   `alpha` is `config/app.json` `conformal.alpha` (default 0.1). mapie is pinned at `==1.6.0`.
2. Class probabilities come from the selected pipeline refit on all train rows (MAPIE 1.6.0
   `CrossConformalClassifier` has no `predict_proba`).
3. The domain decision agent (`api/domain/decision.py`, contract in `docs/contracts.md` §4.1) sends a comment to
   human review when the set is empty, when the set has more than one label and `review_if_set_not_singleton` is
   true, when the top label is outside the set, or when the expected cost of classifying
   `(1 - p_top) * error_cost` exceeds `review_cost`.

## Consequences

- Test reports include empirical coverage, mean set size and a risk-coverage curve; the acceptance bound for
  coverage is ≥ 0.85 at `alpha` 0.1 (1.96 binomial standard errors at 124 rows).
- Costs in `config/app.json` are provisional until the risk-coverage results exist (`ARCHITECTURE.md` §7).
- The bundle holds two polarity objects: the refit pipeline and the cross-conformal classifier.
