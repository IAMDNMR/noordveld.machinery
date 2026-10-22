"""Voice-first Design Studio: speech, the conversation turn, proposals, revert, and the live project state.

Included into the Design Studio router (so identity, organization and permission gates apply to every route here).

* A turn is planned by the agent (language model or local rules), then applied by the deterministic action engine.
  Additive, low-impact changes are saved as a new revision at once; changes to roles, rules, approvals, processes and reference
  knowledge are returned as a PROPOSAL bound to the exact revision and content digests, and are saved only by `/studio/apply`.
* Every saved change is an ordinary project revision, so history, comparison, approval staleness and safe regeneration work unchanged.
* Nothing here approves anything. Approval stays a separate action by a separate approver.
"""

from __future__ import annotations

import hashlib
import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.dependencies import CurrentUser
from app.design_studio.releases import ReleaseStore, get_release_store, retain_package
from app.api.routes.design_studio import (
    DomainPacks,
    Knowledge,
    ProjectUser,
    Projects,
    _current_at,
    _error,
    _store_call,
)
from app.assistant import studio_agent
from app.assistant.contracts import ProviderDisabled, SpeechProvider
from app.assistant.providers import get_speech, get_studio_llm, studio_assistant_status
from app.assistant.speech_deepgram import MAX_AUDIO_BYTES, SpeechUnavailable
from app.assistant.studio_actions import (
    DECISION_ACTIONS,
    REVIEW_ACTIONS,
    apply_actions,
    parse_actions,
)
from app.design_studio import approval, guided
from app.design_studio import stages as stage_model
from app.design_studio.completeness import analyze
from app.design_studio.diff import compare
from app.design_studio.discovery import discover
from app.design_studio.knowledge.provider import identify_domains
from app.design_studio.frontend_generation import is_current
from app.design_studio.settle import settle
from app.orgs.audited import AuditedRoute
from app.orgs.directory import OrgDirectory, get_org_directory
from app.schemas.application_definition import ApplicationDefinition, StudioFlow

router = APIRouter(route_class=AuditedRoute)
MAX_PROPOSAL_ACTIONS = 25


# ── voice ──────────────────────────────────────────────────────────────


def _describe(item) -> dict:
    found = item.status() if hasattr(item, "status") else item
    return {
        "capability": found.capability,
        "enabled": found.enabled,
        "provider": found.provider,
        "reason": found.reason,
        "credential_present": found.credential_present,
    }


@router.get("/voice/status")
def voice_status(_: CurrentUser, speech: Annotated[SpeechProvider, Depends(get_speech)]):
    """What can work right now. Never contains a credential; a disabled state says why."""
    return {"assistant": _describe(studio_assistant_status()), "speech": _describe(speech)}


def _speech_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProviderDisabled):
        return _error(503, "voice_unavailable", str(exc))
    return _error(502, "speech_failed", str(exc))


@router.post("/voice/transcribe")
async def transcribe(
    request: Request, _: CurrentUser, speech: Annotated[SpeechProvider, Depends(get_speech)]
):
    """Speech to text. The recording is processed in memory and discarded; the text goes back to the browser to be shown before it is sent."""
    if int(request.headers.get("content-length") or 0) > MAX_AUDIO_BYTES:
        raise _error(
            413, "audio_too_large", "That recording is too long. Keep it under about a minute."
        )
    audio = await request.body()
    try:
        result = await run_in_threadpool(
            speech.transcribe, None, audio, request.headers.get("content-type", "")
        )
    except (ProviderDisabled, SpeechUnavailable) as exc:
        raise _speech_error(exc) from None
    return {"text": result.text, "confidence": result.confidence, "language": result.language}


class SpeakRequest(BaseModel):
    model_config = {"extra": "forbid"}
    text: str = Field(min_length=1, max_length=1500)


@router.post("/voice/speak")
async def speak(
    body: SpeakRequest, _: CurrentUser, speech: Annotated[SpeechProvider, Depends(get_speech)]
):
    try:
        audio = await run_in_threadpool(speech.synthesize, None, body.text)
    except (ProviderDisabled, SpeechUnavailable) as exc:
        raise _speech_error(exc) from None
    return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "no-store"})


# ── project state ─────────────────────────────────────────────────────────


def _compile_summary(definition, domain, knowledge) -> dict:
    from app.design_studio.compiler import compile_project

    result = compile_project(definition, domain, knowledge)
    failed = [c for c in result["checks"] if c["status"] == "fail"]
    return {
        "status": result["status"],
        "files": len(result["files"]),
        "checks_passed": sum(1 for c in result["checks"] if c["status"] == "pass"),
        "checks_failed": len(failed),
        "reason": (result["plan"]["reasons"] or [None])[0]
        or (failed[0].get("message") if failed else None),
    }


