"""The knowledge graph schema (version 2): labels, relationship types, who may connect to whom, constraints and indexes.

This extends the namespaced DK schema in `app.domain_knowledge.graph` (DKEntity, DKRule, ...) rather than replacing it, so what is already
specified keeps its meaning. Everything here is *definition*: nothing connects to a database, and the operational commerce graph
(Part, Machine, Order, ...) is never touched, because every label starts with `DK` and every relationship type with `DK_`.

Ownership boundaries
  shared         reusable domain knowledge, scope = "shared"
  company        one company's own layer, scope = "company:<id>", linked to the shared definitions it reuses (DK_DEPENDS_ON) and the ones it changes (DK_OVERRIDES)
  transactional  live orders, stock, shipments and so on stay in each application's own store: this graph describes meaning and structure, never records

Every node carries: dk_key (unique), pack_id, version, item_id, name, scope, status, provenance_kind, verification.
Provenance kind says where a definition comes from: verified_source | derived | synthetic | user_provided | assumption.
Status says where it stands in review: draft | in_review | approved | deprecated. Nothing is "approved" because it exists.
"""

from __future__ import annotations


from app.domain_knowledge import graph as v1

SCHEMA_VERSION = 2

# label -> (what it is, properties indexed for lookup besides dk_key)
NODE_LABELS: dict[str, tuple[str, tuple[str, ...]]] = {
    # version 1 (already specified in app.domain_knowledge.graph)
    "DKPackVersion": (
        "One version of a knowledge pack: the unit that is reviewed, approved and adopted.",
        ("pack_id",),
    ),
    "DKDomain": ("A business domain or subdomain.", ("item_id",)),
    "DKConcept": ("A business concept with a canonical name.", ("canonical_name",)),
    "DKEntity": ("A business entity.", ("pack_id", "name")),
    "DKAttribute": ("An attribute of an entity: type, constraints, ownership, sensitivity.", ()),
    "DKEvent": ("Something that happens to an entity.", ()),
    "DKRule": ("A business rule, validation or policy.", ("status",)),
    "DKProcess": ("A business process.", ("pack_id",)),
    "DKDecision": ("A decision only the business can make; open until answered.", ("status",)),
    "DKSourceMapping": ("Where an attribute's value comes from in a system of record.", ()),
    # added in version 2
    "DKCompany": ("A company and its operating context.", ("company_id",)),
    "DKOrgUnit": ("A business unit or team of a company.", ()),
    "DKSystem": ("A system of record or external system.", ("name",)),
    "DKCapability": (
        "A reusable capability (approvals, audit history, task management, ...) with how far generated applications provide it.",
        ("capability_id",),
    ),
    "DKRole": ("A role and its responsibilities.", ("pack_id",)),
    "DKPermission": ("A permission a role is granted.", ("permission",)),
    "DKRequirement": (
        "A functional or non-functional requirement with acceptance criteria.",
        ("pack_id",),
    ),
    "DKActivity": ("A step of a process: what is done, by whom, on which entities.", ("pack_id",)),
    "DKException": ("An exception path and how work recovers from it.", ()),
    "DKTerm": (
        "A business term, its definition and the other words used for it.",
        ("term_normalized",),
    ),
    "DKReview": (
        "The review state of a pack version: who reviewed it, when and with what outcome. Absent reviewer means not reviewed.",
        ("state",),
    ),
}
V1_LABELS = frozenset(v1.ALL_LABELS)

