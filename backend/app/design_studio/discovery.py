"""Deterministic requirements discovery.

Each topic has a fixed question and a test for whether the design already answers it. Questions are only added for
unanswered topics, kept (with their answers) once answered, and withdrawn when the design itself now covers the topic.
No model is used; nothing here infers business requirements.
"""

from __future__ import annotations

from typing import Callable

from app.design_studio.knowledge.provider import KnowledgeProvider, identify_domains
from app.schemas.application_definition import ApplicationDefinition, BusinessDefinition

Covered = Callable[[BusinessDefinition], bool]


def _nfr(category: str) -> Covered:
    return lambda b: any(
        r.kind == "non_functional" and r.category == category for r in b.requirements
    )


def _criteria(b: BusinessDefinition) -> bool:
    active = [r for r in b.requirements if r.status in ("draft", "agreed")]
    return bool(active) and all(r.acceptance_criteria for r in active)


TOPICS: tuple[tuple[str, str, str, Covered], ...] = (
    (
        "q_goal",
        "goal",
        "What business goal should this application achieve?",
        lambda b: bool(b.brief.goal.strip()),
    ),
    (
        "q_problem",
        "problem",
        "What problem does it solve today, and for whom?",
        lambda b: bool(b.brief.problem.strip()),
    ),
    (
        "q_domain",
        "domain",
        "Which business domain does it belong to?",
        lambda b: b.brief.domain_id is not None,
    ),
    (
        "q_purpose",
        "purpose",
        "What is the application for: which part of the business process does it support?",
        lambda b: bool(b.brief.purpose.strip() or b.brief.capability.strip()),
    ),
    (
        "q_users",
        "users",
        "Who will use it, and what is each type of user responsible for?",
        lambda b: bool(b.brief.user_types or b.roles),
    ),
    (
        "q_outcomes",
        "outcomes",
        "Which outcomes will show that it works?",
        lambda b: bool(b.brief.outcomes),
    ),
    (
        "q_functional",
        "functional",
        "What must users be able to do? Record each as a functional requirement.",
        lambda b: any(r.kind == "functional" for r in b.requirements),
    ),
    (
        "q_acceptance",
        "acceptance",
        "How will each requirement be accepted? Add acceptance criteria to every active requirement.",
        _criteria,
    ),
    (
        "q_security",
        "security",
        "Who may see or change what? Record any security requirement.",
        _nfr("security"),
    ),
    (
        "q_auditability",
        "auditability",
        "Which actions must be recorded for audit?",
        _nfr("auditability"),
    ),
    (
        "q_accessibility",
        "accessibility",
        "Which accessibility standard must the screens meet?",
        _nfr("accessibility"),
    ),
    (
        "q_performance",
        "performance",
        "Are there response-time or volume expectations?",
        _nfr("performance"),
    ),
    (
        "q_data",
        "data",
        "Which business records does it read, create or change?",
        lambda b: bool(b.entities),
    ),
    (
        "q_integrations",
        "integrations",
        "Which systems does it read from or write to, and what happens when they are unavailable?",
        lambda b: bool(b.integrations or b.brief.dependencies),
    ),
    (
        "q_constraints",
        "constraints",
        "Are there constraints such as regulation, deadlines or technology choices?",
        lambda b: bool(b.brief.constraints),
    ),
)


def blank_definition() -> ApplicationDefinition:
    return ApplicationDefinition.model_validate(
        {
            "version": 2,
            "id": "app_intake",
            "metadata": {
                "name": "Untitled application",
                "description": "",
                "purpose": "",
                "domain": "other",
            },
            "screens": [
                {
                    "id": "screen_main",
                    "title": "New screen",
                    "components": [
                        {
                            "kind": "container",
                            "id": "container_main",
                            "placement": {"span": 12},
                            "children": [],
                            "props": {
                                "title": "New section",
                                "layout": {
                                    "mobile": {"mode": "stack", "columns": 1},
                                    "tablet": {"mode": "grid", "columns": 2},
                                    "desktop": {"mode": "grid", "columns": 2},
                                },
                            },
                        }
                    ],
                }
            ],
            "theme": {
                "primary": "#00756A",
                "background": "#FFFFFF",
                "surface": "#F7F5F0",
                "text": "#14181A",
                "font": "inter",
            },
        }
    )


def discover(
    definition: ApplicationDefinition, provider: KnowledgeProvider, brief_text: str | None = None
) -> tuple[ApplicationDefinition, list[dict]]:
    raw = definition.model_dump(mode="json")
    business = raw["business"]
    if brief_text and brief_text.strip() and not business["brief"]["goal"].strip():
        business["brief"]["goal"] = " ".join(brief_text.split())[:2000]
    current = BusinessDefinition.model_validate(business)
    existing = {question["id"]: question for question in business["questions"]}
    questions = []
    for question_id, topic, text, covered in TOPICS:
        previous = existing.pop(question_id, None)
        answered = previous is not None and (
            previous["status"] != "open" or previous["answer"].strip()
        )
        if answered:
            questions.append(previous)  # an answer is never discarded
        elif not covered(current):
            questions.append(
                previous
                or {"id": question_id, "topic": topic, "text": text, "answer": "", "status": "open"}
            )
    questions.extend(
        existing.values()
    )  # questions added outside this catalogue are kept as they are
    business["questions"] = questions
    text = " ".join(
        [
            business["brief"]["goal"],
            business["brief"]["problem"],
            business["brief"]["purpose"],
            brief_text or "",
        ]
    )
    return ApplicationDefinition.model_validate(raw), identify_domains(text, provider)
