"""Spark's presentation choice: text by default, a table, chart or card only when the verified records support it."""

from app.schemas.agent import AgentResponse, Interpretation
from app.schemas.intelligence import Answer, Clarification, Fact, QueryResponse, ResultItem
from app.schemas.spark import SparkPlan
from app.services.spark_presentation import present


def item(title, kind="warehouse", **facts):
    return ResultItem(kind=kind, key=title, title=title, facts=[Fact(label=k.replace("_", " "), value=v) for k, v in facts.items()])


def answer(summary, results, clarify=False):
    return QueryResponse(question="q", intent="PART_TO_LOCATION", intent_label="Where", understood_by="llm", entities=[],
                         answer=Answer(summary=summary, grounded=True, source="template"), results=results, total=len(results),
                         evidence=[], provenance=[], graph_path=[], warnings=[], actions=[],
                         clarification=Clarification(question="Which part?") if clarify else None, elapsed_ms=1)


def test_intelligence_format_follows_the_request_and_the_records():
    stock = [item("Zwolle", Units="2", Status="Low"), item("Muenster", Units="8", Status="Stocked"), item("Gent", Units="0", Status="Out")]
    named = answer("Zwolle has 2, Muenster 8 and Gent none.", stock)
    unnamed = answer("Three locations hold the part.", stock)
    cases = [
        ("answer", answer("Nothing is recorded.", []), "text"),
        ("answer", answer("NVM-1 is a bucket.", [item("NVM-1", kind="part", Category="Attachments")]), "text"),
        ("answer", named, "text"),              # the sentence already names every record: no repeated table
        ("answer", unnamed, "table"),           # consistent records the sentence does not list
        ("answer", answer("A bucket that fits two machines.", [item("M1", kind="path", Connection="Fits"),
                                                                item("M2", kind="path", Connection="Fits")]), "text"),
        ("compare", named, "table"),            # asked to compare: a table even when the sentence names them
        ("chart", unnamed, "chart"),
        ("graph", unnamed, "graph"),
        ("answer", answer("Which part?", stock, clarify=True), "choices"),
        ("answer", answer("Mixed.", [item("A", kind="part", Category="x"), item("B", kind="machine", Family="y")]), "cards"),
    ]
    for view, response, expected in cases:
        assert present(view, response, None, None).intelligence == expected, (view, response.answer.summary)

    shown = present("chart", unnamed, None, None)
    assert [(r.name, r.value) for r in shown.chart.rows] == [("Zwolle", 2), ("Muenster", 8), ("Gent", 0)]
    table = present("answer", unnamed, None, None).table
    assert table.columns == ["Location", "Units", "Status"] and table.rows[1].cells == ["8", "Stocked"]


def test_a_chart_is_never_drawn_from_missing_or_non_numeric_values():
    for records in ([item("A", Units="3"), item("B", Units=None)], [item("A", Status="Low"), item("B", Status="High")],
                    [item("A", Units="0"), item("B", Units="0")]):
        shown = present("chart", answer("Two places.", records), None, None)
        assert shown.intelligence != "chart" and shown.chart is None and shown.note


def test_shopping_account_and_plan_fallbacks():
    def shop(state, n):
        from app.schemas.agent import Candidate, PartSummary
        parts = [Candidate.model_construct(part=PartSummary.model_construct(part_number=f"NVM-{i}"), recommended=i == 0) for i in range(n)]
        return AgentResponse(request="r", state=state, interpretation=Interpretation(), steps=[], candidates=parts)
    assert present("answer", None, shop("need_machine", 0), None).shopping == "text"
    assert present("answer", None, shop("recommendation", 3), None).shopping == "product"
    assert present("compare", None, shop("recommendation", 3), None).shopping == "compare"
    assert present("compare", None, shop("recommendation", 1), None).shopping == "product"

    assert present("answer", None, None, {"answer": {"text": "Shipped."}, "contexts": {"LOGISTICS": {}}}).account == "text"
    assert present("answer", None, None, {"contexts": {"LOGISTICS": {"lookup": "ROUTE_OPTIONS"}}}).account == "detail"
    assert present("answer", None, None, {"clarification": {"question": "Which order?"}, "contexts": {}}).account == "text"

    # a presentation value the model invents never fails the request
    assert SparkPlan(intelligence="x?", shopping=None, account=None, clarification=None, view="pie").view == "answer"
