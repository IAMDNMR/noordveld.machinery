"""Deterministic synthetic lifecycle data and scenario records, written as canonical files.

No random numbers: every value is a function of the existing graph records and a record's position, so the same graph always gives the same files.
Everything here is SYNTHETIC_DEMO and says so. The lifecycle domain did not exist before (no machine serials, installations, work orders or claims), so these
files are the trustworthy FOUNDATION that the ingestion, validation and integrity layers are exercised on. They are not claims about real machines.
"""
from __future__ import annotations

import dataclasses
import json
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from app.canonical.io import CANON_DIR, dump_rows, load_rows
from app.canonical.registry import BY_NAME
from app.core.config import get_settings
from app.graph.client import GraphClient

SYN = {"data_status": "SYNTHETIC_DEMO", "source_type": "SYNTHETIC_DEMO"}
NO_DOCUMENT = "Synthetic demonstration record: no real document exists"
BASE_DATE = date(2025, 1, 15)
N_INSTANCES = 12
REPLACED_EVERY = 3  # instances 0, 3, 6, 9 had their first part replaced
CLAIMED = 3  # the first three replaced instances have a claim
SPECIALIZATIONS = ["Hydraulics", "Powertrain", "Electrical", "Transmission"]


def _rows(name: str, root: Path) -> list[dict[str, Any]]:
    return load_rows(BY_NAME[name], root)[0]


def _d(offset: int) -> str:
    return (BASE_DATE + timedelta(days=offset)).isoformat()


