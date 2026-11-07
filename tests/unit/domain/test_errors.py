"""Tests for api/domain/errors.py."""

from __future__ import annotations

import pytest

from api.domain.errors import (
    AnonymizerUnavailableError,
    AppError,
    ConfigError,
    CsvFormatError,
    DatasetError,
    InferenceError,
    InvalidInputError,
    ModelIntegrityError,
    ModelUnavailableError,
    NotFoundError,
    PayloadTooLargeError,
    UnsafePathError,
    UnsupportedMediaTypeError,
)

CODES: list[tuple[type[AppError], str]] = [
    (AppError, "internal_error"),
    (InvalidInputError, "invalid_input"),
    (CsvFormatError, "invalid_csv"),
    (PayloadTooLargeError, "payload_too_large"),
    (UnsupportedMediaTypeError, "unsupported_media_type"),
    (NotFoundError, "not_found"),
    (ModelUnavailableError, "model_unavailable"),
    (ModelIntegrityError, "model_unavailable"),
    (ConfigError, "internal_error"),
    (AnonymizerUnavailableError, "internal_error"),
    (InferenceError, "internal_error"),
    (UnsafePathError, "internal_error"),
    (DatasetError, "internal_error"),
]


@pytest.mark.parametrize(("error_class", "code"), CODES)
def test_errors_codes(error_class: type[AppError], code: str) -> None:
    assert error_class.code == code


def test_errors_hierarchy() -> None:
    assert issubclass(CsvFormatError, InvalidInputError)
    assert issubclass(ModelIntegrityError, ModelUnavailableError)
    assert all(issubclass(error_class, AppError) for error_class, _ in CODES)
    assert len(CODES) == 13
    assert issubclass(AppError, Exception)


def test_errors_detail() -> None:
    error = UnsafePathError("path escapes base")
    assert error.detail == "path escapes base"
    assert str(error) == "path escapes base"