def state_payload(
    definition: ApplicationDefinition, knowledge, compile_summary: dict | None = None
) -> dict:
    process, design = (
        analyze(definition, knowledge, "process"),
        analyze(definition, knowledge, "design"),
    )
    brief = definition.business.brief
    matches = identify_domains(
        " ".join(
            [brief.goal, brief.problem, brief.purpose, brief.capability, definition.metadata.name]
        ),
        knowledge,
    )
    stages = stage_model.compute(definition, design, matches, compile_summary)
    if definition.studio_flow:
        stages = guided.statuses(definition, stages)
    adopted = {link.pack_id for link in definition.business.knowledge}
    # Reference knowledge worth offering: what is adopted, plus the packs of the project's domain and of every other matched domain
    # whose verified knowledge covers part of the request (the same domains the assistant is offered).
    from app.design_studio.knowledge.planning import reference_domains

    focus = set(reference_domains(brief.domain_id or None, matches))
    from app.design_studio.knowledge.process_library import process_library
    from app.design_studio.knowledge.quality import assess

    packs = [
        {
            "quality": assess(p),
            "usage": p.usage,
            "id": p.id,
            "title": p.title,
            "description": p.description,
            "domain_id": p.domain_id,
            "version": p.version,
            "synthetic": p.synthetic,
            "adopted": p.id in adopted,
            "role_names": [r.name for r in p.business.roles],
            "counts": {
                group: len(getattr(p.business, group))
                for group in (
                    "requirements",
                    "roles",
                    "entities",
                    "rules",
                    "exceptions",
                    "decisions",
                )
            }
            | {"workflows": len(p.workflows)},
        }
        for p in knowledge.packs()
        if p.verified and p.layer in ("business", "company") and (p.id in adopted or p.domain_id in focus)
    ]
    from app.design_studio.knowledge.system_context import discovery_context
    from app.design_studio.runtime_generation import unsupported_items

    return {
        "intake": discovery_context(knowledge, definition),
        "definition": definition.model_dump(mode="json"),
        "revision": definition.revision,
        "base_sha256": approval.digest(definition, "design"),
        "stages": stages,
        "next": stage_model.next_step(stages),
        "questions": [] if definition.studio_flow else studio_agent.open_questions(definition, 12),
        "flow": {
            "active": guided.active(definition),
            "reviewed": guided.reviewed(definition),
            "ready": guided.ready(definition, guided.active(definition))
            and stages[guided.active(definition)]["status"] != "blocked",
        }
        if definition.studio_flow
        else None,
        "analysis": {"process": process, "design": design},
        "execution_gaps": unsupported_items(definition),
        "approval": approval.status(definition),
        "domain": {
            "source": getattr(knowledge, "source", "local"),
            "matches": matches,
            "packs": packs,
            "process_library": process_library(knowledge, adopted, focus),
            "domains": [d.model_dump(mode="json") for d in knowledge.domains()],
        },
        "compile": compile_summary,
        "assistant": _describe(studio_assistant_status()),
    }


@router.get("/projects/{project_id}/studio/access")
def studio_access(
    project_id: str,
    request: Request,
    actor: CurrentUser,
    directory: Annotated[OrgDirectory, Depends(get_org_directory)],
):
    """What the signed-in person may do in this project, and why not where they may not. For the interface; the gate still checks every request."""
    from app.orgs.studio_access import access_summary

    return access_summary(directory, actor.id, getattr(request.state, "org_id", None), project_id)


@router.get("/projects/{project_id}/studio/state")
def studio_state(
    project_id: str,
    user: ProjectUser,
    projects: Projects,
    knowledge: Knowledge,
    domain: DomainPacks,
    compile: bool = False,
):
    """Everything the workspace shows, from one revision: the specification, the checks, the stage statuses and the open questions.
    `compile=true` also runs the generator (read-only) so the Generate stage reports what really happens."""
    definition = _store_call(projects.current, user.id, project_id)
    summary = None
    if compile and approval.is_valid(definition, "design"):
        summary = _compile_summary(definition, domain, knowledge)
    return state_payload(definition, knowledge, summary)


# ── the conversation turn ─────────────────────────────────────────────────


class Spoken(BaseModel):
    model_config = {"extra": "forbid"}
    role: Literal["user", "assistant"]
    text: str = Field(max_length=1000)


class TurnRequest(BaseModel):
    guided: bool = False
    stage: str | None = None
    model_config = {"extra": "forbid"}
    message: str = Field(min_length=1, max_length=4000)
    expected_revision: int = Field(ge=1)
    history: list[Spoken] = Field(default_factory=list, max_length=12)
    asked_question_id: str | None = Field(default=None, max_length=80)
    selected: str | None = Field(default=None, max_length=120)
    input_mode: Literal["text", "voice"] = "text"


class ApplyRequest(BaseModel):
    model_config = {"extra": "forbid"}
    expected_revision: int = Field(ge=1)
    base_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    actions: list[dict] = Field(min_length=1, max_length=MAX_PROPOSAL_ACTIONS)


class RevertRequest(BaseModel):
    model_config = {"extra": "forbid"}
    expected_revision: int = Field(ge=1)
    to_revision: int = Field(ge=1)


def _with_questions(
    definition: ApplicationDefinition, questions: list[dict]
) -> ApplicationDefinition:
    """Follow-up questions the agent wants on the list. Duplicates of an existing question are ignored."""
    if not questions:
        return definition
    raw = definition.model_dump(mode="json")
    topics = {
        "users": "users",
        "user": "users",
        "roles": "users",
        "role": "users",
        "actors": "users",
        "personas": "users",
        "goal": "goal",
        "problem": "problem",
        "data": "data",
        "entities": "data",
        "records": "data",
        "security": "security",
        "permissions": "security",
        "audit": "auditability",
        "auditability": "auditability",
        "accessibility": "accessibility",
        "performance": "performance",
        "integrations": "integrations",
        "integration": "integrations",
        "constraints": "constraints",
        "outcomes": "outcomes",
        "success": "outcomes",
    }
    from app.design_studio.discovery import TOPICS

    # Topics the catalogue already asks about, or whose answer the specification already holds (roles exist, so "who uses it" is answered).
    catalogue = {
        q["topic"] for q in raw["business"]["questions"] if not q["id"].startswith("q_ai_")
    } | {topic for _, topic, _, covered in TOPICS if covered(definition.business)}

    def words(text):
        return set(re.findall(r"[a-z0-9]+", text.lower())) - {
            "the",
            "a",
            "an",
            "and",
            "of",
            "to",
            "is",
            "it",
            "in",
            "for",
            "what",
            "how",
            "who",
            "which",
            "does",
            "do",
            "are",
        }  # noqa: E731

    known = [words(q["text"]) for q in raw["business"]["questions"]]
    ids = {q["id"] for q in raw["business"]["questions"]}
    for item in questions:
        text = " ".join(item["text"].lower().split())
        ident = f"q_ai_{hashlib.sha256(text.encode()).hexdigest()[:8]}"
        mine = words(item["text"])
        similar = any(
            mine and other and len(mine & other) / len(mine | other) >= 0.5 for other in known
        )  # the same question in other words is not a new question
        similar = (
            similar or topics.get(re.sub(r"[^a-z]+", "", item["topic"].lower()), "") in catalogue
        )  # nor is a question on a topic the catalogue already asks
        if (
            similar
            or ident in ids
            or sum(
                1
                for q in raw["business"]["questions"]
                if q["id"].startswith("q_ai_") and q["status"] == "open"
            )
            >= 8
        ):
            continue
        raw["business"]["questions"].append(
            {
                "id": ident,
                "topic": item["topic"] or "other",
                "text": item["text"],
                "answer": "",
                "status": "open",
            }
        )
        known.append(mine), ids.add(ident)
    return ApplicationDefinition.model_validate(raw)


