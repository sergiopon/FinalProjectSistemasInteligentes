"""Application error hierarchy shared by every layer."""

from __future__ import annotations

from typing import ClassVar


class AppError(Exception):
    """Base class of every error the application raises on purpose.

    Attributes:
        code: Stable identifier that the entry layer maps to an HTTP status and message.
        detail: Diagnostic text for operators. It MUST NOT contain comment text.
    """

    code: ClassVar[str] = "internal_error"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class InvalidInputError(AppError):
    """A value or request failed validation."""

    code = "invalid_input"


class CsvFormatError(InvalidInputError):
    """An uploaded CSV file is malformed."""

    code = "invalid_csv"


class PayloadTooLargeError(AppError):
    """An upload exceeds the configured size limit."""

    code = "payload_too_large"


class UnsupportedMediaTypeError(AppError):
    """A request carries a content type the route does not accept."""

    code = "unsupported_media_type"


class NotFoundError(AppError):
    """The requested resource does not exist."""

    code = "not_found"


class ModelUnavailableError(AppError):
    """No usable model bundle is available."""

    code = "model_unavailable"


class ModelIntegrityError(ModelUnavailableError):
    """A model bundle failed its hash or version verification."""


class ConfigError(AppError):
    """The configuration file is missing or invalid."""


class AnonymizerUnavailableError(AppError):
    """The anonymizer could not be loaded."""


class InferenceError(AppError):
    """A model failed while predicting."""


class UnsafePathError(AppError):
    """A path resolves outside its allowed directory."""


class DatasetError(AppError):
    """The training dataset is missing or malformed."""