# type -> (allowed source labels, allowed target labels, what it means)
REL_TYPES: dict[str, tuple[tuple[str, ...], tuple[str, ...], str]] = {
    "DK_IN_PACK": (
        tuple(NODE_LABELS),
        ("DKPackVersion",),
        "The item belongs to this pack version.",
    ),
    "DK_DEPENDS_ON": (
        ("DKPackVersion", "DKDomain", "DKCapability"),
        ("DKPackVersion", "DKDomain", "DKCapability"),
        "Needs the definitions of the other.",
    ),
    "DK_INCLUDES": (
        ("DKPackVersion",),
        ("DKPackVersion",),
        "Adopts the other pack completely, with its processes.",
    ),
    "DK_SUPERSEDES": (("DKPackVersion",), ("DKPackVersion",), "A newer version of the same pack."),
    "DK_OWNS": (("DKCompany",), ("DKPackVersion",), "The company owns this layer."),
    "DK_EXTENDS": (
        ("DKPackVersion",),
        ("DKPackVersion",),
        "A company layer extending shared knowledge.",
    ),
    "DK_OVERRIDES": (
        ("DKPackVersion",),
        tuple(n for n in NODE_LABELS if n not in ("DKPackVersion", "DKCompany")),
        "A company layer changes this shared item, with a reason.",
    ),
    "DK_HAS_UNIT": (("DKCompany",), ("DKOrgUnit",), "A business unit of the company."),
    "DK_USES_SYSTEM": (("DKCompany",), ("DKSystem",), "A system of record the company runs."),
    "DK_SOURCE_OF": (
        ("DKSystem",),
        ("DKEntity", "DKAttribute"),
        "The system holds the authoritative records.",
    ),
    "DK_IN_DOMAIN": (
        ("DKEntity", "DKProcess", "DKPackVersion"),
        ("DKDomain",),
        "Belongs to the domain.",
    ),
    "DK_SUBDOMAIN_OF": (("DKDomain",), ("DKDomain",), "A subdomain."),
    "DK_BROADER": (("DKConcept",), ("DKConcept",), "A broader concept."),
    "DK_REPRESENTS": (
        ("DKEntity", "DKTerm"),
        ("DKConcept", "DKEntity", "DKRole", "DKRule"),
        "The term or entity stands for this concept.",
    ),
    "DK_HAS_ATTRIBUTE": (("DKEntity",), ("DKAttribute",), "An attribute of the entity."),
    "DK_RELATES_TO": (
        ("DKEntity",),
        ("DKEntity",),
        "A relationship with cardinality and whether it is required.",
    ),
    "DK_USES_CAPABILITY": (("DKPackVersion",), ("DKCapability",), "The pack uses this capability."),
    "DK_PROVIDES_CAPABILITY": (
        ("DKPackVersion",),
        ("DKCapability",),
        "The pack supplies the capability's data and process.",
    ),
    "DK_REQUIRES_CAPABILITY": (
        ("DKCapability",),
        ("DKCapability",),
        "The capability needs the other.",
    ),
    "DK_HAS_ACTIVITY": (("DKProcess",), ("DKActivity",), "A step of the process."),
    "DK_NEXT": (("DKActivity",), ("DKActivity",), "What can follow, with the condition."),
    "DK_PERFORMED_BY": (("DKActivity",), ("DKRole",), "The role that does the step."),
    "DK_USES": (
        ("DKActivity", "DKProcess"),
        ("DKEntity",),
        "Reads or changes the entity (property mode).",
    ),
    "DK_APPLIES_RULE": (("DKActivity", "DKProcess"), ("DKRule",), "The rule is evaluated here."),
    "DK_GOVERNS": (("DKRule",), ("DKEntity",), "The rule constrains the entity."),
    "DK_AFFECTS": (
        ("DKDecision",),
        ("DKRule", "DKActivity", "DKEntity", "DKException", "DKRole", "DKRequirement", "DKProcess"),
        "The decision holds this back until it is answered.",
    ),
    "DK_HANDLES_EXCEPTION": (
        ("DKActivity",),
        ("DKException",),
        "The step deals with the exception.",
    ),
    "DK_RECOVERS_AT": (("DKException",), ("DKActivity",), "Work resumes here after the exception."),
    "DK_SERVES": (("DKActivity",), ("DKRequirement",), "The step serves the requirement."),
    "DK_GRANTS": (("DKRole",), ("DKPermission",), "The role holds the permission."),
    "DK_MAPS_TO": (("DKSourceMapping",), ("DKAttribute",), "The mapping fills this attribute."),
    "DK_REVIEWED_BY": (("DKPackVersion",), ("DKReview",), "The review record of this version."),
    "DK_IMPACTS": (
        ("DKPackVersion", "DKEntity", "DKRule"),
        ("DKPackVersion", "DKEntity", "DKRule", "DKProcess"),
        "A change here affects the other.",
    ),
}
# Version-1 types that already exist in app.domain_knowledge.graph and keep their meaning.
V1_TYPES = frozenset(v1.REL_TYPES)
ALL_LABELS = tuple(NODE_LABELS)
ALL_TYPES = tuple(REL_TYPES)

