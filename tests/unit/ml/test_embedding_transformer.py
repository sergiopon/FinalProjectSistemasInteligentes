"""Tests for EmbeddingTransformer, download and main of ml/representations.py.

The sentence-transformers model is replaced by FakeModel: no test reaches the network or the cache.
"""

from __future__ import annotations

import copy
import logging
import os
from dataclasses import dataclass, field

import numpy as np
import pytest
from sklearn.base import clone

from api.domain.errors import InferenceError, InvalidInputError
from ml import representations
from ml.representations import (
    EMBEDDING_MODEL_NAME,
    EMBEDDING_REVISION,
    EmbeddingTransformer,
    build_representation,
    download,
    main,
)


@dataclass
class Calls:
    """What FakeModel recorded, and an optional encode output that replaces the default."""

    constructed: list[tuple[tuple[object, ...], dict[str, object]]] = field(default_factory=list)
    encoded: list[dict[str, object]] = field(default_factory=list)
    instances: list[object] = field(default_factory=list)
    output: object = None


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> Calls:
    record = Calls()

    class FakeModel:
        def __init__(self, *args: object, **kwargs: object) -> None:
            record.constructed.append((args, kwargs))
            record.instances.append(self)

        def encode(self, texts: list[str], **kwargs: object) -> object:
            record.encoded.append(kwargs)
            if record.output is not None:
                return record.output
            return np.tile(np.eye(384, dtype=np.float64)[0], (len(texts), 1))

    monkeypatch.setattr(representations, "SentenceTransformer", FakeModel)
    return record


def raise_os_error(*args: object, **kwargs: object) -> None:
    raise OSError("no cache")


def new_transformer() -> EmbeddingTransformer:
    return EmbeddingTransformer(EMBEDDING_MODEL_NAME, EMBEDDING_REVISION)


def test_build_representation_embeddings(calls: Calls) -> None:
    transformer = build_representation("embeddings")
    assert isinstance(transformer, EmbeddingTransformer)
    assert transformer.model_name == EMBEDDING_MODEL_NAME
    assert transformer.revision == EMBEDDING_REVISION
    assert calls.constructed == []


def test_embedding_fit_is_noop(calls: Calls) -> None:
    transformer = new_transformer()
    assert transformer.fit(["a"]) is transformer
    assert calls.constructed == []


def test_embedding_transform_loads_cache_only(calls: Calls) -> None:
    output = new_transformer().transform(["uno", "dos"])
    assert output.shape == (2, 384)
    assert output.dtype == np.float32
    assert calls.constructed == [
        (
            (EMBEDDING_MODEL_NAME,),
            {"revision": EMBEDDING_REVISION, "local_files_only": True, "device": "cpu"},
        )
    ]
    assert calls.encoded == [
        {
            "batch_size": 32,
            "show_progress_bar": False,
            "convert_to_numpy": True,
            "normalize_embeddings": True,
        }
    ]


def test_embedding_transform_loads_once(calls: Calls) -> None:
    transformer = new_transformer()
    transformer.transform(["uno"])
    transformer.transform(["dos"])
    assert len(calls.constructed) == 1


def test_embedding_transform_rejects_empty(calls: Calls) -> None:
    with pytest.raises(InvalidInputError) as info:
        new_transformer().transform([])
    assert info.value.detail == "transform needs at least 1 text"


def test_embedding_transform_missing_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(representations, "SentenceTransformer", raise_os_error)
    with pytest.raises(InferenceError) as info:
        new_transformer().transform(["uno"])
    assert info.value.detail == "embedding model is not in the local cache"
    assert isinstance(info.value.__cause__, OSError)


def test_embedding_transform_rejects_list_output(calls: Calls) -> None:
    calls.output = [[0.0] * 384]
    with pytest.raises(InferenceError) as info:
        new_transformer().transform(["uno"])
    assert info.value.detail == "embedding output is not an array"


def test_embedding_transform_rejects_bad_shape(calls: Calls) -> None:
    calls.output = np.zeros((2, 10))
    with pytest.raises(InferenceError) as info:
        new_transformer().transform(["uno", "dos"])
    assert info.value.detail == "embedding output has an unexpected shape"


def test_embedding_state_drops_model(calls: Calls) -> None:
    transformer = new_transformer()
    transformer.transform(["uno"])
    loaded = calls.instances[0]
    assert copy.deepcopy(transformer)._model is None
    cloned = clone(transformer)
    assert cloned.model_name == transformer.model_name
    assert cloned.revision == transformer.revision
    assert transformer._model is loaded
    assert len(calls.constructed) == 1


def test_embedding_clones_share_one_model(calls: Calls) -> None:
    original = new_transformer()
    before_load = clone(original)
    original.transform(["uno"])
    after_load = clone(original)
    for twin in (before_load, after_load, clone(after_load)):
        twin.transform(["dos"])
    assert len(calls.constructed) == 1
    assert before_load._model is original._model


def test_embedding_copied_clones_share_one_model_after_loading(calls: Calls) -> None:
    original = new_transformer()
    first, second = copy.deepcopy([original, clone(original)])
    first.transform(["uno"])
    second.transform(["dos"])
    assert len(calls.constructed) == 1
    assert first._model is second._model
    assert original._model is None


def test_embedding_independent_transformers_do_not_share(calls: Calls) -> None:
    new_transformer().transform(["uno"])
    new_transformer().transform(["uno"])
    assert len(calls.constructed) == 2


def test_download_uses_network_call(calls: Calls) -> None:
    download("m", "r")
    assert calls.constructed == [(("m",), {"revision": "r", "device": "cpu"})]


def test_download_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(representations, "SentenceTransformer", raise_os_error)
    with pytest.raises(InferenceError) as info:
        download("m", "r")
    assert info.value.detail == "embedding model download failed"


def test_main_download_success(
    calls: Calls, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    events: list[object] = []
    original_umask = os.umask

    def record_umask(mask: int) -> int:
        events.append(("umask", mask))
        return original_umask(mask)

    def record_download(model_name: str, revision: str) -> None:
        events.append("download")

    monkeypatch.setattr(os, "umask", record_umask)
    monkeypatch.setattr(representations, "download", record_download)
    previous_mask = original_umask(0o022)
    try:
        assert main(["--download"]) == 0
    finally:
        original_umask(previous_mask)
    assert events == [("umask", 0o077), "download"]
    assert capsys.readouterr().out == f"downloaded={EMBEDDING_REVISION}\n"


def test_main_requires_flag() -> None:
    with pytest.raises(SystemExit) as info:
        main([])
    assert info.value.code == 2


def test_main_app_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def failing_download(model_name: str, revision: str) -> None:
        raise InferenceError("embedding model download failed")

    monkeypatch.setattr(representations, "download", failing_download)
    monkeypatch.setattr(os, "umask", lambda mask: mask)
    assert main(["--download"]) == 2
    assert capsys.readouterr().err == "error=internal_error\n"


def test_main_unexpected_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    def broken_download(model_name: str, revision: str) -> None:
        raise RuntimeError("x")

    monkeypatch.setattr(representations, "download", broken_download)
    monkeypatch.setattr(os, "umask", lambda mask: mask)
    with caplog.at_level(logging.ERROR):
        assert main(["--download"]) == 1
    assert capsys.readouterr().err == "error=internal_error\n"
    errors = [record for record in caplog.records if record.levelno == logging.ERROR]
    assert [record.getMessage() for record in errors] == ["representations_command_failed"]


def test_main_rejects_unknown_argument() -> None:
    with pytest.raises(SystemExit) as info:
        main(["--download", "--other"])
    assert info.value.code == 2
