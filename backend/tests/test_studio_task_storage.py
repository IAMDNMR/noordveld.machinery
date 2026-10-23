"""Conversation CAS is independent of immutable application content revisions."""
# ruff: noqa: F811 -- pytest fixture intentionally shares its parameter name

from copy import deepcopy

import pytest

from app.design_studio.discovery import blank_definition
from app.design_studio.neo4j_store import Neo4jProjectStore
from app.design_studio.projects import MemoryProjectStore
from app.design_studio.sqlite_store import SqliteProjectStore
from app.design_studio.store import RevisionConflict
from app.schemas.studio_task import StudioTask
from tests.test_design_studio_postgres_contract import adapter as postgres_adapter  # noqa: F401


class Documents:
    """Transaction/document seam, without connecting to a graph service."""

    namespace = "isolated_studio"

    def __init__(self):
        self.data = {}

    def get(self, tx, kind, identifier):
        return deepcopy(self.data.get((kind, identifier)))

    def put(self, tx, kind, identifier, value, immutable=False):
        if immutable and (kind, identifier) in self.data:
            raise RevisionConflict()
        self.data[kind, identifier] = deepcopy(value)

    def read(self, work):
        return work(self)

    write = read

    def run(self, *args, **kwargs):
        return self

    def consume(self):
        pass


@pytest.mark.parametrize("kind", ["memory", "sqlite", "postgres", "neo4j"])
def test_context_persists_with_own_cas_without_invalidating_application(
    kind, tmp_path, postgres_adapter
):
    store = {
        "memory": lambda: MemoryProjectStore(),
        "sqlite": lambda: SqliteProjectStore(tmp_path / "private-context.sqlite"),
        "postgres": lambda: postgres_adapter[1],
        "neo4j": lambda: Neo4jProjectStore(Documents()),
    }[kind]()
    first = store.create("owner", blank_definition())
    candidate = first.model_copy(
        deep=True, update={"assistant_context": StudioTask(selected="shipment")}
    )
    candidate.metadata.name = "Unrelated content must not be changed by a context write"
    saved = store.update("owner", first.id, first.revision, candidate, "assistant:context", "owner")
    assert saved.revision == first.revision
    assert saved.metadata.name == first.metadata.name
    assert saved.assistant_context.version == 1
    assert store.current("owner", first.id).assistant_context.selected == "shipment"
    assert len(store.history("owner", first.id)) == 1
    assert store.audit_trail("owner", first.id)[0]["operation"] == "create"
    with pytest.raises(RevisionConflict):
        store.update("owner", first.id, first.revision, candidate, "assistant:context", "owner")
    change = saved.model_copy(deep=True)
    change.metadata.name = "An actual application change"
    revised = store.update("owner", first.id, saved.revision, change, "update", "owner")
    assert revised.revision == first.revision + 1
    assert revised.assistant_context.version == 1
    context = revised.model_copy(deep=True)
    context.assistant_context.selected = "carrier"
    completed = store.update(
        "owner", first.id, revised.revision, context, "assistant:context", "owner"
    )
    assert completed.revision == revised.revision and completed.assistant_context.version == 2
    assert len(store.history("owner", first.id)) == 2
