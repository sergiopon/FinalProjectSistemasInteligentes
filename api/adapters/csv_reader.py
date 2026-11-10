"""Bounded reader of raw text/csv request bodies (SEC-01, SEC-11)."""

from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterable, Iterator
from typing import Final

from api.adapters.settings import LimitSettings
from api.domain.entities import Comment
from api.domain.errors import CsvFormatError, InvalidInputError, PayloadTooLargeError

FEEDBACK_COLUMN: Final[str] = "feedback"
COURSE_COLUMN: Final[str] = "curso"


async def read_body_limited(
    chunks: AsyncIterable[bytes], content_length: str | None, limits: LimitSettings
) -> bytes:
    """Read a request body in memory without exceeding the upload limit.

    Args:
        chunks: Body chunks, such as Starlette's Request.stream().
        content_length: Raw Content-Length header value, or None when absent.
        limits: Upload ceilings.

    Returns:
        The whole body.

    Raises:
        InvalidInputError: If content_length is not a plain decimal number.
        PayloadTooLargeError: If the declared or the actual size exceeds the limit.
    """
    if content_length is not None:
        if not (content_length.isascii() and content_length.isdigit()):
            raise InvalidInputError("invalid content-length")
        if int(content_length) > limits.max_upload_bytes:
            raise PayloadTooLargeError("content-length over limit")
    body = bytearray()
    async for chunk in chunks:
        body.extend(chunk)
        if len(body) > limits.max_upload_bytes:
            raise PayloadTooLargeError("body over limit")
    return bytes(body)


def _column_indexes(header: list[str]) -> tuple[int, int]:
    """Return the positions of the feedback and course columns."""
    if len(set(header)) != len(header):
        raise CsvFormatError("duplicate column names")
    if FEEDBACK_COLUMN not in header or COURSE_COLUMN not in header:
        raise CsvFormatError("missing required columns")
    return header.index(FEEDBACK_COLUMN), header.index(COURSE_COLUMN)


def _comment_from_row(row: list[str], indexes: tuple[int, int], limits: LimitSettings) -> Comment:
    """Build a comment from a data row."""
    feedback = row[indexes[0]].strip()
    if not 1 <= len(feedback) <= limits.max_text_chars:
        raise CsvFormatError("feedback length out of range")
    course = row[indexes[1]].strip()
    return Comment(text=feedback, course=course or None)


def _data_rows(rows: Iterator[list[str]], header: list[str]) -> Iterator[list[str]]:
    """Yield the rows that are neither blank nor a repeated header."""
    for row in rows:
        if not row or [cell.strip() for cell in row] == header:
            continue
        if len(row) != len(header):
            raise CsvFormatError("row has a wrong number of fields")
        yield row


def _comments(rows: Iterator[list[str]], limits: LimitSettings) -> tuple[Comment, ...]:
    """Read the header and the data rows into comments."""
    first_row = next(rows, None)
    if first_row is None:
        raise CsvFormatError("missing header row")
    header = [cell.strip() for cell in first_row]
    indexes = _column_indexes(header)
    comments: list[Comment] = []
    for number, row in enumerate(_data_rows(rows, header), start=1):
        if number > limits.max_upload_rows:
            raise PayloadTooLargeError("too many rows")
        comments.append(_comment_from_row(row, indexes, limits))
    return tuple(comments)


def parse_csv_body(body: bytes, limits: LimitSettings) -> tuple[Comment, ...]:
    """Parse an uploaded CSV body into comments.

    Args:
        body: Raw request body.
        limits: Upload and text ceilings.

    Returns:
        The comments in file order.

    Raises:
        PayloadTooLargeError: If the body or the row count exceeds its limit.
        CsvFormatError: If the body is not valid UTF-8 or CSV, lacks the required columns,
            has no data rows or has a feedback outside the length bounds.
    """
    if len(body) > limits.max_upload_bytes:
        raise PayloadTooLargeError("body over limit")
    try:
        text = body.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise CsvFormatError("body is not valid UTF-8") from error
    rows = csv.reader(io.StringIO(text, newline=""), strict=True)
    try:
        comments = _comments(rows, limits)
    except csv.Error as error:
        raise CsvFormatError("malformed CSV") from error
    if not comments:
        raise CsvFormatError("no data rows")
    return comments
