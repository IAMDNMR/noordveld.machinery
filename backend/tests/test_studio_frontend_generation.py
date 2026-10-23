"""Fresh source, isolation, revision protection and exact preview/export parity."""

import json
import base64
import re
from uuid import uuid4
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi.testclient import TestClient

from app.design_studio.frontend_generation import (
    FrontendGenerationError,
    build_source,
    generate_frontend,
    guard_open_business_limits,
    generated_files,
    input_digest,
    is_current,
    preview_document,
    validate_proposal,
)
from app.design_studio.codegen import archive_files
from app.design_studio.discovery import blank_definition
from app.design_studio.local_app import create_local_app
from app.schemas.application_definition import ApplicationDefinition
from app.schemas.generated_frontend import FrontendProposal
from tests.test_design_studio_business import pack_design
from app.design_studio.application_blueprint import application_blueprint


def proposal(definition):
    return {
        "design_summary": "A bespoke purchasing workbench with a focused request queue.",
        "pages": [
            {
                "id": "work",
                "title": "Work",
                "purpose": "Manage the application's process tasks.",
                "step_ids": [
                    f"{w.id}/{s.id}" for w in definition.workflow_definitions for s in w.states
                ],
                "entity_ids": [e.id for e in definition.business.entities],
                "surface_ids": [s["id"] for s in application_blueprint(definition)["surfaces"]],
            }
        ],
        "files": {
            "src/App.tsx": "import {useStudio} from '@studio/sdk'; export default function App(){const {app}=useStudio();return <main><h1>{app.name}</h1></main>}",
            "src/styles.css": "body{margin:0;background:#faf8f2;color:#122a3c}button:focus-visible{outline:2px solid blue}@media(min-width:768px){main{padding:24px}}",
        },
    }


DIRECTION = {
    "identity": {
        "palette": {
            "background": "#faf8f2",
            "surface": "#ffffff",
            "text": "#122a3c",
            "muted": "#4a5a68",
            "accent": "#0b6b4f",
            "accent_text": "#ffffff",
        },
    },
    "navigation": {"pattern": "persistent side rail", "reason": "buyers switch queues all day"},
    "pages": [
        {
            "title": "Work",
            "composition": "queue beside detail",
            "reason": "approvers compare while deciding",
        }
    ],
}


class Model:
    name = "isolated-test-model"

    def __init__(self, definition):
        self.definition = definition
        self.calls = 0

    def studio_frontend(self, system, prompt):
        self.calls += 1
        if "art director" in system:
            return DIRECTION
        assert "sdk_types" in prompt
        return proposal(self.definition)

    def studio_frontend_file(self, system, prompt):
        name = prompt.rsplit("WRITE THIS FILE ONLY: ", 1)[-1].split("\n")[0]
        return proposal(self.definition)["files"][name]


@pytest.fixture(autouse=True)
def model_contract_tests_do_not_launch_browser(monkeypatch):
    from app.design_studio import ui_quality

    monkeypatch.setattr(ui_quality, "check_ui", lambda _definition: {"findings": []})


@pytest.fixture
def built():
    definition = ApplicationDefinition.model_validate(pack_design())
    artifact = generate_frontend(definition, Model(definition), brief=f"test-{uuid4()}")
    return definition.model_copy(update={"generated_frontend": artifact, "frontend_required": True})


def test_real_react_build_typechecks_and_export_uses_exact_bundle(built):
    assert "TypeScript strict check passes" in built.generated_frontend.checks
    files = archive_files(built)
    assert files["runtime/app.js"].decode() == built.generated_frontend.bundle_js
    assert files["runtime/app.css"].decode() == built.generated_frontend.bundle_css
    assert files["src/App.tsx"].decode() == built.generated_frontend.files["src/App.tsx"].replace(
        "@studio/sdk", "./studio-sdk"
    )
    assert files["src/studio-sdk.tsx"].decode() == built.generated_frontend.sdk_source
    manifest = json.loads(files["manifest.json"])
    from hashlib import sha256

    assert manifest["file_sha256"]["runtime/app.js"] == sha256(files["runtime/app.js"]).hexdigest()
    catalogue = json.loads(files["design/artifacts.json"])
    assert (
        next(item for item in catalogue["files"] if item["path"] == "src/App.tsx")["kind"]
        == "executable"
    )


