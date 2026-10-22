"""A stand-in for the Studio language model in offline tests: it drafts a small transport foundation, never a network call."""

FOUNDATION = [
    {"type": "add_role", "name": "Dispatcher", "responsibilities": ["Plan shipments", "Assign vehicles"]},
    {"type": "add_role", "name": "Driver", "responsibilities": ["Deliver shipments"]},
    {"type": "add_entity", "name": "Vehicle", "attributes": [
        {"name": "Registration", "type": "string", "required": True, "key": True},
        {"name": "Capacity", "type": "integer", "required": False}]},
    {"type": "add_entity", "name": "Shipment", "attributes": [
        {"name": "Reference", "type": "string", "required": True, "key": True},
        {"name": "Destination", "type": "string", "required": True},
        {"name": "Notes", "type": "string", "required": False}],
     "relationships": [{"name": "Vehicle", "target": "Vehicle", "cardinality": "many_to_one"}]},
    {"type": "add_rule", "description": "Only an available vehicle may be assigned.", "condition": "vehicle is available", "outcomes": ["assign", "refuse"]},
    {"type": "create_workflow", "name": "Deliver shipment", "steps": [
        {"name": "Plan shipment", "kind": "form", "role": "Dispatcher", "writes": ["Shipment"]},
        {"name": "Check vehicle capacity", "kind": "branch", "role": "Dispatcher", "reads": ["Shipment", "Vehicle"]},
        {"name": "Assign vehicle", "kind": "action", "role": "Dispatcher", "reads": ["Vehicle"], "writes": ["Shipment"]},
        {"name": "Confirm delivery", "kind": "form", "role": "Driver", "writes": ["Shipment"]}]},
]


class FoundationModel:
    name = "fake"
    _model = "fake-foundation"

    def studio_json(self, system: str, prompt: str) -> dict:
        return {"reply": "Draft ready for your review.", "actions": [], "questions": [], "ask": None}

    def studio_blueprint(self, system: str, prompt: str) -> dict:
        return {"reply": "I've drafted a foundation for this transport application.", "actions": FOUNDATION, "questions": [], "ask": None}
