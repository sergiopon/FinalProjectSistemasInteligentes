"""Tests for api/adapters/csv_reader.py."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from api.adapters.csv_reader import parse_csv_body, read_body_limited
from api.adapters.settings import LimitSettings
from api.domain.entities import Comment
from api.domain.errors import CsvFormatError, InvalidInputError, PayloadTooLargeError

LIMITS = LimitSettings(max_text_chars=2000, max_upload_bytes=2097152, max_upload_rows=5000)
BOM = "\ufeff"
MULTI = (
    "id,curso,feedback\r\n1,Bases de datos,  Buen curso  \r\n\r\n"
    "id,curso,feedback\r\n2,,Mal horario\r\n"
)
EXPECTED = (Comment("Buen curso", "Bases de datos"), Comment("Mal horario", None))


def parse(text: str) -> tuple[Comment, ...]:
    return parse_csv_body(text.encode("utf-8"), LIMITS)


def test_parse_csv_reads_comments() -> None:
    assert parse_csv_body((BOM + MULTI).encode("utf-8"), LIMITS) == EXPECTED


def test_parse_csv_without_bom() -> None:
    assert parse(MULTI) == EXPECTED


def test_parse_csv_rejects_invalid_utf8() -> None:
    for body in (b"feedback,curso\n\xff,x\n", b"feedback,curso\nlecci\xf3n,x\n"):
        with pytest.raises(CsvFormatError):
            parse_csv_body(body, LIMITS)


@pytest.mark.parametrize(
    "text",
    ["feedback\nhola\n", "feedback,feedback,curso\na,b,c\n", BOM + BOM + "feedback,curso\na,b\n"],
)
def test_parse_csv_rejects_columns(text: str) -> None:
    with pytest.raises(CsvFormatError):
        parse(text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "feedback,curso\n",
        "feedback,curso\nfeedback,curso\n",
        "feedback,curso\nhola\n",
        'feedback,curso\n"hola,x\n',
        "feedback,curso\n" + "a" * 131073 + ",x\n",
    ],
)
def test_parse_csv_rejects_structure(text: str) -> None:
    with pytest.raises(CsvFormatError):
        parse(text)


def test_parse_csv_text_length_bounds() -> None:
    for feedback in ("   ", "a" * 2001):
        with pytest.raises(CsvFormatError):
            parse(f"feedback,curso\n{feedback},x\n")
    assert parse("feedback,curso\n" + "a" * 2000 + ",x\n") == (Comment("a" * 2000, "x"),)


def test_parse_csv_row_limit() -> None:
    assert len(parse("feedback,curso\n" + "hola,x\n" * 5000)) == 5000
    with pytest.raises(PayloadTooLargeError):
        parse("feedback,curso\n" + "hola,x\n" * 5001)


def test_parse_csv_body_over_limit() -> None:
    small = LimitSettings(max_text_chars=2000, max_upload_bytes=10, max_upload_rows=5000)
    with pytest.raises(PayloadTooLargeError):
        parse_csv_body(b"x" * 11, small)


class Chunks:
    def __init__(self, items: list[bytes]) -> None:
        self.items = items
        self.yielded = 0

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for item in self.items:
            self.yielded += 1
            yield item


def read(items: list[bytes], content_length: str | None) -> tuple[bytes, int]:
    chunks = Chunks(items)
    body = asyncio.run(read_body_limited(chunks, content_length, LIMITS))
    return body, chunks.yielded


def test_read_body_limited_cases() -> None:
    assert read([b"ab", b"cd"], "4") == (b"abcd", 2)
    exact = [b"a" * 2097152]
    assert read(exact, None)[0] == exact[0]

    over = Chunks([b"a"])
    with pytest.raises(PayloadTooLargeError):
        asyncio.run(read_body_limited(over, "2097153", LIMITS))
    assert over.yielded == 0

    streamed = Chunks([b"a" * 699051] * 3)
    with pytest.raises(PayloadTooLargeError):
        asyncio.run(read_body_limited(streamed, None, LIMITS))
    assert streamed.yielded == 3

    for bad in ("abc", "-1", "²"):
        with pytest.raises(InvalidInputError):
            read([b"a"], bad)