def test_preview_is_opaque_offline_and_staleness_tracks_business_contract(built):
    document = preview_document(built)
    assert "connect-src &#x27;none&#x27;" in document
    assert "Content-Security-Policy" in document
    assert "frame-src data:" in document
    encoded = re.search(r"data:text/html;base64,([^\"]+)", document).group(1)
    assert (
        built.generated_frontend.bundle_js.replace("</", "<\\/")
        in base64.b64decode(encoded).decode()
    )
    assert is_current(built)
    changed = built.model_copy(deep=True)
    changed.business.entities[0].name += " changed"
    assert input_digest(changed) != input_digest(built)
    assert not is_current(changed)
    with pytest.raises(FrontendGenerationError, match="out of date"):
        generated_files(changed)
    revised = built.model_copy(update={"revision": built.revision + 1, "approvals": []})
    assert is_current(revised)


def test_missing_and_unknown_process_bindings_are_rejected(built):
    value = proposal(built)
    value["pages"][0]["step_ids"] = []
    with pytest.raises(FrontendGenerationError, match="omit process"):
        validate_proposal(FrontendProposal.model_validate(value), built)
    # Planning must repair the source responsibilities, never silently add labels.
    assert value["pages"][0]["step_ids"] == []
    value["pages"][0]["entity_ids"] = ["not_in_project"]
    with pytest.raises(FrontendGenerationError, match="[Uu]nknown"):
        validate_proposal(FrontendProposal.model_validate(value), built)
    done = FrontendProposal.model_validate(proposal(built))
    done.pages[0].step_ids = done.pages[0].step_ids[:3]
    with pytest.raises(FrontendGenerationError, match="omit process"):
        validate_proposal(done, built, complete=True)


def test_api_saves_history_and_refuses_client_bundle_replacement(tmp_path, monkeypatch, built):
    monkeypatch.setenv("DESIGN_KNOWLEDGE_SOURCE", "local")
    monkeypatch.setenv("DESIGN_STUDIO_LOCAL_DEV", "1")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.setattr("app.api.routes.studio_frontend.get_studio_llm", lambda: Model(built))
    monkeypatch.setattr(
        "app.api.routes.studio_frontend.generate_frontend",
        lambda *args, **kwargs: built.generated_frontend,
    )
    with (
        TemporaryDirectory(prefix="noordveld-studio-") as directory,
        TestClient(create_local_app(Path(directory) / "studio.sqlite")) as client,
    ):
        client.post("/api/v1/auth/login", json={"user_id": "studio-alice"})
        created = client.post("/api/v1/design-studio/projects", json=built.model_dump(mode="json"))
        assert created.status_code == 200, created.text
        first = created.json()
        assert "generated_frontend" not in first
        assert first["frontend_required"] is True
        url = f"/api/v1/design-studio/projects/{first['id']}"
        def fail_plan(*args, **kwargs):
            raise FrontendGenerationError('Pages omit application surfaces: record:ent_order:detail')
        monkeypatch.setattr('app.api.routes.studio_frontend.generate_frontend', fail_plan)
        failed = client.post(url + '/frontend/generate', json={'expected_revision': first['revision']})
        assert failed.status_code == 422
        failure = client.get(url + '/frontend/progress').json()
        assert failure['progress'] is None and failure['result']['status'] == 'failed'
        assert 'omit application surfaces' in failure['result']['diagnostics']
        assert len(client.get(url + '/history').json()) == 1
        monkeypatch.setattr('app.api.routes.studio_frontend.generate_frontend', lambda *args, **kwargs: built.generated_frontend)
        generated = client.post(
            url + "/frontend/generate", json={"expected_revision": first["revision"]}
        )
        assert generated.status_code == 200, generated.text
        saved = generated.json()["definition"]
        assert saved["revision"] == first["revision"] + 1
        assert len(client.get(url + "/history").json()) == 2
        progress = client.get(url + "/frontend/progress").json()
        assert progress['progress'] is None and progress['result'] == {'status': 'saved', 'revision': saved['revision']}
        assert client.get(url + "/frontend/preview").json()["current"]
        blueprint = client.get(url + "/frontend/blueprint")
        assert blueprint.status_code == 200 and blueprint.json()['revision'] == saved['revision']
        assert blueprint.json()['surfaces']
        assert (
            client.post(
                url + "/frontend/generate", json={"expected_revision": first["revision"]}
            ).status_code
            == 409
        )
        saved["generated_frontend"]["bundle_js"] = "malicious replacement"
        edited = client.put(url, json={"expected_revision": saved["revision"], "definition": saved})
        assert edited.status_code == 200, edited.text
        assert (
            edited.json()["generated_frontend"]["bundle_js"] == built.generated_frontend.bundle_js
        )
        client.post("/api/v1/auth/login", json={"user_id": "studio-bob"})
        assert client.get(url + "/frontend/preview").status_code == 200
        assert (
            client.post(
                url + "/frontend/generate", json={"expected_revision": edited.json()["revision"]}
            ).status_code
            == 403
        )
        client.post("/api/v1/auth/login", json={"user_id": "studio-gina"})
        assert client.get(url + "/frontend/blueprint", headers={"X-Org-Id": "org_harbor"}).status_code == 404
        assert (
            client.get(url + "/frontend/preview", headers={"X-Org-Id": "org_harbor"}).status_code
            == 404
        )


