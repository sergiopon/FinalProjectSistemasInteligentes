"""Validated application settings read from config/app.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from api.domain.errors import ConfigError, UnsafePathError
from api.domain.safety import resolve_within

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
ROOT_LOCATION: Final = "<root>"


class CostSettings(BaseModel):
    """Costs that drive the expected-utility decision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    error_cost: float = Field(gt=0, allow_inf_nan=False, strict=True)
    review_cost: float = Field(gt=0, allow_inf_nan=False, strict=True)
    review_if_set_not_singleton: bool = Field(strict=True)


class ConformalSettings(BaseModel):
    """Conformal prediction parameters."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    alpha: float = Field(gt=0, lt=1, allow_inf_nan=False, strict=True)


class LimitSettings(BaseModel):
    """Ceilings for text length and uploads."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    max_text_chars: int = Field(ge=1, le=2000, strict=True)
    max_upload_bytes: int = Field(ge=1, le=2097152, strict=True)
    max_upload_rows: int = Field(ge=1, le=5000, strict=True)


class AppSettings(BaseModel):
    """Whole configuration document."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    costs: CostSettings
    conformal: ConformalSettings
    limits: LimitSettings
    models_dir: Path

    @field_validator("models_dir")
    @classmethod
    def _models_dir_inside_repo(cls, value: Path) -> Path:
        if value.is_absolute():
            raise ValueError("models_dir must be relative")
        try:
            return resolve_within(REPO_ROOT, value)
        except UnsafePathError as error:
            raise ValueError("models_dir escapes the repository") from error


def _error_locations(error: ValidationError) -> str:
    """Join the location of every validation error without echoing any value."""
    locations = [
        ".".join(str(part) for part in item["loc"]) or ROOT_LOCATION for item in error.errors()
    ]
    return ",".join(locations)


def load_settings(path: Path) -> AppSettings:
    """Read and validate the configuration file.

    Args:
        path: Location of the JSON configuration file.

    Returns:
        Frozen settings whose models_dir is absolute and inside the repository.

    Raises:
        ConfigError: If the file is unreadable, is not JSON or violates the schema. The detail
            never contains a value of the file.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ConfigError("config file unreadable") from error
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as error:
        raise ConfigError("config file is not valid JSON") from error
    try:
        return AppSettings.model_validate(document)
    except ValidationError as error:
        raise ConfigError("config invalid: " + _error_locations(error)) from error
