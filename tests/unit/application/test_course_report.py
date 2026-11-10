from __future__ import annotations

import pytest

from api.application.analyze import AnalyzeBatch
from api.application.course_report import BuildCourseReport
from api.domain.decision import CommentAnalysis, DecisionCosts, DecisionResult
from api.domain.entities import (
    ASPECT_ORDER,
    AspectGroup,
    AspectSentiment,
    ClassProbabilities,
    Comment,
    ConformalSet,
    Decision,
    DecisionReason,
    Polarity,
)
from api.domain.errors import InferenceError, InvalidInputError
from api.domain.reports import CourseReport, PolarityCounts, TopicSummary
from tests.fixtures.fake_ports import (
    FakeAnonymizer,
    FakeAspectModel,
    FakePolarityModel,
    FakeSummarizer,
    FakeTopicModel,
)

TERMS_0 = ("parciales", "examen", "notas", "preguntas", "dificultad")
TERMS_1 = ("contenido", "horario", "clase", "tema", "curso")
c0 = Comment("Ana explicó bien el contenido.", "Redes")
c1 = Comment("Los parciales fueron difíciles.", "Redes")
c2 = Comment("El horario fue malo.", "Redes")
c3 = Comment("Buen curso.")


def analysis(
    comment: Comment,
    label: Polarity,
    decision: Decision,
    aspects: tuple[tuple[AspectGroup, Polarity], ...] = (),
) -> CommentAnalysis:
    values = {polarity: 0.8 if polarity is label else 0.1 for polarity in Polarity}
    reason = (
        DecisionReason.CONFIDENT if decision is Decision.CLASSIFY else DecisionReason.EXPECTED_COST
    )
    return CommentAnalysis(
        comment,
        ClassProbabilities(
            values[Polarity.NEGATIVE], values[Polarity.NEUTRAL], values[Polarity.POSITIVE]
        ),
        ConformalSet(frozenset({label}), 0.9),
        DecisionResult(decision, reason, label),
        tuple(
            AspectSentiment(group, polarity, 0.9, index)
            for index, (group, polarity) in enumerate(aspects)
        ),
        (),
    )


a0 = analysis(c0, Polarity.POSITIVE, Decision.CLASSIFY, ((AspectGroup.CONTENT, Polarity.POSITIVE),))
a1 = analysis(
    c1,
    Polarity.NEGATIVE,
    Decision.REVIEW,
    ((AspectGroup.CONTENT, Polarity.NEGATIVE), (AspectGroup.ASSESSMENT, Polarity.NEGATIVE)),
)
a2 = analysis(
    c2,
    Polarity.NEGATIVE,
    Decision.CLASSIFY,
    ((AspectGroup.ORGANIZATION_SCHEDULE, Polarity.NEGATIVE),),
)
a3 = analysis(c3, Polarity.NEUTRAL, Decision.REVIEW)


def topic_model(short_by: int = 0) -> FakeTopicModel:
    return FakeTopicModel(
        {c0.text: 1, c1.text: 0, c2.text: 1, c3.text: 0}, {0: TERMS_0, 1: TERMS_1}, short_by
    )


def use_case(
    topics: FakeTopicModel | None = None,
    summarizer: FakeSummarizer | None = None,
    quote_count: int = 3,
) -> BuildCourseReport:
    return BuildCourseReport(
        FakeAnonymizer(), summarizer or FakeSummarizer(), topics or topic_model(), quote_count
    )


def run() -> tuple[CourseReport, ...]:
    return use_case().execute((c0, c1, c2, c3), (a0, a1, a2, a3))


def cell_counts(report: CourseReport, group: AspectGroup) -> tuple[int, int, int, int]:
    cell = report.aspects[ASPECT_ORDER.index(group)]
    return (cell.mentions, cell.negative, cell.neutral, cell.positive)


def test_course_report_groups_and_sorts() -> None:
    reports = run()
    assert len(reports) == 2
    assert reports[0].course == "Redes"
    assert reports[1].course == "unknown"


def test_course_report_counts() -> None:
    reports = run()
    assert reports[0].comment_count == 3
    assert reports[0].review_count == 1
    assert reports[0].polarity_counts == PolarityCounts(2, 0, 1)
    assert reports[1].comment_count == 1
    assert reports[1].review_count == 1
    assert reports[1].polarity_counts == PolarityCounts(0, 1, 0)


def test_course_report_aspect_cells() -> None:
    reports = run()
    assert tuple(cell.group for cell in reports[0].aspects) == ASPECT_ORDER
    expected = {
        AspectGroup.CONTENT: (2, 1, 0, 1),
        AspectGroup.ASSESSMENT: (1, 1, 0, 0),
        AspectGroup.ORGANIZATION_SCHEDULE: (1, 1, 0, 0),
    }
    for group in ASPECT_ORDER:
        assert cell_counts(reports[0], group) == expected.get(group, (0, 0, 0, 0))
    assert all(cell.mentions == 0 for cell in reports[1].aspects)