def _approvals_made_stale(before: ApplicationDefinition, after: ApplicationDefinition) -> list[str]:
    stale = []
    for scope, name in (("process", "The process approval"), ("design", "The design approval")):
        if approval.is_valid(before, scope) and approval.digest(before, scope) != approval.digest(
            after, scope
        ):
            stale.append(f"{name} no longer covers this content and must be given again.")
    return stale


def _refresh(definition: ApplicationDefinition, knowledge) -> ApplicationDefinition:
    return discover(definition, knowledge)[0]


def decision_impact(definition: ApplicationDefinition, decision_ref: str) -> list[str]:
    """What answering a business decision changes, and what it does not: the answer is recorded, but a rule that waits on it still
    needs executable logic before the generated application will run the steps that depend on it."""
    business = definition.business
    decision = next(
        (d for d in business.decisions if d.id == decision_ref or d.question == decision_ref), None
    )
    if decision is None:
        return []
    rules = [r for r in business.rules if r.id in (decision.affects or [])]
    steps = [
        s
        for w in definition.workflow_definitions
        for s in w.states
        if s.id in (decision.affects or []) or set(s.rule_ids or []) & {r.id for r in rules}
    ]
    lines = [
        "Records company policy. Only a project or process owner may apply it, and the process approval is judged again."
    ]
    if steps:
        lines.append("Affects " + ", ".join(f"“{s.label}”" for s in steps[:6]) + ".")
    unbound = [r for r in rules if r.execution is None]
    if unbound:
        lines.append(
            f"{len(unbound)} rule{'s' if len(unbound) != 1 else ''} still need{'s' if len(unbound) == 1 else ''} executable logic after this answer ("
            + "; ".join(f"“{r.description[:90]}”" for r in unbound[:3])
            + "). Until then the generated application keeps refusing those steps; bind the rule in Rules & Logic."
        )
    return lines


def effect_notes(before: ApplicationDefinition, after: ApplicationDefinition) -> list[str]:
    """What a saved change does and does not mean, from the specification alone: applied is not generated, and generated is not tested."""
    if approval.digest(before, "design") == approval.digest(after, "design"):
        return []
    notes = [f"Applied to the specification (revision {after.revision})."]
    if any(screen.trace and screen.trace.generated for screen in before.screens):
        notes.append(
            "Not in the generated application yet: generate it again, then run its tests, to try this change."
        )
    old = {rule.id for rule in before.business.rules}
    for rule in after.business.rules:
        if rule.id not in old and rule.execution is None:
            notes.append(
                f"“{rule.description[:80]}” is recorded as an assumption without executable logic; the application will refuse steps that depend on it until it is bound."
            )
    old_steps = {state.id for workflow in before.workflow_definitions for state in workflow.states}
    for workflow in after.workflow_definitions:
        for state in workflow.states:
            if (
                state.id not in old_steps
                and state.kind not in ("start", "end")
                and not state.role_id
            ):
                notes.append(
                    f"“{state.label}” has no responsible role yet, so nobody can perform it in the application."
                )
    return notes


def _require_decision_authority(
    request: Request, actor, directory: OrgDirectory, actions: list
) -> None:
    if not any(a.type in DECISION_ACTIONS for a in actions) or not directory.configured:
        return
    org = getattr(request.state, "org_id", None)
    if org is None or "studio.review" not in directory.permissions(actor.id, org):
        raise _error(
            403,
            "decision_authority_required",
            "Recording a business decision needs a project or process owner. Your proposal is kept; ask one of them to apply it.",
        )


def _proposal(
    saved: ApplicationDefinition, actions: list, knowledge
) -> tuple[dict | None, list[dict]]:
    candidate, changes, rejected = apply_actions(saved, actions, knowledge)
    if not changes:
        return None, rejected
    candidate = _refresh(candidate, knowledge)
    before_findings, after_findings = (
        analyze(saved, knowledge, "process")["counts"],
        analyze(candidate, knowledge, "process")["counts"],
    )
    reasons = []
    kinds = {a.type for a in actions}
    if "adopt_pack" in kinds:
        reasons.append(
            "Adds reference knowledge: roles, rules and processes that decide how the business runs."
        )
        for action in actions:
            if action.type != "adopt_pack":
                continue
            try:
                pack = knowledge.pack(action.pack_id)
            except Exception:  # noqa: BLE001  an unknown pack is refused by the action engine; the reason is only informative
                continue
            if (
                pack.status != "approved"
                or pack.provenance.verification != "verified"
                and pack.synthetic
            ):
                reasons.append(
                    f"\u201c{pack.title}\u201d is {pack.status.replace('_', ' ')} and {'synthetic' if pack.synthetic else 'unverified'}: nobody has approved it as company policy. Review every item before relying on it."
                )
    if kinds & {"add_role", "assign_step_role", "set_step_data"}:
        reasons.append("Changes who may do what.")
    if kinds & {"add_rule", "add_exception"}:
        reasons.append(
            "Adds business rules or exceptions. Rules written in conversation stay assumptions until the owner confirms them."
        )
    if kinds & {"create_workflow", "insert_step", "add_approval"}:
        reasons.append("Changes how work moves through the process.")
    for action in actions:
        if action.type == "answer_decision":
            reasons.extend(decision_impact(saved, action.decision_id))
    return {
        "id": hashlib.sha256(approval.digest(candidate, "design").encode()).hexdigest()[:12],
        "summary": "; ".join(c["summary"] for c in changes[:3])
        + (f" and {len(changes) - 3} more" if len(changes) > 3 else ""),
        "changes": changes,
        "actions": [a.model_dump(mode="json") for a in actions],
        "base_sha256": approval.digest(saved, "design"),
        "candidate_sha256": approval.digest(candidate, "design"),
        "reasons": reasons,
        "approvals_made_stale": _approvals_made_stale(saved, candidate),
        "validation": {"before": before_findings, "after": after_findings},
        "diff": compare(saved, candidate)[:80],
    }, rejected