def generate(root: Path = CANON_DIR, generated_at: str = "") -> dict[str, int]:
    vocab = json.loads((root / "reference" / "discovery_vocabulary.json").read_text(encoding="utf-8"))
    g = GraphClient(dataclasses.replace(get_settings(), neo4j_query_timeout=120.0))
    try:
        variants = g.read("MATCH (v:MachineVariant)-[:VARIANT_OF]->(m:Machine) RETURN v.variant_id AS v, m.machine_id AS m, v.serial_from AS f, v.serial_to AS t ORDER BY v")
        shiptos = g.read("MATCH (c:Customer)-[:HAS_SHIP_TO]->(s:ShipTo) RETURN c.customer_id AS c, s.shipto_id AS s, s.country_code AS cc ORDER BY c, s")
        warranty_dealers = g.read("MATCH (d:Dealer)-[:HAS_CAPABILITY]->(:Capability {name: 'Warranty Service'}) RETURN d.dealer_id AS d, d.country_code AS cc ORDER BY d")
        categories = g.read("MATCH (p:Part)-[:IN_CATEGORY]->(c:Category) RETURN p.part_id AS p, c.name AS c")
    finally:
        g.close()
    category_of = {r["p"]: r["c"] for r in categories}
    customers = sorted(r["customer_id"] for r in _rows("customers", root))
    parts = {r["part_id"]: r for r in _rows("parts", root)}
    machines = {r["machine_id"]: r for r in _rows("machines", root)}
    fits: dict[str, list[str]] = defaultdict(list)
    for f in _rows("fitment", root):
        if f["fitment_status"] == "APPROVED" and parts.get(f["part_id"], {}).get("status") == "VERIFIED":
            fits[f["machine_id"]].append(f["part_id"])
    ship_of: dict[str, list[dict]] = defaultdict(list)
    for s in shiptos:
        ship_of[s["c"]].append(s)
    pool = [d["d"] for d in warranty_dealers]
    country_of = {d["d"]: d["cc"] for d in warranty_dealers}
    names = vocab["technician_names"]

    # variants that have approved, verified parts, in a fixed order
    usable = [v for v in variants if fits.get(v["m"])]
    chosen = usable[::2][:N_INSTANCES]
    instances, work_orders, installs, replaces, claims, evidence = [], [], [], [], [], []
    techs: dict[str, dict] = {}
    decided_claims: set[str] = set()  # claims whose status/decision is derived by the evaluator (golden claims stay SUBMITTED unless marked decided)
    wo_n = inst_n = 0

    def dealer_for(country: str, i: int) -> str:
        same = [d for d in pool if country_of[d] == country]
        return (same or pool)[i % len(same or pool)]

    def technician(dealer: str, k: int) -> str:
        tid = f"TEC-{dealer}-{k}"
        if tid not in techs:
            idx = len(techs)
            techs[tid] = {"technician_id": tid, "dealer_id": dealer, "name": names[idx % len(names)], "certification": "Noordveld Certified Technician L" + ("3" if k == 1 else "2"),
                          "specialization": SPECIALIZATIONS[idx % len(SPECIALIZATIONS)], "status": "ACTIVE", **SYN, "source_record_id": f"synthetic:{tid}"}
        return tid

    for i, v in enumerate(chosen):
        owner = customers[i % len(customers)]
        ship = ship_of[owner][0]
        dealer = dealer_for(ship["cc"], i)
        mid = f"MI-{i + 1:04d}"
        prefix, _, tail = v["f"].rpartition("-")
        lo, hi = int(tail), int(v["t"].rpartition("-")[2])
        serial = f"{prefix}-{lo + (i * 37) % max(1, hi - lo):05d}"
        instances.append({"machine_instance_id": mid, "machine_id": v["m"], "variant_id": v["v"], "serial_number": serial, "model_year": 2019 + i % 6, "owner_id": owner,
                          "location_id": ship["s"], "status": "IN_SERVICE", **SYN, "source_record_id": f"synthetic:{mid}"})
        candidates = sorted(fits[v["m"]])
        k1 = i % len(candidates)
        k2 = (i + 3) % len(candidates)
        k2 = (i + 1) % len(candidates) if k2 == k1 else k2
        p1, p2 = candidates[k1], (candidates[k2] if k2 != k1 else None)  # a machine with a single fitting part gets a single installation
        replaced = i % REPLACED_EVERY == 0
        timeline = [(p1, 17 * i, "INSTALLATION"), (p2, 17 * i + 9, "INSTALLATION")]

        def install(part: str, offset: int, kind: str, status: str, removal: str | None, serial_suffix: str, k: int, dealer: str = dealer, mid: str = mid) -> str:
            nonlocal wo_n, inst_n
            wo_n += 1
            inst_n += 1
            wo, inst, tec = f"WO-{wo_n:04d}", f"INS-{inst_n:04d}", technician(dealer, k)
            work_orders.append({"work_order_id": wo, "machine_instance_id": mid, "dealer_id": dealer, "technician_id": tec, "service_date": _d(offset), "service_type": kind,
                                "status": "COMPLETED", "reason": "Scheduled fitting of a catalogue part" if kind == "INSTALLATION" else "Replacement of a failed part", **SYN,
                                "source_record_id": f"synthetic:{wo}"})
            installs.append({"installation_id": inst, "machine_instance_id": mid, "part_id": part, "part_serial_number": f"SN-{part.replace('PRT-', '')}-{mid[3:]}-{serial_suffix}",
                             "dealer_id": dealer, "technician_id": tec, "work_order_id": wo, "installation_date": _d(offset), "removal_date": removal, "status": status, **SYN,
                             "source_record_id": f"synthetic:{inst}"})
            evidence.append({"evidence_id": f"EV-{wo}", "evidence_type": "WORK_ORDER", "entity_type": "WORK_ORDER", "entity_id": wo, "reference": NO_DOCUMENT, "created_at": _d(offset), **SYN,
                             "source_record_id": f"synthetic:EV-{wo}"})
            evidence.append({"evidence_id": f"EV-{inst}", "evidence_type": "INSTALLATION_RECORD", "entity_type": "INSTALLATION", "entity_id": inst, "reference": NO_DOCUMENT,
                             "created_at": _d(offset), **SYN, "source_record_id": f"synthetic:EV-{inst}"})
            return inst

        removal_offset = 17 * i + 200
        first = install(p1, timeline[0][1], "INSTALLATION", "REMOVED" if replaced else "CURRENT", _d(removal_offset) if replaced else None, "A", 1)
        if p2:
            install(p2, timeline[1][1], "INSTALLATION", "CURRENT", None, "A", 2)
        if replaced:
            new = install(p1, removal_offset, "REPLACEMENT", "CURRENT", None, "B", 1)
            replaces.append({"replacement_id": f"REP-{len(replaces) + 1:04d}", "machine_instance_id": mid, "removed_part_id": p1, "installed_part_id": p1, "removed_installation_id": first,
                             "new_installation_id": new, "replacement_date": _d(removal_offset), "reason": "Failed in service", "work_order_id": work_orders[-1]["work_order_id"], **SYN,
                             "source_record_id": f"synthetic:REP-{len(replaces) + 1:04d}"})
            if len(replaces) <= CLAIMED:
                n = len(replaces)
                cid = f"CLM-{n:04d}"
                # status and decision are placeholders: derive_claims() replaces them with what the deterministic evaluator returns for the recorded facts
                claims.append({"claim_id": cid, "machine_instance_id": mid, "part_id": p1, "installation_id": first, "failure_date": _d(removal_offset), "claim_date": _d(removal_offset + 2),
                               "dealer_id": dealer, "status": "SUBMITTED", "decision": None, "decision_reason": None, **SYN, "source_record_id": f"synthetic:{cid}"})
                decided_claims.add(cid)
                evidence.append({"evidence_id": f"EV-{cid}", "evidence_type": "SERVICE_REPORT", "entity_type": "WARRANTY_CLAIM", "entity_id": cid, "reference": NO_DOCUMENT,
                                 "created_at": _d(removal_offset + 2), **SYN, "source_record_id": f"synthetic:EV-{cid}"})

    first_ship = next((s for s in _rows("shipments", root) if s["order_id"]), None)
    film_part = next((p for p in parts.values() if p["part_number"] == "NVM-1010-HY"), None)
    film_machine = next((m for m in machines.values() if m["model"] == "NV-4500"), None)
    replaced_inst = replaces[0] if replaces else None
    discovery = [{"scenario_id": "SCN-DISC-001", "scenario_type": "DISCOVERY", "title": "Find a hydraulic hose for an NV-4500", "machine_id": film_machine["machine_id"] if film_machine else None,
                  "part_id": film_part["part_id"] if film_part else None, "customer_id": None, "machine_instance_id": None, "shipment_id": None, "order_id": None,
                  "notes": "Natural-language request resolved to a part through fitment, approved source and availability", **SYN},
                 {"scenario_id": "SCN-FILM-001", "scenario_type": "FILM", "title": "Featured records of the launch film (replaces the FILM_* constants)", "machine_id": film_machine["machine_id"] if film_machine else None,
                  "part_id": film_part["part_id"] if film_part else None, "customer_id": "CUS-008", "machine_instance_id": None, "shipment_id": None, "order_id": None,
                  "notes": "The launch film reads this record (services/site.py): the former FILM_* constants no longer exist in code", **SYN}]
    logistics = [{"scenario_id": "SCN-LOG-001", "scenario_type": "LOGISTICS", "title": "Where is my shipment", "machine_id": None, "part_id": None, "customer_id": None, "machine_instance_id": None,
                  "shipment_id": first_ship["shipment_id"] if first_ship else None, "order_id": first_ship["order_id"] if first_ship else None,
                  "notes": "A seeded shipment with tracking events; its route is not determinable yet (see its remediation flags)", **SYN}]
    warranty = [{"scenario_id": "SCN-WAR-001", "scenario_type": "WARRANTY", "title": "Is this part covered and was it properly fitted", "machine_id": instances[0]["machine_id"] if instances else None,
                 "part_id": replaced_inst["installed_part_id"] if replaced_inst else None, "customer_id": instances[0]["owner_id"] if instances else None,
                 "machine_instance_id": replaced_inst["machine_instance_id"] if replaced_inst else None, "shipment_id": None, "order_id": None,
                 "notes": "A machine whose first part was replaced and claimed; history is preserved, not overwritten", **SYN}]

    golden = json.loads((root / "reference" / "lifecycle_scenarios.json").read_text(encoding="utf-8"))
    for t in golden["technicians"]:
        techs[t["technician_id"]] = {**t, **SYN, "source_record_id": "scenario:lifecycle_scenarios"}
    evidence.extend({**e, **SYN, "source_record_id": "scenario:lifecycle_scenarios"} for e in golden["entity_evidence"])  # dealer, technician and part records: once per entity
    for s in golden["scenarios"]:
        src = {**SYN, "source_record_id": f"scenario:{s['scenario_id']}"}
        instances.append({**s["machine_instance"], **src})
        for key, rows in (("work_orders", work_orders), ("installations", installs), ("replacements", replaces), ("evidence", evidence)):
            rows.extend({**r, **src} for r in s[key])
        for c in s["claims"]:
            if c["decided"]:
                decided_claims.add(c["claim_id"])
            claims.append({**{k: v for k, v in c.items() if k != "decided"}, **src})
        warranty.append({"scenario_id": f"SCN-{s['scenario_id']}", "scenario_type": "WARRANTY", "title": s["title"], "machine_id": s["machine_instance"]["machine_id"], "part_id": s["part_id"],
                         "customer_id": s["machine_instance"]["owner_id"], "machine_instance_id": s["machine_instance_id"], "shipment_id": None, "order_id": None,
                         "notes": f"Expected outcome {s['expected_outcome']}. {s['notes']}", **SYN})

    out = {"machine_instances": instances, "technicians": sorted(techs.values(), key=lambda t: t["technician_id"]), "work_orders": work_orders, "installations": installs,
           "replacements": replaces, "warranty_claims": claims, "evidence": evidence, "scenarios_discovery": discovery, "scenarios_logistics": logistics, "scenarios_warranty": warranty}
    for name, rows in out.items():
        spec = BY_NAME[name]
        rows = [spec.model.model_validate(r).model_dump(exclude={"ingestion_timestamp"}) for r in rows]  # an invalid generated record is a bug: fail loudly
        dump_rows(spec, rows, root, generated_at)
    assert all(category_of.get(i["part_id"]) for i in installs)
    derive_lifecycle(root, generated_at, decided_claims)
    return {k: len(v) for k, v in out.items()}


