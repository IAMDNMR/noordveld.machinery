"""Domain-to-application compiler.

    approved domain packs + project revision
      → resolve      DomainResolution        which pack versions the project's adopted items came from, overrides,
                                             unresolved dependencies, incompatible mixes, open decisions
      → specify      ApplicationSpecification  references, collections, operations and permissions derived from the
                                             project's entities, relationships, process and roles
      → plan         GenerationPlan          every file to be generated, its kind and its sources; blocked with reasons
      → generate     files                   the existing artifact generator plus relationship-aware artifacts
      → check        checks                  static checks of the generated files (no generated code is executed)

Every stage is deterministic: the same project revision, pack versions and compiler version give byte-identical output.
Nothing here invents a rule, picks a winner between conflicting definitions or changes shared domain knowledge.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.design_studio import approval
from app.design_studio.artifacts import ARTIFACT_GENERATOR_VERSION
from app.design_studio.codegen import GENERATOR_VERSION, archive_files
from app.design_studio.completeness import analyze
from app.design_studio.knowledge.provider import KnowledgeProvider
from app.design_studio.process import needs_screen, outgoing, steps
from app.domain_knowledge.adoption import overrides as pack_overrides
from app.domain_knowledge.models import DomainPack
from app.domain_knowledge.store import DomainStore, VersionMissing, active
from app.domain_knowledge.traversal import KnowledgeGraph
from app.schemas.application_definition import ApplicationDefinition, BusinessEntity

COMPILER_VERSION = "2"
OWNED_PREFIXES = ("src/generated/", "schemas/", "api/", "design/", "runtime/", "integrations/")


class Typed(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Issue(Typed):
    code: str
    severity: Literal["error", "warning", "info"]
    item: str
    message: str
    remediation: str


class PackUse(Typed):
    pack_id: str
    version: str
    status: str
    active_version: str | None
    content_sha256: str | None
    entities: list[str]


class PackRef(Typed):
    """What the specification records about a pack: immutable facts only (no lifecycle status, no active version)."""

    pack_id: str
    version: str
    content_sha256: str | None
    entities: list[str]


class AdoptedItem(Typed):
    entity_id: str
    pack_id: str
    pack_version: str
    item_id: str
    state: str
    overridden_fields: list[str]


class DomainResolution(Typed):
    packs: list[PackUse]
    adopted: list[AdoptedItem]
    issues: list[Issue]
    unresolved_decisions: list[dict]


class Reference(Typed):
    relationship_id: str
    source: str
    target: str
    cardinality: str
    required: bool
    # The record field that carries the reference: a declared foreign-key attribute, or a link field named after the
    # relationship when the source declares no such attribute (supplied on create, not stored as an attribute).
    field: str
    target_key: str | None
    enforcement: Literal["foreign_key", "link"]


class Collection(Typed):
    entity: str
    lists: str
    via: str
    relationship_id: str
    inverse: bool


class Operation(Typed):
    id: str
    workflow_id: str
    step_id: str
    kind: Literal["read", "write"]
    entity: str
    permission: str | None
    roles: list[str]
    requirement_ids: list[str]
    rule_ids: list[str]
    next_steps: list[str]


class ApplicationSpecification(Typed):
    spec_version: Literal[1] = 1
    compiler_version: str
    project_id: str
    project_revision: int
    design_sha256: str
    approval: dict[str, str]
    domain_packs: list[PackRef]
    entities: list[dict]
    references: list[Reference]
    collections: list[Collection]
    operations: list[Operation]
    rules: list[dict]
    roles: list[dict]
    unresolved_decisions: list[dict]


class PlannedFile(Typed):
    path: str
    kind: str
    sources: list[str]


class GenerationPlan(Typed):
    blocked: bool
    reasons: list[str]
    files: list[PlannedFile]


def _issue(code: str, severity: str, item: str, message: str, remediation: str) -> Issue:
    return Issue(code=code, severity=severity, item=item, message=message, remediation=remediation)


# ── Stage 1: resolve ──


def resolve(definition: ApplicationDefinition, store: DomainStore) -> DomainResolution:
    by_pack: dict[str, dict[str, list[str]]] = {}
    for entity in definition.business.entities:
        if entity.origin is not None:
            by_pack.setdefault(entity.origin.pack_id, {}).setdefault(
                entity.origin.pack_version, []
            ).append(entity.id)
    current = {pack.id: pack for pack in active(store)}
    known = {(meta["pack_id"], meta["version"]): meta for meta in store.versions()}
    packs, adopted, issues, decisions = [], [], [], []
    for pack_id, versions in sorted(by_pack.items()):
        if (pack_id, next(iter(versions))) not in known and pack_id not in current:
            continue  # a Design Studio reference pack, not a shared domain pack; completeness reports its staleness
        if len(versions) > 1:
            issues.append(
                _issue(
                    "MIXED_PACK_VERSIONS",
                    "error",
                    pack_id,
                    f"Entities come from {pack_id} versions {', '.join(sorted(versions))}.",
                    "Re-adopt them from one version so their relationships and rules agree.",
                )
            )
        for version, entity_ids in sorted(versions.items()):
            meta = known.get((pack_id, version))
            active_version = current[pack_id].version if pack_id in current else None
            packs.append(
                PackUse(
                    pack_id=pack_id,
                    version=version,
                    status=meta["status"] if meta else "missing",
                    active_version=active_version,
                    content_sha256=meta["content_sha256"] if meta else None,
                    entities=sorted(entity_ids),
                )
            )
            if meta is None or meta["status"] not in ("approved", "deprecated"):
                issues.append(
                    _issue(
                        "PACK_VERSION_UNAPPROVED",
                        "error",
                        f"{pack_id}@{version}",
                        f"{pack_id} {version} is {meta['status'] if meta else 'not in the domain store'}.",
                        "Adopt from an approved version.",
                    )
                )
                continue
            try:
                pack = store.get(pack_id, version)
            except VersionMissing:
                continue
            if meta["status"] == "deprecated":
                issues.append(
                    _issue(
                        "PACK_VERSION_DEPRECATED",
                        "warning",
                        f"{pack_id}@{version}",
                        f"{pack_id} {version} is deprecated; {active_version} is active.",
                        "Review the version comparison and re-adopt when ready.",
                    )
                )
            elif active_version != version:
                issues.append(
                    _issue(
                        "PACK_NEWER_VERSION",
                        "info",
                        f"{pack_id}@{version}",
                        f"{pack_id} {active_version} is active; the project uses {version}.",
                        "Nothing changes until you re-adopt.",
                    )
                )
            drift = {item["entity_id"]: item for item in pack_overrides(definition, pack)}
            for entity in sorted(
                (
                    e
                    for e in definition.business.entities
                    if e.origin and e.origin.pack_id == pack_id and e.origin.pack_version == version
                ),
                key=lambda e: e.id,
            ):
                found = drift.get(entity.id)
                adopted.append(
                    AdoptedItem(
                        entity_id=entity.id,
                        pack_id=pack_id,
                        pack_version=version,
                        item_id=entity.origin.item_id,
                        state="same" if found is None else found["state"],
                        overridden_fields=[] if found is None else found["fields"],
                    )
                )
            issues.extend(_dependencies(definition, pack, set(entity_ids)))
            used = {
                e.origin.item_id
                for e in definition.business.entities
                if e.origin and e.origin.pack_id == pack_id
            }
            processes = {p.id for p in pack.processes if used & set(p.entity_ids)}
            for decision in pack.decisions:
                if decision.status == "open" and (processes | used) & set(decision.affects):
                    decisions.append(
                        {
                            "pack_id": pack_id,
                            "id": decision.id,
                            "question": decision.question,
                            "affects": decision.affects,
                        }
                    )
    return DomainResolution(
        packs=packs,
        adopted=adopted,
        issues=sorted(issues, key=lambda i: (i.severity, i.code, i.item)),
        unresolved_decisions=decisions,
    )


def _dependencies(
    definition: ApplicationDefinition, pack: DomainPack, project_entities: set[str]
) -> list[Issue]:
    adopted = {
        e.origin.item_id: e.id
        for e in definition.business.entities
        if e.origin and e.origin.pack_id == pack.id
    }
    issues = []
    for rel in pack.relationships:
        if rel.source_id in adopted and rel.required and rel.target_id not in adopted:
            issues.append(
                _issue(
                    "UNRESOLVED_DEPENDENCY",
                    "error",
                    f"{adopted[rel.source_id]}/{rel.id}",
                    f"{adopted[rel.source_id]} requires {rel.target_id} ({rel.type}), which the project does not include.",
                    f"Adopt {rel.target_id}, or remove {adopted[rel.source_id]}. The compiler does not add it for you.",
                )
            )
    return issues


# ── Stage 2: specify ──


def _key(entity: BusinessEntity) -> str | None:
    keys = [attribute.id for attribute in entity.attributes if attribute.key]
    return keys[0] if len(keys) == 1 else None


def references(definition: ApplicationDefinition) -> tuple[list[Reference], list[Collection]]:
    """Relationship semantics → behaviour. A to-one relationship binds to a foreign-key attribute only when the source
    declares a non-key attribute named like the target's key; otherwise the reference is a link field named after the
    relationship. Only to-one relationships carry a reference; to-many ones become collection views."""
    entities = {entity.id: entity for entity in definition.business.entities}
    refs, collections = [], []
    for entity in definition.business.entities:
        attrs = {attribute.id: attribute for attribute in entity.attributes}
        for rel in entity.relationships:
            target = entities.get(rel.target)
            if target is None:
                continue
            if rel.cardinality in ("many_to_one", "one_to_one"):
                key = _key(target)
                candidate = attrs.get(key)
                # Generic document keys such as "number" identify this record.
                # Matching a parent's key name does not make them a foreign key.
                declared = candidate.reference if candidate else None
                explicit = declared and declared.entity_id == target.id and declared.attribute_id == key
                fk = key if candidate and (not candidate.key or explicit) and entity.id != target.id else None
                refs.append(
                    Reference(
                        relationship_id=rel.id,
                        source=entity.id,
                        target=target.id,
                        cardinality=rel.cardinality,
                        required=rel.required,
                        field=fk or rel.id,
                        target_key=key,
                        enforcement="foreign_key" if fk else "link",
                    )
                )
                if rel.cardinality == "many_to_one" and entity.id != target.id:
                    collections.append(
                        Collection(
                            entity=target.id,
                            lists=entity.id,
                            via=fk or rel.id,
                            relationship_id=rel.id,
                            inverse=True,
                        )
                    )
            else:
                collections.append(
                    Collection(
                        entity=entity.id,
                        lists=target.id,
                        via=rel.id,
                        relationship_id=rel.id,
                        inverse=False,
                    )
                )
    return refs, collections


def reference_rules(spec: ApplicationSpecification) -> dict[str, list[dict]]:
    rules: dict[str, list[dict]] = {}
    for ref in spec.references:
        rules.setdefault(ref.source, []).append(
            {
                "field": ref.field,
                "target": ref.target,
                "required": ref.required,
                "relationship_id": ref.relationship_id,
                "enforcement": ref.enforcement,
            }
        )
    return {
        key: sorted(value, key=lambda item: item["field"]) for key, value in sorted(rules.items())
    }


def validate_references(rules: list[dict], record: dict, existing: dict[str, list]) -> list[dict]:
    """Server mirror of the generated validateReferences: required references present; every reference resolves."""
    errors = []
    for rule in rules:
        value = record.get(rule["field"])
        if value is None or value == "":
            if rule["required"]:
                errors.append(
                    {
                        "field": rule["field"],
                        "code": "reference_required",
                        "message": f"{rule['field']} must reference a {rule['target']}.",
                    }
                )
        elif value not in existing.get(rule["target"], []):
            errors.append(
                {
                    "field": rule["field"],
                    "code": "reference_missing",
                    "message": f"No {rule['target']} has {rule['field']} = {value}.",
                }
            )
    return errors


def specify(
    definition: ApplicationDefinition, resolution: DomainResolution
) -> ApplicationSpecification:
    business = definition.business
    refs, collections = references(definition)
    holders: dict[str, list[str]] = {}
    for role in business.roles:
        for permission in role.permissions:
            holders.setdefault(permission, []).append(role.id)
    operations = []
    for workflow, state in steps(definition):
        if not needs_screen(state) and state.kind != "action":
            continue
        roles = (
            sorted(holders.get(state.permission, []))
            if state.permission
            else ([state.role_id] if state.role_id else [])
        )
        nxt = sorted({edge.target for edge in outgoing(workflow, state.id)})
        for kind, ids in (("read", state.reads_entity_ids), ("write", state.writes_entity_ids)):
            for entity_id in ids:
                operations.append(
                    Operation(
                        id=f"{state.id}.{kind}.{entity_id}",
                        workflow_id=workflow.id,
                        step_id=state.id,
                        kind=kind,
                        entity=entity_id,
                        permission=state.permission,
                        roles=roles,
                        requirement_ids=state.requirement_ids,
                        rule_ids=state.rule_ids,
                        next_steps=nxt,
                    )
                )
    entities = [
        {
            "id": e.id,
            "name": e.name,
            "key": _key(e),
            "origin": e.origin.model_dump() if e.origin else None,
            "attributes": [
                {
                    "id": a.id,
                    "type": a.type,
                    "required": a.required,
                    "system_managed": a.system_managed or not a.writable,
                }
                for a in e.attributes
            ],
        }
        for e in business.entities
    ]
    return ApplicationSpecification(
        compiler_version=COMPILER_VERSION,
        project_id=definition.id,
        project_revision=definition.revision,
        design_sha256=approval.digest(definition, "design"),
        approval={scope: state["state"] for scope, state in approval.status(definition).items()},
        domain_packs=[
            PackRef(
                pack_id=p.pack_id,
                version=p.version,
                content_sha256=p.content_sha256,
                entities=p.entities,
            )
            for p in resolution.packs
        ],
        entities=entities,
        references=refs,
        collections=collections,
        operations=operations,
        rules=[
            {
                "id": r.id,
                "status": r.status,
                "type": r.type,
                "outcomes": r.outcomes,
                "origin": r.origin.model_dump() if r.origin else None,
            }
            for r in business.rules
        ],
        roles=[{"id": r.id, "permissions": r.permissions} for r in business.roles],
        unresolved_decisions=resolution.unresolved_decisions,
    )


# ── Stages 3–5: plan, generate, check ──


def _json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


RELATIONSHIPS_TS = """export type ReferenceRule = { field: string; target: string; required: boolean; relationship_id: string; enforcement: 'foreign_key' | 'link' }
export type ReferenceError = { field: string; code: 'reference_required' | 'reference_missing'; message: string }