def _generation(
    definition: ApplicationDefinition, project_id: str, user, actor, projects, knowledge, domain
) -> tuple[ApplicationDefinition, dict]:
    """ "Generate the application now": do whatever the approvals allow, and say plainly what is missing."""
    process_ok, design_ok = (
        approval.is_valid(definition, "process"),
        approval.is_valid(definition, "design"),
    )
    if not process_ok:
        blocking = [
            f
            for f in analyze(definition, knowledge, "process")["findings"]
            if f["severity"] == "error"
        ]
        message = (
            (
                f"I can't generate yet: {len(blocking)} finding{'s' if len(blocking) != 1 else ''} still block approval. "
                if blocking
                else "The process is complete enough, but it has not been approved. "
            )
            + "A separate approver must approve the process before screens and the application can be generated."
        )
        return definition, {
            "state": "needs_process_approval",
            "message": message,
            "focus": "checks",
        }
    if definition.generated_frontend and not is_current(definition):
        # The screens derived from the process need nothing more; a custom interface must match the current design.
        return definition, {
            "state": "needs_interface",
            "message": "The custom interface no longer matches the process and data model. Regenerate it in Screens & UI, then the design can be approved again.",
            "focus": "screen",
        }
    if not design_ok:
        return definition, {
            "state": "needs_design_approval",
            "message": "The interface exists but the design has not been approved. A separate approver must approve it before the application can be generated.",
            "focus": "checks",
        }
    return definition, {
        "state": "ready",
        "message": "The design is approved. I'm generating the application and checking it.",
        "focus": "export",
        "client_action": "compile",
    }


