"""Immutable, additive storage for sourced process references. No project writes."""

from hashlib import sha256
import json

from app.design_studio.knowledge.process_references import validate_references
from app.knowledge_graph.neo4j import KnowledgeConflict


def import_references(graph, documents):
    references = validate_references(documents)
    profiles, sources, claims, evidence, endpoints = [], [], [], [], []
    for reference in references:
        key = f"{reference.id}|{reference.version}"
        document = json.dumps(
            reference.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        profiles.append(
            {
                "key": key,
                "id": reference.id,
                "version": reference.version,
                "name": reference.name,
                "domain_id": reference.domain_id,
                "blueprint_id": reference.blueprint_id,
                "blueprint_version": reference.blueprint_version,
                "system": reference.system,
                "review_state": reference.review_state,
                "document": document,
                "hash": sha256(document.encode()).hexdigest(),
            }
        )
        for source in reference.sources:
            sources.append(
                {"key": key + "|" + source.id, "reference": key, **source.model_dump(mode="json")}
            )
        for claim in reference.claims:
            claim_key = key + "|" + claim.id
            claims.append({"key": claim_key, "reference": key, **claim.model_dump(mode="json")})
            evidence.extend(
                {"claim": claim_key, "source": key + "|" + source_id}
                for source_id in claim.source_ids
            )
            if claim.kind == "relationship":
                endpoints.append(
                    {
                        "claim": claim_key,
                        "subject": key + "|" + claim.subject,
                        "target": key + "|" + claim.target,
                    }
                )
    with graph.driver.session(database=graph._settings.neo4j_database) as session:
        for label in ("DKProcessReference", "DKReferenceSource", "DKReferenceClaim"):
            session.run(
                f"CREATE CONSTRAINT {label.lower()}_key IF NOT EXISTS FOR (n:{label}) REQUIRE n.dk_key IS UNIQUE"
            ).consume()

        def commit(tx):
            conflicts = tx.run(
                "UNWIND $rows AS row MATCH (n:DKProcessReference {dk_key:row.key}) WHERE n.content_sha256 IS NULL OR n.content_sha256 <> row.hash RETURN n.dk_key AS key",
                rows=profiles,
            ).data()
            if conflicts:
                raise KnowledgeConflict(
                    "A process reference version is immutable; publish a new version"
                )
            missing = tx.run(
                "UNWIND $rows AS row OPTIONAL MATCH (p:DKPackVersion {pack_id:row.blueprint_id,version:row.blueprint_version}) WITH row,p WHERE p IS NULL RETURN row.blueprint_id AS id",
                rows=profiles,
            ).data()
            if missing:
                raise ValueError(
                    "Import the exact blueprint versions before their process references: "
                    + str(missing)
                )
            tx.run(
                'UNWIND $rows AS row MATCH (p:DKPackVersion {pack_id:row.blueprint_id,version:row.blueprint_version}) MERGE (n:DKProcessReference {dk_key:row.key}) ON CREATE SET n.reference_id=row.id,n.version=row.version,n.name=row.name,n.domain_id=row.domain_id,n.system=row.system,n.review_state=row.review_state,n.scope="shared",n.document=row.document,n.content_sha256=row.hash,n.created_at=datetime() MERGE (n)-[:DK_REFERENCES_BLUEPRINT]->(p)',
                rows=profiles,
            ).consume()
            tx.run(
                "UNWIND $rows AS row MATCH (p:DKProcessReference {dk_key:row.reference}) MERGE (s:DKReferenceSource {dk_key:row.key}) ON CREATE SET s.source_id=row.id,s.title=row.title,s.url=row.url,s.publisher=row.publisher,s.product_version=row.product_version,s.checked_on=row.checked_on MERGE (p)-[:DK_HAS_REFERENCE_SOURCE]->(s)",
                rows=sources,
            ).consume()
            tx.run(
                'UNWIND $rows AS row MATCH (p:DKProcessReference {dk_key:row.reference}) MERGE (c:DKReferenceClaim {dk_key:row.key}) ON CREATE SET c.claim_id=row.id,c.kind=row.kind,c.text=row.text,c.locator=row.locator,c.review_state="draft" MERGE (p)-[:DK_HAS_REFERENCE_CLAIM]->(c)',
                rows=claims,
            ).consume()
            tx.run(
                "UNWIND $rows AS row MATCH (c:DKReferenceClaim {dk_key:row.claim}),(s:DKReferenceSource {dk_key:row.source}) MERGE (c)-[:DK_SUPPORTED_BY]->(s)",
                rows=evidence,
            ).consume()
            tx.run(
                "UNWIND $rows AS row MATCH (r:DKReferenceClaim {dk_key:row.claim}),(a:DKReferenceClaim {dk_key:row.subject}),(b:DKReferenceClaim {dk_key:row.target}) MERGE (r)-[:DK_RELATION_SUBJECT]->(a) MERGE (r)-[:DK_RELATION_TARGET]->(b)",
                rows=endpoints,
            ).consume()

        session.execute_write(commit)
    return {
        "references": len(profiles),
        "sources": len(sources),
        "claims": len(claims),
        "evidence_links": len(evidence),
        "relationships": len(endpoints),
    }


def read_references(graph):
    return [
        json.loads(row["document"])
        for row in graph.read(
            'MATCH (n:DKProcessReference) WHERE n.review_state <> "deprecated" RETURN n.document AS document ORDER BY n.reference_id,n.version'
        )
    ]
