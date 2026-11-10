from __future__ import annotations

import re

from api.adapters.monitoring import utc_now_iso


def test_utc_now_iso_format() -> None:
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", utc_now_iso())