def _execute(
    plan: studio_agent.Plan,
    view: ApplicationDefinition,
    current: ApplicationDefinition,
    project_id: str,
    input_mode: str,
    user,
    actor,
    projects,
    knowledge,
    domain,
    request_text: str = "",
) -> dict:
    """Apply a plan: additive changes are saved as a revision, review-class changes come back as a proposal, and the reply is assembled from what really happened."""
    if plan.mode != "direct":
        # New business policy must be grounded in what the person actually supplied.
        # Verified policies enter via adopt_pack, never via a model's invented citation.
        def words(text):
            return " ".join(re.findall(r"[a-z0-9]+", text.lower()))

        evidence = [words(request_text), words(current.business.brief.goal)]
        retained = []
        for action in plan.actions:
            if action.type == "add_rule":
                quote = words(action.evidence_quote or action.description)
                if len(quote) < 8 or not any(quote in source for source in evidence if source):
                    plan.rejected.append({"type": "add_rule", "reason": "This proposed policy was not stated in your requirements. Record it as a business decision, or provide the policy before adding a rule."})
                    continue
            retained.append(action)
        plan.actions = retained
    if plan.mode != "direct" and any(a.type == "confirm_rule" for a in plan.actions):
        # A confirmation records that a person checked a rule against real evidence. A model turn cannot give it on their behalf,
        # whatever source it names; the person confirms the rule themselves in Rules & Logic.
        plan.actions = [a for a in plan.actions if a.type != "confirm_rule"]
        plan.rejected = [
            *plan.rejected,
            {"type": "confirm_rule", "reason": "Only a person can confirm a rule. Open it in Rules & Logic and confirm it with its evidence."},
        ]
    is_guided = view.studio_flow is not None
    if is_guided:
        key = guided.active(view)
        allowed = set(guided.ALLOWED[key])
        if plan.mode == "direct":
            # Explicit controls can revise a reviewed stage; the digest reopens it after saving.
            # Future, unreviewed stages remain locked.
            for reviewed_stage in guided.reviewed(view):
                allowed |= guided.ALLOWED[reviewed_stage]
            refused = [action for action in plan.actions if action.type not in allowed]
            if refused:
                raise _error(
                    409,
                    "stage_action_unavailable",
                    "Review the relevant stage before making this change.",
                    {"actions": [action.type for action in refused]},
                )
        if key == "knowledge" and plan.knowledge and plan.knowledge.get("generated_blueprint"):
            allowed |= {  # requirements belong to the reviewed brief, not to the foundation
                "adopt_pack",
                "add_role",
                "add_entity",
                "create_workflow",
                "add_rule",
                "add_exception",
                "update_exception",
                "link_requirement",
                "insert_step",
            }
        plan.actions = [a for a in plan.actions if a.type in allowed]
        plan.focus = key
        plan.focus_item = None
        plan.questions = []
        plan.asking = None
        if key != "export":
            plan.command = None
    validation_repair = is_guided and guided.active(view) == "checks"
    # Validation revisits already reviewed content. Every repair is a proposal;
    # merely asking for fixes must not rewrite the design and invalidate approvals.
    immediate = (
        []
        if validation_repair
        else [a for a in plan.actions if is_guided or a.type not in REVIEW_ACTIONS]
    )
    review = (
        list(plan.actions)
        if validation_repair
        else ([] if is_guided else [a for a in plan.actions if a.type in REVIEW_ACTIONS])
    )
    # Executable policy bindings always remain reviewable, including guided draft stages.
    if is_guided and not validation_repair:
        review.extend(a for a in immediate if a.type in DECISION_ACTIONS)
        immediate = [a for a in immediate if a.type not in DECISION_ACTIONS]
    saved, rejected = current, list(plan.rejected)
    candidate, applied, more_rejected = apply_actions(view, immediate, knowledge)
    if candidate.business.brief.intake is None:
        from app.design_studio.knowledge.system_context import region_in_text, catalog_for
        from app.assistant.studio_actions import SetIntakeContext

        region = region_in_text(candidate.business.brief.goal)
        if region and catalog_for(knowledge):
            candidate, context_changes, _ = apply_actions(
                candidate, [SetIntakeContext(type="set_intake_context", region=region)], knowledge
            )
            applied += context_changes
    rejected += more_rejected
    candidate = _with_questions(candidate, plan.questions)
    if applied or plan.questions:
        candidate = _refresh(candidate, knowledge)
    if (
        is_guided
        and candidate != current
        and immediate
        and getattr(knowledge, "source", "local") == "neo4j"
    ):
        rejected_kinds = {r.get("type") for r in rejected}
        proposed = [
            a.model_dump(mode="json")
            for a in immediate
            if a.type not in rejected_kinds and a.type != "adopt_pack"
        ]
        recorder = getattr(knowledge, "record_proposal", None)
        if recorder and proposed:
            recorder(
                project_id,
                guided.active(candidate),
                proposed,
                [
                    {"pack_id": link.pack_id, "version": link.pack_version}
                    for link in candidate.business.knowledge
                ],
                actor.id,
            )
    if (
        approval.digest(candidate, "design") != approval.digest(current, "design")
        or candidate.studio_flow != current.studio_flow
    ):
        saved = _store_call(
            projects.update,
            user.id,
            project_id,
            current.revision,
            candidate,
            "assistant:apply",
            actor.id,
        )
    stale = _approvals_made_stale(current, saved) if saved is not current else []
    notes = effect_notes(current, saved) if saved is not current else []

    proposal, more_rejected = _proposal(saved, review, knowledge) if review else (None, [])
    rejected += more_rejected

    generation = None
    focus, client_action = plan.focus, None
    if plan.command == "design_frontend" and not plan.actions and proposal is None:
        available = not saved.studio_flow or guided.active(saved) == "screen" or "screen" in guided.reviewed(saved)
        if available:
            focus, client_action = "screen", "frontend"
            generation = {"state": "design_requested", "message": "I'll rebuild the application's interface from your instruction and check it before saving. The current saved version stays available until the replacement passes.", "focus": "screen", "client_action": "frontend"}
    if plan.command == "generate":
        after, generation = _generation(saved, project_id, user, actor, projects, knowledge, domain)
        if after is not saved:
            applied.append(
                {
                    "area": "screens",
                    "kind": "added",
                    "item_id": "screens",
                    "summary": "Screens generated from the approved process",
                }
            )
        saved, focus, client_action = (
            after,
            generation.get("focus", focus),
            generation.get("client_action"),
        )

    # What the person hears. The model's wording is kept, but what changed and what failed comes from the real result, never from the model.
    nothing_done = bool(plan.actions) and not applied and proposal is None
    parts = [] if nothing_done else [plan.reply]
    if generation:
        if generation["state"] not in ("ready", "screens_generated"):
            parts = []  # the model said it would generate; the real answer is that it cannot yet, so only the real answer is given
        parts.append(generation["message"])
    if rejected:
        reasons = " ".join(r["reason"] for r in rejected[:2])
        parts.append(
            reasons
            if nothing_done
            else "However, I could not do "
            + ("one thing" if len(rejected) == 1 else f"{len(rejected)} things")
            + ": "
            + reasons
        )
    if proposal:
        parts.append(
            "I've prepared a change for you to review. Say “apply” to accept it, or press Apply."
        )
    questions = studio_agent.open_questions(saved, 6)
    asking = plan.asking if plan.asking and any(q["id"] == plan.asking for q in questions) else None
    if asking is None and plan.questions:
        text = " ".join(plan.questions[0]["text"].lower().split())
        asking = next(
            (
                q["id"]
                for q in studio_agent.open_questions(saved, 40)
                if " ".join(q["text"].lower().split()) == text
            ),
            None,
        )
    if (
        asking is None and plan.questions
    ):  # the model's question was the catalogue's on another wording: ask the catalogue's
        wanted = re.sub(r"[^a-z]+", "", plan.questions[0]["topic"].lower())
        asking = next(
            (q["id"] for q in questions if re.sub(r"[^a-z]+", "", q["topic"].lower()) == wanted),
            None,
        )
    if (
        asking is None
        and plan.mode == "local_rules"
        and not generation
        and not plan.command
        and (applied or plan.actions)
        and questions
    ):
        asking = questions[0]["id"]
        parts.append(questions[0]["text"])
    if is_guided:
        asking = None
        key = guided.active(saved)
        label = dict(stage_model.STAGES)[key]
        if key != "export" and guided.ready(saved, key):
            parts = [
                f"Your {label.lower()} draft is ready to review. Ask for any changes, or select Continue when you are happy with it."
            ] + (
                [
                    "Some requested changes could not be applied: "
                    + " ".join(r["reason"] for r in rejected[:2])
                ]
                if rejected
                else []
            )
        elif key == "checks":
            if proposal:
                parts = [
                    "I prepared a batch of validation repairs. Review the proposed changes and the before/after findings, then select Apply. Assumptions and formal approvals still require review."
                ]
            elif rejected and not applied:
                parts = [
                    "The repair could not be completed: "
                    + " ".join(r["reason"] for r in rejected[:3])
                ]
            elif not applied and not plan.actions:
                parts = [
                    "No design changes were saved. "
                    + (plan.degraded or plan.reply)
                    + " The validation findings remain open."
                ]
            else:
                remaining = analyze(saved, knowledge, "process")["counts"]["error"]
                parts = [
                    f"Saved {len(applied)} design repair changes and rechecked validation. {remaining} process blockers remain. Business assumptions and formal approvals have not been confirmed automatically."
                ]
                if rejected:
                    parts.append(
                        "Unresolved repairs: " + " ".join(r["reason"] for r in rejected[:3])
                    )
        elif key == "knowledge" and plan.degraded:
            parts = [
                "No matching reference domain was found, and the language model could not prepare a complete proposed foundation. Try preparing this stage again; you do not need to supply the domain knowledge."
            ]
        elif key != "export":
            parts = [
                f"The {label.lower()} draft is not complete yet. "
                + (" ".join(r["reason"] for r in rejected[:2]) if rejected else plan.reply)
            ]
        if validation_repair and applied and key != "checks":
            parts.insert(
                0,
                f"Saved {len(applied)} design repair changes. The {label.lower()} content changed after review, so review it again before continuing.",
            )
    reply = " ".join(part.strip() for part in parts if part and part.strip()) or "Done."
    return {
        "turn": {
            "mode": plan.mode,
            "degraded": plan.degraded,
            "reply": reply,
            "applied": applied,
            "previous_revision": current.revision,
            "revision": saved.revision,
            "approvals_made_stale": stale,
            "proposal": proposal,
            "rejected": rejected,
            "asked_question_id": asking,
            "focus": focus,
            "focus_item": plan.focus_item,
            "generation": generation,
            "client_action": client_action,
            "input_mode": input_mode,
            "notes": notes,
            "knowledge": plan.knowledge,
        },
        "state": state_payload(saved, knowledge),
    }