def test_course_report_priorities() -> None:
    reports = run()
    priorities = reports[0].priorities
    assert [entry.group for entry in priorities] == [
        AspectGroup.CONTENT,
        AspectGroup.ASSESSMENT,
        AspectGroup.ORGANIZATION_SCHEDULE,
    ]
    assert [entry.rank for entry in priorities] == [1, 2, 3]
    expected_scores = [0.3333333333333333, 0.2222222222222222, 0.2222222222222222]
    for entry, score in zip(priorities, expected_scores, strict=True):
        assert entry.score == pytest.approx(score, abs=1e-12)
        assert entry.low_support is True
    assert priorities[0].prevalence == pytest.approx(2 / 3, abs=1e-12)
    assert priorities[0].smoothed_negative_share == pytest.approx(0.5, abs=1e-12)
    assert priorities[1].prevalence == pytest.approx(1 / 3, abs=1e-12)
    assert priorities[1].smoothed_negative_share == pytest.approx(2 / 3, abs=1e-12)
    assert reports[1].priorities == ()


def test_course_report_topics() -> None:
    reports = run()
    assert reports[0].topics == (
        TopicSummary(1, 2, TERMS_1, "[PERSON] explicó bien el contenido."),
        TopicSummary(0, 1, TERMS_0, "Los parciales fueron difíciles."),
    )
    assert reports[1].topics == (TopicSummary(0, 1, TERMS_0, "Buen curso."),)


def test_course_report_quotes_masked() -> None:
    reports = run()
    assert reports[0].quotes == (
        "[PERSON] explicó bien el contenido.",
        "Los parciales fueron difíciles.",
        "El horario fue malo.",
    )
    assert reports[1].quotes == ("Buen curso.",)
    texts = [quote for report in reports for quote in report.quotes]
    texts += [topic.quote for report in reports for topic in report.topics]
    assert all("Ana" not in text for text in texts)


def test_course_report_assign_once_on_original_texts() -> None:
    topics = topic_model()
    use_case(topics).execute((c0, c1, c2, c3), (a0, a1, a2, a3))
    assert topics.assign_calls == [(c0.text, c1.text, c2.text, c3.text)]


def test_course_report_summarizer_calls() -> None:
    summarizer = FakeSummarizer()
    use_case(summarizer=summarizer).execute((c0, c1, c2, c3), (a0, a1, a2, a3))
    for call in (
        ((c0.text, c2.text), 1),
        ((c1.text,), 1),
        ((c0.text, c1.text, c2.text), 3),
        ((c3.text,), 1),
        ((c3.text,), 3),
    ):
        assert call in summarizer.calls


def test_course_report_topic_size_tie_by_id() -> None:
    first = Comment("Primer comentario.", "Redes")
    second = Comment("Segundo comentario.", "Redes")
    topics = FakeTopicModel({first.text: 3, second.text: 1}, {1: TERMS_1, 3: TERMS_0})
    pairs = (
        analysis(first, Polarity.POSITIVE, Decision.CLASSIFY),
        analysis(second, Polarity.POSITIVE, Decision.CLASSIFY),
    )
    reports = use_case(topics).execute((first, second), pairs)
    assert [topic.topic for topic in reports[0].topics] == [1, 3]


def test_course_report_rejects_length_mismatch() -> None:
    topics = topic_model()
    with pytest.raises(InvalidInputError) as error:
        use_case(topics).execute((c0, c1), (a0,))
    assert error.value.detail == "comments and analyses differ in length"
    assert topics.assign_calls == []


def test_course_report_rejects_empty() -> None:
    with pytest.raises(InvalidInputError) as error:
        use_case().execute((), ())
    assert error.value.detail == "batch must hold between 1 and 5000 comments"


def test_course_report_rejects_unpaired() -> None:
    with pytest.raises(InvalidInputError) as error:
        use_case().execute((c3,), (a0,))
    assert error.value.detail == "comment and analysis are not paired"


def test_course_report_short_assign() -> None:
    with pytest.raises(InferenceError) as error:
        use_case(topic_model(short_by=1)).execute((c0, c1, c2, c3), (a0, a1, a2, a3))
    assert error.value.detail == "TopicModel.assign returned 3 results for 4 texts"


def test_course_report_empty_summary() -> None:
    with pytest.raises(InferenceError) as error:
        use_case(summarizer=FakeSummarizer(empty=True)).execute((c0, c1, c2, c3), (a0, a1, a2, a3))
    assert error.value.detail == "Summarizer.summarize returned no sentence"


def test_course_report_rejects_quote_count() -> None:
    for count in (0, 11):
        with pytest.raises(InvalidInputError) as error:
            use_case(quote_count=count)
        assert error.value.detail == "quote_count must be between 1 and 10"
    use_case(quote_count=1)
    use_case(quote_count=10)


def test_course_report_with_analyze_batch() -> None:
    batch = AnalyzeBatch(
        FakePolarityModel({}, {}),
        FakeAspectModel({}),
        FakeAnonymizer(),
        DecisionCosts(5.0, 1.0, True),
    )
    batch_result = batch.execute((c0, c3))
    reports = use_case(FakeTopicModel({}, {0: TERMS_0})).execute((c0, c3), batch_result)
    assert len(reports) == 2
    assert reports[0].course == "Redes"
    assert reports[0].quotes == ("[PERSON] explicó bien el contenido.",)
