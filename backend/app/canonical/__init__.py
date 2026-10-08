"""Canonical data layer: typed contracts for every Agentic E-Commerce entity, a JSON/CSV ingestion engine, and the integrity checks around it.

Files (backend/data/canonical) -> parse -> validate -> normalise -> resolve references -> plan -> MERGE into Neo4j -> checksum -> report.
The existing graph stays the system of record for protected data: see app/canonical/engine.py for the write policy."""
SCHEMA_VERSION = "1.0"
