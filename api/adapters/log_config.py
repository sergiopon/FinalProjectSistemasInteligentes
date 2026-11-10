"""Logging setup: one stdout handler with redaction for the root and uvicorn loggers."""

from __future__ import annotations

import logging
import sys
import time
from typing import Final

from api.domain.safety import RedactingFilter

LOG_FORMAT: Final = "time=%(asctime)s level=%(levelname)s logger=%(name)s %(message)s"
DATE_FORMAT: Final = "%Y-%m-%dT%H:%M:%SZ"
UVICORN_LOGGERS: Final[tuple[str, ...]] = ("uvicorn", "uvicorn.error", "uvicorn.access")


def build_stdout_handler() -> logging.Handler:
    """Build the only handler of the service: stdout, UTC timestamps, redacting filter.

    Returns:
        Handler that writes key=value lines with contact data masked.
    """
    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    formatter.converter = time.gmtime
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(RedactingFilter())
    return handler


def configure_logging(level: int = logging.INFO) -> None:
    """Route every record of the root and uvicorn loggers to one redacting stdout handler.

    Args:
        level: Level of the root logger.
    """
    logging.basicConfig(handlers=[build_stdout_handler()], level=level, force=True)
    for name in UVICORN_LOGGERS:
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
