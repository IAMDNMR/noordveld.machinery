"""Runnable target for the existing compiler; templates contain no business-specific identifiers."""

from pathlib import Path
import json

from app.design_studio import approval
from app.design_studio.record_validation import entity_rules

ROOT = Path(__file__).parent


# System font stacks only, as in the template engine (frontend/src/templates/theme.ts): the application loads nothing from the network.
FONTS = {
    "grotesk": "'Segoe UI Variable Display','Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif",
    "humanist": "'Segoe UI',Candara,'Gill Sans','Trebuchet MS',sans-serif",
    "serif": "Georgia,'Iowan Old Style','Palatino Linotype','Times New Roman',serif",
    "mono": "'Cascadia Mono',Consolas,'SF Mono',monospace",
    "system": "system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif",
}
SHADOWS = {
    "none": "none",
    "soft": "0 1px 2px rgba(15,23,42,.06),0 8px 24px rgba(15,23,42,.06)",
    "crisp": "0 1px 0 rgba(15,23,42,.08),0 2px 6px rgba(15,23,42,.08)",
}


def template_tokens(theme) -> dict[str, str]:
    """A template theme as the runtime client's CSS custom properties."""
    c = theme.colors
    return {
        "--accent": c.primary,
        "--accent-ink": c.primary_text,
        "--accent-soft": f"color-mix(in srgb,{c.primary} 12%,{c.surface})",
        "--rail": c.nav_background,
        "--rail-ink": c.nav_text,
        "--rail-muted": f"color-mix(in srgb,{c.nav_text} 62%,{c.nav_background})",
        "--rail-active": f"color-mix(in srgb,{c.nav_text} 14%,{c.nav_background})",
        "--bg": c.background,
        "--surface": c.surface,
        "--ink": c.text,
        "--muted": c.muted,
        "--line": c.border,
        "--danger": c.danger,
        "--danger-soft": f"color-mix(in srgb,{c.danger} 10%,{c.surface})",
        "--warn": c.warning,
        "--warn-soft": f"color-mix(in srgb,{c.warning} 12%,{c.surface})",
        "--done": c.success,
        "--done-soft": f"color-mix(in srgb,{c.success} 12%,{c.surface})",
        "--radius": f"{theme.radius}px",
        "--shadow": SHADOWS[theme.shadow],
        "--font-heading": FONTS[theme.font_heading],
        "--font-body": FONTS[theme.font_body],
    }


def work_areas(definition, provider=None) -> list[dict]:
    """The application's navigation areas, named by the knowledge each process came from ("Warehouse fulfilment", "Stock control").

    A pack's processes form its area. A process drafted for the project joins the area whose records it works with most (by the
    records' pack of origin); one that touches none stays in "Other processes". Nothing is named per application by hand."""
    entity_pack = {e.id: e.origin.pack_id for e in definition.business.entities if e.origin}
    owner, names = {}, {}
    for link in definition.business.knowledge:
        try:
            pack = provider.pack(link.pack_id) if provider is not None else None
        except (KeyError, ValueError, Exception):  # an unavailable pack keeps its processes ungrouped
            pack = None
        if pack is None:
            continue
        names[pack.id] = pack.capability.name if pack.capability else pack.title
        for workflow in pack.workflows:
            owner[workflow.id] = pack.id
    areas: dict[str, dict] = {}
    for workflow in definition.workflow_definitions:
        area = owner.get(workflow.id)
        if area is None:
            touched = [
                entity_pack[entity_id]
                for step in workflow.states
                for entity_id in [*step.reads_entity_ids, *step.writes_entity_ids]
                if entity_pack.get(entity_id) in names
            ]
            area = max(set(touched), key=touched.count) if touched else "other"
        name = names.get(area, "Other processes")
        if area == "other" and is_view(workflow):
            area, name = "views", "Dashboards and views"
        areas.setdefault(area, {"id": area, "name": name, "workflow_ids": []})["workflow_ids"].append(workflow.id)
    return list(areas.values())


def is_view(workflow) -> bool:
    """A dashboard, directory or tracking view: it is looked at, never started, because every step only looks something up or checks it.
    The application client applies the same rule (runtime_app.js isView)."""
    steps = [step for step in workflow.states if step.kind not in ("start", "end")]
    return bool(steps) and all(step.kind in ("search", "review") for step in steps)


