"""What stage the project is really in. Pure functions over the saved specification and its deterministic checks.

A stage is never "done" because the AI said something: it is `completed` only when the approval that covers it is valid for the
current content (or, for generation, when the generator really ran and its checks passed). Everything else is derived from findings,
open questions and open decisions that exist in the specification right now.

Statuses: not_started | in_progress | needs_input | ready_for_review | completed | blocked
"""

from __future__ import annotations

from app.design_studio import approval
from app.schemas.application_definition import ApplicationDefinition

STAGES: tuple[tuple[str, str], ...] = (
    ("brief", "Requirements"),
    ("knowledge", "Domain Knowledge"),
    ("workflow", "Business Process"),
    ("data", "Data Model"),
    ("screen", "Screens & UI"),
    ("rules", "Rules & Logic"),
    ("roles", "Roles & Permissions"),
    ("checks", "Validation"),
    ("export", "Generate Application"),
)
# Where each discovery question belongs.
QUESTION_STAGE = {
    "goal": "brief",
    "problem": "brief",
    "purpose": "brief",
    "users": "brief",
    "outcomes": "brief",
    "functional": "brief",
    "acceptance": "brief",
    "constraints": "brief",
    "accessibility": "brief",
    "performance": "brief",
    "auditability": "brief",
    "domain": "knowledge",
    "data": "data",
    "security": "roles",
    "integrations": "rules",
}
FINDING_STAGE = {
    "brief": "brief",
    "knowledge": "knowledge",
    "workflow": "workflow",
    "data": "data",
    "rules": "rules",
    "roles": "roles",
    "screen": "screen",
    "approval": "screen",
}
# Without these the design cannot be built; the other questions are worth asking but never hold a stage back.
ESSENTIAL_TOPICS = frozenset({"goal", "purpose", "users", "functional", "domain", "data"})


def _entry(status: str, reason: str, **counts: int) -> dict:
    return {
        "status": status,
        "reason": reason,
        "counts": {key: value for key, value in counts.items() if value},
    }


def relevant_findings(definition: ApplicationDefinition, design: dict) -> list[dict]:
    """The design analysis without the two codes that are a next step rather than a defect: the process approval is its own gate, and screens
    that have not been generated yet are what generation is for."""
    generated = definition.generated_frontend is not None  # the application's own model-generated interface
    ignored = {"PROCESS_NOT_APPROVED"} | (set() if generated else {"STEP_NO_SCREEN"})
    return [item for item in design["findings"] if item["code"] not in ignored]


