"""Local website with opt-in Design Studio SQLite persistence.

Uses the isolated Studio factory's environment/path checks. Commerce and sign-in
continue to use the normal website backend and graph.
"""

import os

from app.main import create_app
from app.design_studio.local_app import _from_environment
from app.api.routes.design_studio import get_design_store, get_project_store
from app.domain_knowledge.store import get_domain_store
from app.design_studio.releases import ReleaseStore, get_release_store
from pathlib import Path

studio = _from_environment()
app = create_app()
release_path = os.environ.get("DESIGN_STUDIO_RELEASE_DB")
if release_path:
    release_store = ReleaseStore(Path(release_path))
    app.dependency_overrides[get_release_store] = lambda: release_store
else:
    app.dependency_overrides[get_release_store] = studio.dependency_overrides[get_release_store]
app.state.release_store = app.dependency_overrides[get_release_store]()
for dependency in (get_design_store, get_project_store, get_domain_store):
    if dependency is get_domain_store and os.environ.get("DESIGN_KNOWLEDGE_SOURCE") == "neo4j":
        continue
    app.dependency_overrides[dependency] = studio.dependency_overrides[dependency]

# Primary project storage changes only after an explicit, verified migration.
namespace = os.environ.get("DESIGN_STUDIO_LOCAL_GRAPH_NAMESPACE")
sql_selected = os.environ.get("DESIGN_STUDIO_STORAGE_BACKEND") in {"postgres", "cockroach"}
if sql_selected:
    from app.design_studio.postgres_activation import configured_stores, configured_release_store

    stores = configured_stores()
    releases = configured_release_store()
    if stores is None or releases is None:
        raise RuntimeError("Enable and migrate the selected SQL storage before starting Studio")
    with stores[0]._connection() as connection:
        marker = connection.execute(
            "SELECT value FROM studio_meta WHERE key=%s", ("migration_complete",)
        ).fetchone()
    if not marker or marker["value"] != "1":
        raise RuntimeError("Verify the Studio data migration before selecting SQL storage")
    app.dependency_overrides[get_design_store] = lambda: stores[0]
    app.dependency_overrides[get_project_store] = lambda: stores[1]
    app.dependency_overrides[get_release_store] = lambda: releases
    app.state.release_store = releases
elif namespace:
    from app.api.dependencies import get_graph
    from app.design_studio.neo4j_store import Neo4jDocuments, Neo4jProjectStore

    graph = get_graph()
    marker = graph.read(
        "MATCH (w:DSWorkspace {namespace:$ns}) RETURN w.schema AS schema,w.project_migration_complete AS complete",
        ns=namespace,
    )
    if not marker or marker[0]["schema"] != "studio-neo4j-v1" or not marker[0]["complete"]:
        raise RuntimeError("Migrate and verify projects before selecting Neo4j project storage")
    project_store = Neo4jProjectStore(
        Neo4jDocuments(graph.driver, graph._settings.neo4j_database, namespace)
    )
    app.dependency_overrides[get_project_store] = lambda: project_store
