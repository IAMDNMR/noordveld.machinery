"""Seed the demo users of the two workflow roles. Idempotent: users and links are MERGEd on their ids, so running it twice changes nothing.

Usage (from backend/):  python scripts/seed_demo_users.py

Creates three synthetic AppUser nodes (data_status SYNTHETIC_DEMO) and links each End User to an existing demo customer, so the orders
that customer already has become that user's own orders. Nothing else in the graph is touched; no order, stock or price is created.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
logging.disable(logging.CRITICAL)

from app.core.config import get_settings  # noqa: E402
from app.graph.client import GraphClient  # noqa: E402

TODAY = "2026-10-04"
USERS = [
    {"user_id": "USR-EU-001", "name": "Anna de Vries (demo)", "email": "anna.devries@brabantia.example", "role": "END_USER", "customer_id": "CUS-008"},
    {"user_id": "USR-EU-002", "name": "Lars Becker (demo)", "email": "lars.becker@harmsen.example", "role": "END_USER", "customer_id": "CUS-001"},
    {"user_id": "USR-OP-001", "name": "Jane Doe (demo)", "email": "jane.doe@noordveld.example", "role": "ORDER_PROCESSOR", "customer_id": None},
]

SEED = """
UNWIND $users AS u
MERGE (a:AppUser {user_id: u.user_id})
ON CREATE SET a += {name: u.name, email: u.email, role: u.role, source_record_id: u.user_id, data_status: 'SYNTHETIC_DEMO', provenance_type: 'SYNTHETIC_DEMO',
  source_id: 'APP-SEED', source_name: 'seed_demo_users.py', authoritative_flag: false, confidence: 'NOT_STATED', last_updated: $today}
WITH a, u
OPTIONAL MATCH (c:Customer {customer_id: u.customer_id})
FOREACH (x IN CASE WHEN c IS NULL THEN [] ELSE [c] END |
  MERGE (a)-[r:ACTS_FOR]->(x) ON CREATE SET r += {rel_id: 'ACTS_FOR:' + u.user_id, data_status: 'SYNTHETIC_DEMO', provenance_type: 'SYNTHETIC_DEMO',
    source_id: 'APP-SEED', source_name: 'seed_demo_users.py', last_updated: $today})
RETURN a.user_id AS user_id, a.role AS role, c.customer_id AS customer_id
"""


def main() -> None:
    g = GraphClient(get_settings())
    try:
        g.write("CREATE CONSTRAINT app_user_id IF NOT EXISTS FOR (a:AppUser) REQUIRE a.user_id IS UNIQUE")
        for row in g.write(SEED, users=USERS, today=TODAY):
            print(f"{row['user_id']}  {row['role']:<16} {row['customer_id'] or '-'}")
        print("users:", g.read("MATCH (a:AppUser) RETURN count(a) AS n")[0]["n"], "· ACTS_FOR:", g.read("MATCH ()-[r:ACTS_FOR]->() RETURN count(r) AS n")[0]["n"])
    finally:
        g.close()


if __name__ == "__main__":
    main()