def compute(
    definition: ApplicationDefinition,
    design: dict,
    domain_suggestions: list[dict],
    compile_summary: dict | None = None,
) -> dict:
    business = definition.business
    state = approval.status(definition)
    process_ok, design_ok = (
        state["process"]["state"] == "valid",
        state["design"]["state"] == "valid",
    )
    generated = definition.generated_frontend is not None  # the application's own model-generated interface
    # The design analysis contains every process finding. Two codes are not defects of the design itself: the process approval is
    # its own gate, and screens that have not been generated yet are the next step, not an error.
    findings = relevant_findings(definition, design)
    # An empty section is "not started" or "in progress", not a defect to fix.
    findings_by_stage = [
        item for item in findings if item["code"] not in ("PROCESS_MISSING", "REQUIREMENTS_MISSING")
    ]

    per_stage: dict[str, dict[str, list]] = {
        key: {"defects": [], "decisions": [], "warnings": []} for key, _ in STAGES
    }
    for item in findings_by_stage:
        key = FINDING_STAGE.get(item["tab"])
        if key is None:
            continue
        if item["category"] == "business_decision" or item["code"] in ("QUESTION_OPEN",):
            per_stage[key]["decisions"].append(item)
        elif item["severity"] == "error":
            per_stage[key]["defects"].append(item)
        elif item["severity"] == "warning":
            per_stage[key]["warnings"].append(item)
    open_questions: dict[str, list] = {key: [] for key, _ in STAGES}
    for question in business.questions:
        if question.status == "open":
            open_questions[QUESTION_STAGE.get(question.topic, "brief")].append(question)
    essential = {
        key: [q for q in items if q.topic in ESSENTIAL_TOPICS]
        for key, items in open_questions.items()
    }
    open_decisions = [item for item in business.decisions if item.status != "decided"]

    def judge(
        key: str,
        present: bool,
        gated: bool,
        none_reason: str,
        partial: str | None = None,
        extra_decisions: int = 0,
        assumed: int = 0,
    ) -> dict:
        defects = per_stage[key]["defects"]
        decisions = (
            len([item for item in per_stage[key]["decisions"] if item["code"] != "QUESTION_OPEN"])
            + extra_decisions
        )
        counts = {
            "errors": len(defects),
            "warnings": len(per_stage[key]["warnings"]),
            "open_questions": len(open_questions[key]),
        }
        if not present:
            return _entry("not_started", none_reason, **counts)
        if defects:
            return _entry(
                "blocked",
                f"{len(defects)} issue{'s' if len(defects) != 1 else ''} must be fixed: {defects[0]['message']}",
                **counts,
            )
        approved = (gated and process_ok) or (not gated and design_ok)
        if approved:
            # Approval is the owner's acknowledgement of what is still assumed or unanswered, so those no longer hold the stage back.
            return _entry(
                "completed",
                "Approved at revision "
                + str(state["process" if gated else "design"]["record"]["revision"])
                + ".",
                **counts,
            )
        parts = [
            f"{count} {one if count == 1 else many}"
            for count, one, many in (
                (len(essential[key]), "question", "questions"),
                (decisions, "open decision", "open decisions"),
                (assumed, "unconfirmed rule", "unconfirmed rules"),
            )
            if count
        ]
        if parts:
            return _entry(
                "needs_input", "Your input is needed: " + ", ".join(parts) + ".", **counts
            )
        if partial:
            return _entry("in_progress", partial, **counts)
        return _entry("ready_for_review", "Ready for you to review and approve.", **counts)

    goal = bool(business.brief.goal.strip())
    functional = [item for item in business.requirements if item.kind == "functional"]
    result: dict[str, dict] = {}
    partial = (
        None
        if goal and functional and (business.brief.user_types or business.roles)
        else (
            "Still gathering what the application must do."
            if goal and not functional
            else "Still gathering who uses it."
            if goal
            else "The goal is not captured yet."
        )
    )
    result["brief"] = judge(
        "brief",
        goal or bool(business.requirements),
        True,
        "Describe the application you want to build.",
        partial,
    )
    has_pack = bool(business.knowledge)
    if has_pack:
        result["knowledge"] = judge(
            "knowledge",
            True,
            True,
            "",
            extra_decisions=sum(1 for item in open_decisions if item.origin),
        )
    elif business.brief.domain_id or domain_suggestions:
        result["knowledge"] = _entry(
            "in_progress",
            "The design is built from your requirements; reference knowledge for this domain only informs it.",
        )
    else:
        result["knowledge"] = _entry(
            "not_started", "The domain is identified from your description."
        )
    result["workflow"] = judge(
        "workflow",
        bool(definition.workflow_definitions),
        True,
        "The business process is designed once the requirements are clear.",
    )
    result["data"] = judge(
        "data",
        bool(business.entities),
        True,
        "The data model is derived from the process and requirements.",
    )
    result["rules"] = judge(
        "rules",
        bool(business.rules or business.exceptions),
        True,
        "Rules and exceptions are captured as the process is designed.",
        assumed=sum(1 for item in business.rules if item.status == "assumption"),
    )
    result["roles"] = judge(
        "roles",
        bool(business.roles),
        True,
        "Roles are identified from who does what in the process.",
    )

    if not definition.workflow_definitions or not process_ok:
        if generated:
            result["screen"] = judge("screen", True, False, "")
        else:
            result["screen"] = _entry(
                "not_started",
                "Screens are derived from the process and records; approve the process to review them."
                if definition.workflow_definitions
                else "Screens are derived from the process once it is designed.",
            )
    else:
        # Approved process: the schema-driven client already gives every step and record its screen; a generated interface is optional.
        result["screen"] = judge("screen", True, False, "")

    errors = sum(1 for item in findings if item["severity"] == "error")
    waiting = sum(
        1
        for item in findings
        if item["category"] == "business_decision" and item["severity"] == "error"
    )
    counts = {
        "errors": errors,
        "warnings": sum(1 for item in findings if item["severity"] == "warning"),
    }
    if not (business.requirements or definition.workflow_definitions):
        result["checks"] = _entry(
            "not_started", "Checks run as soon as there is something to check."
        )
    elif not (business.requirements and definition.workflow_definitions):
        result["checks"] = _entry(
            "in_progress",
            "Waiting for "
            + ("requirements" if not business.requirements else "a business process")
            + " to check against.",
        )
    elif errors - waiting > 0:
        result["checks"] = _entry(
            "blocked",
            f"{errors - waiting} blocking issue{'s' if errors - waiting != 1 else ''} to fix.",
            **counts,
        )
    elif waiting:
        result["checks"] = _entry(
            "needs_input",
            f"{waiting} business decision{'s' if waiting != 1 else ''} need an answer.",
            **counts,
        )
    elif process_ok and design_ok:
        result["checks"] = _entry(
            "completed", "No blocking findings; process and design are approved.", **counts
        )
    else:
        result["checks"] = _entry(
            "ready_for_review",
            "No blocking findings. Waiting for a separate approver."
            if not process_ok
            else "Process approved. Design approval is next.",
            **counts,
        )

    if not design_ok:
        result["export"] = _entry(
            "not_started",
            "Generation needs an approved process and design."
            if not process_ok
            else "Generation needs the design to be approved.",
        )
    elif compile_summary is None:
        result["export"] = _entry(
            "ready_for_review", "Approved. Generate to build the application and check it."
        )
    elif compile_summary["status"] == "generated":
        result["export"] = _entry(
            "completed",
            f"Generated {compile_summary['files']} files; {compile_summary['checks_passed']} checks passed.",
        )
    else:
        result["export"] = _entry(
            "blocked", compile_summary.get("reason") or "Generation is blocked for this revision."
        )
    return result


def next_step(stages: dict) -> dict:
    """The one thing most worth doing next, taken from the stage statuses."""
    for status in ("needs_input", "blocked", "in_progress", "ready_for_review"):
        for key, label in STAGES:
            if stages[key]["status"] == status:
                return {
                    "stage": key,
                    "label": label,
                    "status": status,
                    "text": stages[key]["reason"],
                }
    for key, label in STAGES:
        if stages[key]["status"] == "not_started":
            return {
                "stage": key,
                "label": label,
                "status": "not_started",
                "text": stages[key]["reason"],
            }
    return {
        "stage": "export",
        "label": "Generate Application",
        "status": "completed",
        "text": "Everything is complete.",
    }
