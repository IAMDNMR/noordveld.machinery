"""Neo4j storage for versioned Studio knowledge and project-scoped proposals."""

from __future__ import annotations

from hashlib import sha256
import json
from threading import Lock
import time

from app.core.exceptions import GraphUnavailableError
from app.domain_knowledge.models import DomainPack
from app.domain_knowledge.store import ReadOnlyDomainStore
from app.knowledge_graph.projection import lint


class KnowledgeConflict(ValueError):
    pass


# One cheap read that changes whenever anything the shared provider or domain store serves changes (content, status, version).
_FINGERPRINT = (
    "MATCH (p:DKPackVersion) RETURN 'pack' AS label, p.dk_key AS key, [p.document_kind, p.status, p.scope, p.verification, "
    "toString(p.synthetic), p.content_sha256, toString(size(p.document))] AS mark "
    "UNION ALL MATCH (c:DKCapability) RETURN 'capability' AS label, c.capability_id AS key, [c.document] AS mark "
    "UNION ALL MATCH (c:DKContextCatalog) RETURN 'catalog' AS label, c.dk_key AS key, "
    "[c.version, c.content_sha256, toString(size(c.document))] AS mark "
    "UNION ALL MATCH (n:DKProcessReference) RETURN 'reference' AS label, n.dk_key AS key, "
    "[n.review_state, n.content_sha256, toString(size(n.document))] AS mark"
)
_cache: dict[str, tuple[str, object]] = {}
_cache_lock = Lock()
_FINGERPRINT_REUSE_SECONDS = 2.0  # one request resolves both the provider and the domain store; check the graph once for both
_last_fingerprint: tuple[float, str] | None = None


