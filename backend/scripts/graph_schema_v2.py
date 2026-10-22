"""Knowledge graph schema v2: print, validate, export and (only on a dedicated instance, with a backup) apply.

    python scripts/graph_schema_v2.py print            the idempotent schema script (constraints and indexes)
    python scripts/graph_schema_v2.py validate         schema checks, projection of every pack, statement lint, in-memory round trip. Needs no database.
    python scripts/graph_schema_v2.py export PATH      every write statement and its parameters as JSON, for review
    python scripts/graph_schema_v2.py apply --backup-confirmed PATH --yes
                                                       runs the schema and the write plan against DOMAIN_GRAPH_URI. Refuses unless that is a
                                                       dedicated graph, different from the operational NEO4J_URI, and a backup file exists.

`apply` is deliberately hard to run. This repository has not run it against any server: only the in-memory double has been exercised.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app.core.config as config  # noqa: E402

config._load_env_file = lambda *args: None  # never read .env: this tool takes its target only from explicit environment variables

from app.design_studio.knowledge.provider import LocalKnowledgeProvider  # noqa: E402
from app.knowledge_graph import schema  # noqa: E402
from app.knowledge_graph.memory import InMemoryGraph  # noqa: E402
from app.knowledge_graph.projection import lint, project  # noqa: E402
from app.knowledge_graph.provider import GraphKnowledgeProvider  # noqa: E402


def blockers(backup: str | None, yes: bool) -> list[str]:
    uri, shared = os.environ.get("DOMAIN_GRAPH_URI", ""), os.environ.get("NEO4J_URI", "")
    problems = []
    if not uri:
        problems.append("DOMAIN_GRAPH_URI is not set: there is no dedicated knowledge graph to apply to. Create a separate development instance first.")
    if uri and shared and uri.rstrip("/") == shared.rstrip("/"):
        problems.append("DOMAIN_GRAPH_URI is the same as NEO4J_URI, the shared operational graph. Refusing.")
    for name in ("DOMAIN_GRAPH_USERNAME", "DOMAIN_GRAPH_PASSWORD"):
        if not os.environ.get(name):
            problems.append(f"{name} is not set (dedicated credentials are required).")
    if os.environ.get("DOMAIN_GRAPH_USERNAME") and os.environ.get("DOMAIN_GRAPH_USERNAME") == os.environ.get("NEO4J_USERNAME") and os.environ.get("DOMAIN_GRAPH_PASSWORD") == os.environ.get("NEO4J_PASSWORD"):
        problems.append("The dedicated credentials equal the operational credentials. Refusing.")
    if not backup or not Path(backup).is_file():
        problems.append("--backup-confirmed must name an existing backup or export file taken before this change.")
    if not yes:
        problems.append("--yes is required: this writes to a database.")
    return problems


def validate() -> int:
    provider = LocalKnowledgeProvider()
    problems = schema.validate_schema()
    projection = project(provider.packs(), provider.capabilities())
    plan = projection.write_plan()
    problems += lint(plan)
    graph = InMemoryGraph().load(projection)
    problems += graph.verify()
    before = graph.counts()
    graph.load(project(provider.packs(), provider.capabilities()))
    if graph.counts() != before:
        problems.append("loading the same projection twice changed the graph: it is not idempotent")
    served = GraphKnowledgeProvider(graph)
    if sorted(p.id for p in served.packs()) != sorted(p.id for p in provider.packs()):
        problems.append("the graph does not serve the same packs it was loaded from")
    print(f"schema v{schema.SCHEMA_VERSION}: {len(schema.ALL_LABELS)} labels, {len(schema.ALL_TYPES)} relationship types, {len(schema.constraints())} constraints, {len(schema.indexes())} indexes")
    print(f"projection: {len(provider.packs())} pack versions -> {before['nodes']} nodes, {before['relationships']} relationships, {len(plan)} statements")
    print("NOT verified here: the Cypher has never run against a Neo4j server (no dedicated development graph exists).")
    for problem in problems:
        print("PROBLEM:", problem)
    return 1 if problems else 0


def apply(backup: str | None, yes: bool) -> int:
    problems = blockers(backup, yes)
    if problems:
        print("Refusing to apply:")
        for problem in problems:
            print(" -", problem)
        return 2
    from neo4j import GraphDatabase  # imported only here: nothing else in this tool opens a connection
    provider = LocalKnowledgeProvider()
    plan = project(provider.packs(), provider.capabilities()).write_plan()
    driver = GraphDatabase.driver(os.environ["DOMAIN_GRAPH_URI"], auth=(os.environ["DOMAIN_GRAPH_USERNAME"], os.environ["DOMAIN_GRAPH_PASSWORD"]))
    with driver.session(database=os.environ.get("DOMAIN_GRAPH_DATABASE") or None) as session:
        for _, statements in schema.MIGRATIONS:
            for statement in statements:
                session.run(statement).consume()
        for step in plan:
            session.run(step["cypher"], step["params"]).consume()
    driver.close()
    print(f"applied schema v{schema.SCHEMA_VERSION} and {len(plan)} statements to the dedicated graph")
    return 0


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "validate"
    if command == "print":
        print(schema.migration_script())
        return 0
    if command == "validate":
        return validate()
    if command == "export":
        out = Path(argv[1])
        provider = LocalKnowledgeProvider()
        out.write_text(json.dumps({"schema": schema.migration_script(), "plan": project(provider.packs(), provider.capabilities()).write_plan()}), encoding="utf-8")
        print(f"wrote {out}")
        return 0
    if command == "apply":
        backup = argv[argv.index("--backup-confirmed") + 1] if "--backup-confirmed" in argv else None
        return apply(backup, "--yes" in argv)
    print(__doc__)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
