# Studio gap closure — 19 October 2026

This supersedes the earlier 40-open-finding catalog report. The user explicitly selected: **keep legacy packs as reference; generate from reusable blueprints**.

## Knowledge and generation

- Neo4j contains 39 immutable knowledge versions: 36 reference-pack versions and 3 domain-document versions. The active catalog has 18 packs.
- `noordveld_transport` and `noordveld_spare_parts` now have new immutable `2026.10.19.1` versions marked `source_reference`. Their sourced facts, business rules, processes, evidence and previous versions remain stored.
- Automatic planning and conversational adoption select executable blueprints, even when a prompt names Noordveld. Historical reference designs remain inspectable; compiling their workflows is blocked, including launching their downloaded runtime.
- Quality version 2 separates implementation findings from source observations. Active reusable blueprints have **0 structural findings**. The two legacy sources retain **34 reference execution observations**; these were not rewritten or presented as implemented business logic.
- Two reusable integration contracts require customer configuration. A zero structural finding count is not business approval or production certification.
- Process variants retain source, family, region and verification metadata. No Zoho or other vendor policy has been invented without source material.

## Generated application behavior

- Task forms use their declared fields and relationships rather than repeating whole-entity forms. Server checks enforce current task, responsible role, linked record, process revision and field scope for task-context edits.
- General record maintenance retains its own server role/ownership checks; it is not implicitly restricted to a running process task.
- Record history shows actor, time and changed field names without logging field values. Saving a task record returns to the process and refreshes labels.
- Semantic task/entity icons, distinct process-based layouts, detailed activity views and saved palette choices are shared across domain blueprints.
- Signed inbound record exchange and scoped outbound snapshot export are generated as portable standard-library Python. Connections are off until configured. Tenant, business role, mapped entities and fields are server-owned.
- HMAC signatures cover timestamp, method, exact request target and raw body, expire after five minutes, and never use browser login cookies. Incoming event IDs have atomic durable receipts: retries return the same receipt; conflicting payloads fail. Record validation, reference checks, optimistic revision checks and role ownership still apply.
- Export exposes mapped fields only, scoped to the configured tenant and role, in bounded pages. It is snapshot pagination, not a change feed.
- Provider-specific delivery, retries against a remote service, binary document storage, production identity and public deployment remain explicit implementation/configuration work after the customer chooses systems. Document metadata exchange does not claim to store document bytes.
- Each generated app owns its schema and operational database. It does not automatically connect to Noordveld catalogue/order APIs. Integration setup instructions are included in each export.

## Reviews, repairs and persistence

- New stage reviews bind to content digests. A later edit reopens the earliest changed review instead of silently preserving completion. Existing unhashed reviews retain backward-compatible handling.
- Duplicate reconciliation preserves sourced definitions, rewires typed references and refuses conflicting executable policies or exception outcomes. Business assumptions and formal approvals are not automatically confirmed.
- The existing TMS project was repaired at revision 11: duplicate rules/exceptions/requirements were reconciled and requirement links repaired. Its remaining blocking finding is formal process approval, which has not been impersonated or bypassed.
- Explicit three-way reference upgrades preserve local edits, add upstream changes and reject conflicting changes. They require review and do not silently rewrite saved projects or manually edited screens.
- Five local Studio projects and their 23 original revisions were migrated to Neo4j with ownership and audit metadata. The subsequent TMS repair adds one revision. The active local server uses graph project storage in namespace `studio-local-site`.
- Migration backup: `C:/Users/iamdn/AppData/Local/Temp/studio-project-migration-backup-ibyhfg_2/projects.json`. Original SQLite was retained. Restoring this older backup alone would omit later graph writes.
- This migration concerns Studio specifications/history and knowledge. Generated application records remain in each application's own database; local demo identity/organization stores were not represented as a production authentication migration.

## Verification

See `STUDIO_FINAL_QUALITY_2026_10_19.json` for the live graph-backed catalog assessment. Browser verification confirmed the saved TMS revision and focused generated task editing with record history. Frontend production build and the focused preview/process/icon/role tests pass. The implementation tests include signed HTTP exchange without a browser session, invalid signatures, stale events, duplicate receipts, rollback, field/entity/tenant scope, role ownership, review freshness, reference upgrade conflicts, graph migration rollback, and standalone generated runtime execution.

Final result: 104 backend tests passed; 8 focused frontend tests passed; frontend production build and generated JavaScript syntax checks passed. One existing python_multipart deprecation warning remains.
