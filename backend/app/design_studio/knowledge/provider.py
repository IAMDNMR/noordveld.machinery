"""Knowledge providers and pack application.

`LocalKnowledgeProvider` reads repository reference packs for offline use and tests.
With DESIGN_KNOWLEDGE_SOURCE=neo4j, the live provider reads the imported versioned
knowledge from Neo4j; model additions remain project-specific draft proposals.
"""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Callable, Protocol

from app.design_studio.knowledge.models import Capability, KnowledgeDomain, ReferencePack
from app.schemas.application_definition import ApplicationDefinition, KnowledgeOrigin

PACK_DIR = Path(__file__).with_name("packs")
GROUPS = (
    "requirements",
    "roles",
    "entities",
    "rules",
    "exceptions",
    "decisions",
    "integrations",
    "terms",
)


class PackUnavailable(LookupError):
    pass


class PackConflict(ValueError):
    def __init__(self, ids: list[str]):
        super().__init__("Pack items collide with existing project items")
        self.ids = ids


class KnowledgeProvider(Protocol):
    def packs(self) -> list[ReferencePack]: ...
    def pack(self, pack_id: str) -> ReferencePack: ...
    def domains(self) -> list[KnowledgeDomain]: ...


def load_packs(directories: list[Path]) -> dict[str, ReferencePack]:
    """Every pack in the directories, each validated together with the packs it depends on (so it may refer to their items)."""
    import json

    documents: dict[str, dict] = {}
    for directory in directories:
        for path in sorted(directory.glob("*.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            if document["id"] in documents:
                raise ValueError(f"Duplicate reference pack {document['id']}")
            documents[document["id"]] = document
    return build_packs(documents)


def build_packs(documents: dict[str, dict]) -> dict[str, ReferencePack]:
    """Validate pack documents (from files or from a graph) in dependency order, each together with the packs it depends on."""
    for pack_id, document in documents.items():
        if any(dep not in documents for dep in document.get("depends_on", [])):
            raise ValueError(f"Reference pack {pack_id} depends on an unknown pack")
    packs: dict[str, ReferencePack] = {}

    def build(pack_id: str, trail: tuple[str, ...] = ()):
        if pack_id in packs:
            return
        if pack_id in trail:
            raise ValueError("Reference pack dependency cycle")
        for dep in documents[pack_id].get("depends_on", []):
            build(dep, trail + (pack_id,))
        packs[pack_id] = ReferencePack.model_validate(
            documents[pack_id], context={"dependencies": packs}
        )

    for pack_id in sorted(documents):
        build(pack_id)
    return packs


CAPABILITIES_FILE = PACK_DIR.parent / "capabilities.json"
FIXTURES_DIR = PACK_DIR.parent / "fixtures"


def load_capabilities(path: Path | None) -> dict[str, Capability]:
    """The capability registry, checked: dependencies exist and do not form a cycle."""
    import json

    if path is None or not path.exists():
        return {}
    capabilities = {
        item["id"]: Capability.model_validate(item)
        for item in json.loads(path.read_text(encoding="utf-8"))["capabilities"]
    }
    for capability in capabilities.values():
        missing = [dep for dep in capability.depends_on if dep not in capabilities]
        if missing:
            raise ValueError(
                f"Capability {capability.id} depends on unknown capability {missing[0]}"
            )

    def visit(current: str, trail: tuple[str, ...]):
        if current in trail:
            raise ValueError("Capability dependency cycle")
        for dep in capabilities[current].depends_on:
            visit(dep, trail + (current,))

    for capability_id in capabilities:
        visit(capability_id, ())
    return capabilities


class LocalKnowledgeProvider:
    def process_references(self):
        from app.design_studio.knowledge.process_references import load_references

        return load_references()

    def context_catalog(self, version=None):
        from app.design_studio.knowledge.system_context import load_catalog

        catalog = load_catalog()
        return catalog if version is None or version == catalog["version"] else None

    def __init__(
        self,
        directory: Path | list[Path] = PACK_DIR,
        capabilities_file: Path | None = CAPABILITIES_FILE,
    ):
        self._packs = load_packs([directory] if isinstance(directory, Path) else list(directory))
        self._capabilities = load_capabilities(capabilities_file)
        for pack in self._packs.values():
            unknown = [item for item in pack.uses_capabilities if item not in self._capabilities]
            if unknown and self._capabilities:
                raise ValueError(f"Reference pack {pack.id} uses unknown capability {unknown[0]}")
            if pack.status != "deprecated" and any(
                self._packs[dep].status == "deprecated" for dep in pack.depends_on
            ):
                raise ValueError(f"Reference pack {pack.id} depends on a deprecated pack")

    def capabilities(self) -> list[Capability]:
        return [item.model_copy(deep=True) for item in self._capabilities.values()]

    def packs(self) -> list[ReferencePack]:
        return [pack.model_copy(deep=True) for pack in self._packs.values()]

    def pack(self, pack_id: str) -> ReferencePack:
        if pack_id not in self._packs:
            raise PackUnavailable(pack_id)
        return self._packs[pack_id].model_copy(deep=True)

    def domains(self) -> list[KnowledgeDomain]:
        seen: dict[str, KnowledgeDomain] = {}
        for pack in self._packs.values():
            for domain in pack.domains:
                seen.setdefault(domain.id, domain)
        return [domain.model_copy(deep=True) for domain in seen.values()]

    def context(self, domain_ids: list[str]) -> list[dict]:
        """The domain's packs plus the packs they depend on, as documents the Studio model reads (same shape as the graph provider)."""
        packs = [
            pack
            for pack in sorted(self._packs.values(), key=lambda p: p.id)
            if pack.domain_id in domain_ids and pack.company is None and pack.verified
        ][:3]
        dependencies = {dep for pack in packs for dep in pack.depends_on} - {pack.id for pack in packs}
        packs += [self._packs[dep] for dep in sorted(dependencies) if dep in self._packs][:3]
        return [pack.model_dump(mode="json") for pack in packs]


class GraphKnowledgeProvider:
    """Placeholder for approved, read-only graph knowledge. Disabled: no queries are issued."""

    def packs(self) -> list[ReferencePack]:
        raise PackUnavailable("Graph-backed design knowledge is not enabled")

    def pack(self, pack_id: str) -> ReferencePack:
        raise PackUnavailable("Graph-backed design knowledge is not enabled")

    def domains(self) -> list[KnowledgeDomain]:
        raise PackUnavailable("Graph-backed design knowledge is not enabled")


@lru_cache
def _local() -> LocalKnowledgeProvider:
    return LocalKnowledgeProvider()


def get_knowledge_provider() -> KnowledgeProvider:
    import os
    from app.core.config import get_settings

    get_settings()
    if os.environ.get("DESIGN_KNOWLEDGE_SOURCE", "local") == "neo4j":
        from app.knowledge_graph.neo4j import provider

        return provider()
    return _local()


def identify_domains(text: str, provider: KnowledgeProvider) -> list[dict]:
    """Deterministic curated-vocabulary match. Transparent by design: returns the keywords that matched."""
    words = set(re.findall(r"[a-z0-9]+(?:[-'][a-z0-9]+)*", text.lower()))
    words |= {
        word[:-1] for word in words if word.endswith("s") and len(word) > 3
    }  # plain plurals only
    lower = text.lower()
    packs = provider.packs()
    results = []
    for domain in provider.domains():
        matched = sorted(
            {
                keyword
                for keyword in domain.keywords
                if (keyword in words if " " not in keyword else keyword in lower)
            }
        )
        if matched:
            from app.design_studio.knowledge.planning import eligible

            results.append(
                {
                    "domain_id": domain.id,
                    "name": domain.name,
                    "score": len(matched),
                    "matched_keywords": matched,
                    "pack_ids": sorted(
                        pack.id
                        for pack in packs
                        if pack.domain_id == domain.id and eligible(pack, text)
                    ),
                }
            )
    return sorted(results, key=lambda item: (-item["score"], item["domain_id"]))


def _with_dependencies(pack_id: str, provider: KnowledgeProvider) -> list[ReferencePack]:
    ordered: list[ReferencePack] = []

    def visit(current: str, trail: tuple[str, ...]):
        if current in trail:
            raise ValueError("Reference pack dependency cycle")
        pack = provider.pack(current)
        for dep in pack.depends_on:
            visit(dep, trail + (current,))
        if all(item.id != pack.id for item in ordered):
            ordered.append(pack)

    visit(pack_id, ())
    return ordered


def adoption_order(
    root_ids: list[str], provider: KnowledgeProvider
) -> tuple[list[ReferencePack], set[str]]:
    """The packs adopting these roots brings in, in the order they are applied, and which of them come with their processes."""
    ordered: list[ReferencePack] = []
    full: set[str] = set()
    for root_id in root_ids:
        chain = _with_dependencies(root_id, provider)
        full |= _full_content(chain, root_id)
        ordered += [pack for pack in chain if all(pack.id != seen.id for seen in ordered)]
    return ordered, full


def _full_content(ordered: list[ReferencePack], root_id: str) -> set[str]:
    """The packs whose complete content is copied: the root, what its `full` dependency mode pulls in, and what a pack `includes`."""
    by_id = {pack.id: pack for pack in ordered}
    full: set[str] = set()

    def visit(pack_id: str):
        if pack_id in full:
            return
        full.add(pack_id)
        pack = by_id[pack_id]
        for dep in pack.depends_on:
            if pack.dependency_mode == "full" or dep in pack.includes:
                visit(dep)

    visit(root_id)
    return full


def _data_model_only(
    content: dict, ordered: list[ReferencePack], pack: ReferencePack, full: set[str]
) -> dict:
    """A dependency's data model: entities and terms, plus the roles and rules that something being copied refers to."""
    wanted = {item["id"] for item in content["entities"]} | {
        item["id"] for item in content["terms"]
    }
    referenced: set[str] = set()
    for other in ordered:
        if other.id == pack.id:
            continue
        if other.id in full:
            text = other.model_dump_json()
        else:
            text = json.dumps(
                [
                    item
                    for group in ("entities",)
                    for item in other.business.model_dump(mode="json")[group]
                ]
            )
        referenced |= set(re.findall(r'"([a-z][a-z0-9_-]{1,79})"', text))
    own = {group: {item["id"]: item for item in content[group]} for group in GROUPS}
    grew = True
    while grew:
        grew = False
        text = json.dumps([own[group][i] for group in GROUPS for i in own[group] if i in wanted])
        for found in set(re.findall(r'"([a-z][a-z0-9_-]{1,79})"', text)) | referenced:
            for group in ("roles", "rules"):
                if found in own[group] and found not in wanted:
                    wanted.add(found)
                    grew = True
    return {group: [item for item in content[group] if item["id"] in wanted] for group in GROUPS}


# Regions that name a legal regime ("remedies under Directive (EU) 2019/771"). A process written for one applies only when the project
# chose that region; "Global", "Europe" (a geographic variant of a standard flow) and "Unspecified" are never held back.
LEGAL_REGIONS = {"European Union": "eu", "India": "india"}


def _applies_in(context_region: str, selected: str | None) -> bool:
    code = LEGAL_REGIONS.get(context_region)
    return code is None or selected == code


def _leave_out_other_regions(raw: dict, pack, selected: str | None) -> list[str]:
    """Remove the pack's processes written for a legal region the project did not choose, and what only they use.

    A small workshop that never chose the European Union should not get an EU consumer-law remedy process, its record, rules and
    requirements. Anything also used by a process that stays, and anything not copied from this pack, is kept. A pack is never emptied.
    Returns the names of the processes left out."""
    held_back = {c.workflow_id for c in pack.process_contexts if not _applies_in(c.region, selected)}
    own = {w.id for w in pack.workflows}
    present = [w for w in raw["workflow_definitions"] if w["id"] in held_back]
    if not present or len(present) == len([w for w in raw["workflow_definitions"] if w["id"] in own]):
        return []
    kept = [w for w in raw["workflow_definitions"] if w not in present]

    def used(workflows) -> dict[str, set]:
        found = {key: set() for key in ("entities", "rules", "exceptions", "requirements")}
        for workflow in workflows:
            for state in workflow["states"]:
                found["entities"] |= set(state.get("reads_entity_ids", [])) | set(state.get("writes_entity_ids", []))
                found["rules"] |= set(state.get("rule_ids", []))
                found["exceptions"] |= set(state.get("exception_ids", []))
                found["requirements"] |= set(state.get("requirement_ids", []))
        return found

    gone, still = used(present), used(kept)
    business = raw["business"]
    for group in ("entities", "rules", "exceptions", "requirements"):
        only_there = gone[group] - still[group]
        business[group] = [
            item
            for item in business[group]
            if not (item["id"] in only_there and (item.get("origin") or {}).get("pack_id") == pack.id)
        ]
    removed_entities = gone["entities"] - still["entities"]
    for entity in business["entities"]:
        entity["relationships"] = [r for r in entity.get("relationships", []) if r["target"] not in removed_entities]
    names = [w["name"] for w in present]
    ids = {w["id"] for w in present}
    raw["workflow_definitions"] = [w for w in raw["workflow_definitions"] if w["id"] not in ids]
    raw["workflows"] = [i for i in raw["workflows"] if i not in ids]
    return names


def apply_pack(
    definition: ApplicationDefinition, pack_id: str, provider: KnowledgeProvider
) -> tuple[ApplicationDefinition, dict]:
    """Copy a pack (and what it depends on) into a project, stamping each item's origin.

    Items already copied from the same pack are kept unchanged, never rewritten, so a newer pack version shows up as
    stale instead of silently changing an approved design. An ID used by anything else is a conflict.
    """
    raw = definition.model_dump(mode="json")
    business = raw["business"]
    existing = {item["id"]: item for group in GROUPS for item in business[group]}
    added: dict[str, int] = {group: 0 for group in GROUPS}
    added["workflows"] = 0
    conflicts: list[str] = []
    workflow_ids = {item["id"] for item in raw["workflow_definitions"]}
    ordered = _with_dependencies(pack_id, provider)
    full = _full_content(ordered, pack_id)
    for pack in ordered:
        content = pack.business.model_dump(mode="json")
        if pack.id not in full:
            content = _data_model_only(content, ordered, pack, full)
        for group in GROUPS:
            for item in content[group]:
                current = existing.get(item["id"])
                if current is not None:
                    if (current.get("origin") or {}).get("pack_id") != pack.id:
                        conflicts.append(item["id"])
                    continue
                item["origin"] = KnowledgeOrigin(
                    pack_id=pack.id, pack_version=pack.version, item_id=item["id"]
                ).model_dump()
                business[group].append(item)
                existing[item["id"]] = item
                added[group] += 1
        if pack.overrides:
            from app.design_studio.knowledge.overrides import apply_overrides

            changed = apply_overrides(
                {group: [item for item in business[group]] for group in GROUPS}, pack.overrides
            )
            for override in pack.overrides:
                target = next(
                    (
                        item
                        for group in GROUPS
                        for item in changed[group]
                        if item["id"] == override.item_id
                    ),
                    None,
                )
                if target is not None:
                    target["origin"] = KnowledgeOrigin(
                        pack_id=pack.id, pack_version=pack.version, item_id=override.item_id
                    ).model_dump()
            for group in GROUPS:
                business[group] = changed[group]
                existing.update({item["id"]: item for item in business[group]})
            added["overrides"] = added.get("overrides", 0) + len(pack.overrides)
        for workflow in pack.workflows if pack.id in full else []:
            if workflow.id in workflow_ids:
                continue
            raw["workflow_definitions"].append(workflow.model_dump(mode="json"))
            raw["workflows"].append(workflow.id)
            workflow_ids.add(workflow.id)
            added["workflows"] += 1
        if all(link["pack_id"] != pack.id for link in business["knowledge"]):
            business["knowledge"].append({"pack_id": pack.id, "pack_version": pack.version})
        brief = business["brief"]
        if pack.id == pack_id and pack.domain_id and not brief["domain_id"]:
            brief["domain_id"] = pack.domain_id
        if pack.id == pack_id and pack.capability and not brief["capability"]:
            brief["capability"] = pack.capability.name
    if conflicts:
        raise PackConflict(sorted(set(conflicts)))
    intake = definition.business.brief.intake
    left_out = [
        name
        for pack in ordered
        if pack.id in full
        for name in _leave_out_other_regions(raw, pack, intake.region if intake else None)
    ]
    if left_out:
        added["left_out_for_region"] = len(left_out)
    # A draft may already express exactly the same requirement in user wording.
    # Keep the sourced canonical ID (used by the imported process) and preserve
    # the user's acceptance criteria instead of leaving an uncovered duplicate.
    from app.design_studio.knowledge.deduplication import reconcile

    def normalize(text):
        return " ".join(re.findall(r"[a-z0-9]+", text.lower()))

    sourced = {
        normalize(r["statement"]): r["id"] for r in business["requirements"] if r.get("origin")
    }
    merged = False
    for requirement in list(business["requirements"]):
        canonical = sourced.get(normalize(requirement["statement"]))
        if canonical and not requirement.get("origin"):
            reconcile(raw, "requirement", canonical, requirement["id"])
            merged = True
    from app.design_studio.knowledge.deduplication import merge_shared_entities

    # Capabilities adopted together share master records (Item, Warehouse): one record each, not one per pack.
    if shared := merge_shared_entities(raw):
        added["merged_records"] = len(shared)
    updated = ApplicationDefinition.model_validate(raw)
    from app.design_studio.auto_resolve import assign_owners

    # Records every capability points at (suppliers, carriers, warehouses) need someone to maintain them, or nothing that needs one can be created.
    if owned := assign_owners(raw, updated):
        added["maintained_records"] = len(owned)
        updated = ApplicationDefinition.model_validate(raw)
    if merged and definition.studio_flow and "brief" in definition.studio_flow.reviewed:
        from app.design_studio.guided import stage_digest

        previous = definition.studio_flow.reviewed_digests.get("brief")
        if previous == stage_digest(definition, "brief"):
            # Identity reconciliation preserved the exact requirement and all
            # acceptance checks; it must not send a reviewed brief backwards.
            updated.studio_flow.reviewed_digests["brief"] = stage_digest(updated, "brief")
    return updated, added


class WithDomainPacks:
    """A provider that also knows the active version of shared domain packs from the configured domain store."""

    def __init__(self, inner: KnowledgeProvider, domain_pack_version: Callable[[str], str | None]):
        self._inner, self.domain_pack_version = inner, domain_pack_version

    def packs(self) -> list[ReferencePack]:
        return self._inner.packs()

    def process_references(self):
        reader = getattr(self._inner, "process_references", None)
        return reader() if reader else []

    def context_catalog(self, version=None):
        reader = getattr(self._inner, "context_catalog", None)
        return reader(version) if reader else None

    def pack(self, pack_id: str) -> ReferencePack:
        return self._inner.pack(pack_id)

    def pack_version(self, pack_id: str, version: str) -> ReferencePack:
        reader = getattr(self._inner, "pack_version", None)
        if reader:
            return reader(pack_id, version)
        pack = self._inner.pack(pack_id)
        if pack.version != version:
            raise PackUnavailable(f"{pack_id}@{version}")
        return pack

    def domains(self) -> list[KnowledgeDomain]:
        return self._inner.domains()

    @property
    def source(self):
        return getattr(self._inner, "source", "local")

    def context(self, domains):
        return getattr(self._inner, "context", lambda _: [])(domains)

    def proposals(self, project_id):
        return getattr(self._inner, "proposals", lambda _: [])(project_id)

    def record_proposal(self, *args):
        record = getattr(self._inner, "record_proposal", None)
        if record:
            record(*args)

    def capabilities(self) -> list[Capability]:
        return getattr(self._inner, "capabilities", lambda: [])()


def _domain_pack_version(pack_id: str) -> str | None:
    """Entities adopted from a shared domain pack (app.domain_knowledge) record that pack as their origin."""
    from app.domain_knowledge.packs import shipped_packs

    versions = sorted(
        (tuple(int(p) for p in pack.version.split(".")), pack.version)
        for pack in shipped_packs()
        if pack.id == pack_id and pack.status == "approved"
    )
    return versions[-1][1] if versions else None


def stale_items(definition: ApplicationDefinition, provider: KnowledgeProvider) -> list[dict]:
    """Items whose source pack has moved on. Reported, never rewritten."""
    stale = []
    for group in GROUPS:
        for item in getattr(definition.business, group):
            origin = getattr(item, "origin", None)
            if origin is None:
                continue
            try:
                current = provider.pack(origin.pack_id).version
            except PackUnavailable:
                lookup = getattr(provider, "domain_pack_version", None) or _domain_pack_version
                current = lookup(origin.pack_id)
                if current is not None:
                    if current != origin.pack_version:
                        stale.append(
                            {
                                "item_id": item.id,
                                "pack_id": origin.pack_id,
                                "pack_version": origin.pack_version,
                                "current_version": current,
                            }
                        )
                    continue
                stale.append(
                    {
                        "item_id": item.id,
                        "pack_id": origin.pack_id,
                        "pack_version": origin.pack_version,
                        "current_version": None,
                    }
                )
                continue
            if current != origin.pack_version:
                stale.append(
                    {
                        "item_id": item.id,
                        "pack_id": origin.pack_id,
                        "pack_version": origin.pack_version,
                        "current_version": current,
                    }
                )
    return stale
