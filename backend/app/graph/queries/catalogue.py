"""Cypher for the catalogue's filter options: machines, categories and availability states, all with live counts."""

MACHINES = """
MATCH (m:Machine)
RETURN m{.machine_id, .model_code, .name, .machine_type, .origin_plant, .country} AS machine,
       size([(m)<-[:FITS]-(:Part) | 1]) AS part_count
ORDER BY m.model_code
"""

CATEGORIES = """
MATCH (c:Category) WHERE c.level = 1
RETURN c{.category_id, .name} AS category, size([(c)<-[:IN_CATEGORY]-(:Part) | 1]) AS part_count
ORDER BY c.name
"""

AVAILABILITY = """
MATCH (c:PartCatalogProfile) WHERE c.availability_state IS NOT NULL
RETURN c.availability_state AS state, count(*) AS part_count, collect(DISTINCT c.data_status)[0] AS data_status
ORDER BY state
"""

READY = "RETURN 1 AS ok"