class Neo4jKnowledgeRepository:
    def __init__(self, graph):
        self.graph = graph

    def fingerprint(self) -> str:
        rows = sorted(json.dumps([r["label"], r["key"], r["mark"]]) for r in self.graph.read(_FINGERPRINT))
        return sha256("\n".join(rows).encode()).hexdigest()

    def process_references(self):
        from app.knowledge_graph.process_references import read_references
        return read_references(self.graph)

    def documents(self, statuses=("approved", "in_review")):
        return [
            json.loads(row["document"])
            for row in self.graph.read(
                "MATCH (p:DKPackVersion) WHERE p.document_kind = 'reference' AND p.status IN $statuses "
                "RETURN p.document AS document ORDER BY p.pack_id, p.version",
                statuses=list(statuses),
            )
        ]

    def capability_documents(self):
        return [
            json.loads(row["document"])
            for row in self.graph.read(
                "MATCH (c:DKCapability) WHERE c.document IS NOT NULL RETURN c.document AS document ORDER BY c.capability_id"
            )
        ]

    def context_catalog(self, version=None):
        from app.design_studio.knowledge.system_context import validate_catalog

        rows = self.graph.read(
            "MATCH (c:DKContextCatalog) WHERE $version IS NULL OR c.version=$version RETURN c.document AS document",
            version=version,
        )
        if not rows:
            return None
        documents = [validate_catalog(json.loads(r["document"])) for r in rows]
        return max(documents, key=lambda d: tuple(int(x) for x in d["version"].split(".")))

    def import_context_catalog(self, document):
        from app.design_studio.knowledge.system_context import validate_catalog

        document = validate_catalog(document)
        payload = json.dumps(document, sort_keys=True, separators=(",", ":"))
        digest = sha256(payload.encode()).hexdigest()
        version = document["version"]
        with self.graph.driver.session(database=self.graph._settings.neo4j_database) as session:
            for label in (
                "DKContextCatalog",
                "DKSystemProfile",
                "DKIndustryContext",
                "DKRegionContext",
            ):
                session.run(
                    f"CREATE CONSTRAINT {label.lower()}_key IF NOT EXISTS FOR (c:{label}) REQUIRE c.dk_key IS UNIQUE"
                ).consume()

            def write(tx):
                existing = tx.run(
                    "MATCH (c:DKContextCatalog {dk_key:$key}) RETURN c.content_sha256 AS hash",
                    key=version,
                ).single()
                if existing and existing["hash"] != digest:
                    raise KnowledgeConflict(
                        "A published context catalog version cannot be overwritten"
                    )
                missing = tx.run(
                    "UNWIND $systems AS s OPTIONAL MATCH (p:DKPackVersion {pack_id:s.blueprint_id,version:s.blueprint_version}) WITH s,p WHERE p IS NULL RETURN s.id AS id",
                    systems=document["systems"],
                ).data()
                if missing:
                    raise ValueError(
                        "Import the referenced blueprint versions before the context catalog"
                    )
                tx.run(
                    "MERGE (c:DKContextCatalog {dk_key:$key}) ON CREATE SET c.version=$key,c.document=$document,c.content_sha256=$hash,c.created_at=datetime()",
                    key=version,
                    document=payload,
                    hash=digest,
                ).consume()
                for group, label, rel in [
                    ("industries", "DKIndustryContext", "DK_HAS_INDUSTRY"),
                    ("regions", "DKRegionContext", "DK_HAS_REGION"),
                    ("systems", "DKSystemProfile", "DK_HAS_SYSTEM"),
                ]:
                    rows = [
                        {
                            "key": version + "|" + r["id"],
                            "id": r["id"],
                            "name": r["name"],
                            "document": json.dumps(r, sort_keys=True),
                        }
                        for r in document[group]
                    ]
                    tx.run(
                        f"UNWIND $rows AS row MATCH (c:DKContextCatalog {{dk_key:$version}}) MERGE (n:{label} {{dk_key:row.key}}) ON CREATE SET n.item_id=row.id,n.name=row.name,n.document=row.document,n.catalog_version=$version MERGE (c)-[:{rel}]->(n)",
                        rows=rows,
                        version=version,
                    ).consume()
                tx.run(
                    'UNWIND $systems AS s MATCH (n:DKSystemProfile {dk_key:$version+"|"+s.id}) MATCH (p:DKPackVersion {pack_id:s.blueprint_id,version:s.blueprint_version}) MERGE (n)-[:DK_REUSES_BLUEPRINT]->(p) WITH n,s UNWIND s.industry_ids AS industry MATCH (i:DKIndustryContext {dk_key:$version+"|"+industry}) MERGE (n)-[:DK_FOR_INDUSTRY]->(i)',
                    systems=document["systems"],
                    version=version,
                ).consume()
                tx.run(
                    'UNWIND $systems AS s MATCH (n:DKSystemProfile {dk_key:$version+"|"+s.id}) UNWIND s.regions AS region MATCH (r:DKRegionContext {dk_key:$version+"|"+region}) MERGE (n)-[:DK_FOR_REGION]->(r)',
                    systems=document["systems"],
                    version=version,
                ).consume()

            session.execute_write(write)
        return {
            "version": version,
            "systems": len(document["systems"]),
            "industries": len(document["industries"]),
            "regions": len(document["regions"]),
        }

    def domain_documents(self):
        return [
            DomainPack.model_validate_json(row["document"])
            for row in self.graph.read(
                "MATCH (p:DKPackVersion) WHERE p.document_kind = 'domain' RETURN p.document AS document ORDER BY p.pack_id, p.version"
            )
        ]

    def _latest_references(self, condition, ids):
        """Reference packs matching the condition, only the newest version of each pack."""
        rows = self.graph.read(
            "MATCH (p:DKPackVersion) WHERE p.document_kind='reference' AND p.scope='shared' "
            f"AND p.status = 'approved' AND p.verification = 'verified' AND coalesce(p.synthetic, false) = false AND {condition} RETURN p.document AS document",
            ids=ids,
        )
        latest = {}
        for row in rows:
            document = json.loads(row["document"])
            version = tuple(int(part) for part in document["version"].split(".") if part.isdigit())
            if document["id"] not in latest or version > latest[document["id"]][0]:
                latest[document["id"]] = (version, document)
        return [document for _, document in sorted(latest.values(), key=lambda item: item[1]["id"])]

    def context(self, domain_ids):
        """The domain's packs plus the packs they depend on (shared records such as Supplier live there), newest version each."""
        packs = self._latest_references("p.domain_id IN $ids", domain_ids)[:3]
        dependencies = {dep for pack in packs for dep in pack.get("depends_on", [])} - {pack["id"] for pack in packs}
        if dependencies:
            packs += self._latest_references("p.pack_id IN $ids", sorted(dependencies))[:3]
        return packs

    def proposals(self, project_id):
        return self.graph.read(
            "MATCH (p:DKProposedKnowledge {project_id: $project_id}) "
            "RETURN p.stage AS stage, p.document AS document, p.status AS status, p.provenance_kind AS provenance "
            "ORDER BY p.created_at DESC LIMIT 20",
            project_id=project_id,
        )

    def record_proposal(self, project_id, stage, actions, source_packs, actor_id):
        if not actions:
            return
        document = json.dumps(actions, sort_keys=True, separators=(",", ":"))
        key = f"proposal|{project_id}|{sha256((stage + document).encode()).hexdigest()}"
        with self.graph.driver.session(database=self.graph._settings.neo4j_database) as session:
            session.execute_write(
                lambda tx: tx.run(
                    "MERGE (p:DKProposedKnowledge {dk_key: $key}) "
                    "ON CREATE SET p.project_id=$project_id, p.stage=$stage, p.document=$document, "
                    "p.status='draft', p.provenance_kind='assumption', p.verification='needs_review', "
                    "p.actor_id=$actor, p.source_packs=$source_json, p.created_at=datetime() "
                    "WITH p UNWIND $sources AS source "
                    "MATCH (k:DKPackVersion {pack_id: source.pack_id, version: source.version}) "
                    "MERGE (p)-[:DK_DERIVED_FROM]->(k)",
                    key=key,
                    project_id=project_id,
                    stage=stage,
                    document=document,
                    sources=source_packs,
                    source_json=json.dumps(source_packs),
                    actor=actor_id,
                ).consume()
            )

    def import_knowledge(self, projection, domain_packs):
        """Atomic, additive import. Existing version content cannot be overwritten."""
        from app.knowledge_graph import schema
        from app.domain_knowledge.graph import write_plan

        plan = projection.write_plan()
        problems = lint(plan)
        if problems:
            raise ValueError("Invalid knowledge projection: " + "; ".join(problems))
        documents = []
        for pack in projection.packs.values():
            documents.append(
                {
                    "key": f"{pack.id}|{pack.version}",
                    "kind": "reference",
                    "document": pack.model_dump_json(),
                }
            )
        for pack in domain_packs:
            documents.append(
                {
                    "key": f"{pack.id}|{pack.version}",
                    "kind": "domain",
                    "document": pack.model_dump_json(),
                }
            )
            plan += write_plan(pack)
        for item in documents:
            item["hash"] = sha256(item["document"].encode()).hexdigest()
        with self.graph.driver.session(database=self.graph._settings.neo4j_database) as session:
            for statement in schema.constraints():
                session.run(statement).consume()
            session.run(
                "CREATE CONSTRAINT dk_proposed_knowledge_key IF NOT EXISTS FOR (p:DKProposedKnowledge) REQUIRE p.dk_key IS UNIQUE"
            ).consume()

            def commit(tx):
                conflicts = tx.run(
                    "UNWIND $documents AS d MATCH (p:DKPackVersion {dk_key:d.key}) "
                    "WHERE p.content_sha256 IS NOT NULL AND p.content_sha256 <> d.hash RETURN p.dk_key AS key",
                    documents=documents,
                ).data()
                if conflicts:
                    raise KnowledgeConflict(
                        "An existing knowledge version has different content; publish a new version"
                    )
                for step in plan:
                    tx.run(step["cypher"], step["params"]).consume()
                tx.run(
                    "UNWIND $documents AS d MATCH (p:DKPackVersion {dk_key:d.key}) "
                    "SET p.document=d.document, p.document_kind=d.kind, p.content_sha256=d.hash",
                    documents=documents,
                ).consume()
                for capability in projection.capabilities:
                    tx.run(
                        "MATCH (c:DKCapability {capability_id:$id}) SET c.document=$document",
                        id=capability.id,
                        document=capability.model_dump_json(),
                    ).consume()

            session.execute_write(commit)
        return self.counts()

    def counts(self):
        return self.graph.read(
            "MATCH (p:DKPackVersion) RETURN count(p) AS versions, "
            "count(CASE WHEN p.document_kind='reference' THEN 1 END) AS reference_versions, "
            "count(CASE WHEN p.document_kind='domain' THEN 1 END) AS domain_versions"
        )[0]

    def record_quality(self, reports):
        """Versioned assessments attach to immutable knowledge, never change its approval."""
        documents = [
            {
                "key": f"{r['pack_id']}|{r['pack_version']}",
                "assessment": f"{r['pack_id']}|{r['pack_version']}|quality:{r['quality_version']}|{r['content_sha256']}",
                "document": json.dumps(r, sort_keys=True),
                "hash": r["content_sha256"],
                "status": r["status"],
            }
            for r in reports
        ]
        with self.graph.driver.session(database=self.graph._settings.neo4j_database) as session:
            session.run(
                "CREATE CONSTRAINT dk_quality_key IF NOT EXISTS FOR (q:DKQualityAssessment) REQUIRE q.dk_key IS UNIQUE"
            ).consume()

            def commit(tx):
                missing = tx.run(
                    "UNWIND $items AS item OPTIONAL MATCH (p:DKPackVersion {dk_key:item.key}) "
                    "WITH item,p WHERE p IS NULL OR p.content_sha256 <> item.hash RETURN item.key AS key",
                    items=documents,
                ).data()
                if missing:
                    raise ValueError(
                        "Quality assessment must match an imported knowledge version exactly"
                    )
                tx.run(
                    "UNWIND $items AS item MATCH (p:DKPackVersion {dk_key:item.key}) "
                    "MERGE (q:DKQualityAssessment {dk_key:item.assessment}) "
                    "ON CREATE SET q.document=item.document,q.status=item.status,q.created_at=datetime() "
                    "MERGE (p)-[:DK_ASSESSED_BY]->(q)",
                    items=documents,
                ).consume()

            session.execute_write(commit)

    def quality_documents(self):
        return [
            json.loads(row["document"])
            for row in self.graph.read(
                "MATCH (p:DKPackVersion)-[:DK_ASSESSED_BY]->(q:DKQualityAssessment) "
                "RETURN q.document AS document ORDER BY p.pack_id,p.version,q.created_at"
            )
        ]


