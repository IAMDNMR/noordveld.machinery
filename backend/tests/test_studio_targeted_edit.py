"""Retained-source editing: real TypeScript builds and authenticated save semantics."""

# ruff: noqa: F811 -- pytest fixtures intentionally share their parameter names
import json

import pytest

from app.design_studio.frontend_edit import edit_frontend
from app.design_studio.frontend_generation import (
    FrontendGenerationError,
    build_source,
    input_digest,
)
from app.schemas.application_definition import ApplicationDefinition
from app.schemas.generated_frontend import GeneratedFrontend
from tests.test_design_studio_business import pack_design
from tests.test_studio_frontend_generation import proposal
from tests.test_studio_voice_first import API, studio  # noqa: F401


class Editor:
    name = "test-editor"

    def __init__(self, files):
        self.files = files

    def studio_frontend(self, system, prompt):
        self.context = json.loads(prompt)
        return {
            "summary": "Retain the existing application and update its requested heading.",
            "files": self.files,
        }


@pytest.fixture
def retained(monkeypatch):
    definition = ApplicationDefinition.model_validate(pack_design())
    plan = proposal(definition)
    plan["files"]["src/Heading.tsx"] = (
        "export default function Heading(){return <h1>Original heading</h1>}"
    )
    plan["files"]["src/App.tsx"] = (
        "import Heading from './Heading'; export default function App(){return <main><Heading /></main>}"
    )
    output = build_source(plan["files"])
    artifact = GeneratedFrontend(
        **plan,
        input_sha256=input_digest(definition),
        source_sha256="0" * 64,
        provider="test",
        generated_at="2026-10-23T10:00:00Z",
        bundle_js=output["js"],
        bundle_css=output["css"],
        checks=output["checks"],
        sdk_source=output["sdk_source"],
        entry_source=output["entry_source"],
    )
    monkeypatch.setattr(
        "app.design_studio.ui_quality.check_ui", lambda definition: {"findings": []}
    )
    return definition.model_copy(update={"generated_frontend": artifact})


def test_targeted_edit_updates_shared_consumers_and_preserves_unrelated_sources(retained):
    editor = Editor(
        {
            "src/Heading.tsx": "export default function Heading({title}:{title:string}){return <h1>{title}</h1>}",
            "src/App.tsx": "import Heading from './Heading'; export default function App(){return <main><Heading title='Updated queue' /></main>}",
        }
    )
    changed = edit_frontend(retained, editor, "Change the heading to Updated queue")
    assert changed.files["src/styles.css"] == retained.generated_frontend.files["src/styles.css"]
    assert "Updated queue" in changed.files["src/App.tsx"]
    assert changed.bundle_js != retained.generated_frontend.bundle_js
    assert retained.generated_frontend.files["src/Heading.tsx"].startswith(
        "export default function Heading()"
    )
    assert editor.context["files"] == retained.generated_frontend.files
    assert changed.input_sha256 == input_digest(retained)


def test_missing_consumer_change_is_rejected_by_real_typescript_build(retained):
    with pytest.raises(FrontendGenerationError):
        edit_frontend(
            retained,
            Editor(
                {
                    "src/Heading.tsx": "export default function Heading({title}:{title:string}){return <h1>{title}</h1>}"
                }
            ),
            "Add required title",
        )
    with pytest.raises(FrontendGenerationError, match="paths"):
        edit_frontend(retained, Editor({"../secret.ts": "bad"}), "Change heading")


def test_authenticated_edit_saves_only_after_checks_and_exposes_current_preview(
    studio, retained, monkeypatch
):
    client, _, _ = studio
    editor = Editor(
        {"src/Heading.tsx": "export default function Heading(){return <h1>Transport queue</h1>}"}
    )
    monkeypatch.setattr("app.api.routes.studio_frontend.get_studio_llm", lambda: editor)
    monkeypatch.setattr(
        "app.api.routes.studio_frontend.generate_frontend",
        lambda *args, **kwargs: retained.generated_frontend,
    )
    created = client.post(f"{API}/projects", json=retained.model_dump(mode="json")).json()
    root = f"{API}/projects/{created['id']}"
    initial = client.post(
        root + "/frontend/generate", json={"expected_revision": created["revision"]}
    )
    assert initial.status_code == 200, initial.text
    result = client.post(
        root + "/frontend/generate",
        json={
            "expected_revision": initial.json()["definition"]["revision"],
            "design_brief": "Change the heading to Transport queue",
        },
    )
    assert result.status_code == 200, result.text
    saved = result.json()["definition"]
    assert (
        saved["generated_frontend"]["files"]["src/styles.css"]
        == retained.generated_frontend.files["src/styles.css"]
    )
    preview = client.get(root + "/frontend/preview").json()
    assert preview["current"] and preview["revision"] == saved["revision"]
    editor.files = {"src/Heading.tsx": "export default function Heading( { broken"}
    failed = client.post(
        root + "/frontend/generate",
        json={"expected_revision": saved["revision"], "design_brief": "Change the heading again"},
    )
    assert failed.status_code == 422, failed.text
    after = client.get(root + "/studio/state").json()["definition"]
    assert after["generated_frontend"] == saved["generated_frontend"]
