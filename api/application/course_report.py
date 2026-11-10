"""Use case that builds one report per course from the analyses of a batch."""

from __future__ import annotations

from collections.abc import Sequence

from api.domain.decision import CommentAnalysis
from api.domain.entities import ASPECT_ORDER, Comment, Decision, Polarity
from api.domain.errors import InferenceError, InvalidInputError
from api.domain.priority import rank_priorities
from api.domain.reports import AspectCell, CourseReport, PolarityCounts, TopicSummary
from api.ports.text import Anonymizer, Summarizer, TopicModel

UNKNOWN_COURSE: str = "unknown"
MIN_QUOTE_COUNT: int = 1
MAX_QUOTE_COUNT: int = 10
MAX_BATCH_COMMENTS: int = 5000


def _course_key(comment: Comment) -> str:
    """Return the course of a comment, or UNKNOWN_COURSE when it has none."""
    return comment.course if comment.course is not None else UNKNOWN_COURSE


def _group_indices(comments: Sequence[Comment]) -> tuple[tuple[str, tuple[int, ...]], ...]:
    """Return (course, indices in input order) pairs sorted by course ascending."""
    groups: dict[str, list[int]] = {}
    for index, comment in enumerate(comments):
        groups.setdefault(_course_key(comment), []).append(index)
    return tuple((course, tuple(groups[course])) for course in sorted(groups))


def _polarity_counts(analyses: Sequence[CommentAnalysis]) -> PolarityCounts:
    """Count the decided labels of the analyses."""
    labels = [analysis.decision.label for analysis in analyses]
    return PolarityCounts(
        labels.count(Polarity.NEGATIVE),
        labels.count(Polarity.NEUTRAL),
        labels.count(Polarity.POSITIVE),
    )


def _aspect_cells(analyses: Sequence[CommentAnalysis]) -> tuple[AspectCell, ...]:
    """Return one cell per aspect group, in ASPECT_ORDER, with mentions split by polarity."""
    cells: list[AspectCell] = []
    for group in ASPECT_ORDER:
        polarities = [
            item.polarity
            for analysis in analyses
            for item in analysis.aspects
            if item.group is group
        ]
        cells.append(
            AspectCell(
                group,
                len(polarities),
                polarities.count(Polarity.NEGATIVE),
                polarities.count(Polarity.NEUTRAL),
                polarities.count(Polarity.POSITIVE),
            )
        )
    return tuple(cells)


def _validate(comments: Sequence[Comment], analyses: Sequence[CommentAnalysis]) -> None:
    """Reject unpaired, empty or oversized inputs."""
    if len(comments) != len(analyses):
        raise InvalidInputError("comments and analyses differ in length")
    if not 1 <= len(comments) <= MAX_BATCH_COMMENTS:
        raise InvalidInputError("batch must hold between 1 and 5000 comments")
    for comment, analysis in zip(comments, analyses, strict=True):
        if analysis.comment.course != comment.course:
            raise InvalidInputError("comment and analysis are not paired")


class BuildCourseReport:
    """Builds the aspect heatmap, priorities, topics and masked quotes of each course."""

    def __init__(
        self,
        anonymizer: Anonymizer,
        summarizer: Summarizer,
        topics: TopicModel,
        quote_count: int = 3,
    ) -> None:
        """Store the dependencies.

        Args:
            anonymizer: Masks personal data in quotes.
            summarizer: Picks representative sentences.
            topics: Assigns comments to topics.
            quote_count: Quotes per course, 1 to 10.

        Raises:
            InvalidInputError: quote_count is outside 1..10.
        """
        if not MIN_QUOTE_COUNT <= quote_count <= MAX_QUOTE_COUNT:
            raise InvalidInputError("quote_count must be between 1 and 10")
        self._anonymizer = anonymizer
        self._summarizer = summarizer
        self._topics = topics
        self._quote_count = quote_count

    def execute(
        self, comments: Sequence[Comment], analyses: Sequence[CommentAnalysis]
    ) -> tuple[CourseReport, ...]:
        """Build one report per course.

        Args:
            comments: Original comments of the batch, unmasked.
            analyses: Analyses paired by position with the comments.

        Returns:
            One report per course, sorted by course; every quote is masked (SEC-02).

        Raises:
            InvalidInputError: The inputs are unpaired, empty or hold more than 5000 comments.
            InferenceError: A port returns a wrong number of results or no sentence.
        """
        _validate(comments, analyses)
        texts = tuple(comment.text for comment in comments)
        topic_ids = self._topics.assign(texts)
        if len(topic_ids) != len(texts):
            raise InferenceError(
                f"TopicModel.assign returned {len(topic_ids)} results for {len(texts)} texts"
            )
        return tuple(
            self._report(
                course,
                [texts[i] for i in indices],
                [topic_ids[i] for i in indices],
                [analyses[i] for i in indices],
            )
            for course, indices in _group_indices(comments)
        )

    def _report(
        self,
        course: str,
        texts: Sequence[str],
        topic_ids: Sequence[int],
        analyses: Sequence[CommentAnalysis],
    ) -> CourseReport:
        """Build the report of one course from its texts, topic ids and analyses."""
        aspects = _aspect_cells(analyses)
        review_count = sum(1 for item in analyses if item.decision.decision is Decision.REVIEW)
        summary = self._summarizer.summarize(texts, self._quote_count)
        return CourseReport(
            course=course,
            comment_count=len(texts),
            review_count=review_count,
            polarity_counts=_polarity_counts(analyses),
            aspects=aspects,
            priorities=rank_priorities(aspects, len(texts)),
            topics=self._topic_summaries(texts, topic_ids),
            quotes=tuple(self._anonymizer.mask(sentence) for sentence in summary),
        )

    def _topic_summaries(
        self, texts: Sequence[str], topic_ids: Sequence[int]
    ) -> tuple[TopicSummary, ...]:
        """Return one summary per topic of the course, largest first, then by topic id."""
        sizes = {topic: topic_ids.count(topic) for topic in set(topic_ids)}
        result: list[TopicSummary] = []
        for topic in sorted(sizes, key=lambda item: (-sizes[item], item)):
            topic_texts = [text for text, tid in zip(texts, topic_ids, strict=True) if tid == topic]
            summary = self._summarizer.summarize(topic_texts, 1)
            if not summary:
                raise InferenceError("Summarizer.summarize returned no sentence")
            quote = self._anonymizer.mask(summary[0])
            result.append(TopicSummary(topic, sizes[topic], self._topics.terms(topic), quote))
        return tuple(result)
