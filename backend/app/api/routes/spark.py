"""One read-only Spark entry point; purchasing still requires explicit cart/checkout actions."""

import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.app_access import require_any_app, check_app_operation
from app.api.dependencies import (
    CommerceAgentDep, Graph, OrdersSvc, current_user, get_agent, get_question_service, require,
)
from app.api.routes.commerce import AgentBody, agent as account_answer
from app.core.config import get_settings
from app.core.exceptions import GraphUnavailableError
from app.core.session import COOKIE, verify
from app.llm import LLMClient, LLMError
from app.llm import create_reasoning_llm
from app.schemas.intelligence import QueryRequest
from app.schemas.spark import SparkPlan, SparkRequest, SparkResponse, SparkStep
from app.services.spark import (
    elapsed, interpret, order_carry, read_memory, resolve_order_part, save_memory, previous_answer, remember_answer,
)
from app.api.routes.spark_voice import limit_spark
from app.services.spark_presentation import present
from app.api.routes.profile import get_profile_store

def get_spark_llm():
    return create_reasoning_llm(get_settings())


router = APIRouter(prefix="/spark", tags=["spark"], dependencies=[
    Depends(require_any_app("parts_intelligence", "agentic_shopping")), Depends(limit_spark),
])


def spark_questions(graph: Graph, llm: Annotated[LLMClient | None, Depends(get_spark_llm)]):
    return get_question_service(graph, llm)


def spark_shopping(graph: Graph, llm: Annotated[LLMClient | None, Depends(get_spark_llm)]):
    return get_agent(graph, llm)


def used_profile(plan: SparkPlan, message: str, profile: dict | None) -> list[str]:
    """Name a saved machine only when the shopping request now carries it and the user did not type it."""
    if not profile or not plan.shopping:
        return []
    norm = lambda s: " ".join(s.casefold().replace("-", " ").split())  # noqa: E731
    return [f"machine {m}" for m in [profile.get("preferred_machine"), *(profile.get("machines") or [])]
            if m and norm(m) in norm(plan.shopping) and norm(m) not in norm(message)][:1]


