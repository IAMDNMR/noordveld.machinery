"""AgenticCommerceService: the thin, agent-facing adapter.

  1. accept a normalised intent (or, failing that, a conservative cue selection)
  2. call the matching CommerceContextEngine method
  3. return the structured context and its decision, with the evidence
  4. the conversational agent writes the answer from that structure

It holds no domain rule: every decision is made in the engine and the modules under it. An unclear request is REQUIRES_CLARIFICATION, never a guessed flow.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from app.commerce import contract as c
from app.commerce.access import Principal
from app.commerce.engine import CommerceContextEngine
from app.commerce.intent import DISCOVERY, INTENTS, LOGISTICS, select_intent


@dataclass
class ServiceRequest:
    text: str = ""
    intent: str | None = None
    principal: Principal | None = None
    machine_id: str | None = None
    machine_instance_id: str | None = None
    destination_country: str | None = None
    shipment_id: str | None = None
    order_id: str | None = None
    claim_id: str | None = None
    part_id: str | None = None


@dataclass
class ServiceResponse:
    intent: str | None
    intent_source: str
    intent_scores: dict[str, int]
    decision: c.CommerceDecision
    context: Any  # DiscoveryContext | LogisticsContext | WarrantyContext | None

    def to_dict(self) -> dict[str, Any]:
        return {"intent": self.intent, "intent_source": self.intent_source, "intent_scores": self.intent_scores, "decision": asdict(self.decision),
                "context": self.context.to_dict() if self.context is not None else None}


class AgenticCommerceService:
    def __init__(self, engine: CommerceContextEngine) -> None:
        self.engine = engine

    def handle(self, req: ServiceRequest) -> ServiceResponse:
        choice = select_intent(req.text, req.intent)
        if choice.intent is None:
            d = c.CommerceDecision(status=c.REQUIRES_CLARIFICATION, decision=c.REQUIRES_CLARIFICATION,
                                   summary="I can help find a part, track a shipment, or check warranty. Which do you need?", facts={"options": list(INTENTS), "scores": choice.scores},
                                   reasons=[choice.reason], missing=["intent"], recommended_next_action="Ask the user which of the three they mean.")
            d.source_records = []
            return ServiceResponse(None, choice.source, choice.scores, d, None)
        e, p = self.engine, req.principal
        if choice.intent == DISCOVERY:
            ctx = e.build_discovery_context(req.text, principal=p, machine_id=req.machine_id, machine_instance_id=req.machine_instance_id, destination_country=req.destination_country)
        elif choice.intent == LOGISTICS:
            ctx = e.build_logistics_context(principal=p, shipment_id=req.shipment_id, order_id=req.order_id)
        else:
            ctx = e.build_warranty_context(principal=p, claim_id=req.claim_id, machine_instance_id=req.machine_instance_id, part_id=req.part_id)
        return ServiceResponse(choice.intent, choice.source, choice.scores, ctx.decision, ctx)
