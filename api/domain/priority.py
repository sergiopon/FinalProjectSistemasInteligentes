"""Priority ranking of the aspect groups of a course."""

from __future__ import annotations

from collections.abc import Sequence

from api.domain.entities import ASPECT_ORDER
from api.domain.errors import InvalidInputError
from api.domain.reports import AspectCell, PriorityEntry

MIN_SUPPORT: int = 5


def _validate(cells: Sequence[AspectCell], comment_count: int) -> None:
    """Reject a bad comment count, a repeated group or more mentions than comments."""
    if comment_count < 1:
        raise InvalidInputError("comment_count must be >= 1")
    for position, cell in enumerate(cells):
        if cell.group in {earlier.group for earlier in cells[:position]}:
            raise InvalidInputError("duplicate aspect group")
        if cell.mentions > comment_count:
            raise InvalidInputError("mentions must not exceed comment_count")


def _shares(cell: AspectCell, comment_count: int) -> tuple[float, float, float]:
    """Return the prevalence, the smoothed negative share and their product."""
    prevalence = cell.mentions / comment_count
    smoothed_negative_share = (cell.negative + 1) / (cell.mentions + 2)
    return prevalence, smoothed_negative_share, prevalence * smoothed_negative_share


def rank_priorities(cells: Sequence[AspectCell], comment_count: int) -> tuple[PriorityEntry, ...]:
    """Rank the aspect groups of a course by how much they call for action.

    The score is the share of comments that mention the group times its smoothed share of
    negative mentions. Groups without mentions are omitted. Floats are not rounded.

    Args:
        cells: One cell per aspect group, without repeated groups.
        comment_count: Comments analyzed, at least 1.

    Returns:
        One entry per group with mentions, best score first; a tie follows ASPECT_ORDER.

    Raises:
        InvalidInputError: If comment_count is below 1, a group repeats, or a cell has more
            mentions than comment_count.
    """
    _validate(cells, comment_count)
    mentioned = [cell for cell in cells if cell.mentions >= 1]
    ordered = sorted(
        mentioned,
        key=lambda cell: (-_shares(cell, comment_count)[2], ASPECT_ORDER.index(cell.group)),
    )
    entries: list[PriorityEntry] = []
    for rank, cell in enumerate(ordered, start=1):
        prevalence, smoothed_negative_share, score = _shares(cell, comment_count)
        entries.append(
            PriorityEntry(
                rank=rank,
                group=cell.group,
                mentions=cell.mentions,
                negative=cell.negative,
                prevalence=prevalence,
                smoothed_negative_share=smoothed_negative_share,
                score=score,
                low_support=cell.mentions < MIN_SUPPORT,
            )
        )
    return tuple(entries)