def test_new_project_cannot_review_screens_without_model_frontend():
    from app.design_studio import guided

    definition = blank_definition().model_copy(update={"frontend_required": True})
    assert not guided.ready(definition, "screen")


def test_generation_repairs_the_failed_file_instead_of_returning_a_template():
    definition = ApplicationDefinition.model_validate(pack_design())

    class RepairingModel(Model):
        repairs = 0

        def studio_frontend(self, system, prompt):
            if "specific problems in one source file" in system:
                self.repairs += 1
                return {"edits": [{"find": "missingName", "replace": "'Ready'"}]}
            return super().studio_frontend(system, prompt)

        def studio_frontend_file(self, system, prompt):
            if "REPAIR ONLY src/App.tsx" in prompt:
                self.repairs += 1
                return proposal(self.definition)["files"]["src/App.tsx"]
            if "WRITE THIS FILE ONLY: src/App.tsx" in prompt:
                return "export default function App(){return <p>{missingName}</p>}"  # a name that does not exist breaks the app
            return super().studio_frontend_file(system, prompt)

    model = RepairingModel(definition)
    artifact = generate_frontend(definition, model, brief=f"test-{uuid4()}")
    assert model.repairs == 1
    assert "<p>{'Ready'}</p>" in artifact.files["src/App.tsx"]
    assert "TypeScript strict check passes" in artifact.checks


def test_art_direction_must_be_readable_and_the_gate_findings_drive_a_bounded_fix(monkeypatch):
    from app.design_studio import ui_quality
    from app.design_studio.ui_direction import validate_direction

    unreadable = json.loads(json.dumps(DIRECTION))
    unreadable["identity"]["palette"]["text"] = "#f0eee8"
    with pytest.raises(ValueError, match="contrast"):
        validate_direction(unreadable)

    definition = ApplicationDefinition.model_validate(pack_design())
    reports = iter(
        [
            {
                "findings": [
                    {
                        "id": "no-responsive-rules",
                        "severity": "error",
                        "message": "no @media rules",
                        "evidence": {},
                    }
                ]
            },
            {"findings": []},
        ]
    )
    monkeypatch.setattr(ui_quality, "check_ui", lambda _definition: next(reports))

    class FixingModel(Model):
        fixes = 0

        def studio_frontend_file(self, system, prompt):
            if "REPAIR ONLY src/styles.css" in prompt:
                self.fixes += 1
                assert "no @media rules" in prompt
            return super().studio_frontend_file(
                system, prompt.replace("REPAIR ONLY", "WRITE THIS FILE ONLY:")
            )

    model = FixingModel(definition)
    artifact = generate_frontend(definition, model, brief=f"test-{uuid4()}")
    assert model.fixes == 1 and artifact.checks[-1].startswith(
        "UI review at 375, 768 and 1280px: no layout"
    )


