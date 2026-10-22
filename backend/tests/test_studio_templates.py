"""The application template library: every template is valid, readable and distinct, and recommendations are honest."""

from app.design_studio.discovery import blank_definition
from app.design_studio.templates import recommend, templates
from app.schemas.application_definition import ApplicationDefinition, TemplateSelection


def _contrast(a: str, b: str) -> float:
    def luminance(color: str) -> float:
        channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        r, g, b_ = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * r + 0.7152 * g + 0.0722 * b_

    high, low = sorted((luminance(a), luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


def test_every_template_is_valid_readable_and_has_its_own_design():
    library = templates()
    assert len(library) == 10
    assert len({item.theme.id for item in library}) == 10, "each domain has its own theme preset"
    assert len({item.nav_style for item in library}) >= 4, "navigation differs between domains, not only colour"
    for item in library:
        c = item.theme.colors
        for text, background in ((c.text, c.background), (c.text, c.surface), (c.primary_text, c.primary), (c.nav_text, c.nav_background), (c.muted, c.surface)):
            assert _contrast(text, background) >= 4.5, f"{item.id}: {text} on {background}"
        assert all(m.note for m in item.modules if m.status == "requires_integration"), "an integration gap always says what is needed"


def test_recommendation_explains_the_match_and_never_overstates_coverage():
    raw = blank_definition().model_dump(mode="json")
    raw["business"]["brief"].update(goal="Transport management to plan shipments, assign carriers and handle delays.", domain_id="transport_management")
    make = lambda i, text: {"id": i, "statement": text, "kind": "functional", "priority": "must", "status": "draft", "acceptance_criteria": [{"id": "ac_" + i[4:], "statement": "x"}]}  # noqa: E731
    raw["business"]["requirements"] = [
        make("req_assign", "Planners assign a carrier and vehicle to each transport order"),
        make("req_gps", "Live GPS map of every truck"),
        make("req_pay", "Payroll for drivers"),
    ]
    definition = ApplicationDefinition.model_validate(raw)
    best = recommend(definition)[0]
    assert best["template"]["id"] == "transport_tms" and best["fit"] == "strong" and best["reasons"]
    status = {entry["requirement_id"]: entry["status"] for entry in best["coverage"]}
    assert status == {"req_assign": "supported", "req_gps": "requires_integration", "req_pay": "unsupported"}
    chosen = definition.model_copy(update={"template": TemplateSelection(template_id="transport_tms", version="1.0.0", selected_at="2026-10-22T00:00:00Z")})
    assert ApplicationDefinition.model_validate(chosen.model_dump(mode="json")).template.template_id == "transport_tms"
