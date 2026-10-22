"""Reference packs, capabilities and company layers -> graph operations -> idempotent, parameterised write plans.

A pack is projected as data, never executed here. The projection is the same whether it later runs against a development graph or the
in-memory double used by the tests, because both consume the same *operations* (node and relationship upserts); Cypher is rendered from them.

Rules the projection follows:
* every node carries scope, version, provenance and status, so shared and company knowledge are separable by query;
* a node's key is `pack|version|item` (versions coexist; re-running a projection changes nothing);
* a reference into another pack (a relationship to a core entity) points at that pack's own node, found through the dependency closure;
* the pack document itself is stored on the DKPackVersion node, so the graph can serve packs without a second source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any

from app.design_studio.knowledge.models import Capability, ReferencePack
from app.knowledge_graph import schema

RULE_PROVENANCE = {
    "business_owner": "user_provided",
    "implemented_code": "verified_source",
    "document": "verified_source",
    "graph_data": "derived",
    "workshop": "user_provided",
    "synthetic_assumption": "assumption",
}


@dataclass(frozen=True)
class NodeOp:
    label: str
    key: str
    props: dict[str, Any]


@dataclass(frozen=True)
class RelOp:
    type: str
    source: tuple[str, str]  # (label, key)
    target: tuple[str, str]
    props: dict[str, Any] = field(default_factory=dict)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def normalize(term: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", term.lower()).strip()


class Projection:
    """The operations that describe a set of packs (and the capability registry) in the graph."""

    def __init__(self, packs: list[ReferencePack], capabilities: list[Capability] | None = None):
        self.packs = {pack.id: pack for pack in packs}
        self.capabilities = capabilities or []
        self.nodes: dict[tuple[str, str], NodeOp] = {}
        self.rels: dict[tuple, RelOp] = {}
        # Where each item lives, so a reference into a dependency resolves to the dependency's own node.
        self.home: dict[str, tuple[str, str, str]] = {}
        for pack in packs:
            for item_id, group in _items(pack):
                self.home.setdefault(item_id, (pack.id, pack.version, group))
        for pack in packs:
            self._pack(pack)
        for capability in self.capabilities:
            self._capability(capability)

    # ── helpers ──
    def key(self, pack: ReferencePack, item_id: str) -> str:
        return f"{pack.id}|{pack.version}|{item_id}"

    def ref(self, pack: ReferencePack, item_id: str, label: str) -> tuple[str, str]:
        """The node an id refers to: this pack's own, or the one that defines it in a dependency."""
        owner = self.home.get(item_id)
        if owner and owner[0] != pack.id and self._reaches(pack, owner[0]):
            return label, f"{owner[0]}|{owner[1]}|{item_id}"
        return label, self.key(pack, item_id)

    def _reaches(self, pack: ReferencePack, other_id: str, seen: set | None = None) -> bool:
        seen = seen if seen is not None else set()
        for dep in pack.depends_on:
            if dep == other_id:
                return True
            if dep in self.packs and dep not in seen:
                seen.add(dep)
                if self._reaches(self.packs[dep], other_id, seen):
                    return True
        return False

    def node(
        self,
        pack: ReferencePack,
        label: str,
        item_id: str,
        name: str,
        provenance: str | None = None,
        **props,
    ) -> tuple[str, str]:
        key = self.key(pack, item_id)
        scope = f"company:{pack.company.id}" if pack.company else schema.SCOPE_SHARED
        base = {
            "dk_key": key,
            "pack_id": pack.id,
            "version": pack.version,
            "item_id": item_id,
            "name": name[:200],
            "scope": scope,
            "status": pack.status,
            "provenance_kind": provenance or pack.provenance.kind,
            "verification": pack.provenance.verification,
        }
        self.nodes[(label, key)] = NodeOp(
            label, key, {**base, **{k: v for k, v in props.items() if v is not None}}
        )
        self.rel("DK_IN_PACK", (label, key), ("DKPackVersion", f"{pack.id}|{pack.version}"))
        return label, key

    def rel(self, kind: str, source: tuple[str, str], target: tuple[str, str], **props):
        if source == target:
            return
        sources, targets, _ = schema.REL_TYPES[kind]
        if source[0] not in sources or target[0] not in targets:
            raise ValueError(f"{kind} cannot connect {source[0]} to {target[0]}")
        identity = (
            kind,
            source,
            target,
            props.get("def_id") or props.get("mode") or props.get("condition_key"),
        )
        self.rels[identity] = RelOp(kind, source, target, props)

    # ── one pack ──
    def _pack(self, pack: ReferencePack):
        scope = f"company:{pack.company.id}" if pack.company else schema.SCOPE_SHARED
        pack_key = f"{pack.id}|{pack.version}"
        document = pack.model_dump_json()
        self.nodes[("DKPackVersion", pack_key)] = NodeOp(
            "DKPackVersion",
            pack_key,
            {
                "dk_key": pack_key,
                "pack_id": pack.id,
                "version": pack.version,
                "item_id": pack.id,
                "name": pack.title,
                "title": pack.title,
                "layer": pack.layer,
                "scope": scope,
                "status": pack.status,
                "provenance_kind": pack.provenance.kind,
                "verification": pack.provenance.verification,
                "provenance_reference": pack.provenance.reference,
                "synthetic": pack.synthetic,
                "usage": pack.usage,
                "dependency_mode": pack.dependency_mode,
                "domain_id": pack.domain_id,
                "document": document,
            },
        )
        pack_node = ("DKPackVersion", pack_key)
        review = self.node(
            pack,
            "DKReview",
            "review",
            f"Review of {pack.id} {pack.version}",
            state=pack.status,
            reviewer=None,
            decision=None,
            note="No reviewer is recorded: the pack has not been reviewed."
            if pack.status in ("draft", "in_review")
            else "Approved.",
        )
        self.rel("DK_REVIEWED_BY", pack_node, review)
        for dep in pack.depends_on:
            if dep in self.packs:
                dep_pack = self.packs[dep]
                self.rel(
                    "DK_DEPENDS_ON",
                    pack_node,
                    ("DKPackVersion", f"{dep}|{dep_pack.version}"),
                    mode="includes" if dep in pack.includes else pack.dependency_mode,
                )
                if pack.layer == "company":
                    self.rel(
                        "DK_EXTENDS", pack_node, ("DKPackVersion", f"{dep}|{dep_pack.version}")
                    )
            if dep in pack.includes and dep in self.packs:
                self.rel(
                    "DK_INCLUDES", pack_node, ("DKPackVersion", f"{dep}|{self.packs[dep].version}")
                )
        for (
            other
        ) in self.packs.values():  # a newer version of the same pack supersedes the older one
            if (
                other.id == pack.id
                and other.version != pack.version
                and _version_key(other.version) < _version_key(pack.version)
            ):
                self.rel(
                    "DK_SUPERSEDES", pack_node, ("DKPackVersion", f"{other.id}|{other.version}")
                )
        if pack.company:
            company = ("DKCompany", f"company|{pack.company.id}")
            self.nodes[company] = NodeOp(
                "DKCompany",
                company[1],
                {
                    "dk_key": company[1],
                    "company_id": pack.company.id,
                    "name": pack.company.name,
                    "industry": pack.company.industry,
                    "operating_context": pack.company.operating_context,
                    "scope": f"company:{pack.company.id}",
                    "version": pack.version,
                    "pack_id": pack.id,
                    "item_id": pack.company.id,
                    "status": pack.status,
                    "provenance_kind": pack.provenance.kind,
                    "verification": pack.provenance.verification,
                },
            )
            self.rel("DK_OWNS", company, pack_node)
            for unit in pack.company.business_units:
                node = ("DKOrgUnit", f"orgunit|{pack.company.id}|{_slug(unit)}")
                self.nodes[node] = NodeOp(
                    "DKOrgUnit",
                    node[1],
                    {
                        "dk_key": node[1],
                        "name": unit,
                        "scope": scope,
                        "pack_id": pack.id,
                        "version": pack.version,
                        "item_id": _slug(unit),
                        "status": pack.status,
                        "provenance_kind": pack.provenance.kind,
                        "verification": pack.provenance.verification,
                    },
                )
                self.rel("DK_HAS_UNIT", company, node)
            for system in pack.company.systems_of_record:
                node = self._system(system, scope, pack)
                self.rel("DK_USES_SYSTEM", company, node)
        for domain in pack.domains:
            node = self.node(
                pack,
                "DKDomain",
                domain.id,
                domain.name,
                keywords=list(domain.keywords),
                description=domain.description,
            )
            self.rel("DK_IN_DOMAIN", pack_node, node) if pack.domain_id == domain.id else None
            if domain.parent_id:
                self.rel("DK_SUBDOMAIN_OF", node, self.ref(pack, domain.parent_id, "DKDomain"))
            for sub in domain.subdomains:
                child = self.node(pack, "DKDomain", f"{domain.id}.{_slug(sub)}", sub)
                self.rel("DK_SUBDOMAIN_OF", child, node)
        for capability in pack.uses_capabilities:
            self.rel("DK_USES_CAPABILITY", pack_node, ("DKCapability", f"capability|{capability}"))
        business = pack.business
        for role in business.roles:
            node = self.node(
                pack,
                "DKRole",
                role.id,
                role.name,
                responsibilities=list(role.responsibilities),
                approval_authority=list(role.approval_authority),
            )
            for permission in role.permissions:
                perm = self.node(
                    pack, "DKPermission", f"perm:{permission}", permission, permission=permission
                )
                self.rel("DK_GRANTS", node, perm)
        for entity in business.entities:
            node = self.node(
                pack,
                "DKEntity",
                entity.id,
                entity.name,
                description=entity.description,
                owner_role=entity.owner_role_id,
                source_system=entity.source_system or None,
            )
            if entity.owner_role_id:
                pass  # ownership is a property; the role node is reachable through it
            if pack.domain_id:
                domain_ref = self.ref(pack, pack.domain_id, "DKDomain")
                if domain_ref in {(n.label, n.key) for n in self.nodes.values()}:
                    self.rel("DK_IN_DOMAIN", node, domain_ref)
            for attribute in entity.attributes:
                attr = self.node(
                    pack,
                    "DKAttribute",
                    f"{entity.id}.{attribute.id}",
                    attribute.name,
                    type=attribute.type,
                    required=attribute.required,
                    key=attribute.key,
                    value_source=attribute.value_source,
                    sensitivity=attribute.sensitivity,
                    enum=list(attribute.enum) or None,
                    writable=attribute.writable,
                    minimum=attribute.minimum,
                    maximum=attribute.maximum,
                    owner_role=attribute.owner_role_id,
                )
                self.rel("DK_HAS_ATTRIBUTE", node, attr)
            for relation in entity.relationships:
                self.rel(
                    "DK_RELATES_TO",
                    node,
                    self.ref(pack, relation.target, "DKEntity"),
                    def_id=relation.id,
                    type=relation.name,
                    cardinality=relation.cardinality,
                    required=relation.required,
                )
        for requirement in business.requirements:
            self.node(
                pack,
                "DKRequirement",
                requirement.id,
                requirement.statement[:200],
                statement=requirement.statement,
                priority=requirement.priority,
                kind=requirement.kind,
                acceptance=[c.statement for c in requirement.acceptance_criteria],
            )
        for rule in business.rules:
            node = self.node(
                pack,
                "DKRule",
                rule.id,
                rule.description[:200],
                RULE_PROVENANCE.get(rule.source.kind, pack.provenance.kind),
                rule_status=rule.status,
                rule_type=rule.type,
                outcomes=list(rule.outcomes) or None,
                executable=rule.execution is not None,
                source_reference=rule.source.reference[:300],
            )
            if rule.execution:
                for ref in (rule.execution.field, rule.execution.other_field):
                    if ref:
                        self.rel("DK_GOVERNS", node, self.ref(pack, ref.split(".")[0], "DKEntity"))
        for exception in business.exceptions:
            node = self.node(
                pack,
                "DKException",
                exception.id,
                exception.name,
                trigger=exception.trigger,
                recovery=exception.recovery,
                resolution=exception.resolution,
            )
            if exception.resolution_state_id:
                self.rel(
                    "DK_RECOVERS_AT",
                    node,
                    ("DKActivity", self.key(pack, exception.resolution_state_id)),
                )
        for decision in business.decisions:
            node = self.node(
                pack,
                "DKDecision",
                decision.id,
                decision.question[:200],
                decision_status=decision.status,
                question=decision.question,
                answer=decision.answer or None,
            )
            for target in decision.affects:
                label = self._label_of(pack, target)
                if (
                    label in schema.REL_TYPES["DK_AFFECTS"][1]
                ):  # an id that names something the graph does not model (an integration) is kept on the decision only
                    self.rel("DK_AFFECTS", node, self.ref(pack, target, label))
        for integration in business.integrations:
            node = self._system(
                integration.system,
                schema.SCOPE_SHARED if not pack.company else f"company:{pack.company.id}",
                pack,
                contract_status=integration.contract_status,
            )
            for entity_id in integration.entity_ids:
                self.rel("DK_SOURCE_OF", node, self.ref(pack, entity_id, "DKEntity"))
        for term in business.terms:
            glossary = next((g for g in pack.glossary if g.term == term.term), None)
            synonyms = list(glossary.synonyms) if glossary else []
            node = self.node(
                pack,
                "DKTerm",
                term.id,
                term.term,
                definition=term.definition,
                term_normalized=normalize(term.term),
                synonyms=synonyms or None,
                synonyms_normalized=[normalize(s) for s in synonyms] or None,
            )
            if glossary and glossary.refers_to:
                label = self._label_of(pack, glossary.refers_to)
                if label:
                    self.rel("DK_REPRESENTS", node, self.ref(pack, glossary.refers_to, label))
        for workflow in pack.workflows:
            context = next((c for c in pack.process_contexts if c.workflow_id == workflow.id), None)
            process = self.node(
                pack,
                "DKProcess",
                workflow.id,
                workflow.name,
                family_id=context.family_id if context else pack.domain_id,
                variant=context.variant if context else workflow.name,
                region=context.region if context else "Unspecified",
                source_system=context.source_system if context else None,
                source_reference=context.provenance.reference
                if context
                else pack.provenance.reference,
            )
            for state in workflow.states:
                activity = self.node(
                    pack,
                    "DKActivity",
                    state.id,
                    state.label,
                    kind=state.kind,
                    outcome=state.outcome,
                    permission=state.permission,
                    input_fields_json=json.dumps(state.input_fields, sort_keys=True),
                    input_relationships_json=json.dumps(state.input_relationships, sort_keys=True),
                    preconditions=list(state.preconditions),
                    postconditions=list(state.postconditions),
                )
                self.rel("DK_HAS_ACTIVITY", process, activity)
                if state.role_id:
                    self.rel("DK_PERFORMED_BY", activity, self.ref(pack, state.role_id, "DKRole"))
                for entity_id in state.reads_entity_ids:
                    self.rel(
                        "DK_USES", activity, self.ref(pack, entity_id, "DKEntity"), mode="reads"
                    )
                for entity_id in state.writes_entity_ids:
                    self.rel(
                        "DK_USES", activity, self.ref(pack, entity_id, "DKEntity"), mode="writes"
                    )
                for rule_id in state.rule_ids:
                    self.rel("DK_APPLIES_RULE", activity, self.ref(pack, rule_id, "DKRule"))
                for exception_id in state.exception_ids:
                    self.rel(
                        "DK_HANDLES_EXCEPTION",
                        activity,
                        self.ref(pack, exception_id, "DKException"),
                    )
                for requirement_id in state.requirement_ids:
                    self.rel("DK_SERVES", activity, self.ref(pack, requirement_id, "DKRequirement"))
            for transition in workflow.transitions:
                condition = transition.condition
                self.rel(
                    "DK_NEXT",
                    ("DKActivity", self.key(pack, transition.source)),
                    ("DKActivity", self.key(pack, transition.target)),
                    condition_key=transition.id,
                    def_id=transition.id,
                    condition=condition.kind
                    if condition.kind == "always"
                    else f"{condition.field} {'!=' if condition.kind == 'not_equals' else '='} {condition.value}",
                    condition_kind=condition.kind,
                    condition_field=condition.field,
                    condition_value_json=json.dumps(condition.value),
                )
        for override in pack.overrides:
            label = self._label_of(pack, override.item_id)
            if label:
                self.rel(
                    "DK_OVERRIDES",
                    pack_node,
                    self.ref(pack, override.item_id, label),
                    def_id=override.item_id,
                    reason=override.reason,
                    fields=sorted(
                        {
                            *override.patch,
                            *(["attributes"] if override.add_attributes else []),
                            *(["permissions"] if override.add_permissions else []),
                        }
                    ),
                )

    def _system(self, name: str, scope: str, pack: ReferencePack, **props) -> tuple[str, str]:
        node = ("DKSystem", f"system|{scope}|{_slug(name)}")
        self.nodes[node] = NodeOp(
            "DKSystem",
            node[1],
            {
                "dk_key": node[1],
                "name": name,
                "scope": scope,
                "pack_id": pack.id,
                "version": pack.version,
                "item_id": _slug(name),
                "status": pack.status,
                "provenance_kind": pack.provenance.kind,
                "verification": pack.provenance.verification,
                **props,
            },
        )
        return node

    def _label_of(self, pack: ReferencePack, item_id: str) -> str | None:
        group = self.home.get(item_id, (None, None, None))[2]
        return {
            "entities": "DKEntity",
            "roles": "DKRole",
            "rules": "DKRule",
            "requirements": "DKRequirement",
            "exceptions": "DKException",
            "decisions": "DKDecision",
            "terms": "DKTerm",
            "workflow": "DKProcess",
        }.get(group) or ("DKActivity" if item_id.startswith("st_") else None)

    def _capability(self, capability: Capability):
        key = f"capability|{capability.id}"
        self.nodes[("DKCapability", key)] = NodeOp(
            "DKCapability",
            key,
            {
                "dk_key": key,
                "capability_id": capability.id,
                "item_id": capability.id,
                "name": capability.name,
                "description": capability.description,
                "level": capability.level,
                "note": capability.note,
                "provided_by": capability.provided_by,
                "pack_id": "capabilities",
                "version": "registry",
                "scope": schema.SCOPE_SHARED,
                "status": "approved",
                "provenance_kind": "derived",
                "verification": "verified",
            },
        )
        for dep in capability.depends_on:
            self.rel(
                "DK_REQUIRES_CAPABILITY",
                ("DKCapability", key),
                ("DKCapability", f"capability|{dep}"),
            )
        provider = self.packs.get(capability.provided_by)
        if provider:
            self.rel(
                "DK_PROVIDES_CAPABILITY",
                ("DKPackVersion", f"{provider.id}|{provider.version}"),
                ("DKCapability", key),
            )

    # ── output ──
    def operations(self) -> tuple[list[NodeOp], list[RelOp]]:
        return list(self.nodes.values()), list(self.rels.values())

    def write_plan(self) -> list[dict]:
        """Idempotent MERGE statements with their parameters, grouped by label and relationship type. Labels and types come only from the schema registry."""
        plan = []
        by_label: dict[str, list[dict]] = {}
        for node in self.nodes.values():
            by_label.setdefault(node.label, []).append({"dk_key": node.key, "props": node.props})
        for label in schema.ALL_LABELS:
            if label in by_label:
                plan.append(
                    {
                        "cypher": f"UNWIND $rows AS row MERGE (n:{label} {{dk_key: row.dk_key}}) SET n += row.props",
                        "params": {"rows": by_label[label]},
                    }
                )
        by_type: dict[tuple, list[dict]] = {}
        for rel in self.rels.values():
            by_type.setdefault((rel.type, rel.source[0], rel.target[0]), []).append(
                {"source": rel.source[1], "target": rel.target[1], "props": rel.props}
            )
        for (kind, source_label, target_label), rows in sorted(by_type.items()):
            identity = (
                "{def_id: row.props.def_id}"
                if rows and "def_id" in rows[0]["props"]
                else "{mode: row.props.mode}"
                if rows and "mode" in rows[0]["props"]
                else ""
            )
            plan.append(
                {
                    "cypher": f"UNWIND $rows AS row MATCH (a:{source_label} {{dk_key: row.source}}), (b:{target_label} {{dk_key: row.target}}) MERGE (a)-[r:{kind}{(' ' + identity) if identity else ''}]->(b) SET r += row.props",
                    "params": {"rows": rows},
                }
            )
        return plan