def test_builder_errors_become_small_line_patches_instead_of_whole_file_rewrites():
    from app.design_studio.frontend_repair import build_errors, patch_file

    report = "src/Modal.tsx: Use @studio/sdk instead of window [line 3: window.scrollTo(0, 0)]\nsrc/Page.tsx: Unexpected token (9:0)"
    errors = build_errors(report)
    assert errors['src/Modal.tsx'][0]['line'] == 3
    assert errors['src/Modal.tsx'][0]['message'].startswith('Use @studio/sdk instead of window FIX:')
    assert errors['src/Page.tsx'] == [{"line": 9, "message": "Unexpected token"}]

    class Patcher:
        def studio_frontend(self, system, prompt):
            assert "window.scrollTo(0, 0)" in prompt  # the model sees the offending line
            return {"edits": [{"find": "window.scrollTo(0, 0)", "replace": "setTop(true)"}]}

    sources = {"src/Modal.tsx": "a\nb\nwindow.scrollTo(0, 0)\nc"}
    assert patch_file(Patcher(), sources, "src/Modal.tsx", build_errors(report)["src/Modal.tsx"])
    assert sources["src/Modal.tsx"] == "a\nb\nsetTop(true)\nc"


def test_base_layer_carries_the_palette_and_is_never_duplicated():
    from app.design_studio.ui_direction import with_base

    styled = with_base(".queue{display:grid}", DIRECTION)
    assert "--accent:#0b6b4f" in styled and styled.endswith(".queue{display:grid}")
    assert with_base(styled, DIRECTION) == styled, (
        "a file the model rewrote with the base layer in it keeps exactly one"
    )


def test_frontend_uses_saved_domain_knowledge_without_graph_network(monkeypatch):
    from app.design_studio.ui_direction import domain_reference
    from app.schemas.application_definition import KnowledgeLink

    monkeypatch.setenv("DESIGN_KNOWLEDGE_SOURCE", "neo4j")
    definition = ApplicationDefinition.model_validate(pack_design())
    definition.business.knowledge = [KnowledgeLink(pack_id="procurement", pack_version="1.0")]
    context = domain_reference(definition)[0]
    assert context['domain_id'] == definition.business.brief.domain_id
    assert context['adopted_packs'] == [{"pack_id": "procurement", "version": "1.0"}]
    assert context['visual_references']
    assert all('sample' not in resource and 'coverage' not in resource for resource in context['visual_references'])


def test_indexed_jsx_tags_are_rewritten_before_the_build():
    from app.design_studio.frontend_repair import fix_indexed_tags

    source = "const ICONS = { a: () => null }; const role = 'a' as const; const list = [1]\nexport default function App(){return <p><ICONS[role] aria-hidden='true' />{list[0]}</p>}"
    fixed = fix_indexed_tags(source)
    assert (
        "<DynamicIcon icon={ICONS[role]}" in fixed
        and "{list[0]}" in fixed
        and "function DynamicIcon" in fixed
    )
    assert build_source({"src/App.tsx": fixed, "src/styles.css": "p{margin:0}"})["js"]


def test_generated_modal_scroll_lock_does_not_touch_host_document():
    from app.design_studio.frontend_repair import fix_indexed_tags

    source = (
        "document.body.style.overflow = 'hidden';\n"
        "document.documentElement.classList.add('modal-open');\n"
        "const root = document.getElementById('app-root');\n"
        "root?.classList.remove('modal-open');\n"
        "openDialog();\ndocument.body.style.overflow = '';"
    )
    fixed = fix_indexed_tags(source)
    assert "document.body" not in fixed
    assert "openDialog();" in fixed


def test_generated_retry_uses_sdk_refresh():
    from app.design_studio.frontend_repair import fix_indexed_tags

    source = "const { records, error } = useStudio(); return <ErrorState onRetry={() => window.location.reload()} />"
    fixed = fix_indexed_tags(source)
    assert "window" not in fixed
    assert "refresh" in fixed.split("= useStudio()")[0]
    assert "onRetry={() => refresh()}" in fixed


