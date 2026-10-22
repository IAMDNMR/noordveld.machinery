"""Deterministic, review-only source archive from validated definitions.

No build, command, generated code execution, network fetch, or publishing occurs.
"""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from app.design_studio import approval
from app.design_studio.artifacts import (
    ARTIFACT_GENERATOR_VERSION,
    BUILD_GUIDE,
    application_files,
    catalogue,
)
from app.design_studio.completeness import analyze
from app.design_studio.knowledge.provider import KnowledgeProvider
from app.design_studio.process import is_business_aware
from app.design_studio.traceability import report
from app.design_studio.application_blueprint import application_blueprint
from app.schemas.application_definition import ApplicationDefinition

GENERATOR_VERSION = "2"
APP_TEMPLATE_VERSION = "3"
APP_SOURCE = """import React from 'react'
import definition from './definition.json'

// Review-only mockup. This template never calls commerce APIs or executes events.
type Node = { kind: string; id: string; props: Record<string, unknown>; children?: Node[] | null }
function NodeView({ node }: { node: Node }) {
  switch (node.kind) {
    case 'container': return <section><h2>{String(node.props.title)}</h2>{node.children?.map(child => <NodeView key={child.id} node={child} />)}</section>
    case 'text': return <p>{String(node.props.content)}</p>
    case 'field': {
      // Validation metadata is shown, never executed: required fields are marked and carry the required attribute.
      const required = Array.isArray(node.props.validations) && node.props.validations.some(rule => (rule as { kind?: unknown }).kind === 'required')
      return <label>{String(node.props.label)}{required ? ' *' : ''}<input disabled required={required} aria-required={required} placeholder="Mockup only" />{node.props.help_text ? <small>{String(node.props.help_text)}</small> : null}</label>
    }
    case 'table': return <section><h2>{String(node.props.title)}</h2><p>No live data</p></section>
    case 'button': return <button type="button" disabled>{String(node.props.label)}</button>
    default: return null
  }
}
type Workflow = { id: string; name: string; states: { id: string; label: string; kind: string }[]
  transitions: { id: string; source: string; target: string; condition: { kind: string; field: string | null; value: unknown } }[] }
// Workflows are listed for review only; conditions are shown as text and never evaluated.
function WorkflowView({ workflow }: { workflow: Workflow }) {
  return <section><h2>Workflow: {workflow.name}</h2>
    <ol>{workflow.states.map(state => <li key={state.id}>{state.label} ({state.kind})</li>)}</ol>
    <ul>{workflow.transitions.map(edge => <li key={edge.id}>{edge.source} → {edge.target}{edge.condition.kind === 'always' ? '' : ` when ${edge.condition.field} ${edge.condition.kind === 'equals' ? '=' : '≠'} ${String(edge.condition.value)}`}</li>)}</ul>
  </section>
}
export default function App() {
  const workflows = ((definition as { workflow_definitions?: Workflow[] }).workflow_definitions ?? [])
  return <main><p>MOCKUP ONLY — no business actions</p>{definition.screens.map(screen =>
    <section key={screen.id}><h1>{screen.title}</h1>{screen.components.map(node => <NodeView key={node.id} node={node} />)}</section>)}
    {workflows.map(workflow => <WorkflowView key={workflow.id} workflow={workflow} />)}</main>
}
"""
MAIN_SOURCE = """import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'

createRoot(document.getElementById('root')!).render(<App />)
"""
PACKAGE_SOURCE = {
    "name": "noordveld-generated-mockup",
    "private": True,
    "version": "0.0.1",
    "type": "module",
    "scripts": {
        "build": "tsc && vite build",
        "dev": "vite",
        "typecheck": "tsc",
        "test": "vitest run",
    },
    "dependencies": {"react": "19.3.0", "react-dom": "19.3.0"},
    "devDependencies": {
        "typescript": "7.0.2",
        "vite": "8.3.3",
        "vitest": "3.2.7",
        "@types/react": "19.3.0",
        "@types/react-dom": "19.3.0",
    },
}


def _json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2).encode("utf-8")


def design_manifests(
    definition: ApplicationDefinition, provider: KnowledgeProvider | None = None
) -> dict[str, bytes]:
    """Declarative manifests of the business design. Descriptions only: nothing here is executable."""
    raw = definition.model_dump(mode="json")
    business = raw["business"]
    return {
        "design/requirements.json": _json(
            {
                "brief": business["brief"],
                "requirements": business["requirements"],
                "questions": business["questions"],
                "terms": business["terms"],
            }
        ),
        "design/process.json": _json(
            {"workflows": raw["workflows"], "workflow_definitions": raw["workflow_definitions"]}
        ),
        "design/entities.json": _json(
            {"entities": business["entities"], "integrations": business["integrations"]}
        ),
        "design/roles.json": _json(
            {
                "roles": business["roles"],
                "note": "Design-time roles. They do not enforce access in this export.",
            }
        ),
        "design/rules.json": _json(
            {
                "rules": business["rules"],
                "exceptions": business["exceptions"],
                "decisions": business["decisions"],
                "note": "Conditions are documentation and are never evaluated.",
            }
        ),
        "design/screens.json": _json({"screens": raw["screens"], "navigation": raw["navigation"]}),
        "design/traceability.json": _json(report(definition)),
        "design/application-blueprint.json": _json(application_blueprint(definition)),
        "design/validation-report.json": _json(
            {
                "revision": definition.revision,
                "knowledge": business["knowledge"],
                "approval": approval.status(definition),
                "analysis": analyze(definition, provider),
            }
        ),
    }


