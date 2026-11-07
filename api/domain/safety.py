"""Path confinement and personal-data masking shared by adapters and ml."""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Final

from api.domain.errors import UnsafePathError

EMAIL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,}"
)
PHONE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\+?\(?\d[\d\s().-]{5,}\d")
ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b\d{6,10}\b")
MIN_PHONE_DIGITS: Final[int] = 7
MAX_UNSEPARATED_DIGITS: Final[int] = 10
EMAIL_MASK: Final = "[EMAIL]"
PHONE_MASK: Final = "[PHONE]"
ID_MASK: Final = "[ID]"


def resolve_within(base: Path, candidate: Path) -> Path:
    """Resolve candidate under base and refuse any result outside it.

    Creates no file or directory. An absolute candidate replaces base, so it passes only
    when it already lies inside base.

    Args:
        base: Existing directory that confines the result.
        candidate: Path relative to base, or absolute.

    Returns:
        Absolute path with symlinks resolved.

    Raises:
        UnsafePathError: If base or candidate cannot be resolved, or the result escapes base.
    """
    try:
        root = base.resolve(strict=True)
    except (OSError, RuntimeError, ValueError) as error:
        raise UnsafePathError("base cannot be resolved") from error
    try:
        target = (root / candidate).resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as error:
        raise UnsafePathError("path cannot be resolved") from error
    if not target.is_relative_to(root):
        raise UnsafePathError("path escapes base")
    return target


def _is_word_boundary(text: str, index: int) -> bool:
    """Return True when index lies outside text or holds a non-word character."""
    return not 0 <= index < len(text) or not (text[index].isalnum() or text[index] == "_")


def _mask_phone(match: re.Match[str]) -> str:
    """Mask a candidate with a separator, or over 10 digits not glued to word characters."""
    matched = match.group()
    digits = sum(character.isdecimal() for character in matched)
    if digits < MIN_PHONE_DIGITS:
        return matched
    standalone = _is_word_boundary(match.string, match.start() - 1) and _is_word_boundary(
        match.string, match.end()
    )
    if digits < len(matched) or (digits > MAX_UNSEPARATED_DIGITS and standalone):
        return PHONE_MASK
    return matched


def mask_contact_data(text: str) -> str:
    """Replace emails, phone numbers and numeric ids in text with their masks.

    Args:
        text: Free text that may hold contact data.

    Returns:
        The text with emails, then phones, then ids masked; equal to text when nothing matches.
    """
    masked = EMAIL_PATTERN.sub(EMAIL_MASK, text)
    masked = PHONE_PATTERN.sub(_mask_phone, masked)
    return ID_PATTERN.sub(ID_MASK, masked)


def redact(text: str) -> str:
    """Describe text by its length and a short hash, without revealing it.

    Args:
        text: Text that must not be logged; it MUST be valid Unicode.

    Returns:
        A marker with the character count and the first 8 hex digits of the UTF-8 SHA-256.

    Raises:
        UnicodeEncodeError: If text holds a lone surrogate.
    """
    return f"<redacted len={len(text)} sha={hashlib.sha256(text.encode()).hexdigest()[:8]}>"


class RedactingFilter(logging.Filter):
    """Logging filter that masks contact data in messages and tracebacks."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Mask the formatted message and the traceback of record in place.

        Args:
            record: Record about to be emitted.

        Returns:
            Always True; the filter never drops a record.
        """
        record.msg = mask_contact_data(record.getMessage())
        record.args = None
        if record.exc_info:
            record.exc_text = mask_contact_data(
                logging.Formatter().formatException(record.exc_info)
            )
            record.exc_info = None
        return True
