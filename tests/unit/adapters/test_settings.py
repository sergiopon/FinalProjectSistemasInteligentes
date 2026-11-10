"""Tests for load_settings in api/adapters/settings.py."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from api.adapters.settings import REPO_ROOT, load_settings
from api.domain.errors import ConfigError

VALID_DOCUMENT: dict[str, object] = {
    "costs": {"error_cost": 5.0, "review_cost": 1.0, "review_if_set_not_singleton": True},
    "conformal": {"alpha": 0.1},
    "limits": {"max_text_chars": 2000, "max_upload_bytes": 2097152, "max_upload_rows": 5000},
    "models_dir": "models",
}


def document_with(section: str, key: str, literal: str) -> str:
    """Return the valid document as JSON text with one value replaced by a raw JSON literal."""
    document = copy.deepcopy(VALID_DOCUMENT)
    section_values = document[section]
    assert isinstance(section_values, dict)
    section_values[key] = "@@"
    return json.dumps(document).replace('"@@"', literal)


def write_config(directory: Path, text: str) -> Path:
    path = directory / "app.json"
    path.write_text(text, encoding="utf-8")
    return path


def assert_config_error(path: Path, detail: str) -> None:
    with pytest.raises(ConfigError) as info:
        load_settings(path)
    assert info.value.detail == detail


def test_load_settings_reads_versioned_config() -> None:
    settings = load_settings(REPO_ROOT / "config" / "app.json")
    assert settings.costs.error_cost == 5.0
    assert settings.costs.review_cost == 1.0
    assert settings.costs.review_if_set_not_singleton is True
    assert settings.conformal.alpha == 0.1
    assert settings.limits.max_text_chars == 2000
    assert settings.limits.max_upload_bytes == 2097152
    assert settings.limits.max_upload_rows == 5000
    assert settings.models_dir == REPO_ROOT / "models"


def test_load_settings_accepts_integer_cost(tmp_path: Path) -> None:
    path = write_config(tmp_path, document_with("costs", "review_cost", "1"))
    assert load_settings(path).costs.review_cost == 1.0


def test_load_settings_rejects_missing_file(tmp_path: Path) -> None:
    assert_config_error(tmp_path / "absent.json", "config file unreadable")


def test_load_settings_rejects_directory_path(tmp_path: Path) -> None:
    assert_config_error(tmp_path, "config file unreadable")


def test_load_settings_rejects_non_utf8(tmp_path: Path) -> None:
    path = tmp_path / "app.json"
    path.write_bytes(b"\xff\xfe")
    assert_config_error(path, "config file unreadable")


def test_load_settings_rejects_invalid_json(tmp_path: Path) -> None:
    assert_config_error(write_config(tmp_path, '{"costs": '), "config file is not valid JSON")


def test_load_settings_rejects_non_object(tmp_path: Path) -> None:
    assert_config_error(write_config(tmp_path, "[1]"), "config invalid: <root>")


@pytest.mark.parametrize("literal", ["Infinity", "NaN", "0.0", "-1.0", '"5"', "true"])
def test_load_settings_rejects_bad_error_cost(tmp_path: Path, literal: str) -> None:
    path = write_config(tmp_path, document_with("costs", "error_cost", literal))
    assert_config_error(path, "config invalid: costs.error_cost")


def test_load_settings_rejects_non_bool_flag(tmp_path: Path) -> None:
    path = write_config(tmp_path, document_with("costs", "review_if_set_not_singleton", "1"))
    assert_config_error(path, "config invalid: costs.review_if_set_not_singleton")


@pytest.mark.parametrize("literal", ["0.0", "1.0"])
def test_load_settings_rejects_alpha_bounds(tmp_path: Path, literal: str) -> None:
    path = write_config(tmp_path, document_with("conformal", "alpha", literal))
    assert_config_error(path, "config invalid: conformal.alpha")


@pytest.mark.parametrize(
    ("field", "literal"),
    [
        ("max_text_chars", "2001"),
        ("max_text_chars", "0"),
        ("max_text_chars", "2000.0"),
        ("max_upload_bytes", "2097153"),
        ("max_upload_rows", "5001"),
    ],
)
def test_load_settings_rejects_limit_ceilings(tmp_path: Path, field: str, literal: str) -> None:
    path = write_config(tmp_path, document_with("limits", field, literal))
    assert_config_error(path, f"config invalid: limits.{field}")


@pytest.mark.parametrize("value", ["/srv/models", "../outside"])
def test_load_settings_rejects_bad_models_dir(tmp_path: Path, value: str) -> None:
    document = {**VALID_DOCUMENT, "models_dir": value}
    path = write_config(tmp_path, json.dumps(document))
    assert_config_error(path, "config invalid: models_dir")


def test_load_settings_joins_multiple_locations(tmp_path: Path) -> None:
    document = copy.deepcopy(VALID_DOCUMENT)
    costs, conformal, limits = document["costs"], document["conformal"], document["limits"]
    assert isinstance(costs, dict)
    assert isinstance(conformal, dict)
    assert isinstance(limits, dict)
    costs["error_cost"] = 0.0
    conformal["alpha"] = 1.0
    limits["max_upload_rows"] = 5001
    path = write_config(tmp_path, json.dumps(document))
    assert_config_error(
        path, "config invalid: costs.error_cost,conformal.alpha,limits.max_upload_rows"
    )


def test_load_settings_rejects_extra_key(tmp_path: Path) -> None:
    path = write_config(tmp_path, json.dumps({**VALID_DOCUMENT, "debug": True}))
    assert_config_error(path, "config invalid: debug")


def test_load_settings_rejects_missing_section(tmp_path: Path) -> None:
    document = {key: value for key, value in VALID_DOCUMENT.items() if key != "conformal"}
    path = write_config(tmp_path, json.dumps(document))
    assert_config_error(path, "config invalid: conformal")


def test_app_settings_is_frozen() -> None:
    settings = load_settings(REPO_ROOT / "config" / "app.json")
    attribute = "models_dir"
    with pytest.raises(ValidationError):
        setattr(settings, attribute, Path("x"))
