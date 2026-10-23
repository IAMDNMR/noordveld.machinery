"""Bounded conversation memory and idempotency, using the existing project CAS store."""

import hashlib
import json

from app.schemas.studio_task import StudioTask, TaskMessage, TaskReceipt


def fingerprint(body) -> str:
    # A retry may have refreshed its revision, but must still be the same instruction.
    content = {
        key: getattr(body, key) for key in ("message", "selected", "stage", "input_mode", "guided")
    }
    return hashlib.sha256(json.dumps(content, sort_keys=True).encode()).hexdigest()


def begin(current, body):
    context = (current.assistant_context or StudioTask()).model_copy(deep=True)
    context.history = [
        *context.history,
        TaskMessage(role="user", text=body.message, request_id=body.request_id),
    ][-24:]
    context.receipts = [
        *context.receipts,
        TaskReceipt(request_id=body.request_id, fingerprint=fingerprint(body), status="running"),
    ][-8:]
    context.selected = body.selected or context.selected
    context.blocked_before_turn = context.status == "blocked"
    context.status = "working"
    return current.model_copy(update={"assistant_context": context})


def finish(current, body, turn):
    context = current.assistant_context.model_copy(deep=True)
    context.blocked_before_turn = False
    receipt = next(r for r in context.receipts if r.request_id == body.request_id)
    receipt.status, receipt.turn = "completed", turn
    context.history = [
        *context.history,
        TaskMessage(role="assistant", text=turn["reply"][:4000], request_id=body.request_id),
    ][-24:]
    context.asked_question_id = turn.get("asked_question_id")
    context.pending_proposal = turn.get("proposal")
    context.pending_operation = (
        turn.get("client_action") if turn.get("client_action") in ("frontend", "test") else None
    )
    context.status = (
        "awaiting_review"
        if context.pending_proposal
        else "awaiting_answer"
        if context.asked_question_id
        else "awaiting_execution"
        if context.pending_operation
        else "blocked"
        if turn.get("rejected") or turn.get("degraded")
        else "completed"
    )
    context.original_request = (
        body.message if context.asked_question_id or context.pending_operation else None
    )
    return current.model_copy(update={"assistant_context": context})


def operation_result(current, operation: str, message: str, *, failed=False):
    """Complete a dispatched operation only when its real service returns."""
    task = current.assistant_context
    if not task or task.pending_operation != operation:
        return None
    task = task.model_copy(deep=True)
    task.status = (
        "blocked" if failed else "awaiting_answer" if task.asked_question_id else "completed"
    )
    if not failed:
        task.pending_operation = None
    receipt = next(
        (r for r in reversed(task.receipts) if r.turn and r.turn.get("client_action") == operation),
        None,
    )
    if receipt:
        receipt.turn = {**receipt.turn, "reply": message, "client_action": None}
        for item in reversed(task.history):
            if item.role == "assistant" and item.request_id == receipt.request_id:
                item.text = message[:4000]
                break
    return current.model_copy(update={"assistant_context": task})


def resolve_proposal(current):
    task = current.assistant_context
    if not task or not task.pending_proposal:
        return None
    task = task.model_copy(deep=True)
    task.pending_proposal = None
    next_decision = next((d for d in current.business.decisions if d.status == "open"), None)
    next_question = next((q for q in current.business.questions if q.status == "open"), None)
    task.asked_question_id = (
        next_decision.id if next_decision else next_question.id if next_question else None
    )
    task.status = "awaiting_answer" if task.asked_question_id else "completed"
    for receipt in task.receipts:
        if receipt.turn and receipt.turn.get("proposal"):
            receipt.turn = {**receipt.turn, "proposal": None}
    return current.model_copy(update={"assistant_context": task})
