"""Tests for build_stdout_handler and configure_logging in api/adapters/log_config.py."""

from __future__ import annotations

import logging
import re
import sys
from collections.abc import Iterator

import pytest

from api.adapters.log_config import (
    UVICORN_LOGGERS,
    build_stdout_handler,
    configure_logging,
)
from api.domain.safety import RedactingFilter


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    saved_uvicorn = {
        name: (list(logging.getLogger(name).handlers), logging.getLogger(name).propagate)
        for name in UVICORN_LOGGERS
    }
    yield
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)
    for name, (handlers, propagate) in saved_uvicorn.items():
        logger = logging.getLogger(name)
        logger.handlers[:] = handlers
        logger.propagate = propagate


def make_logger() -> logging.Logger:
    logger = logging.Logger("api.test")
    logger.setLevel(logging.INFO)
    logger.addHandler(build_stdout_handler())
    return logger


def test_build_stdout_handler_writes_key_value_line(capsys: pytest.CaptureFixture[str]) -> None:
    make_logger().info("event=startup version=%s", "v001")
    captured = capsys.readouterr()
    assert captured.err == ""
    pattern = (
        r"^time=\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z level=INFO logger=api.test "
        r"event=startup version=v001$"
    )
    assert re.match(pattern, captured.out.rstrip("\n"))
    assert len(captured.out.splitlines()) == 1


def test_build_stdout_handler_has_redacting_filter() -> None:
    handler = build_stdout_handler()
    assert any(isinstance(item, RedactingFilter) for item in handler.filters)


def test_build_stdout_handler_masks_contact_data(capsys: pytest.CaptureFixture[str]) -> None:
    make_logger().info("contact=%s", "ana.gomez@uni.edu.co")
    out = capsys.readouterr().out
    assert out.rstrip("\n").endswith("contact=[EMAIL]")
    assert "ana.gomez" not in out


def test_build_stdout_handler_masks_traceback(capsys: pytest.CaptureFixture[str]) -> None:
    logger = make_logger()
    try:
        raise ValueError("bad ana@x.com")
    except ValueError:
        logger.exception("event=failed")
    out = capsys.readouterr().out
    assert "ValueError: bad [EMAIL]" in out
    assert "ana@x.com" not in out


def test_build_stdout_handler_uses_utc() -> None:
    handler = build_stdout_handler()
    assert handler.formatter is not None
    record = logging.LogRecord("api.test", logging.INFO, __file__, 1, "event=x", None, None)
    record.created = 0.0
    assert handler.formatter.format(record).startswith("time=1970-01-01T00:00:00Z ")


def test_configure_logging_replaces_root_handlers() -> None:
    configure_logging(logging.DEBUG)
    configure_logging(logging.DEBUG)
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert any(isinstance(item, RedactingFilter) for item in root.handlers[0].filters)
    assert root.level == logging.DEBUG


def test_configure_logging_routes_uvicorn_loggers() -> None:
    uvicorn_logger = logging.getLogger("uvicorn")
    uvicorn_logger.addHandler(logging.StreamHandler(sys.stderr))
    uvicorn_logger.propagate = False
    configure_logging()
    for name in UVICORN_LOGGERS:
        logger = logging.getLogger(name)
        assert logger.handlers == []
        assert logger.propagate is True