@router.post("/projects/{project_id}/studio/turn")
def studio_turn(
    project_id: str,
    body: TurnRequest,
    user: ProjectUser,
    actor: CurrentUser,
    projects: Projects,
    knowledge: Knowledge,
    domain: DomainPacks,
):
    current = _current_at(projects, user.id, project_id, body.expected_revision)
    # The planner sees the question list as it will be saved (a new project has none yet), so it never asks what the catalogue already asks.
    view = _refresh(current, knowledge)
    if body.guided and view.studio_flow is None:
        view = view.model_copy(update={"studio_flow": StudioFlow()})
    if view.studio_flow and body.stage and body.stage != guided.active(view):
        if body.stage not in view.studio_flow.reviewed:
            raise _error(
                409, "stage_locked", "Review the current stage before starting the next one."
            )
        index = view.studio_flow.reviewed.index(body.stage)
        view = view.model_copy(
            update={
                "studio_flow": StudioFlow(
                    reviewed=view.studio_flow.reviewed[:index],
                    reviewed_digests={
                        k: v
                        for k, v in view.studio_flow.reviewed_digests.items()
                        if k in view.studio_flow.reviewed[:index]
                    },
                )
            }
        )
    analysis = analyze(view, knowledge, "design")
    stages = stage_model.compute(
        view, analysis, identify_domains(view.business.brief.goal, knowledge)
    )
    from app.design_studio.knowledge.system_context import discovery_context

    setup = discovery_context(knowledge, view)
    if (
        setup
        and setup["questions"]
        and re.fullmatch(
            r"\s*(skip|skip all|skip both|use defaults|skip questions)[.!]?\s*", body.message, re.I
        )
    ):
        from app.assistant.studio_actions import SetIntakeContext

        plan = studio_agent.Plan(
            actions=[
                SetIntakeContext(
                    type="set_intake_context", skip=[q["id"] for q in setup["questions"]]
                )
            ],
            reply="I will continue with the shared process draft. Skipped preferences remain unspecified.",
        )
    else:
        plan = studio_agent.run(
            get_studio_llm(),
            body.message,
            [h.model_dump() for h in body.history],
            body.asked_question_id,
            view,
            stage_model.relevant_findings(view, analysis),
            stages,
            knowledge,
            body.selected,
        )
    if not view.studio_flow:
        plan = studio_agent.ground_first_request(plan, view, body.message)
    elif guided.active(view) == "brief" and not current.business.brief.goal:
        from app.assistant.studio_actions import SetBrief, AddRequirement

        if not any(a.type == "set_brief" for a in plan.actions):
            plan.actions.insert(0, SetBrief(type="set_brief", goal=body.message))
        if not any(a.type == "add_requirement" for a in plan.actions):
            plan.actions.append(
                AddRequirement(
                    type="add_requirement",
                    statement=body.message[:1000],
                    acceptance_criteria=[
                        "The application supports the capabilities described in the request."
                    ],
                )
            )
    return _execute(
        plan, view, current, project_id, body.input_mode, user, actor, projects, knowledge, domain,
        request_text=body.message,
    )


class StartGuidedRequest(BaseModel):
    expected_revision: int = Field(ge=1)


@router.post("/projects/{project_id}/studio/start-guided")
def start_guided(
    project_id: str,
    body: StartGuidedRequest,
    user: ProjectUser,
    actor: CurrentUser,
    projects: Projects,
    knowledge: Knowledge,
):
    current = _current_at(projects, user.id, project_id, body.expected_revision)
    if current.studio_flow is None:
        candidate = current.model_copy(update={"studio_flow": StudioFlow()})
        current = _store_call(
            projects.update, user.id, project_id, current.revision, candidate, "update", actor.id
        )
    return state_payload(current, knowledge)


class ContinueRequest(BaseModel):
    expected_revision: int = Field(ge=1)
    stage: str


@router.post("/projects/{project_id}/studio/continue")
def continue_stage(
    project_id: str,
    body: ContinueRequest,
    user: ProjectUser,
    actor: CurrentUser,
    projects: Projects,
    knowledge: Knowledge,
    domain: DomainPacks,
):
    current = _current_at(projects, user.id, project_id, body.expected_revision)
    if (
        current.studio_flow is None
        or body.stage != guided.active(current)
        or body.stage == "export"
    ):
        raise _error(
            409, "stage_changed", "The current stage changed. Reload it before continuing."
        )
    if not guided.ready(current, body.stage):
        raise _error(409, "stage_incomplete", "Complete this stage's draft before continuing.")
    state = state_payload(current, knowledge)["stages"][body.stage]
    if state["status"] == "blocked":
        raise _error(409, "stage_blocked", state["reason"])
    prior_reviews = guided.reviewed(current)
    reviewed_content = current
    if body.stage == "brief":
        from app.design_studio.knowledge.system_context import discovery_context
        from app.assistant.studio_actions import SetIntakeContext

        setup = discovery_context(knowledge, current)
        if setup and setup["questions"]:
            reviewed_content, _, _ = apply_actions(
                current,
                [
                    SetIntakeContext(
                        type="set_intake_context", skip=[q["id"] for q in setup["questions"]]
                    )
                ],
                knowledge,
            )
    flow = StudioFlow(
        reviewed=[*prior_reviews, body.stage],
        reviewed_digests={
            **{k: v for k, v in current.studio_flow.reviewed_digests.items() if k in prior_reviews},
            body.stage: guided.stage_digest(reviewed_content, body.stage),
        },
    )
    view = reviewed_content.model_copy(update={"studio_flow": flow})
    key = guided.active(view)
    label = dict(stage_model.STAGES)[key]
    analysis = analyze(view, knowledge, "design")
    plan = studio_agent.run(
        get_studio_llm(),
        f"I reviewed the previous stage. Prepare the complete {label} draft now using my requirements and our domain knowledge. Use proposed defaults and ask only if something essential prevents a draft. Stop for my review after this stage.",
        [],
        None,
        view,
        [],
        stage_model.compute(view, analysis, identify_domains(view.business.brief.goal, knowledge)),
        knowledge,
        None,
    )
    if key == "export":
        plan.command = "generate"
    result = _execute(
        plan, view, current, project_id, "text", user, actor, projects, knowledge, domain
    )
    return _repair_own_draft(result, key, project_id, user, actor, projects, knowledge, domain)


