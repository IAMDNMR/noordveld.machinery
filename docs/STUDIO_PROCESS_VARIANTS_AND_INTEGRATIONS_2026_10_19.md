# Process variants and customer-selected integrations

Implemented after the user's clarification on 19 October 2026.

Generated applications own their schemas and data. They do not automatically call the existing Noordveld catalogue or order APIs. Exported `integrations/contracts.json` declares each exchange, its events, direction, generated entity schema references, and required configuration. `integrations/README.md` explains mapping, service identity, idempotency, retries and failure handling. No endpoint, provider, credential or successful connection is fabricated.

## Reusable process knowledge

Knowledge packs can optionally declare `process_contexts`. An entry names an existing workflow and supplies a process family ID, variant name, region, source system and provenance. Unknown workflows and duplicate contexts are rejected. The default empty collection is omitted from serialization, preserving existing immutable pack content hashes.

Example context to add to a **new version** of a pack after collecting customer information:

```json
{
  "workflow_id": "existing_workflow_id",
  "family_id": "transport_delivery",
  "variant": "Customer-specific delivery process",
  "region": "European operations",
  "source_system": "Customer-selected TMS",
  "provenance": {
    "kind": "user_provided",
    "reference": "Customer process workshop or source document",
    "verification": "needs_review"
  }
}
```

This example is a schema illustration, not an imported workflow or verified vendor process. Actual vendor workflows must come from supplied or researched documentation; their names alone do not establish their business behavior.

Company differences use the existing company layers, dependencies and explicit overrides. A generic shared process can therefore be reused without mixing one company's rules into another's application. The process library excludes company packs unless adopted by the current project.

## Graph and UI

Neo4j stores versioned pack documents and semantic process/activity nodes. Process nodes now include family, variant, region, source system and source reference. Activity nodes include task field/relationship contracts and pre/postconditions. Transition relationships retain the exact condition kind, field and JSON value; inequality is no longer displayed as equality.

Graph read-back verified 37 pack versions and 42 process nodes across versions. The current shared library exposes 13 process entries, plus the company layers adopted by a project. These are existing stored processes, not a claim that every TMS vendor is represented.

Business Process now defaults to a detailed activity view, with a flow-diagram alternative. Each activity shows ownership, permission, inputs, changed fields and relationships, rule executability and source, exceptions, linked requirements and onward conditions. Selecting a route opens its existing step inspector; it does not execute a business action.

Domain Knowledge includes searchable process-library entries with source and verification details. The library uses the active Neo4j provider and preserves pack/version identity.

## Still open

The catalog repair reduced the original findings from 132 to 40. The remaining 26 legacy executable-rule implementations, 3 prose conditions, 5 execution-identity/permission gaps and 6 actual integrations remain listed in `STUDIO_KNOWLEDGE_QUALITY_AFTER_FIXES_2026_10_19.json`. Generic integration handoff contracts do not resolve an unimplemented adapter. No unimplemented rule was converted into a passing constant or silently removed.