/** Foreign-key references per entity, compiled from the specification's relationships. */
export const REFERENCES: Record<string, ReferenceRule[]> = __RULES__

/** Required references must be present; every reference must resolve to an existing record (`exists` is supplied by the caller). */
export function validateReferences(entity: string, record: Record<string, unknown>, exists: (target: string, id: unknown) => boolean): ReferenceError[] {
  const errors: ReferenceError[] = []
  for (const rule of REFERENCES[entity] ?? []) {
    const value = record[rule.field]
    if (value === undefined || value === null || value === '') {
      if (rule.required) errors.push({ field: rule.field, code: 'reference_required', message: `${rule.field} must reference a ${rule.target}.` })
    } else if (!exists(rule.target, value)) errors.push({ field: rule.field, code: 'reference_missing', message: `No ${rule.target} has ${rule.field} = ${String(value)}.` })
  }
  return errors
}
"""
RELATIONSHIPS_TEST_TS = """import { describe, expect, it } from 'vitest'
import { validateReferences } from './relationships'

// Expected results were computed by the Design Studio server's reference validation.
const CASES: { entity: string; description: string; record: Record<string, unknown>; existing: Record<string, unknown[]>; expected: string[] }[] = __CASES__

describe('generated reference validation agrees with the server', () => {
  for (const item of CASES) it(`${item.entity}: ${item.description}`, () => {
    const exists = (target: string, id: unknown) => (item.existing[target] ?? []).includes(id)
    expect(validateReferences(item.entity, item.record, exists).map(error => `${error.field}:${error.code}`)).toEqual(item.expected)
  })
})
"""


def reference_cases(spec: ApplicationSpecification) -> list[dict]:
    cases = []
    for entity, rules in reference_rules(spec).items():
        valid = {rule["field"]: f"{rule['target']}-1" for rule in rules}
        existing = {rule["target"]: [f"{rule['target']}-1"] for rule in rules}

        def case(description: str, record: dict):
            cases.append(
                {
                    "entity": entity,
                    "description": description,
                    "record": record,
                    "existing": existing,
                    "expected": [
                        f"{e['field']}:{e['code']}"
                        for e in validate_references(rules, record, existing)
                    ],
                }
            )

        case("all references resolve", valid)
        for rule in rules:
            case(f"{rule['field']} must exist", {**valid, rule["field"]: "missing-id"})
            if rule["required"]:
                case(
                    f"{rule['field']} is required",
                    {k: v for k, v in valid.items() if k != rule["field"]},
                )
    return cases


def forms(definition: ApplicationDefinition, spec: ApplicationSpecification) -> dict:
    refs = {(ref.source, ref.field): ref for ref in spec.references}
    result = {}
    for entity in definition.business.entities:
        fields, readonly = [], []
        for attribute in entity.attributes:
            ref = refs.get((entity.id, attribute.id))
            if attribute.system_managed or not attribute.writable:
                readonly.append(
                    {
                        "attribute": attribute.id,
                        "value_source": attribute.value_source,
                        "reference": ref.target if ref else None,
                    }
                )
            else:
                fields.append(
                    {
                        "attribute": attribute.id,
                        "control": "reference_select" if ref else "input",
                        "required": attribute.required or bool(ref and ref.required),
                        "reference": ref.target if ref else None,
                    }
                )
        result[entity.id] = {
            "create": {
                "fields": fields
                + [
                    {
                        "attribute": r.field,
                        "control": "reference_select",
                        "required": r.required,
                        "reference": r.target,
                        "link": True,
                    }
                    for r in spec.references
                    if r.source == entity.id and r.enforcement == "link"
                ],
                "read_only": readonly,
            },
            "detail": {
                "collections": [c.model_dump() for c in spec.collections if c.entity == entity.id]
            },
            "editable": bool(fields),
        }
    return {
        "forms": result,
        "note": "Generated from attribute metadata and relationships. Read-only values are never inputs.",
    }


def _sources_for(
    path: str, definition: ApplicationDefinition, spec: ApplicationSpecification
) -> list[str]:
    if path.startswith("integrations/"):
        return [f"integration:{item.id}" for item in definition.business.integrations] or [
            "specification"
        ]
    if path.startswith("runtime/"):
        return sorted(
            {f"requirement:{r.id}" for r in definition.business.requirements}
            | {f"step:{w.id}/{s.id}" for w, s in steps(definition)}
            | {f"entity:{e.id}" for e in definition.business.entities}
            | {f"rule:{r.id}" for r in definition.business.rules}
        ) or ["specification"]
    entity_ids = [e.id for e in definition.business.entities]
    if path.startswith("schemas/"):
        entity = path.removeprefix("schemas/").removesuffix(".schema.json")
        origin = next(
            (e.origin for e in definition.business.entities if e.id == entity and e.origin), None
        )
        return [f"entity:{entity}"] + (
            [f"domain:{origin.pack_id}@{origin.pack_version}/{origin.item_id}"] if origin else []
        )
    if path in ("api/openapi.json", "design/operations.json"):
        return sorted(
            {f"step:{op.workflow_id}/{op.step_id}" for op in spec.operations}
            | {f"step:{wf.id}/{s.id}" for wf, s in steps(definition) if needs_screen(s)}
        ) or ["specification"]
    if path in (
        "src/generated/relationships.ts",
        "src/generated/relationships.test.ts",
        "design/relationships.json",
    ):
        return sorted(f"relationship:{r.source}/{r.relationship_id}" for r in spec.references) or [
            "specification"
        ]
    if path in (
        "src/generated/models.ts",
        "src/generated/validation.ts",
        "src/generated/validation.test.ts",
        "design/forms.json",
        "design/entities.json",
    ):
        return [f"entity:{entity_id}" for entity_id in entity_ids] or ["specification"]
    if path in ("design/permissions.json",):
        return [f"role:{role.id}" for role in definition.business.roles] or ["specification"]
    if path == "design/domain-provenance.json":
        return [f"domain:{p.pack_id}@{p.version}" for p in spec.domain_packs] or ["specification"]
    return ["specification"]


def plan(
    definition: ApplicationDefinition,
    resolution: DomainResolution,
    spec: ApplicationSpecification,
    files: dict[str, bytes],
    analysis: dict,
) -> GenerationPlan:
    from app.design_studio.artifacts import catalogue

    reasons = [
        f"{issue.code}: {issue.message}" for issue in resolution.issues if issue.severity == "error"
    ]
    if analysis["blocking"]:
        reasons.append(
            f"{analysis['counts']['error']} blocking design finding(s); see the Checks tab."
        )
    if not approval.is_valid(definition, "design"):
        reasons.append(
            "The current revision's design is not approved; generated files are a preview until it is."
        )
    from app.design_studio.frontend_generation import is_current

    # Every application ships the screens derived from its process and data model; a custom interface replaces them only while it is current.
    if definition.generated_frontend and not is_current(definition):
        reasons.append("The custom interface no longer matches the process and data model. Regenerate it in Screens & UI before building the application.")
    kinds = {entry["path"]: entry["kind"] for entry in catalogue(list(files))["files"]}
    planned = [
        PlannedFile(
            path=path,
            kind=kinds.get(path, "manifest"),
            sources=_sources_for(path, definition, spec),
        )
        for path in sorted(files)
    ]
    return GenerationPlan(blocked=bool(reasons), reasons=reasons, files=planned)


def generate(
    definition: ApplicationDefinition,
    provider: KnowledgeProvider | None,
    resolution: DomainResolution,
    spec: ApplicationSpecification,
) -> dict[str, bytes]:
    from app.design_studio.runtime_generation import runtime_files

    extra = {
        "src/generated/relationships.ts": (
            RELATIONSHIPS_TS.replace(
                "__RULES__", json.dumps(reference_rules(spec), sort_keys=True, indent=2)
            )
        ).encode("utf-8"),
        "src/generated/relationships.test.ts": RELATIONSHIPS_TEST_TS.replace(
            "__CASES__", json.dumps(reference_cases(spec), sort_keys=True, indent=2)
        ).encode("utf-8"),
        "design/relationships.json": _json(
            {
                "references": [r.model_dump() for r in spec.references],
                "collections": [c.model_dump() for c in spec.collections],
            }
        ),
        "design/forms.json": _json(forms(definition, spec)),
        "design/operations.json": _json(
            {
                "operations": [o.model_dump() for o in spec.operations],
                "note": "These are process-derived operation contracts. The runtime/ target implements record and workflow routes with server permission checks; prose-only rules fail closed.",
            }
        ),
        # Only immutable facts: a pack's lifecycle status and which version is active change without the project changing,
        # and generated files must be a pure function of the project revision and the versions it adopted.
        "design/domain-provenance.json": _json(
            {
                "domain_packs": [
                    {
                        "pack_id": p.pack_id,
                        "version": p.version,
                        "content_sha256": p.content_sha256,
                        "entities": p.entities,
                    }
                    for p in resolution.packs
                ],
                "adopted": [
                    {
                        "entity_id": a.entity_id,
                        "pack_id": a.pack_id,
                        "pack_version": a.pack_version,
                        "item_id": a.item_id,
                    }
                    for a in resolution.adopted
                ],
                "unresolved_decisions": resolution.unresolved_decisions,
            }
        ),
        "design/specification.json": _json(spec.model_dump(mode="json")),
    }
    links: dict[str, list[dict]] = {}
    for ref in spec.references:
        if ref.enforcement == "link":
            links.setdefault(ref.source, []).append(
                {"field": ref.field, "target": ref.target, "required": ref.required}
            )
    extra.update(runtime_files(definition, spec, provider))
    from app.design_studio.integration_contracts import files as integration_files

    extra.update(integration_files(definition))
    if provider is not None and definition.business.brief.intake is not None:
        from app.design_studio.knowledge.system_context import discovery_context

        context = discovery_context(provider, definition)
        if context:
            extra["design/business-context.json"] = _json(
                {
                    k: context[k]
                    for k in ("catalog_version", "selected", "systems", "regional_guidance", "note")
                }
            )
    return archive_files(definition, provider, extra, links)


def check(files: dict[str, bytes], spec: ApplicationSpecification, manifest: dict) -> list[dict]:
    """Static checks of generated files. Nothing generated is executed here; see BUILD.md for the build and tests."""
    results = []

    def record(name: str, ok: bool, detail: str, severity: str = "error"):
        results.append(
            {
                "check": name,
                "status": "pass" if ok else ("fail" if severity == "error" else "warn"),
                "detail": detail,
            }
        )

    bad_json = []
    for path, data in sorted(files.items()):
        if path.endswith(".json"):
            try:
                json.loads(data)
            except ValueError:
                bad_json.append(path)
    record(
        "json_parses",
        not bad_json,
        ", ".join(bad_json) or f"{sum(p.endswith('.json') for p in files)} JSON files parse",
    )
    missing = []
    if "api/openapi.json" in files:
        api = json.loads(files["api/openapi.json"])
        refs = set()

        def walk(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "$ref" and isinstance(value, str):
                        refs.add(value)
                    else:
                        walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(api)
        for ref in sorted(refs):
            if ref.startswith("#/components/schemas/"):
                if ref.split("/")[-1] not in api["components"]["schemas"]:
                    missing.append(ref)
            elif ref.startswith("../"):
                if ref[3:].split("#")[0] not in files:
                    missing.append(ref)
    record(
        "openapi_refs_resolve",
        not missing,
        ", ".join(missing) or "every $ref resolves to a generated schema",
    )
    unknown = [
        r.relationship_id for r in spec.references if f"schemas/{r.target}.schema.json" not in files
    ]
    record(
        "reference_targets_have_schemas",
        not unknown,
        ", ".join(unknown) or f"{len(spec.references)} reference(s) resolve",
    )
    ungoverned = sorted({o.id for o in spec.operations if o.kind == "write" and not o.permission})
    record(
        "writes_have_permissions",
        not ungoverned,
        ", ".join(ungoverned) or "every write operation names a permission",
        "warning",
    )
    orphan = sorted({o.id for o in spec.operations if o.permission and not o.roles})
    record(
        "permissions_held_by_roles",
        not orphan,
        ", ".join(orphan) or "every required permission is held by a role",
    )
    digest_errors = [
        path
        for path, entry in manifest["files"].items()
        if entry["sha256"] != sha256(files[path]).hexdigest()
    ]
    record(
        "manifest_digests",
        not digest_errors,
        ", ".join(digest_errors) or "every file matches its recorded digest",
    )
    untraced = [path for path, entry in manifest["files"].items() if not entry["sources"]]
    record(
        "files_traced",
        not untraced,
        ", ".join(untraced) or "every generated file names its sources",
    )
    record(
        "generated_code_not_executed",
        True,
        "TypeScript compilation and the generated tests run via BUILD.md, not during compilation",
        "warning",
    )
    if "runtime/schema.json" in files:
        runtime = json.loads(files["runtime/schema.json"])
        import ast

        valid = True
        for name in ("runtime/server.py", "runtime/validation.py", "runtime/test_runtime.py"):
            try:
                ast.parse(files[name])
            except SyntaxError:
                valid = False
        record(
            "runtime_source_parses",
            valid,
            "Python runtime source syntax check; behavior requires the independent runtime tests",
        )
        record(
            "runtime_business_coverage",
            not runtime["unsupported"],
            "; ".join(runtime["unsupported"]) or "All declared rules have executable bindings",
            "warning",
        )
        # Structured issues are authoritative. Explanatory prose may itself contain semicolons.
        results[-1]["items"] = runtime.get("unsupported_items", [])
        # A record that needs another record nobody here can create cannot be created on a fresh database: say so, never discover it at runtime.
        held = {r["id"]: set(r["permissions"]) for r in runtime["roles"]}
        creatable = {
            e
            for w in runtime["workflows"]
            for s in w["states"]
            if s.get("role_id") and s.get("permission") in held.get(s["role_id"], ())
            for e in s.get("writes_entity_ids", [])
        }
        creatable |= {
            e["id"] for e in runtime["entities"] if e.get("owner_role_id")
        }  # an owner role maintains its own entity
        names = {e["id"]: e["name"] for e in runtime["entities"]}
        # Records that originate in another system are entered by the import stand-in until an adapter is connected.
        imported = {
            r["target"]
            for r in runtime["references"]
            if r["required"]
            and r["source"] in creatable
            and r["target"] not in creatable
            and r["target"] in runtime.get("imports", [])
        }
        blocked = sorted(
            {
                f"{names.get(r['source'], r['source'])} needs a related {names.get(r['target'], r['target'])} record, which no role in this application creates"
                for r in runtime["references"]
                if r["required"]
                and r["source"] in creatable
                and r["target"] not in creatable | imported
            }
        )
        detail = "every required related record can be created by a role in this application"
        if imported:
            detail += (
                "; "
                + ", ".join(sorted(names.get(e, e) for e in imported))
                + " come from an external system: no import adapter is connected, so the demo import stand-in enters them"
            )
        record("runtime_records_creatable", not blocked, "; ".join(blocked) or detail, "warning")
    return results


def generation_manifest(
    spec: ApplicationSpecification, planned: GenerationPlan, files: dict[str, bytes]
) -> dict:
    return {
        "compiler_version": COMPILER_VERSION,
        "generator_version": GENERATOR_VERSION,
        "artifact_generator_version": ARTIFACT_GENERATOR_VERSION,
        "project_id": spec.project_id,
        "project_revision": spec.project_revision,
        "design_sha256": spec.design_sha256,
        "domain_packs": [
            {"pack_id": p.pack_id, "version": p.version, "content_sha256": p.content_sha256}
            for p in spec.domain_packs
        ],
        "owned_prefixes": list(OWNED_PREFIXES),
        "files": {
            f.path: {
                "sha256": sha256(files[f.path]).hexdigest(),
                "kind": f.kind,
                "owner": "generator",
                "sources": f.sources,
            }
            for f in planned.files
        },
    }


def compile_project(
    definition: ApplicationDefinition, store: DomainStore, provider: KnowledgeProvider | None
) -> dict:
    resolution = resolve(definition, store)
    spec = specify(definition, resolution)
    analysis = analyze(definition, provider, "design")
    files = generate(definition, provider, resolution, spec)
    planned = plan(definition, resolution, spec, files, analysis)
    if provider is not None:
        for link in definition.business.knowledge:
            try:
                pack = provider.pack(link.pack_id)
            except (KeyError, ValueError):
                continue
            if pack.usage == "source_reference" and {w.id for w in pack.workflows} & {
                w.id for w in definition.workflow_definitions
            }:
                planned.blocked = True
                planned.reasons.append(
                    f"{pack.title} is source reference knowledge. Use a reusable blueprint to generate executable workflows."
                )
    manifest = generation_manifest(spec, planned, files)
    files["generation-manifest.json"] = _json(manifest)
    checks = check(files, spec, manifest)
    failed = [item for item in checks if item["status"] == "fail"]
    return {
        "resolution": resolution.model_dump(mode="json"),
        "specification": spec.model_dump(mode="json"),
        "plan": planned.model_dump(mode="json"),
        "checks": checks,
        "status": "blocked" if planned.blocked or failed else "generated",
        "manifest": manifest,
        "files": files,
    }


# ── Safe regeneration ──


def update_plan(
    previous: dict | None, current_sha256: dict[str, str], new_files: dict[str, bytes]
) -> dict:
    """How to apply a new generation to a workspace without destroying user work.

    `previous` is the last generation manifest applied there; `current_sha256` the digests of files now present.
    A generator-owned file is replaced only if it is unchanged since generation; user-edited files are kept and
    reported; files the generator no longer produces are deleted only if unchanged; files the generator never owned
    are never touched.
    """
    owned = (previous or {}).get("files", {})
    result: dict[str, list[str]] = {
        "create": [],
        "update": [],
        "unchanged": [],
        "conflict_user_modified": [],
        "conflict_not_owned": [],
        "delete": [],
        "keep_user_modified": [],
    }
    for path, data in sorted(new_files.items()):
        digest = sha256(data).hexdigest()
        here = current_sha256.get(path)
        if here is None:
            result["create"].append(path)
        elif here == digest:
            result["unchanged"].append(path)
        elif path not in owned:
            result["conflict_not_owned"].append(path)
        elif owned[path]["sha256"] == here:
            result["update"].append(path)
        else:
            result["conflict_user_modified"].append(path)
    for path, entry in sorted(owned.items()):
        if path in new_files or path not in current_sha256:
            continue
        (
            result["delete"]
            if current_sha256[path] == entry["sha256"]
            else result["keep_user_modified"]
        ).append(path)
    result["safe"] = not (result["conflict_user_modified"] or result["conflict_not_owned"])
    return result


# ── Project dependency graph (requirements → steps → operations/screens → files; domain items → project) ──


def project_graph(
    definition: ApplicationDefinition, compiled: dict | None = None
) -> KnowledgeGraph:
    graph = KnowledgeGraph()
    business = definition.business
    for item in business.requirements:
        graph.node(f"requirement:{item.id}", "requirement", item.statement[:80])
    for item in business.roles:
        graph.node(f"role:{item.id}", "role", item.name)
    for item in business.rules:
        graph.node(f"rule:{item.id}", "rule", item.description[:80])
    for entity in business.entities:
        graph.node(f"entity:{entity.id}", "entity", entity.name)
        if entity.origin:
            node = f"domain:{entity.origin.pack_id}@{entity.origin.pack_version}/{entity.origin.item_id}"
            graph.node(node, "domain_item", entity.origin.item_id)
            graph.edge(
                node,
                f"entity:{entity.id}",
                "ADOPTED_AS",
                f"{entity.origin.pack_id} {entity.origin.pack_version} {entity.origin.item_id} was adopted as {entity.id}",
            )
    for workflow, state in steps(definition):
        graph.node(f"step:{workflow.id}/{state.id}", "step", state.label)
    for entity in business.entities:
        for rel in entity.relationships:
            graph.edge(
                f"entity:{entity.id}",
                f"entity:{rel.target}",
                "RELATES",
                f"{entity.id} {rel.name} {rel.target} ({rel.cardinality.replace('_', ' ')})",
            )
    for workflow, state in steps(definition):
        step = f"step:{workflow.id}/{state.id}"
        for ref in state.requirement_ids:
            graph.edge(
                f"requirement:{ref}",
                step,
                "SATISFIED_BY",
                f"requirement {ref} is satisfied by step {state.label}",
            )
        if state.role_id:
            graph.edge(
                f"role:{state.role_id}",
                step,
                "PERFORMS",
                f"role {state.role_id} performs {state.label}"
                + (f" with {state.permission}" if state.permission else ""),
            )
        for ref in state.rule_ids:
            graph.edge(f"rule:{ref}", step, "GOVERNS", f"rule {ref} governs {state.label}")
        for ref in state.reads_entity_ids:
            graph.edge(step, f"entity:{ref}", "READS", f"{state.label} reads {ref}")
        for ref in state.writes_entity_ids:
            graph.edge(step, f"entity:{ref}", "WRITES", f"{state.label} writes {ref}")
        for edge in outgoing(workflow, state.id):
            when = (
                ""
                if edge.condition.kind == "always"
                else f" when {edge.condition.field} {'=' if edge.condition.kind == 'equals' else '≠'} {edge.condition.value}"
            )
            graph.edge(
                step,
                f"step:{workflow.id}/{edge.target}",
                "NEXT",
                f"{state.label} leads to {edge.target}{when}",
            )
            if edge.condition.field and f"rule:{edge.condition.field}" in graph.nodes:
                graph.edge(
                    f"rule:{edge.condition.field}",
                    step,
                    "DECIDES",
                    f"rule {edge.condition.field} decides the path out of {state.label}",
                )
    for screen in definition.screens:
        graph.node(f"screen:{screen.id}", "screen", screen.title)
        if screen.trace and screen.trace.step_id:
            graph.edge(
                f"step:{screen.trace.workflow_id}/{screen.trace.step_id}",
                f"screen:{screen.id}",
                "SHOWN_ON",
                f"{screen.trace.step_id} is shown on screen {screen.title}",
            )
    if compiled is not None:
        for op in compiled["specification"]["operations"]:
            graph.node(f"operation:{op['id']}", "operation", op["id"])
            graph.edge(
                f"step:{op['workflow_id']}/{op['step_id']}",
                f"operation:{op['id']}",
                "EXPOSES",
                f"step {op['step_id']} exposes a {op['kind']} of {op['entity']}",
            )
            graph.edge(
                f"operation:{op['id']}",
                f"entity:{op['entity']}",
                "ON",
                f"operation {op['id']} acts on {op['entity']}",
            )
        for path, entry in compiled["manifest"]["files"].items():
            graph.node(f"file:{path}", "file", path, artifact_kind=entry["kind"])
            for source in entry["sources"]:
                if source.startswith("step:"):
                    for op in compiled["specification"]["operations"]:
                        if source == f"step:{op['workflow_id']}/{op['step_id']}":
                            graph.edge(
                                f"operation:{op['id']}",
                                f"file:{path}",
                                "GENERATED_IN",
                                f"operation {op['id']} is defined in {path}",
                            )
                    graph.edge(
                        source,
                        f"file:{path}",
                        "GENERATED_IN",
                        f"{source.removeprefix('step:')} is generated into {path}",
                    )
                else:
                    graph.edge(
                        source, f"file:{path}", "GENERATED_IN", f"{source} is generated into {path}"
                    )
    return graph