def archive_files(
    source: ApplicationDefinition,
    provider: KnowledgeProvider | None = None,
    extra_files: dict[str, bytes] | None = None,
    links: dict[str, list[dict]] | None = None,
) -> dict[str, bytes]:
    """Every file of the export, by path. Paths are fixed or built from validated IDs, so no entry can escape the archive."""
    definition = ApplicationDefinition.model_validate(source.model_dump(mode="json"))
    payload = json.dumps(
        definition.model_dump(mode="json"),
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    files = {
        "src/definition.json": payload,
        "src/App.tsx": APP_SOURCE.encode("utf-8"),
        "src/main.tsx": MAIN_SOURCE.encode("utf-8"),
        "index.html": b'<!doctype html><html lang="en"><meta charset="utf-8"><title>Noordveld mockup</title><div id="root"></div><script type="module" src="/src/main.tsx"></script></html>',
        "package.json": json.dumps(PACKAGE_SOURCE, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        ),
        "tsconfig.json": b'{"compilerOptions":{"target":"ES2022","module":"ESNext","moduleResolution":"Bundler","jsx":"react-jsx","strict":true,"resolveJsonModule":true,"esModuleInterop":true,"skipLibCheck":true,"noEmit":true},"include":["src"]}',
        "README.md": b"Review-only generated mockup. Generated source has not been executed or built. No business actions are connected.\n",
    }
    business_aware = is_business_aware(definition)
    if business_aware:
        files.update(design_manifests(definition, provider))
        files.update(application_files(definition, links))
        files.update(extra_files or {})
        files["BUILD.md"] = BUILD_GUIDE.encode("utf-8")
        files["README.md"] += (
            b"\nThe design/ folder holds declarative manifests (requirements, process, entities, roles, rules, screens, traceability, "
            b"validation). src/generated/ holds typed models and record validation with tests; schemas/ and api/ hold contracts. "
            b"No backend API, database migration or integration is generated. See design/artifacts.json and BUILD.md.\n"
        )
        if "runtime/server.py" in files:
            files["README.md"] = (
                b"Generated application with a runnable local target in runtime/. Start with runtime/README.md. The React src/App.tsx remains a design preview; the operational UI is served by runtime/server.py. See runtime/schema.json for unsupported requirements.\n"
            )
            files["BUILD.md"] += (
                b"\n## Runnable local application\n\nThe compiler also generated runtime/. Run its Python server and independent tests as documented in runtime/README.md. It requires no npm packages. The npm commands above concern the separate React design preview and validation library.\n"
            )
        files["design/artifacts.json"] = _json(
            catalogue([*files, "manifest.json", "design/artifacts.json"])
        )
    if definition.generated_frontend:
        from app.design_studio.frontend_generation import generated_files

        files.update(generated_files(definition))
        package = json.loads(files["package.json"])
        package["dependencies"]["lucide-react"] = "1.49.0"
        files["package.json"] = _json(package)
        files["README.md"] = b"Project-specific React application generated by the configured language model. The preview and runtime use the same saved bundle. Start the application using runtime/README.md. Editable React source and transport SDK are in src/. See design/frontend.json for generation provenance and build checks. Backend permissions and workflows remain authoritative.\n"
        files["design/artifacts.json"] = _json(
            catalogue([*files, "manifest.json", "design/artifacts.json"])
        )
    manifest = {
        "schema_version": 3,
        "generator_version": GENERATOR_VERSION,
        "artifact_generator_version": ARTIFACT_GENERATOR_VERSION if business_aware else None,
        "template_versions": {"App.tsx": "model-source-v1" if definition.generated_frontend else APP_TEMPLATE_VERSION},
        "specification_id": definition.id,
        "specification_revision": definition.revision,
        "definition_sha256": sha256(payload).hexdigest(),
        "design_sha256": approval.digest(definition, "design"),
        "approval": {scope: state["state"] for scope, state in approval.status(definition).items()},
        "file_sha256": {name: sha256(data).hexdigest() for name, data in sorted(files.items())},
        "artifacts": sorted(files),
        "validation": "specification validated at export; no build or test execution at export (see BUILD.md)",
    }
    files["manifest.json"] = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return files


def generate_archive(
    source: ApplicationDefinition, provider: KnowledgeProvider | None = None
) -> bytes:
    return zip_files(archive_files(source, provider))


def zip_files(files: dict[str, bytes]) -> bytes:
    """Deterministic ZIP: sorted entries, fixed timestamps and permissions."""
    output = BytesIO()
    with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            info = ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, data)
    return output.getvalue()
