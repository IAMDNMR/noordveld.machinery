"""Cypher for the lifecycle readers (read-only). One machine at a time: nothing here scans the whole graph for a single answer."""

INSTANCE = """
MATCH (m:MachineInstance {machine_instance_id: $id})
OPTIONAL MATCH (m)-[:OWNED_BY_CUSTOMER]->(c:Customer)
OPTIONAL MATCH (m)-[:LOCATED_AT]->(l)
RETURN properties(m) AS p, c.customer_id AS owner_id, coalesce(l.shipto_id, l.warehouse_id, l.plant_id, l.location_id) AS location_id
"""

INSTANCES = "MATCH (m:MachineInstance) RETURN m.machine_instance_id AS id ORDER BY id"

_INSTALLATION_RETURN = """
OPTIONAL MATCH (i)-[:INSTALLED_PART]->(pt:Part)
OPTIONAL MATCH (i)-[:PERFORMED_AT]->(d:Dealer)
OPTIONAL MATCH (i)-[:PERFORMED_BY]->(t:Technician)
OPTIONAL MATCH (i)-[:RECORDED_IN]->(w:WorkOrder)
RETURN properties(i) AS p, m.machine_instance_id AS machine_instance_id, pt.part_id AS part_id, d.dealer_id AS dealer_id, t.technician_id AS technician_id,
       w.work_order_id AS work_order_id
ORDER BY i.installation_date, i.installation_id
"""

INSTALLATIONS_OF = "MATCH (m:MachineInstance {machine_instance_id: $id})-[:HAS_INSTALLATION]->(i:InstallationEvent)" + _INSTALLATION_RETURN
INSTALLATION = "MATCH (m:MachineInstance)-[:HAS_INSTALLATION]->(i:InstallationEvent {installation_id: $id})" + _INSTALLATION_RETURN

WORK_ORDER = """
MATCH (w:WorkOrder {work_order_id: $id})
OPTIONAL MATCH (m:MachineInstance)-[:HAS_WORK_ORDER]->(w)
OPTIONAL MATCH (w)-[:PERFORMED_BY_DEALER]->(d:Dealer)
OPTIONAL MATCH (w)-[:ASSIGNED_TO]->(t:Technician)
RETURN properties(w) AS p, m.machine_instance_id AS machine_instance_id, d.dealer_id AS dealer_id, t.technician_id AS technician_id
"""

WORK_ORDER_EVENTS = """
MATCH (i:InstallationEvent)-[:RECORDED_IN]->(:WorkOrder {work_order_id: $id}) RETURN i.installation_id AS id ORDER BY id
UNION
MATCH (r:ReplacementEvent)-[:RECORDED_IN]->(:WorkOrder {work_order_id: $id}) RETURN r.replacement_id AS id ORDER BY id
"""

TECHNICIAN = """
MATCH (t:Technician {technician_id: $id})
OPTIONAL MATCH (t)-[:EMPLOYED_BY]->(d:Dealer)
RETURN properties(t) AS p, d.dealer_id AS dealer_id
"""

DEALER = "MATCH (d:Dealer {dealer_id: $id}) RETURN properties(d) AS p"

PART = """
MATCH (p:Part {part_id: $id})
OPTIONAL MATCH (c:PartCatalogProfile)-[:PROFILES_PART]->(p)
RETURN properties(p) AS p, c.part_status AS status
"""

FITMENT = "MATCH (f:FitmentContext {machine_id: $machine, part_id: $part}) RETURN properties(f) AS p ORDER BY f.fitment_id"

APPROVED_SOURCES = """
MATCH (p:Part {part_id: $id})-[x:APPROVED_SOURCE]->(s)
RETURN properties(x) AS p, coalesce(s.supplier_id, s.dealer_id) AS source_id ORDER BY x.rel_id
"""

POLICIES = """
MATCH (w:WarrantyPolicy)-[:WARRANTY_FOR_PART]->(:Part {part_id: $id})
RETURN properties(w) AS p, $id AS part_id ORDER BY w.warranty_policy_id
"""

_CLAIM_RETURN = """
OPTIONAL MATCH (c)-[:CLAIM_FOR_PART]->(pt:Part)
OPTIONAL MATCH (c)-[:CLAIM_ON_INSTALLATION]->(i:InstallationEvent)
OPTIONAL MATCH (c)-[:FILED_BY_DEALER]->(d:Dealer)
RETURN properties(c) AS p, m.machine_instance_id AS machine_instance_id, pt.part_id AS part_id, i.installation_id AS installation_id, d.dealer_id AS dealer_id
ORDER BY c.claim_date, c.claim_id
"""
CLAIM = "MATCH (m:MachineInstance)-[:HAS_CLAIM]->(c:WarrantyClaim {claim_id: $id})" + _CLAIM_RETURN
CLAIMS_OF = "MATCH (m:MachineInstance {machine_instance_id: $id})-[:HAS_CLAIM]->(c:WarrantyClaim)" + _CLAIM_RETURN
CLAIM_IDS = "MATCH (c:WarrantyClaim) RETURN c.claim_id AS id ORDER BY id"

REPLACEMENTS_OF = """
MATCH (m:MachineInstance {machine_instance_id: $id})-[:HAS_REPLACEMENT]->(r:ReplacementEvent)
OPTIONAL MATCH (r)-[:REMOVED_INSTALLATION]->(oi:InstallationEvent)-[:INSTALLED_PART]->(op:Part)
OPTIONAL MATCH (r)-[:NEW_INSTALLATION]->(ni:InstallationEvent)-[:INSTALLED_PART]->(np:Part)
OPTIONAL MATCH (r)-[:RECORDED_IN]->(w:WorkOrder)
RETURN properties(r) AS p, m.machine_instance_id AS machine_instance_id, oi.installation_id AS removed_installation_id, ni.installation_id AS new_installation_id,
       op.part_id AS removed_part_id, np.part_id AS installed_part_id, w.work_order_id AS work_order_id
ORDER BY r.replacement_date, r.replacement_id
"""

EVIDENCE = """
MATCH (e:Evidence {entity_type: $type, entity_id: $id})
RETURN properties(e) AS p ORDER BY e.created_at, e.evidence_id
"""
