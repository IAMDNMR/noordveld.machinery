"""Design-time domain knowledge: reference packs behind a provider interface. Read-only; never touches Neo4j."""

from app.design_studio.knowledge.provider import (
    KnowledgeProvider,
    LocalKnowledgeProvider,
    PackUnavailable,
    get_knowledge_provider,
)
from app.design_studio.knowledge.models import KnowledgeDomain, ReferencePack

__all__ = [
    "KnowledgeDomain",
    "KnowledgeProvider",
    "LocalKnowledgeProvider",
    "PackUnavailable",
    "ReferencePack",
    "get_knowledge_provider",
]
