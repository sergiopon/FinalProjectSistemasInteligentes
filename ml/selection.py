"""Polarity model selection by grouped, cross-validated grid search on macro-F1 (spec 010)."""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, cast

import numpy as np
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import ExtraTreesClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression, SGDClassifier
from sklearn.model_selection import GridSearchCV
from sklearn.naive_bayes import ComplementNB, GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from api.domain.errors import InvalidInputError
from ml.representations import REPRESENTATIONS, build_representation
from ml.schemas import SEED
from ml.split import N_SPLITS, cv_splitter

logger = logging.getLogger(__name__)

CLASSIFIERS: Final[tuple[str, ...]] = (
    "dummy",
    "logistic_regression",
    "linear_svm",
    "naive_bayes",
    "random_forest",
    "extra_trees",
    "knn",
    "sgd_log_loss",
)

_GRIDS: Final[Mapping[str, Mapping[str, tuple[object, ...]]]] = MappingProxyType(
    {
        "dummy": MappingProxyType({}),
        "logistic_regression": MappingProxyType({"C": (0.1, 1.0, 10.0)}),
        "linear_svm": MappingProxyType({"C": (0.1, 1.0, 10.0)}),
        "naive_bayes": MappingProxyType({"alpha": (0.1, 0.5, 1.0)}),
        "naive_bayes_dense": MappingProxyType({"var_smoothing": (1e-9, 1e-6, 1e-3)}),
        "random_forest": MappingProxyType({"min_samples_leaf": (1, 3)}),
        "extra_trees": MappingProxyType({"min_samples_leaf": (1, 3)}),
        "knn": MappingProxyType({"n_neighbors": (5, 15, 25)}),
        "sgd_log_loss": MappingProxyType({"alpha": (1e-5, 1e-4, 1e-3)}),
    }
)


@dataclass(frozen=True, slots=True)
class SelectionResult:
    """Winner of the model selection and the score of every candidate.

    Attributes:
        representation: Representation name of the winner.
        classifier: Classifier name of the winner.
        best_params: Grid point of the winner, keys prefixed ``classifier__``.
        cv_macro_f1_mean: Mean cross-validated macro-F1 of the winner.
        cv_macro_f1_std: Standard deviation of that score across folds.
        pipeline: The winner refit on all given rows.
        selection: One row per candidate, in scoring order.
    """

    representation: str
    classifier: str
    best_params: dict[str, object]
    cv_macro_f1_mean: float
    cv_macro_f1_std: float
    pipeline: Pipeline
    selection: tuple[dict[str, object], ...]


def build_pipeline(representation: str, classifier: str) -> Pipeline:
    """Build a new, unfitted pipeline ``features -> classifier``.

    Args:
        representation: One of ``REPRESENTATIONS``.
        classifier: One of ``CLASSIFIERS``.

    Returns:
        The unfitted pipeline.

    Raises:
        InvalidInputError: Unknown representation (checked first) or unknown classifier.
    """
    features = build_representation(representation)
    estimator = _estimator(representation, classifier)
    return Pipeline([("features", features), ("classifier", estimator)])


def select_model(texts: Sequence[str], y: np.ndarray, groups: np.ndarray) -> SelectionResult:
    """Score every candidate on the grouped folds, pick the winner and refit it.

    Args:
        texts: Train texts.
        y: Class index of each text, in ``POLARITY_ORDER``.
        groups: Template group of each text.

    Returns:
        The selection result.

    Raises:
        InvalidInputError: Lengths differ, a class is missing, fewer than ``N_SPLITS`` groups,
            or no candidate exposes ``predict_proba``.
    """
    _validate_selection_input(texts, y, groups)
    X = np.asarray(texts, dtype=object)
    rows = [
        _score_candidate(X, y, groups, representation, classifier)
        for representation in REPRESENTATIONS
        for classifier in CLASSIFIERS
    ]
    winner = _pick_winner(rows)
    representation, classifier = str(winner["representation"]), str(winner["classifier"])
    best_params = cast("dict[str, object]", winner["best_params"])
    fitted = build_pipeline(representation, classifier).set_params(**best_params).fit(X, y)
    mean = cast("float", winner["cv_macro_f1_mean"])
    logger.info(
        "model_selected representation=%s classifier=%s mean=%.4f", representation, classifier, mean
    )
    std = cast("float", winner["cv_macro_f1_std"])
    return SelectionResult(representation, classifier, best_params, mean, std, fitted, tuple(rows))


