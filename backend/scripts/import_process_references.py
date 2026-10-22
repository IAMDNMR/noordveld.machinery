"""Import curated references into Neo4j; rerunning identical versions is idempotent."""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import get_settings
from app.graph.client import GraphClient
from app.design_studio.knowledge.process_references import load_references
from app.knowledge_graph.process_references import import_references, read_references


if __name__ == "__main__":
    graph = GraphClient(get_settings())
    try:
        counts = import_references(graph, load_references())
        counts["stored_versions"] = len(read_references(graph))
        print(json.dumps(counts))
    finally:
        graph.close()
