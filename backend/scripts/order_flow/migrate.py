"""One-off, idempotent graph migration for the direct-order flow. Adds only what the flow needs; changes no existing record.

  * OrderStatus nodes for the new lifecycle and exception states (the existing vocabulary NEW … DELIVERED is kept and reused)
  * unique constraints: Order.idempotency_key (one order per place-order key), OrderSequence.name, DealerService.service_id,
    and rel_id uniqueness for each relationship type the flow introduces

  python migrate.py plan | apply
"""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from neo4j import WRITE_ACCESS  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.graph.client import GraphClient  # noqa: E402
from app.services.order_flow import LABEL, NEW_STATUS_SEQUENCE  # noqa: E402

NEW_RELS = ["PLACED_BY", "SHIPS_TO", "FOR_DEALER", "FULFILLED_FROM", "USES_TRANSPORT", "HAS_SERVICE", "PERFORMED_BY", "USES_ROUTE"]

CONSTRAINTS = [
    "CREATE CONSTRAINT order_idempotency_key_unique IF NOT EXISTS FOR (n:Order) REQUIRE n.idempotency_key IS UNIQUE",
    "CREATE CONSTRAINT order_sequence_name_unique IF NOT EXISTS FOR (n:OrderSequence) REQUIRE n.name IS UNIQUE",
    "CREATE CONSTRAINT dealer_service_id_unique IF NOT EXISTS FOR (n:DealerService) REQUIRE n.service_id IS UNIQUE",
    *[f"CREATE CONSTRAINT rel_{t.lower()}_id_unique IF NOT EXISTS FOR ()-[r:`{t}`]-() REQUIRE r.rel_id IS UNIQUE" for t in NEW_RELS],
]

STATUS = """
MERGE (s:OrderStatus {order_status_code: $code})
ON CREATE SET s += {label: $label, sequence: $seq, data_status: 'USER_PROVIDED', provenance_type: 'USER_PROVIDED', source_id: 'APP-SESSION', source_name: 'Noordveld app (order flow)',
  source_record_id: 'OS-' + $code, authoritative_flag: false, confidence: 'NOT_STATED', last_updated: $today}
RETURN s.order_status_code AS code
"""


def main(mode: str) -> None:
    g = GraphClient(get_settings())
    have = {r["c"] for r in g.read("MATCH (s:OrderStatus) RETURN s.order_status_code AS c")}
    todo = {c: q for c, q in NEW_STATUS_SEQUENCE.items() if c not in have}
    print(f"order statuses present {sorted(have)}; to add {sorted(todo)}; {len(CONSTRAINTS)} constraints (IF NOT EXISTS)")
    if mode != "apply":
        return
    import datetime as dt

    today = dt.date.today().isoformat()
    for stmt in CONSTRAINTS:
        with g.driver.session(database=get_settings().neo4j_database, default_access_mode=WRITE_ACCESS) as s:
            s.run(stmt).consume()
    for code, seq in todo.items():
        g.write(STATUS, code=code, label=LABEL[code], seq=seq, today=today)
    print("applied; statuses now", sorted(r["c"] for r in g.read("MATCH (s:OrderStatus) RETURN s.order_status_code AS c")))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "plan")