def _estimator(representation: str, classifier: str) -> object:
    """Build the unfitted classifier; naive Bayes depends on the representation."""
    trees: dict[str, object] = dict(n_estimators=300, class_weight="balanced", random_state=SEED)
    factories: dict[str, Callable[[], object]] = {
        "dummy": lambda: DummyClassifier(strategy="prior"),
        "logistic_regression": lambda: LogisticRegression(class_weight="balanced", max_iter=1000),
        "linear_svm": lambda: LinearSVC(class_weight="balanced", random_state=SEED),
        "naive_bayes": lambda: ComplementNB() if representation == "tfidf" else GaussianNB(),
        "random_forest": lambda: RandomForestClassifier(**trees),
        "extra_trees": lambda: ExtraTreesClassifier(**trees),
        "knn": lambda: KNeighborsClassifier(metric="cosine"),
        "sgd_log_loss": lambda: SGDClassifier(
            loss="log_loss", class_weight="balanced", max_iter=1000, random_state=SEED
        ),
    }
    factory = factories.get(classifier)
    if factory is None:
        raise InvalidInputError(f"unknown classifier: {classifier}")
    return factory()


def _param_grid(representation: str, classifier: str) -> dict[str, list[object]]:
    """Return the grid of a candidate with every key prefixed ``classifier__``."""
    dense_naive_bayes = classifier == "naive_bayes" and representation != "tfidf"
    key = "naive_bayes_dense" if dense_naive_bayes else classifier
    return {f"classifier__{name}": list(values) for name, values in _GRIDS[key].items()}


def _validate_selection_input(texts: Sequence[str], y: np.ndarray, groups: np.ndarray) -> None:
    """Check lengths, then classes, then the group count."""
    if not len(texts) == len(y) == len(groups):
        raise InvalidInputError("texts, y and groups must have the same length")
    if set(y.tolist()) != {0, 1, 2}:
        raise InvalidInputError("y must contain the classes 0, 1 and 2")
    if len(np.unique(groups)) < N_SPLITS:
        raise InvalidInputError("groups must hold at least 5 distinct values")


def _score_candidate(
    X: np.ndarray, y: np.ndarray, groups: np.ndarray, representation: str, classifier: str
) -> dict[str, object]:
    """Grid-search one candidate on the grouped folds and return its selection row."""
    search = GridSearchCV(
        build_pipeline(representation, classifier),
        _param_grid(representation, classifier),
        scoring="f1_macro",
        cv=cv_splitter(),
        refit=False,
        n_jobs=1,
        error_score="raise",
    )
    search.fit(X, y, groups=groups)
    mean = float(search.best_score_)
    std = float(search.cv_results_["std_test_score"][search.best_index_])
    logger.info(
        "candidate_scored representation=%s classifier=%s mean=%.4f std=%.4f",
        representation,
        classifier,
        mean,
        std,
    )
    return {
        "representation": representation,
        "classifier": classifier,
        "best_params": dict(search.best_params_),
        "cv_macro_f1_mean": mean,
        "cv_macro_f1_std": std,
    }


def _pick_winner(rows: Sequence[dict[str, object]]) -> dict[str, object]:
    """Pick the eligible row with the highest mean, then lowest std, then names."""
    eligible = [
        row
        for row in rows
        if hasattr(
            build_pipeline(str(row["representation"]), str(row["classifier"])), "predict_proba"
        )
    ]
    if not eligible:
        raise InvalidInputError("no candidate exposes predict_proba")
    return min(eligible, key=_winner_key)


def _winner_key(row: dict[str, object]) -> tuple[float, float, str, str]:
    """Sort key of the winner rule: ``(-mean, std, representation, classifier)``."""
    return (
        -cast("float", row["cv_macro_f1_mean"]),
        cast("float", row["cv_macro_f1_std"]),
        str(row["representation"]),
        str(row["classifier"]),
    )