def test_import_errors_with_one_answer_are_wired_and_the_rest_reported():
    from app.design_studio.frontend_imports import wire_imports

    files = {
        "src/ui.tsx": "export function Card(){ return null }\nexport const formatDate = (v: string) => v\n",
        "src/pages/Home.tsx": "import { Card, KPICard } from '../ui'\nexport default function Home(){ return <Card><Wrench />{formatDate('x')}</Card> }\n",
    }
    report = "\n".join(
        [
            "src/pages/Home.tsx(2,51): error TS2304: Cannot find name 'Wrench'.",
            "src/pages/Home.tsx(2,61): error TS2304: Cannot find name 'formatDate'.",
            "src/pages/Home.tsx(1,16): error TS2305: Module '\"../ui\"' has no exported member 'KPICard'.",
        ]
    )
    wired, missing = wire_imports(files, report)
    assert "import { Wrench } from 'lucide-react'" in wired["src/pages/Home.tsx"]
    assert (
        "formatDate" in wired["src/pages/Home.tsx"].splitlines()[1]
        or "formatDate } from '../ui'" in wired["src/pages/Home.tsx"]
    )
    assert missing == {"src/ui.tsx": {"KPICard"}}, (
        "a component nobody wrote is handed back to be written, never stubbed"
    )


def test_builder_rejects_type_errors_and_invented_workflow_instances():
    stylesheet = "main{padding:24px}"
    with pytest.raises(FrontendGenerationError, match="TypeScript check failed"):
        build_source(
            {
                "src/App.tsx": "export default function App(){const id: number = 'opaque-id'; return <main>{id}</main>}",
                "src/styles.css": stylesheet,
            }
        )
    with pytest.raises(FrontendGenerationError, match="empty object cannot act"):
        build_source(
            {
                "src/App.tsx": "import type {Instance} from '@studio/sdk'; export default function App(){const task = {} as Instance; return <main>{task.id}</main>}",
                "src/styles.css": stylesheet,
            }
        )


def test_open_spending_decision_cannot_become_hardcoded_ui_rule():
    from app.schemas.application_definition import BusinessDecision

    definition = ApplicationDefinition.model_validate(pack_design())
    definition.business.decisions.append(
        BusinessDecision(id="dec_limit", question="What spending limit requires approval?")
    )
    with pytest.raises(
        FrontendGenerationError, match="src/pages/Dashboard.tsx.*Unresolved business limit"
    ):
        guard_open_business_limits(
            definition,
            {
                "src/pages/Dashboard.tsx": "const badge = Number(request.estimated_cost) > 5000 ? 'approved' : 'pending'"
            },
        )
    guard_open_business_limits(
        definition,
        {
            "src/pages/Dashboard.tsx": "const label = 'Spending approval is awaiting policy confirmation'"
        },
    )
    guard_open_business_limits(
        definition,
        {
            "src/pages/Budgets.tsx": "const full = percentUsed >= 100 ? 'full budget' : 'budget available'"
        },
    )
    with pytest.raises(FrontendGenerationError, match="Unresolved business limit"):
        guard_open_business_limits(
            definition, {"src/App.tsx": "const label = 'policy limit: 100%'"}
        )


@pytest.mark.parametrize(
    "source,message",
    [
        (
            "// @ts-nocheck\nexport default function App(){return <p>Request</p>}",
            "TypeScript errors must be fixed",
        ),
        ("export default function App(){return <input onChange={event => {}}/>}", "empty handler"),
        (
            "import {useStudio} from '@studio/sdk'; export default function App(){const sdk=useStudio();return <button onClick={()=>sdk.advanceWorkflow('id',1,{'request.decision':'APPROVED'})}>Approve</button>}",
            "Workflow links contain entity IDs",
        ),
        (
            "import {useStudio} from '@studio/sdk'; export default function App(){const sdk=useStudio();return <p>{(sdk.app as any).records}</p>}",
            "casting to any",
        ),
    ],
)
def test_builder_rejects_nonfunctional_controls_and_wrong_workflow_payloads(source, message):
    with pytest.raises(FrontendGenerationError, match=message):
        build_source({"src/App.tsx": source, "src/styles.css": "body{margin:0}"})
