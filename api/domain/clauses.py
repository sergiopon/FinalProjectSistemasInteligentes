"""Clause splitting and per-aspect polarity of a comment."""

from __future__ import annotations

import re
import string
from collections.abc import Sequence

from api.domain.entities import ASPECT_ORDER, AspectSentiment, ClauseAnalysis
from api.domain.errors import InvalidInputError

_SENTENCE_BOUNDARY: re.Pattern[str] = re.compile(r"(?<![.!?;])[.!?;]++(?=\s|$)")
_CONNECTOR: re.Pattern[str] = re.compile(
    r"\b(?:pero|aunque|sin embargo|no obstante|mientras que)\b", re.IGNORECASE
)
_UNICODE_SPACES: str = (
    "\x1c\x1d\x1e\x1f\x85\xa0\u1680\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007"
    "\u2008\u2009\u200a\u2028\u2029\u202f\u205f\u3000"
)
_STRIP_CHARS: str = string.whitespace + _UNICODE_SPACES + ",;:"
_MIN_CLAUSE_CHARS: int = 3


def split_clauses(text: str) -> tuple[str, ...]:
    """Split a comment into clauses at sentence boundaries and contrast connectors.

    Args:
        text: Comment text, unchanged.

    Returns:
        The clauses in source order, stripped, each at least 3 characters long. When none
        qualifies, the stripped text as a single clause.

    Raises:
        InvalidInputError: If the text is blank.
    """
    if text.strip() == "":
        raise InvalidInputError("text must not be empty")
    pieces = (
        piece.strip(_STRIP_CHARS)
        for sentence in _SENTENCE_BOUNDARY.split(text)
        for piece in _CONNECTOR.split(sentence)
    )
    kept = tuple(piece for piece in pieces if len(piece) >= _MIN_CLAUSE_CHARS)
    return kept or (text.strip(),)


def aspect_sentiments(clauses: Sequence[ClauseAnalysis]) -> tuple[AspectSentiment, ...]:
    """Assign one polarity to each aspect group that some clause mentions.

    For each group the clause with the highest presence score decides; a tie goes to the
    earliest clause. Groups absent from every clause are omitted.

    Args:
        clauses: Per-clause analyses, in source order.

    Returns:
        One item per mentioned group, in ASPECT_ORDER.
    """
    result: list[AspectSentiment] = []
    for group in ASPECT_ORDER:
        candidates = [
            (index, clause)
            for index, clause in enumerate(clauses)
            if group in clause.aspects.present
        ]
        if not candidates:
            continue
        index, clause = max(candidates, key=lambda pair: (pair[1].aspects.score(group), -pair[0]))
        result.append(
            AspectSentiment(
                group=group,
                polarity=clause.probabilities.top(),
                score=clause.aspects.score(group),
                clause_index=index,
            )
        )
    return tuple(result)