REPAIR_REQUEST = (
    "Repair all of these validation gaps in this stage together now. Update existing records, do not add duplicate exceptions or rules. "
    "Link every functional requirement to a step that serves it (a dashboard, directory or tracking view is a step of kind search or review "
    "owned by the role that uses it) and give every exception a handler step and a resolution. Preserve business assumptions:\n"
)


MAX_REPAIR_ROUNDS = 3  # model repair passes before the last-resort completion; each is one model call


def _open_defects(saved, key, knowledge):
    """The errors of this stage that are the draft's own to fix (not business decisions, which are the person's)."""
    # The foundation draft (Domain Knowledge) builds the process, records, rules and roles in one go, so it answers for all of them.
    owned = {"knowledge", "workflow", "data", "rules", "roles"} if key == "knowledge" else {key}
    analysis = analyze(saved, knowledge, "design")
    defects = [
        item
        for item in stage_model.relevant_findings(saved, analysis)
        if item["severity"] == "error" and stage_model.FINDING_STAGE.get(item["tab"]) in owned
    ]
    return defects, analysis


def _settle_first(saved, project_id, user, actor, projects, knowledge):
    """Record the findings that follow from the design itself (merged duplicate roles, repeated steps, unowned records) as one
    revision, with no model call, so the slower model repair is only asked about what is genuinely open."""
    from app.design_studio.auto_resolve import resolve

    if saved.studio_flow is None or guided.active(saved) == "brief":
        return saved  # the first stage is where the person answers the optional questions
    resolved, changes = resolve(saved)
    if not changes:
        return saved
    return _store_call(
        projects.update, user.id, project_id, saved.revision, _refresh(resolved, knowledge), "studio:resolve", actor.id
    )


def _repair_own_draft(result, key, project_id, user, actor, projects, knowledge, domain):
    """Repair the stage's own defects, preserving honest blockers if bounded
    repair cannot implement them. Business choices still belong to the owner.
    """
    if key in ("export", "checks"):
        return result
    saved = _settle_first(_store_call(projects.current, user.id, project_id), project_id, user, actor, projects, knowledge)
    for _ in range(MAX_REPAIR_ROUNDS):
        defects, analysis = _open_defects(saved, key, knowledge)
        refused = result["turn"].get("rejected") or []
        if not defects and not refused:
            return result
        notes = "\n".join(f"{item['code']}: {item['message']} {item['remediation']}" for item in defects)
        if refused:
            notes += "\nYour previous attempt was partly refused, so send these again, corrected:\n" + "\n".join(
                f"- {item.get('type')}: {item.get('reason')}" for item in refused[:8]
            )
        plan = studio_agent.run(
            get_studio_llm(),
            REPAIR_REQUEST + notes,
            [],
            None,
            saved,
            defects,
            stage_model.compute(saved, analysis, identify_domains(saved.business.brief.goal, knowledge)),
            knowledge,
            None,
        )
        result = _execute(plan, saved, saved, project_id, "text", user, actor, projects, knowledge, domain)
        saved = _settle_first(_store_call(projects.current, user.id, project_id), project_id, user, actor, projects, knowledge)
    defects, _ = _open_defects(saved, key, knowledge)
    _, notes = settle(saved, defects)
    if not notes:
        return result
    turn = {**result["turn"], "revision": saved.revision}
    turn["reply"] = f"The draft is saved. {len(defects)} validation gap(s) still need to be resolved before this stage can continue. They are listed in validation."
    turn["notes"] = [*(turn.get("notes") or []), *notes]
    return {**result, "turn": turn, "state": state_payload(saved, knowledge)}


class ActRequest(BaseModel):
    model_config = {"extra": "forbid"}
    expected_revision: int = Field(ge=1)
    actions: list[dict] = Field(min_length=1, max_length=MAX_PROPOSAL_ACTIONS)
    reply: str = Field(default="", max_length=300)


@router.post("/projects/{project_id}/studio/act")
def studio_act(
    project_id: str,
    body: ActRequest,
    user: ProjectUser,
    actor: CurrentUser,
    projects: Projects,
    knowledge: Knowledge,
    domain: DomainPacks,
):
    """The same typed actions without a language model: for buttons on the views (answer a question, adopt reference knowledge, make a field mandatory).
    The same split applies: additive changes are saved, review-class changes come back as a proposal."""
    current = _current_at(projects, user.id, project_id, body.expected_revision)
    actions, invalid = parse_actions(body.actions)
    if not actions:
        raise _error(
            422,
            "actions_invalid",
            "That is not a change Design Studio can make.",
            {"rejected": invalid},
        )
    plan = studio_agent.Plan(reply=body.reply, actions=actions, rejected=invalid, mode="direct")
    return _execute(
        plan,
        _refresh(current, knowledge),
        current,
        project_id,
        "text",
        user,
        actor,
        projects,
        knowledge,
        domain,
    )


@router.post("/projects/{project_id}/studio/apply")
def studio_apply(
    project_id: str,
    body: ApplyRequest,
    request: Request,
    user: ProjectUser,
    actor: CurrentUser,
    projects: Projects,
    knowledge: Knowledge,
    directory: Annotated[OrgDirectory, Depends(get_org_directory)],
):
    """Save a reviewed proposal. The actions are re-validated and re-applied to the saved content; the client cannot supply a patch."""
    current = _current_at(projects, user.id, project_id, body.expected_revision)
    if approval.digest(current, "design") != body.base_sha256:
        raise _error(
            409,
            "proposal_stale",
            "The project changed after this proposal was made. Ask again for a fresh proposal.",
        )
    actions, invalid = parse_actions(body.actions)
    if invalid or not actions:
        raise _error(
            422,
            "proposal_invalid",
            "This proposal is not a valid set of changes. Nothing was changed.",
        )
    _require_decision_authority(request, actor, directory, actions)
    candidate, changes, rejected = apply_actions(current, actions, knowledge)
    if rejected or not changes:
        raise _error(
            409,
            "proposal_mismatch",
            "The proposal no longer applies to the saved content. Nothing was changed.",
            {"rejected": rejected},
        )
    candidate = _refresh(candidate, knowledge)
    if approval.digest(candidate, "design") != body.candidate_sha256:
        raise _error(
            409,
            "proposal_mismatch",
            "The proposal does not produce what was reviewed. Nothing was changed.",
        )
    saved = _store_call(
        projects.update,
        user.id,
        project_id,
        current.revision,
        candidate,
        "assistant:apply",
        actor.id,
    )
    return {
        "changes": changes,
        "previous_revision": current.revision,
        "approvals_made_stale": _approvals_made_stale(current, saved),
        "notes": effect_notes(current, saved),
        "state": state_payload(saved, knowledge),
    }


