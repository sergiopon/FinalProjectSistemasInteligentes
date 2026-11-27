"""Tests for resolve_within and mask_contact_data in api/domain/safety.py."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from api.domain.errors import UnsafePathError
from api.domain.safety import mask_contact_data, resolve_within


def assert_unsafe(base: Path, candidate: Path, detail: str) -> UnsafePathError:
    with pytest.raises(UnsafePathError) as info:
        resolve_within(base, candidate)
    assert info.value.detail == detail
    return info.value


def test_resolve_within_inside(tmp_path: Path) -> None:
    result = resolve_within(tmp_path, Path("v001/manifest.json"))
    assert result == tmp_path.resolve() / "v001/manifest.json"


def test_resolve_within_normalizes_dots(tmp_path: Path) -> None:
    result = resolve_within(tmp_path, Path("v001/../v002/x.json"))
    assert result == tmp_path.resolve() / "v002/x.json"


def test_resolve_within_dot_returns_base(tmp_path: Path) -> None:
    assert resolve_within(tmp_path, Path(".")) == tmp_path.resolve()


def test_resolve_within_parent_escape(tmp_path: Path) -> None:
    assert_unsafe(tmp_path, Path("../x"), "path escapes base")


def test_resolve_within_absolute_escape(tmp_path: Path) -> None:
    assert_unsafe(tmp_path, Path("/etc/passwd"), "path escapes base")


def test_resolve_within_symlink_escape(tmp_path: Path) -> None:
    (tmp_path / "link").symlink_to("/etc")
    assert_unsafe(tmp_path, Path("link/passwd"), "path escapes base")


def test_resolve_within_symlink_loop(tmp_path: Path) -> None:
    (tmp_path / "loop").symlink_to(tmp_path / "loop")
    error = assert_unsafe(tmp_path, Path("loop/x"), "path cannot be resolved")
    assert isinstance(error.__cause__, RuntimeError)


def test_resolve_within_missing_base(tmp_path: Path) -> None:
    error = assert_unsafe(tmp_path / "missing", Path("a"), "base cannot be resolved")
    assert isinstance(error.__cause__, FileNotFoundError)


def test_resolve_within_creates_nothing(tmp_path: Path) -> None:
    resolve_within(tmp_path, Path("new/dir/file.json"))
    assert not (tmp_path / "new").exists()


def test_resolve_within_absolute_inside(tmp_path: Path) -> None:
    result = resolve_within(tmp_path, tmp_path.resolve() / "a.json")
    assert result == tmp_path.resolve() / "a.json"


def test_resolve_within_null_byte(tmp_path: Path) -> None:
    error = assert_unsafe(tmp_path, Path("a\x00b"), "path cannot be resolved")
    assert isinstance(error.__cause__, ValueError)


def test_resolve_within_base_symlink_loop(tmp_path: Path) -> None:
    (tmp_path / "loop").symlink_to(tmp_path / "loop")
    error = assert_unsafe(tmp_path / "loop", Path("a"), "base cannot be resolved")
    assert isinstance(error.__cause__, RuntimeError)


def test_resolve_within_base_null_byte() -> None:
    error = assert_unsafe(Path("a\x00b"), Path("x"), "base cannot be resolved")
    assert isinstance(error.__cause__, ValueError)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Escribir a ana.gomez@uni.edu.co o al 300 123 4567, código 20231045",
            "Escribir a [EMAIL] o al [PHONE], código [ID]",
        ),
        ("Llamar al +57 (300) 123-4567 hoy", "Llamar al [PHONE] hoy"),
        ("Fax 601\t2345678", "Fax [PHONE]"),
        ("Número 573001234567", "Número [PHONE]"),
        ("Llamar al 3001234567", "Llamar al [ID]"),
        ("Juan.Perez99@correo.com", "[EMAIL]"),
        ("ana@uni.co1juan@x.com", "[EMAIL][EMAIL]"),
        ("llamar al 300 123 4567ya", "llamar al [PHONE]ya"),
        ("cel3001 234 567", "cel[PHONE]"),
        ("req ab12345678901cd", "req ab12345678901cd"),
        ("Código 12345", "Código 12345"),
        ("Tel 123 456", "Tel 123 456"),
        ("Semestres 2023-1 y 2023-2", "Semestres 2023-1 y 2023-2"),
        ("Sin datos de contacto.", "Sin datos de contacto."),
    ],
)
def test_mask_contact_data_vectors(text: str, expected: str) -> None:
    assert mask_contact_data(text) == expected


def test_mask_contact_data_long_token_is_linear() -> None:
    long_token = "a" * 100000
    started = time.perf_counter()
    assert mask_contact_data(long_token) == long_token
    assert mask_contact_data("@" + long_token) == "@" + long_token
    assert time.perf_counter() - started < 1.0


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("client 172.18.0.1:54586 - GET /health", "client 172.18.0.1:54586 - GET /health"),
        ("from 127.0.0.1", "from 127.0.0.1"),
        ("llamar al 300.123.45.67", "llamar al [PHONE]"),
    ],
)
def test_mask_contact_data_keeps_ipv4_addresses(text: str, expected: str) -> None:
    assert mask_contact_data(text) == expected
