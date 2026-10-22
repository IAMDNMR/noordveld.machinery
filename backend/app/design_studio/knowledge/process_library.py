"""Versioned process variants from the knowledge provider, preserving source boundaries."""


def process_library(provider, adopted=(), focus=()):
    items = []
    for pack in sorted(provider.packs(), key=lambda item: item.id):
        if not pack.verified or (pack.company and pack.id not in adopted) or (pack.id not in adopted and pack.domain_id not in focus):
            continue
        for workflow in pack.workflows:
            context = next((c for c in pack.process_contexts if c.workflow_id == workflow.id), None)
            provenance = context.provenance if context else pack.provenance
            items.append(
                {
                    "id": f"{pack.id}|{pack.version}|{workflow.id}",
                    "pack_id": pack.id,
                    "pack_version": pack.version,
                    "workflow_id": workflow.id,
                    "name": workflow.name,
                    "domain_id": pack.domain_id,
                    "layer": pack.layer,
                    "usage": pack.usage,
                    "company": pack.company.name if pack.company else None,
                    "family_id": context.family_id if context else pack.domain_id,
                    "variant": context.variant if context else workflow.name,
                    "region": context.region if context else "Unspecified",
                    "source_system": context.source_system if context else None,
                    "source": provenance.reference,
                    "verification": provenance.verification,
                    "synthetic": pack.synthetic,
                    "status": pack.status,
                    "steps": len(workflow.states),
                    "decisions": sum(s.kind == "branch" for s in workflow.states),
                    "exceptions": sum(s.kind == "exception" for s in workflow.states),
                    "depends_on": pack.depends_on,
                }
            )
    return items
