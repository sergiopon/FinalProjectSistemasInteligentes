"""Tests for redact and RedactingFilter in api/domain/safety.py."""

from __future__ import annotations

import io
import logging
import sys

import pytest

from api.domain.safety import RedactingFilter, redact


def contact_record() -> logging.LogRecord:
    return logging.LogRecord(
        "t", logging.INFO, "f", 1, "contact %s row=%d", ("ana@uni.edu.co", 3), None
    )


def stream_logger(name: str) -> tuple[logging.Logger, logging.StreamHandler[io.StringIO]]:
    logger = logging.getLogger(name)
    logger.propagate = False
    handler = logging.StreamHandler(io.StringIO())
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(RedactingFilter())
    logger.addHandler(handler)
    return logger, handler


def test_redact_vectors() -> None:
    assert redact("Juan Pérez") == "<redacted len=10 sha=090fd624>"
    assert redact("") == "<redacted len=0 sha=e3b0c442>"
    assert redact("El curso fue bastante bueno") == "<redacted len=27 sha=c489921e>"


def test_redact_lone_surrogate_raises() -> None:
    with pytest.raises(UnicodeEncodeError):
        redact("\ud800")


def test_redacting_filter_masks_message_and_args() -> None:
    record = contact_record()
    assert RedactingFilter().filter(record) is True
    assert record.msg == "contact [EMAIL] row=3"
    assert record.args is None


def test_redacting_filter_idempotent() -> None:
    record = contact_record()
    redacting_filter = RedactingFilter()
    redacting_filter.filter(record)
    assert record.msg == "contact [EMAIL] row=3"
    redacting_filter.filter(record)
    assert record.msg == "contact [EMAIL] row=3"


def test_redacting_filter_masks_traceback() -> None:
    try:
        raise ValueError("id 1234567")
    except ValueError:
        record = logging.LogRecord("t", logging.ERROR, "f", 1, "failed", None, sys.exc_info())
    RedactingFilter().filter(record)
    assert record.exc_text is not None
    assert record.exc_text.splitlines()[-1] == "ValueError: id [ID]"
    assert "1234567" not in record.exc_text
    assert record.exc_info is None


def test_redacting_filter_on_handler_message() -> None:
    logger, handler = stream_logger("tests.safety.message")
    try:
        logger.error("contact %s", "ana@uni.edu.co")
        assert handler.stream.getvalue() == "contact [EMAIL]\n"
    finally:
        logger.removeHandler(handler)


def test_redacting_filter_on_handler_exception() -> None:
    logger, handler = stream_logger("tests.safety.exception")
    try:
        try:
            raise ValueError("id 1234567")
        except ValueError:
            logger.exception("failed row=%d", 3)
        output = handler.stream.getvalue()
        lines = output.splitlines()
        assert lines[0] == "failed row=3"
        assert lines[-1] == "ValueError: id [ID]"
        assert "1234567" not in output
    finally:
        logger.removeHandler(handler)


def test_redacting_filter_percent_in_message() -> None:
    record = logging.LogRecord(
        "t", logging.INFO, "f", 1, "rate 100%% for %s", ("ana@uni.edu.co",), None
    )
    RedactingFilter().filter(record)
    assert record.msg == "rate 100% for [EMAIL]"
    assert record.getMessage() == "rate 100% for [EMAIL]"


def test_redacting_filter_bad_args_propagates() -> None:
    record = logging.LogRecord("t", logging.INFO, "f", 1, "x %d", ("a",), None)
    with pytest.raises(TypeError):
        RedactingFilter().filter(record)


def test_redacting_filter_empty_exc_info() -> None:
    record = logging.LogRecord("t", logging.INFO, "f", 1, "m", None, (None, None, None))
    assert RedactingFilter().filter(record) is True
    assert record.exc_text == "NoneType: None"
    assert record.exc_info is None


def test_redacting_filter_bad_format_propagates() -> None:
    record = logging.LogRecord("t", logging.INFO, "f", 1, "x %y", ("a",), None)
    with pytest.raises(ValueError, match="unsupported format"):
        RedactingFilter().filter(record)