@router.post("/conversation", response_model=SparkResponse)
def conversation(body: SparkRequest, request: Request,
                 questions: Annotated[object, Depends(spark_questions)],
                 shopping: Annotated[object, Depends(spark_shopping)],
                 commerce: CommerceAgentDep, orders: OrdersSvc,
                 llm: Annotated[LLMClient | None, Depends(get_spark_llm)]) -> SparkResponse:
    secret = get_settings().session_secret
    owner = verify(request.cookies.get(COOKIE), secret) or "anonymous"
    memory = read_memory(body.context, secret, owner)
    answer_owner = f"{owner}:{getattr(request.state, 'org_id', '')}"
    started = time.perf_counter()
    profile = None
    # A selected entity/pagination continues only the server-signed last investigation.
    if body.selected or body.limit != 12:
        pending = memory.get("investigation")
        if not pending:
            raise HTTPException(409, detail={"code": "spark_no_investigation", "message": "Ask a question before choosing a record or showing more."})
        plan = SparkPlan(intelligence=pending, shopping=None, account=None, clarification=None)
    else:
        saved = get_profile_store().get(owner) if owner != "anonymous" else None
        profile = saved["profile"] if saved else None
        if profile and profile.get("ship_to_id"):
            try:  # the saved site, re-read from the graph: only its city helps routing
                site = orders._repo.shipto(profile["ship_to_id"])
            except GraphUnavailableError:
                site = None
            profile = {**profile, "delivery_city": site["city"] if site else None}
        mine = None
        if owner != "anonymous":
            try:  # the caller's own orders, newest first; any failure simply leaves them out
                me = orders.user(owner)
                mine = [{"order_id": o["order_id"], "date": o.get("order_date"), "status": o.get("status")} for o in orders.list(me)] if me else None
            except Exception:
                mine = None
        plan = interpret(llm, body.message, memory, profile, mine, (body.order_part or {}).get("label"))
        if plan.view == "graph" and plan.reuse_previous and memory.get("investigation") and not plan.clarification:
            # Presentation changes must not let a paraphrase change the investigation.
            plan = plan.model_copy(update={"intelligence": memory["investigation"]})
    result = SparkResponse(message=plan.clarification or "", context="", view=plan.view, profile_used=used_profile(plan, body.message, profile), steps=[
        SparkStep(label="Understood your request", status="completed", ms=elapsed(started)),
    ])
    tools = [("intelligence", "Checked parts and source evidence"),
             ("shopping", "Compared compatible buying options"),
             ("account", "Checked your account records")]
    if plan.order and not plan.clarification:
        # only a part Spark offered in this conversation, or the one being ordered, can be ordered; the model only names it
        current = body.order_part or {}
        ordering = [{"kind": "PART", "part_id": current["part_id"], "label": current.get("label", "")}] if current.get("part_id") else []
        offered_parts = memory.get("offered", [])
        part = resolve_order_part(plan.order, ordering) or resolve_order_part(plan.order, offered_parts)
        if part:
            # the constraints the user gave the shopping step travel with a part that step offered
            carry = order_carry(memory.get("shopping")) if part in offered_parts else {}
            result.order_part = {"part_id": part["part_id"], "label": part["label"], "patch": carry}
            result.message = f"Let's order {part['label']}. I'll ask only for what I still need."
        else:
            labels = list(dict.fromkeys(o["label"] for o in offered_parts if o.get("kind") == "PART" and o.get("part_id")))[:3]
            result.message = (f"Which part would you like to order: {' or '.join(labels)}?" if labels else
                              "Which part would you like to order? Ask me to find it first, or open it and choose Order this part.")
        plan = plan.model_copy(update={"intelligence": None, "shopping": None, "account": None})
    for tool, label in tools:
        text = getattr(plan, tool)
        if not text or plan.clarification:
            continue
        step = time.perf_counter()
        try:
            if tool in {"intelligence", "shopping"}:
                app_id = "parts_intelligence" if tool == "intelligence" else "agentic_shopping"
                try:
                    check_app_operation(request, app_id)
                except HTTPException as exc:
                    feature = "Parts Intelligence" if tool == "intelligence" else "Shopping"
                    result.warnings.append(f"{feature}: {exc.detail["message"]}")
                    result.steps.append(SparkStep(label=f"{feature} access required", status="access_denied", ms=elapsed(step)))
                    continue
            if tool == "intelligence":
                cached = None
                if plan.view == "graph" and not body.selected and body.limit == 12 and text.strip().casefold() == str(memory.get("investigation", "")).strip().casefold():
                    cached = previous_answer(memory.get("answer_id"), answer_owner)
                result.intelligence = cached or questions.query(QueryRequest(question=text, selected=body.selected, limit=body.limit))
                if cached:
                    label = "Opened the graph of your previous answer"
            elif tool == "shopping":
                result.shopping = shopping.recommend(text)
            else:
                try:
                    user = current_user(orders, request, nv_session=request.cookies.get(COOKIE))
                except HTTPException as exc:
                    if exc.status_code != 401:
                        raise
                    result.sign_in_required = True
                    result.steps.append(SparkStep(label=label, status="sign_in_required", ms=elapsed(step)))
                    continue
                require("commerce.context")(user)
                result.account = account_answer(AgentBody(message=text, state=memory.get("account_state", {})), user, commerce)
            result.steps.append(SparkStep(label=label, status="completed", ms=elapsed(step)))
        except (LLMError, GraphUnavailableError):
            result.warnings.append(f"{label}: the required service is temporarily unavailable. Please retry.")
            result.steps.append(SparkStep(label=label, status="failed", ms=elapsed(step)))
    offered = []
    if result.intelligence:
        offered.extend({"kind": e.kind, "label": e.label} for e in result.intelligence.entities)
        offered.extend({"kind": r.kind, "label": r.part_number or r.title} for r in result.intelligence.results)
    if result.shopping:
        offered.extend({"kind": "PART", "label": c.part.part_number, "name": c.part.name, "part_id": c.part.part_id,
                        "recommended": c.recommended} for c in result.shopping.candidates)
    if plan.view == "graph" and result.intelligence and not result.intelligence.evidence:
        result.warnings.append("There are no recorded connections to draw for this answer.")
    if not any((plan.intelligence, plan.shopping, plan.account, plan.clarification, result.order_part, plan.order)):
        result.message = "What would you like to know about your parts, machines or orders?"
    pending = plan.clarification
    if result.intelligence and result.intelligence.clarification:
        pending = plan.intelligence
    if result.shopping and result.shopping.state != "recommendation":
        pending = plan.shopping
    if result.account and result.account.get("clarification"):
        pending = plan.account
        offered.extend({"kind": "account_option", "label": str(option)[:200]}
                       for option in result.account["clarification"].get("options", [])[:8])
    history = [*memory.get("history", []), {"message": body.message, "request": plan.model_dump(),
               "question": result.intelligence.clarification.question if result.intelligence and result.intelligence.clarification else result.shopping.question if result.shopping else result.account.get("clarification", {}).get("question") if result.account and result.account.get("clarification") else None}][-4:]
    # Failed requests do not replace the last successful context; retry is safe and read-only.
    succeeded = result.intelligence is not None or result.shopping is not None or result.account is not None
    updated = {"history": history, "offered": (offered or memory.get("offered", []))[:12],
               "pending": pending, "investigation": plan.intelligence if result.intelligence else memory.get("investigation"),
               "answer_id": remember_answer(result.intelligence, answer_owner) if result.intelligence else memory.get("answer_id"),
               "account_state": result.account.get("state", {}) if result.account else memory.get("account_state", {}),
               # the latest recommendation's stated constraints, so 'order it' keeps the machine, quantity, budget and priority
               "shopping": result.shopping.interpretation.model_dump(include={"machine", "quantity", "budget_max", "budget_currency", "preference"})
               if result.shopping and result.shopping.state == "recommendation" else memory.get("shopping")}
    result.context = save_memory(updated if succeeded or plan.clarification else memory, secret, owner)
    result.presentation = present(plan.view, result.intelligence, result.shopping, result.account)
    return result
