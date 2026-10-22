"""Import local versioned domain knowledge into the configured Neo4j database."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings
from app.graph.client import GraphClient
from app.design_studio.knowledge.provider import LocalKnowledgeProvider
from app.knowledge_graph.projection import project
from app.knowledge_graph.neo4j import Neo4jKnowledgeRepository
from app.domain_knowledge.models import DomainPack


def main():
    source = LocalKnowledgeProvider()
    root = Path(__file__).resolve().parents[1] / "app" / "domain_knowledge"
    domains = [DomainPack.model_validate_json(p.read_text(encoding="utf-8")) for folder in ("packs", "packs_eu") for p in sorted((root / folder).glob("*.json"))]
    projection = project(source.packs(), source.capabilities())
    graph = GraphClient(get_settings())
    try:
        from app.design_studio.knowledge.quality import catalog_report
        repo = Neo4jKnowledgeRepository(graph)
        counts = repo.import_knowledge(projection, domains)
        report = catalog_report(source)
        repo.record_quality(report['packs'])
        from app.design_studio.knowledge.system_context import load_catalog
        context = repo.import_context_catalog(load_catalog())
        from app.design_studio.knowledge.process_references import load_references
        from app.knowledge_graph.process_references import import_references
        references = import_references(graph, load_references())
        print(json.dumps({"knowledge": counts, "quality": report['summary'], "context_catalog": context, "process_references": references}))
    finally:
        graph.close()


if __name__ == "__main__":
    main()