def derive_lifecycle(root: Path, generated_at: str, decided_claims: set[str]) -> None:
    """Second pass over the written files: installation validation, then the status and decision of decided claims. Both come from app.lifecycle.rules, never by hand."""
    from app.lifecycle.context import WarrantyContextBuilder
    from app.lifecycle.readers import FileReader
    from app.lifecycle.rules import claim_status_for, validate_installation

    reader = FileReader(root)
    rows = []
    for i in reader._rows("installations"):
        status, issues = validate_installation(i, reader.instance(i["machine_instance_id"]), reader.part(i["part_id"]), reader.dealer(i["dealer_id"]) if i["dealer_id"] else None,
                                               reader.technician(i["technician_id"]) if i["technician_id"] else None, reader.work_order(i["work_order_id"]) if i["work_order_id"] else None)
        rows.append({**i, "validation_status": status, "validation_issues": issues})
    spec = BY_NAME["installations"]
    dump_rows(spec, [spec.model.model_validate(r).model_dump(exclude={"ingestion_timestamp"}) for r in rows], root, generated_at)

    builder = WarrantyContextBuilder(FileReader(root))  # fresh reader: the installations were rewritten
    spec = BY_NAME["warranty_claims"]
    out = []
    for c in sorted(builder.r._rows("warranty_claims"), key=lambda c: c["claim_id"]):
        if c["claim_id"] in decided_claims:
            ctx = builder.for_claim(c["claim_id"])
            status, decision = claim_status_for(ctx.outcome)
            c = {**c, "status": status, "decision": decision, "decision_reason": "; ".join(ctx.reasons) if decision else None}
        out.append(c)
    dump_rows(spec, [spec.model.model_validate(r).model_dump(exclude={"ingestion_timestamp"}) for r in out], root, generated_at)