PROVENANCE_KINDS = ("verified_source", "derived", "synthetic", "user_provided", "assumption")
STATUSES = ("draft", "in_review", "approved", "deprecated")
SCOPE_SHARED = "shared"


def constraints() -> list[str]:
    return [
        f"CREATE CONSTRAINT dk_{label.lower()}_key IF NOT EXISTS FOR (n:{label}) REQUIRE n.dk_key IS UNIQUE"
        for label in ALL_LABELS
    ]


def indexes() -> list[str]:
    statements = []
    for label, (_, properties) in NODE_LABELS.items():
        for prop in properties:
            statements.append(
                f"CREATE INDEX dk_{label.lower()}_{prop} IF NOT EXISTS FOR (n:{label}) ON (n.{prop})"
            )
    statements.append(
        "CREATE INDEX dk_scope IF NOT EXISTS FOR (n:DKPackVersion) ON (n.scope, n.status)"
    )
    return statements


MIGRATIONS: list[tuple[str, list[str]]] = [
    ("0001_dk_schema_v1", list(v1.SCHEMA_PROPOSAL)),
    ("0002_dk_schema_v2", [s for s in (*constraints(), *indexes()) if s not in v1.SCHEMA_PROPOSAL]),
]


def migration_script() -> str:
    """The whole schema as a reviewable, idempotent script. Every statement is CREATE ... IF NOT EXISTS: running it twice changes nothing."""
    lines = [
        f"// Knowledge graph schema v{SCHEMA_VERSION}. Idempotent. Review, then run against a DEDICATED development graph first.",
        "// Never run against the shared operational (live demo) graph.",
        "",
    ]
    for name, statements in MIGRATIONS:
        lines.append(f"// ── {name} ──")
        lines += [f"{statement};" for statement in statements]
        lines.append("")
    return "\n".join(lines)


def operational_names() -> tuple[set[str], set[str]]:
    return v1.operational_names()


def validate_schema() -> list[str]:
    """Problems with the schema itself. Empty means: no collision with the operational graph, every label has a unique key, every
    relationship endpoint is a declared label, and nothing from version 1 was dropped."""
    problems = []
    labels, types = operational_names()
    problems += [
        f"{name} collides with an operational label or relationship type"
        for name in sorted((set(ALL_LABELS) & labels) | (set(ALL_TYPES) & types))
    ]
    problems += [
        f"{label} does not start with DK" for label in ALL_LABELS if not label.startswith("DK")
    ]
    problems += [
        f"{kind} does not start with DK_" for kind in ALL_TYPES if not kind.startswith("DK_")
    ]
    declared = {s.split(" FOR (n:")[1].split(")")[0] for s in constraints()}
    problems += [
        f"{label} has no unique key constraint" for label in ALL_LABELS if label not in declared
    ]
    for kind, (sources, targets, _) in REL_TYPES.items():
        problems += [
            f"{kind} refers to unknown label {label}"
            for label in (*sources, *targets)
            if label not in NODE_LABELS
        ]
    problems += [
        f"version 1 label {label} was dropped" for label in sorted(V1_LABELS - set(ALL_LABELS))
    ]
    problems += [
        f"version 1 relationship type {kind} was dropped"
        for kind in sorted(V1_TYPES - set(ALL_TYPES))
    ]
    return problems


def describe() -> dict:
    """The schema as plain data for the explorer and the documentation."""
    return {
        "version": SCHEMA_VERSION,
        "labels": [
            {
                "label": label,
                "description": text,
                "indexed": list(props),
                "version": 1 if label in V1_LABELS else 2,
            }
            for label, (text, props) in NODE_LABELS.items()
        ],
        "relationships": [
            {
                "type": kind,
                "from": list(src),
                "to": list(dst),
                "meaning": text,
                "version": 1 if kind in V1_TYPES else 2,
            }
            for kind, (src, dst, text) in REL_TYPES.items()
        ],
        "constraints": len(constraints()),
        "indexes": len(indexes()),
        "problems": validate_schema(),
    }