def repository():
    from app.api.dependencies import get_graph

    return Neo4jKnowledgeRepository(get_graph())


def _fingerprint(repo) -> str:
    global _last_fingerprint
    with _cache_lock:
        last = _last_fingerprint
    if last is not None and time.monotonic() - last[0] < _FINGERPRINT_REUSE_SECONDS:
        return last[1]
    value = repo.fingerprint()
    with _cache_lock:
        _last_fingerprint = (time.monotonic(), value)
    return value


def _cached(name, fingerprint, build):
    """Reuse the last build while the graph's knowledge is unchanged; rebuilding costs seconds of transfer and validation."""
    with _cache_lock:
        hit = _cache.get(name)
    if hit is not None and hit[0] == fingerprint:
        return hit[1]
    value = build()
    with _cache_lock:
        _cache[name] = (fingerprint, value)
    return value


def provider():
    repo = repository()
    return _cached("provider", _fingerprint(repo), lambda: _build_provider(repo))


def _build_provider(repo):
    from app.knowledge_graph.provider import GraphKnowledgeProvider

    result = GraphKnowledgeProvider(repo)
    if not result.packs():
        raise GraphUnavailableError("Design knowledge has not been imported into Neo4j")
    # Read per-project proposals separately; they never become shared verified knowledge.
    result.context = repo.context
    result.proposals = repo.proposals
    result.record_proposal = repo.record_proposal
    result.source = "neo4j"
    return result


def domain_store():
    repo = repository()
    return _cached("domains", _fingerprint(repo), lambda: _build_domain_store(repo))


def _build_domain_store(repo):
    packs = repo.domain_documents()
    if not packs:
        raise GraphUnavailableError("Domain knowledge has not been imported into Neo4j")
    return ReadOnlyDomainStore(tuple(packs))
