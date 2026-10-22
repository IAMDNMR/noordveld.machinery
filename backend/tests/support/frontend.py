"""A labelled source artifact for tests of stage/auth flows, never a model or network call."""

from hashlib import sha256
import json

from app.design_studio.frontend_generation import input_digest
from app.schemas.generated_frontend import GeneratedFrontend


def artifact_for(definition):
    files = {
        "src/App.tsx": "export default function App(){return <main>Isolated fixture</main>}",
        "src/styles.css": "body{margin:0}",
    }
    return GeneratedFrontend(
        design_summary="Isolated frontend fixture for authorization and sequential review tests.",
        pages=[
            {
                "id": "tasks",
                "title": "Tasks",
                "purpose": "Test process bindings",
                "step_ids": [
                    f"{w.id}/{s.id}" for w in definition.workflow_definitions for s in w.states
                ],
                "entity_ids": [e.id for e in definition.business.entities],
            }
        ],
        files=files,
        input_sha256=input_digest(definition),
        source_sha256=sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
        provider="isolated-fixture",
        generated_at="2026-10-21T00:00:00+00:00",
        bundle_js="/* isolated test fixture, not a certified UI */",
        bundle_css="body{margin:0}",
        checks=["Isolated fixture"],
        sdk_source="// isolated fixture",
        entry_source="// isolated fixture",
    )


def enable_frontend_fixture(monkeypatch):
    monkeypatch.setattr("app.api.routes.studio_frontend.get_studio_llm", lambda: object())
    monkeypatch.setattr(
        "app.api.routes.studio_frontend.generate_frontend",
        lambda definition, *_, **__: artifact_for(definition),
    )


def generate_for_review(client, studio_url, state):
    result = client.post(
        studio_url.removesuffix("/studio") + "/frontend/generate",
        json={"expected_revision": state["revision"]},
    )
    assert result.status_code == 200, result.text
    return client.get(studio_url + "/state").json()


def with_frontend(definition):
    """The project plus the labelled fixture interface every application now needs before it can be built.
    The design approval covers the whole definition, so a test approval is re-stamped to cover the added interface."""
    from app.design_studio.approval import digest

    built = definition.model_copy(update={"generated_frontend": artifact_for(definition)})
    built.approvals = [
        item.model_copy(update={"content_sha256": digest(built, item.scope)})
        for item in definition.approvals
    ]
    return built
