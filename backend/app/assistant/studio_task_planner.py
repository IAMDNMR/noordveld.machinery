"""Deterministic task controls before the existing, untrusted action planner."""

import re

from app.assistant import studio_agent
from app.assistant.studio_actions import AnswerDecision, DeferDecision
from app.design_studio.approval import digest


CONTINUE = re.compile(
    r"^(?:ok(?:ay)?[, ]*)?(?:continue|next(?: phase| stage)?|go ah(?:ead|esd)|proceed(?: to (?:the )?next (?:phase|stage))?)[.! ]*$",
    re.I,
)


def run(llm, message, history, asked, definition, findings, stages, knowledge, selected):
    text = message.strip()
    if re.fullmatch(
        r"(?:please )?(?:run|execute)(?: the)?(?: generated| application| app)? tests[.! ]*",
        text,
        re.I,
    ):
        return studio_agent.Plan(
            mode="direct",
            command="test",
            focus="export",
            reply="I'll run the generated application's tests. The existing generation and access checks still apply.",
        )
    task = definition.assistant_context
    question_id = asked or (task.asked_question_id if task else None)
    decision = next(
        (d for d in definition.business.decisions if d.id == question_id and d.status == "open"),
        None,
    )
    question = next(
        (q for q in definition.business.questions if q.id == question_id and q.status == "open"),
        None,
    )
    defer = re.search(r"\b(?:decide (?:this |it )?later|defer|postpone)\b", text, re.I)
    if not question_id and (defer or CONTINUE.fullmatch(text)):
        decision = next((d for d in definition.business.decisions if d.status == "open"), None)
        question_id = decision.id if decision else None
    if decision and defer:
        reason = re.search(r"\b(?:because|since|reason[: ]+)\s*(.+)", text, re.I)
        if not reason or not reason[1].strip(" ."):
            return studio_agent.Plan(
                mode="direct",
                reply="What is the reason for deciding this later? For example, say ‘decide later because the operations owner must review it’.",
                asking=question_id,
            )
        return studio_agent.Plan(
            mode="direct",
            actions=[
                DeferDecision(
                    type="defer_decision", decision_id=decision.id, reason=reason[1].strip()
                )
            ],
            reply="I prepared the deferral with your reason. Review and apply it; it will then become a warning rather than an approval blocker.",
        )
    if (
        decision
        and task
        and task.original_request
        and re.search(
            r"\b(?:decide (?:this |it )?later|defer|postpone)\b", task.original_request, re.I
        )
        and not CONTINUE.fullmatch(text)
        and not text.endswith("?")
        and not re.search(
            r"\b(?:add|remove|delete|change|make|correct|instead|show|open|generate|build|fix|why|what|how)\b",
            text,
            re.I,
        )
    ):
        return studio_agent.Plan(
            mode="direct",
            actions=[
                DeferDecision(type="defer_decision", decision_id=decision.id, reason=text[:1000])
            ],
            reply="I prepared the deferral with your reason for review.",
        )
    if CONTINUE.fullmatch(text):
        previous = (
            next((r for r in reversed(task.receipts) if r.status != "running"), None)
            if task
            else None
        )
        if task and (
            task.status == "blocked"
            or task.blocked_before_turn
            or previous
            and (
                previous.status == "failed"
                or previous.turn
                and (previous.turn.get("rejected") or previous.turn.get("degraded"))
            )
        ):
            reason = "The previous request did not finish successfully. Inspect its saved changes and resolve the reported failure before continuing."
            return studio_agent.Plan(
                mode="direct", reply=reason, rejected=[{"type": "pending_task", "reason": reason}]
            )
        if decision or question:
            return studio_agent.Plan(
                mode="direct",
                reply=f"Before I continue: {(decision.question if decision else question.text)}",
                asking=question_id,
            )
        if (
            task
            and task.pending_proposal
            and task.pending_proposal["base_sha256"] == digest(definition, "design")
        ):
            return studio_agent.Plan(
                mode="direct",
                reply="Review and apply the pending change before moving to another stage.",
            )
        if task and task.pending_operation:
            return studio_agent.Plan(
                mode="direct",
                reply="The previous application operation still needs to finish. Check its result before moving to another stage.",
            )
        return studio_agent.Plan(
            mode="direct", command="continue", reply="Moving on once this stage's checks pass."
        )
    if re.fullmatch(r"(?:show|open)(?: me)?(?: the)? (?:current )?preview[.! ]*", text, re.I):
        return studio_agent.Plan(
            mode="direct",
            focus="screen",
            reply="Here is the current application preview. Its saved status shows whether it matches the latest design.",
        )
    if re.fullmatch(
        r"(?:what (?:do you need|is missing)(?: from me)?|what next)[?! .]*", text, re.I
    ) and (decision or question):
        return studio_agent.Plan(
            mode="direct",
            reply=(decision.question if decision else question.text),
            asking=question_id,
        )
    if (
        definition.generated_frontend
        and re.search(
            r"\b(?:layout|dashboard|screen|interface|navigation|spacing|font|button|heading)\b",
            text,
            re.I,
        )
        and re.search(
            r"\b(?:change|make|move|add|remove|hide|show|keep|redesign|update)\b", text, re.I
        )
        and not re.search(
            r"\b(?:permission|role|mandatory|required|optional|approval|calculation|rule|policy|workflow)\b",
            text,
            re.I,
        )
    ):
        return studio_agent.Plan(
            mode="direct",
            command="design_frontend",
            focus="screen",
            reply="I'll edit the existing application interface and retain unrelated files.",
        )
    # A short answer to the specific saved question can be recorded without a model.
    # Commands, corrections and new requests must still be interpreted in context.
    instruction = re.search(
        r"\b(?:add|remove|delete|change|make|correct|instead|show|open|generate|build|fix|why|what|how|skip|later|don't know|do not know)\b",
        text,
        re.I,
    )
    if decision and len(text) <= 1000 and not instruction and not text.endswith("?"):
        if re.fullmatch(r"(?:yes|ok(?:ay)?|sure|do it|approve|approved)[.! ]*", text, re.I):
            return studio_agent.Plan(
                mode="direct",
                reply=f"Please specify the policy: {decision.question}",
                asking=question_id,
            )
        return studio_agent.Plan(
            mode="direct",
            actions=[AnswerDecision(type="answer_decision", decision_id=decision.id, answer=text)],
            reply="I prepared your answer for review. It becomes a saved business decision when you apply it.",
        )
    return studio_agent.run(
        llm, message, history, question_id, definition, findings, stages, knowledge, selected
    )