@router.post("/projects/{project_id}/studio/revert")
def studio_revert(
    project_id: str,
    body: RevertRequest,
    user: ProjectUser,
    actor: CurrentUser,
    projects: Projects,
    knowledge: Knowledge,
):
    """Undo by restoring an earlier revision's content as a NEW revision. History is never rewritten; approvals are kept and judged by their digests."""
    current = _current_at(projects, user.id, project_id, body.expected_revision)
    history = _store_call(projects.history, user.id, project_id)
    target = next((item for item in history if item.revision == body.to_revision), None)
    if target is None or body.to_revision >= current.revision:
        raise _error(404, "revision_not_found", "That revision cannot be restored.")
    restored = target.model_copy(update={"approvals": current.approvals})
    saved = _store_call(
        projects.update,
        user.id,
        project_id,
        current.revision,
        restored,
        "assistant:revert",
        actor.id,
    )
    return {"state": state_payload(saved, knowledge), "restored_from": body.to_revision}


class ResolveRequest(BaseModel):
    model_config = {"extra": "forbid"}
    expected_revision: int = Field(ge=1)


@router.post("/projects/{project_id}/studio/resolve")
def studio_resolve(
    project_id: str,
    body: ResolveRequest,
    user: ProjectUser,
    actor: CurrentUser,
    projects: Projects,
    knowledge: Knowledge,
):
    """Settle every validation finding whose fix follows from the design itself, as one new revision. No language model, no policy."""
    from app.design_studio.auto_resolve import resolve

    current = _current_at(projects, user.id, project_id, body.expected_revision)
    resolved, changes = resolve(current)
    saved = current
    if changes:
        saved = _store_call(
            projects.update,
            user.id,
            project_id,
            current.revision,
            _refresh(resolved, knowledge),
            "studio:resolve",
            actor.id,
        )
    return {
        "state": state_payload(saved, knowledge),
        "changes": changes,
        "stale": _approvals_made_stale(current, saved),
    }


# ── run what was generated (local only) ─────────────────────────────────


def _generated_files(
    project_id: str, user, projects, knowledge, domain
) -> tuple[ApplicationDefinition, dict[str, bytes]]:
    from app.design_studio.compiler import compile_project

    definition = _store_call(projects.current, user.id, project_id)
    result = compile_project(definition, domain, knowledge)
    if result["status"] != "generated":
        raise _error(
            409,
            "generation_blocked",
            "Generation is blocked for the current revision.",
            {"reasons": result["plan"]["reasons"]},
        )
    return definition, result["files"]


@router.get("/projects/{project_id}/runtime")
def runtime_status(project_id: str, user: ProjectUser, projects: Projects):
    from app.design_studio.runtime_launcher import manager

    return manager.status(project_id, _store_call(projects.current, user.id, project_id).revision)


@router.post("/projects/{project_id}/runtime/test")
async def runtime_test(
    project_id: str,
    user: ProjectUser,
    projects: Projects,
    knowledge: Knowledge,
    domain: DomainPacks,
    actor: CurrentUser,
    releases: Annotated[ReleaseStore, Depends(get_release_store)],
):
    """Run the generated application's own independent tests (a separate process; nothing of Design Studio is imported)."""
    from app.design_studio.runtime_launcher import LaunchError, manager

    definition, files = await run_in_threadpool(
        _generated_files, project_id, user, projects, knowledge, domain
    )
    release = await run_in_threadpool(
        retain_package, releases, user.id, project_id, definition.revision, actor.id, files
    )
    run = await run_in_threadpool(releases.start_test, user.id, project_id, release["id"], actor.id)
    try:
        result = {
            "revision": definition.revision,
            "release_id": release["id"],
            "run_id": run,
            **await run_in_threadpool(manager.test, project_id, definition.revision, files),
        }
        await run_in_threadpool(releases.finish_test, user.id, project_id, run, result)
        return result
    except LaunchError as exc:
        await run_in_threadpool(
            releases.finish_test,
            user.id,
            project_id,
            run,
            {"passed": False, "revision": definition.revision, "error": str(exc)},
        )
        raise _error(502, "runtime_test_failed", str(exc)) from None
    except Exception:
        await run_in_threadpool(
            releases.finish_test,
            user.id,
            project_id,
            run,
            {
                "passed": False,
                "revision": definition.revision,
                "error": "Test worker failed unexpectedly.",
            },
        )
        raise


@router.post("/projects/{project_id}/runtime/launch")
async def runtime_launch(
    project_id: str,
    user: ProjectUser,
    projects: Projects,
    knowledge: Knowledge,
    domain: DomainPacks,
):
    """Start the generated application on this computer (127.0.0.1 only, its own database). A local preview of the real application, not hosting."""
    from app.design_studio.runtime_launcher import LaunchError, manager

    definition, files = await run_in_threadpool(
        _generated_files, project_id, user, projects, knowledge, domain
    )
    try:
        return await run_in_threadpool(manager.launch, project_id, definition.revision, files)
    except LaunchError as exc:
        raise _error(502, "runtime_launch_failed", str(exc)) from None


@router.post("/projects/{project_id}/runtime/stop")
def runtime_stop(project_id: str, user: ProjectUser, projects: Projects):
    from app.design_studio.runtime_launcher import manager

    _store_call(projects.current, user.id, project_id)
    return {"stopped": manager.stop(project_id)}