def presentation(definition, provider=None) -> dict:
    """What the specification says about the application, plus its visual layer (the person's template, or the closest one chosen automatically). The template decides how the
    application looks (tokens, navigation, density); which screens exist always follows the specification."""
    from app.design_studio.templates import automatic, navigation_for

    brief = definition.business.brief
    result = {
        "description": (definition.metadata.description or brief.goal)[:400],
        "domain": brief.domain_id,
        "areas": work_areas(definition, provider),
    }
    chosen = automatic(definition)
    if chosen:
        result |= {
            "template": {"id": chosen.id, "name": chosen.name, "version": chosen.version},
            "archetype": chosen.profile,
            "tokens": template_tokens(chosen.theme),
            "navigation": navigation_for(definition, chosen.nav_style),
            "density": chosen.theme.density,
            "touch": chosen.theme.touch,
        }
    primary = definition.theme.primary
    channels = [int(primary[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= .04045 else ((value + .055) / 1.055) ** 2.4 for value in channels]
    lightness = sum(value * weight for value, weight in zip(linear, (.2126, .7152, .0722)))
    result["tokens"] = {
        **result.get("tokens", {}),
        "--accent": primary,
        "--accent-ink": "#ffffff" if lightness <= .179 else "#14181a",
        "--accent-soft": f"color-mix(in srgb,{primary} 10%,white)",
        "--rail": f"color-mix(in srgb,{primary} 50%,#101c18)",
        "--rail-ink": "#f1f5f3",
        "--rail-muted": "#c4d1cb",
        "--rail-active": "#ffffff18",
    }
    return result


def client_files() -> dict[str, bytes]:
    """The schema-driven browser client every runtime ships; a model-generated interface, when there is one, replaces it."""
    return {
        "runtime/index.html": (ROOT / "runtime_index.html").read_bytes(),
        "runtime/app.js": (ROOT / "runtime_app.js").read_bytes(),
        "runtime/app.css": (ROOT / "runtime_app.css").read_bytes(),
    }


CATEGORIES = {
    "business_decision": "Unresolved business decision",
    "missing_logic": "Missing executable logic",
    "imported_data": "Missing imported data",
    "unset_status": "Status nothing sets",
    "external_integration": "Unavailable external integration",
}


def unsupported_items(definition) -> list[dict]:
    """Everything the generated application cannot execute, each with one cause. Rules that wait on an open decision are counted
    under the decision's cause, because the missing piece is the business's answer, not code."""
    business = definition.business
    open_decisions = [d for d in business.decisions if d.status != "decided"]
    waiting = {target: d for d in open_decisions for target in (d.affects or [])}
    items = []
    for rule in business.rules:
        if rule.execution is None:
            decision = waiting.get(rule.id)
            items.append(
                {
                    "category": "business_decision" if decision else "missing_logic",
                    "item": rule.id,
                    "text": "This rule is not implemented yet. Process actions that use it remain unavailable.",
                    "detail": (
                        f"Needs a decision: {decision.question}"
                        if decision
                        else rule.description
                    ),
                    "decision": decision.id if decision else None,
                }
            )
    for integration in business.integrations:
        items.append(
            {
                "category": "external_integration",
                "item": integration.id,
                "text": "This connection is not configured. Field mapping, credentials and a provider adapter are needed to exchange live data.",
                "detail": integration.name,
                "decision": None,
            }
        )
    for decision in open_decisions:
        items.append(
            {
                "category": "business_decision",
                "item": decision.id,
                "text": decision.question,
                "detail": decision.question,
                "decision": decision.id,
            }
        )
    for workflow in definition.workflow_definitions:
        for step in workflow.states:
            if step.preconditions or step.postconditions:
                items.append(
                    {
                        "category": "missing_logic",
                        "item": step.id,
                        "text": f"{step.label}: its conditions have not been implemented, so this action is unavailable.",
                        "detail": " ".join(step.preconditions + step.postconditions),
                        "decision": None,
                    }
                )
    for entity in business.entities:
        for attr in entity.attributes:
            if attr.key and attr.value_source == "system_generated":
                continue  # provided: the runtime generates the key when the record is created
            ref = f"{entity.id}.{attr.id}"
            if attr.value_source == "imported":
                items.append(
                    {
                        "category": "imported_data",
                        "item": ref,
                        "text": "This value comes from an external system. The data connection is not configured; only synthetic import data can be used for the demo.",
                        "detail": f"{entity.name} · {attr.name}",
                        "decision": None,
                    }
                )
            elif attr.system_managed or not attr.writable:
                status = attr.id in ("status", "state") or "status" in attr.name.lower()
                items.append(
                    {
                        "category": "unset_status" if status else "missing_logic",
                        "item": ref,
                        "text": "This value should be set automatically, but its calculation or data source is not implemented.",
                        "detail": f"{entity.name} · {attr.name}",
                        "decision": None,
                    }
                )
    return items


BASELINE_CAPABILITIES = (
    "identity_access",
    "audit_history",
    "search_filter",
    "reporting_dashboards",
)


def knowledge_report(definition, provider) -> dict:
    """How the application is organised by the knowledge it was built from, and which capabilities it uses and how far each is provided."""
    packs = []
    for link in definition.business.knowledge:
        try:
            packs.append(provider.pack(link.pack_id))
        except Exception:  # a shared domain pack, or no provider: it still counts as adopted, it just has no catalog description
            continue
    workflow_ids = {w.id for w in definition.workflow_definitions}
    owner_of_workflow = {
        w.id: pack for pack in packs for w in pack.workflows if w.id in workflow_ids
    }
    groups: dict[str, dict] = {}
    for pack in packs:
        groups[pack.id] = {
            "id": pack.id,
            "title": pack.title if pack.layer != "reusable" or pack.workflows else "Shared data",
            "workflow_ids": [],
            "entity_ids": [],
        }
    for workflow in definition.workflow_definitions:
        pack = owner_of_workflow.get(workflow.id)
        if pack is not None:
            groups[pack.id]["workflow_ids"].append(workflow.id)
    for entity in definition.business.entities:
        origin = entity.origin.pack_id if entity.origin else None
        # an entity belongs with the process of its own pack when it has one, otherwise with the pack that defines it
        if origin in groups:
            groups[origin]["entity_ids"].append(entity.id)
    populated = [group for group in groups.values() if group["workflow_ids"] or group["entity_ids"]]
    registry = (
        {item.id: item for item in getattr(provider, "capabilities", lambda: [])()}
        if provider is not None
        else {}
    )
    used: dict[str, set[str]] = {name: set() for name in BASELINE_CAPABILITIES}
    for pack in packs:
        if pack.workflows or pack.layer == "company":
            for capability in pack.uses_capabilities:
                used.setdefault(capability, set()).add(pack.title)
    if any(state.kind == "approval" for w in definition.workflow_definitions for state in w.states):
        used.setdefault("approval_workflow", set())
    if definition.business.integrations:
        used.setdefault("external_integration", set())
    if any(
        attr.key and attr.value_source == "imported"
        for e in definition.business.entities
        for attr in e.attributes
    ):
        used.setdefault("data_import", set())
    capabilities = [
        {
            "id": name,
            "name": registry[name].name,
            "level": registry[name].level,
            "note": registry[name].note,
            "used_by": sorted(users),
        }
        for name, users in sorted(used.items())
        if name in registry
    ]
    return {
        "groups": populated if len(populated) > 1 else [],
        "capabilities": capabilities,
        "packs": [
            {
                "id": p.id,
                "title": p.title,
                "version": p.version,
                "status": p.status,
                "synthetic": p.synthetic,
                "layer": p.layer,
            }
            for p in packs
        ],
    }


def coverage(schema: dict) -> dict:
    """What the generated application really does, from its own schema: rules with executable logic, steps that can complete, what is blocked and why."""
    rules = {r["id"]: r for r in schema["rules"]}
    steps = [
        s
        for w in schema["workflows"]
        for s in w["states"]
        if s["kind"] not in ("start", "end", "branch")
    ]
    runnable = [
        s
        for s in steps
        if all(rules[r].get("execution") for r in s.get("rule_ids", []))
        and not s.get("preconditions")
        and not s.get("postconditions")
    ]
    by_category: dict[str, int] = {}
    for item in schema.get("unsupported_items", []):
        by_category[item["category"]] = by_category.get(item["category"], 0) + 1
    return {
        "entities": len(schema["entities"]),
        "workflows": len(schema["workflows"]),
        "steps": len(steps),
        "steps_runnable": len(runnable),
        "rules": len(rules),
        "rules_with_logic": sum(1 for r in rules.values() if r.get("execution")),
        "rules_assumed": sum(1 for r in rules.values() if r["status"] == "assumption"),
        "unsupported": by_category,
        "open_decisions": len(schema.get("decisions", [])),
    }


def runtime_schema(definition, spec, provider=None):
    knowledge = knowledge_report(definition, provider)
    items = unsupported_items(definition)
    unsupported = [item["text"] for item in items]
    imports = [
        entity.id
        for entity in definition.business.entities
        if any(attr.key and attr.value_source == "imported" for attr in entity.attributes)
    ]
    decisions = [
        {"id": d.id, "question": d.question, "affects": list(d.affects or [])}
        for d in definition.business.decisions
        if d.status != "decided"
    ]
    reference_only = False
    if provider is not None:
        for link in definition.business.knowledge:
            try:
                pack = provider.pack(link.pack_id)
            except (KeyError, ValueError):
                continue
            if pack.usage == "source_reference" and {w.id for w in pack.workflows} & {
                w.id for w in definition.workflow_definitions
            }:
                reference_only = True
    return {
        "runtime_version": "1",
        "name": definition.metadata.name,
        "project_id": definition.id,
        "imports": imports,
        "fingerprint": approval.digest(definition, "design"),
        "approved": approval.is_valid(definition, "design") and not reference_only,
        "source_reference_only": reference_only,
        "entities": [
            {**e.model_dump(mode="json"), "validation": entity_rules(e)}
            for e in definition.business.entities
        ],
        "references": [r.model_dump() for r in spec.references],
        "workflows": [w.model_dump(mode="json") for w in definition.workflow_definitions],
        "roles": [r.model_dump(mode="json") for r in definition.business.roles],
        "integrations": [i.model_dump(mode="json") for i in definition.business.integrations],
        "rules": [r.model_dump(mode="json") for r in definition.business.rules],
        "unsupported": unsupported,
        "unsupported_items": items,
        "decisions": decisions,
        "presentation": presentation(definition, provider),
        **{"groups": knowledge["groups"]},
    }


def runtime_files(definition, spec, provider=None):
    schema = runtime_schema(definition, spec, provider)
    schema["report"] = {**knowledge_report(definition, provider), "coverage": coverage(schema)}
    validation = (ROOT / "record_validation.py").read_text(encoding="utf-8")
    validation = validation.replace(
        "from app.schemas.application_definition import BusinessEntity, EntityAttribute", ""
    )
    files = {
        **client_files(),
        "runtime/server.py": (ROOT / "runtime_server.py").read_bytes(),
        "runtime/integrations.py": (ROOT / "runtime_integrations.py").read_bytes(),
        "runtime/validation.py": validation.encode(),
        "runtime/schema.json": json.dumps(schema, sort_keys=True, indent=2).encode(),
        "runtime/README.md": b"""# Runnable isolated application

This target is an actual local application, separate from the React screen preview.
It uses Python 3.12+ standard-library HTTP and SQLite; no npm install is needed.

Windows PowerShell:
  python runtime/server.py --demo --data-dir "$env:TEMP/studio-runtime-myapp" --port 8091
Unix:
  python runtime/server.py --demo --data-dir /tmp/studio-runtime-myapp --port 8091

Open http://127.0.0.1:8091. Choose an explicitly listed synthetic application identity.
The database persists in the supplied directory across reloads and server restarts.
Only approved specifications can launch. Reusing a database with a changed specification
is refused: migrations must be reviewed, never inferred. This is a local deployment target,
not production identity or hosting. Demo identities are never a production login strategy.

Run independent generated tests: python -m unittest discover -s runtime -p test_runtime.py -v

API: GET /api/application, GET/POST /api/records/{entity}, POST /api/records/{entity}/{id},
GET/POST /api/instances, POST /api/instances/{id}/advance, GET /api/instances/{id}/history.
Record writes submit {data, expected_revision}; process actions submit {expected_revision,links}.
Organization and role come exclusively from the server session. State and rule results cannot
be supplied by the client. Each write is atomic and audited. No deletion endpoint is generated.
Unsupported prose rules fail closed; inspect schema.json unsupported before claiming coverage.
System-generated keys are generated on create. Records of entities listed in schema.json imports come from
another system; no import adapter is connected, so the demo "Data import stand-in" identity enters them by hand
(audited as record.import). It is not a business role and cannot perform process steps.
Assumption bindings stay assumptions: demo execution does not establish company policy.
""",
        "runtime/test_runtime.py": (ROOT / "runtime_test_template.py").read_bytes(),
        "runtime/migrate.py": (ROOT / "runtime_migrate.py").read_bytes(),
        ".github/workflows/quality.yml": (ROOT / "generated_quality.yml").read_bytes(),
    }
    files["runtime/README.md"] += b'''\n## Moving data to another revision\n
Keep the previous package and database for rollback. Stop application writers before promotion.
Preview: python runtime/migrate.py --previous-schema ../previous/runtime/schema.json --source ../previous-data/application.sqlite
Apply compatible changes to a NEW file: append --apply --target ../next-data/application.sqlite --actor operator-name
Only compatible optional-field/data-preserving changes are accepted. Changed rules, permissions,
relationships, workflows, required fields or runtime versions need a reviewed custom migration.
The source is opened read-only, sessions are cleared in the copy, and migration events are recorded.
Validate the new application before redirecting traffic. Roll back using the previous package and
its unchanged database; reconcile any writes made after promotion before switching back.
'''
    return files


def screen_summary(definition) -> dict:
    """The screens the schema-driven client derives: a board per process, a list and form per record type, a work queue per role."""
    return {
        "workflows": len(definition.workflow_definitions),
        "records": len(definition.business.entities),
        "roles": len(definition.business.roles),
        "steps": sum(
            1
            for workflow in definition.workflow_definitions
            for step in workflow.states
            if step.kind not in ("start", "end", "branch")
        ),
    }


def preview_document(definition, provider=None) -> str:
    """The schema-driven client as an opaque, offline Studio preview: same screens as the launched application, records in memory only."""
    import base64
    import html

    from app.design_studio.compiler import references
    from app.design_studio.application_blueprint import preview_role

    app = {
        "name": definition.metadata.name,
        "entities": [
            {**entity.model_dump(mode="json"), "writable": True, "creatable": True}
            for entity in definition.business.entities
        ],
        "references": [reference.model_dump() for reference in references(definition)[0]],
        "workflows": [w.model_dump(mode="json") for w in definition.workflow_definitions],
        "roles": {role.id: role.name for role in definition.business.roles},
        "role_permissions": {role.id: role.permissions for role in definition.business.roles},
        "unsupported": [item["text"] for item in unsupported_items(definition)],
        "presentation": presentation(definition, provider),
    }
    from app.design_studio.runtime_samples import sample_data

    bootstrap = json.dumps(
        {"mode": "preview", "app": app, "preview_role": preview_role(definition), "samples": sample_data(definition)}
    ).replace("<", "\\u003c")
    client = client_files()
    policy = "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; base-uri 'none'; form-action 'none'"
    page = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta http-equiv="Content-Security-Policy" content="{html.escape(policy, quote=True)}">'
        f"<title>{html.escape(definition.metadata.name)}</title>"
        f"<style>{client['runtime/app.css'].decode().replace('<', '\\3c ')}</style></head><body>"
        '<div id="app" aria-live="polite">Loading application…</div>'
        f'<script id="studio-bootstrap" type="application/json">{bootstrap}</script>'
        f"<script>{client['runtime/app.js'].decode().replace('</', '<\\/')}</script></body></html>"
    )
    encoded = base64.b64encode(page.encode()).decode()
    outer = "default-src 'none'; frame-src data:; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; worker-src 'none'; base-uri 'none'; form-action 'none'"
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta http-equiv="Content-Security-Policy" content="{html.escape(outer, quote=True)}">'
        "<style>html,body{margin:0;height:100%}iframe{display:block;border:0;width:100%;height:100%}</style>"
        '</head><body><iframe sandbox="allow-scripts" title="Application workspace" '
        f'src="data:text/html;base64,{encoded}"></iframe>'
        # Relay Studio messages between the workspace and the application; nothing else passes.
        "<script>const f=document.querySelector('iframe');addEventListener('message',e=>{"
        "if(!e.data||typeof e.data.type!=='string'||!e.data.type.startsWith('studio:'))return;"
        "if(e.source===f.contentWindow)parent.postMessage(e.data,'*');else if(e.source===parent)f.contentWindow.postMessage(e.data,'*')})</script>"
        "</body></html>"
    )