def _items(pack: ReferencePack):
    for group in (
        "requirements",
        "roles",
        "entities",
        "rules",
        "exceptions",
        "decisions",
        "integrations",
        "terms",
    ):
        for item in getattr(pack.business, group):
            yield item.id, group
    for workflow in pack.workflows:
        yield workflow.id, "workflow"
        for state in workflow.states:
            yield state.id, "activity"
    for domain in pack.domains:
        yield domain.id, "domain"


def _version_key(version: str) -> tuple:
    return tuple(int(part) if part.isdigit() else 0 for part in re.split(r"[.\-]", version))


def project(packs: list[ReferencePack], capabilities: list[Capability] | None = None) -> Projection:
    return Projection(packs, capabilities)


ALLOWED_STATEMENT = re.compile(
    r"^UNWIND \$rows AS row (MERGE \(n:(?P<label>DK\w+) \{dk_key: row\.dk_key\}\) SET n \+= row\.props"
    r"|MATCH \(a:(?P<a>DK\w+) \{dk_key: row\.source\}\), \(b:(?P<b>DK\w+) \{dk_key: row\.target\}\) MERGE \(a\)-\[r:(?P<type>DK_\w+)( \{(def_id|mode): row\.props\.(def_id|mode)\})?\]->\(b\) SET r \+= row\.props)$"
)


def lint(plan: list[dict]) -> list[str]:
    """Static checks on a write plan. It cannot prove the Cypher runs on a server; it proves the statements are exactly the two
    parameterised templates, name only registered labels and relationship types, and carry JSON-safe parameters."""
    problems = []
    for index, step in enumerate(plan):
        match = ALLOWED_STATEMENT.match(step["cypher"])
        if not match:
            problems.append(f"statement {index} is not one of the allowed templates")
            continue
        for name in (match["label"], match["a"], match["b"]):
            if name and name not in schema.NODE_LABELS:
                problems.append(f"statement {index} uses unregistered label {name}")
        if match["type"] and match["type"] not in schema.REL_TYPES:
            problems.append(
                f"statement {index} uses unregistered relationship type {match['type']}"
            )
        try:
            json.dumps(step["params"])
        except TypeError:
            problems.append(f"statement {index} has parameters that are not JSON-safe")
        if re.search(r"\$(?!rows\b)", step["cypher"]):
            problems.append(f"statement {index} uses a parameter other than $rows")
    return problems
