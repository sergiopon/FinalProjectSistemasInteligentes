"""Tests for ml/selection.py on the synthetic S60 set (TF-IDF only, no embedding model)."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import numpy as np
import pytest
from sklearn.naive_bayes import ComplementNB, GaussianNB

from api.domain.errors import InvalidInputError
from ml import selection
from ml.selection import CLASSIFIERS, SelectionResult, build_pipeline, select_model

S60 = [f"{('malo', 'regular', 'bueno')[i % 3]} curso numero {i}" for i in range(60)]
Y60 = np.arange(60) % 3
G60 = np.arange(60) // 3


@pytest.fixture(autouse=True)
def tfidf_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(selection, "REPRESENTATIONS", ("tfidf",))


@pytest.fixture(scope="module")
def s60_result() -> Iterator[SelectionResult]:
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(selection, "REPRESENTATIONS", ("tfidf",))
        yield select_model(S60, Y60, G60)


def assert_invalid(detail: str, info: pytest.ExceptionInfo[InvalidInputError]) -> None:
    assert info.value.detail == detail


def test_classifiers_constant() -> None:
    assert CLASSIFIERS == (
        "dummy",
        "logistic_regression",
        "linear_svm",
        "naive_bayes",
        "random_forest",
        "extra_trees",
        "knn",
        "sgd_log_loss",
    )


@pytest.mark.parametrize("classifier", CLASSIFIERS)
def test_build_pipeline_steps(classifier: str) -> None:
    pipeline = build_pipeline("tfidf", classifier)
    assert [name for name, _ in pipeline.steps] == ["features", "classifier"]
    assert build_pipeline("tfidf", classifier) is not pipeline


def test_build_pipeline_naive_bayes_depends_on_representation() -> None:
    assert isinstance(build_pipeline("tfidf", "naive_bayes")[-1], ComplementNB)
    assert isinstance(build_pipeline("tfidf_svd", "naive_bayes")[-1], GaussianNB)
    assert isinstance(build_pipeline("embeddings", "naive_bayes")[-1], GaussianNB)


def test_build_pipeline_predict_proba() -> None:
    for classifier in CLASSIFIERS:
        expected = classifier != "linear_svm"
        assert hasattr(build_pipeline("tfidf", classifier), "predict_proba") is expected


@pytest.mark.parametrize(
    ("representation", "classifier", "detail"),
    [
        ("tfidf", "svm", "unknown classifier: svm"),
        ("bow", "dummy", "unknown representation: bow"),
        ("bow", "svm", "unknown representation: bow"),
    ],
)
def test_build_pipeline_rejects_unknown(representation: str, classifier: str, detail: str) -> None:
    with pytest.raises(InvalidInputError) as info:
        build_pipeline(representation, classifier)
    assert_invalid(detail, info)


def test_select_model_vector(s60_result: SelectionResult) -> None:
    assert s60_result.representation == "tfidf"
    assert s60_result.classifier == "extra_trees"
    assert s60_result.best_params == {"classifier__min_samples_leaf": 1}
    assert s60_result.cv_macro_f1_mean == 1.0
    assert s60_result.cv_macro_f1_std == 0.0
    rows = s60_result.selection
    assert [row["classifier"] for row in rows] == list(CLASSIFIERS)
    dummy, svm = rows[0], rows[2]
    assert abs(float(str(dummy["cv_macro_f1_mean"])) - 0.16666666666666666) <= 1e-9
    assert dummy["cv_macro_f1_std"] == 0.0
    assert svm["cv_macro_f1_mean"] == 1.0
    assert svm["best_params"] == {"classifier__C": 0.1}


def test_select_model_best_params_is_a_copy(s60_result: SelectionResult) -> None:
    winner = next(row for row in s60_result.selection if row["classifier"] == "extra_trees")
    assert s60_result.best_params == winner["best_params"]
    assert s60_result.best_params is not winner["best_params"]


def test_select_model_refits_winner(s60_result: SelectionResult) -> None:
    pipeline = s60_result.pipeline
    texts = np.asarray(["bueno curso", "malo curso"], dtype=object)
    assert pipeline.predict(texts).tolist() == [2, 0]
    probabilities = pipeline.predict_proba(np.asarray(["bueno curso"], dtype=object))[0]
    assert int(np.argmax(probabilities)) == 2
    assert probabilities[2] >= 0.9


def test_select_model_excludes_no_proba(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(selection, "CLASSIFIERS", ("dummy", "linear_svm"))
    result = select_model(S60, Y60, G60)
    assert result.classifier == "dummy"
    assert result.selection[1]["cv_macro_f1_mean"] == 1.0


def test_select_model_no_eligible(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(selection, "CLASSIFIERS", ("linear_svm",))
    with pytest.raises(InvalidInputError) as info:
        select_model(S60, Y60, G60)
    assert_invalid("no candidate exposes predict_proba", info)


def test_select_model_rejects_length_mismatch() -> None:
    with pytest.raises(InvalidInputError) as info:
        select_model(S60, Y60, G60[:59])
    assert_invalid("texts, y and groups must have the same length", info)


def test_select_model_rejects_missing_class() -> None:
    with pytest.raises(InvalidInputError) as info:
        select_model(S60, np.arange(60) % 2, G60)
    assert_invalid("y must contain the classes 0, 1 and 2", info)


def test_select_model_rejects_few_groups() -> None:
    with pytest.raises(InvalidInputError) as info:
        select_model(S60, Y60, np.arange(60) % 4)
    assert_invalid("groups must hold at least 5 distinct values", info)


def test_select_model_logs_no_text(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO):
        select_model(S60, Y60, G60)
    messages = [record.getMessage() for record in caplog.records]
    assert sum(message.startswith("candidate_scored") for message in messages) == 8
    selected = "model_selected representation=tfidf classifier=extra_trees mean=1.0000"
    assert messages.count(selected) == 1
    assert not any("curso" in message for message in messages)
