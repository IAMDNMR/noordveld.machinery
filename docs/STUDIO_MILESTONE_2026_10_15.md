# Enterprise Studio milestone — 15 October 2026

## Baseline and safe implementation checklist

The starting tree contains extensive uncommitted Studio, domain, organization and TMS work. It also contains an existing backend/.env modification. Preserve all of it; do not commit, deploy, migrate, or activate providers.

- [x] Inspect identity, organization gates, project stores, process schemas, compiler, domain graph and assistant contracts.
- [x] Frontend baseline: 20 files, 364 tests passed.
- [ ] Backend baseline with environment loading bypassed and remote sockets denied (loopback is needed by Windows asyncio).
- [ ] Extend saved-project conversation with evidence, validated proposals, review and revision conflicts.
- [ ] Integrate the conversation panel into the visual workspace with recoverable states.
- [ ] Verify authorization, proposal tampering, stale revisions, provenance and UI behavior.
- [ ] Run broader checks and record exact results and remaining gaps.

## Architecture and safety findings

Existing identity is demo identity, explicitly restricted to loopback. Deployed Studio fails closed pending trusted identity and approved persistence. Organization membership, controlled invitations, separate domain approval, project ownership, application grants, versioned processes, deterministic generation and regeneration ownership already exist. They must be verified, not replaced.

Operational Neo4j access is in app/graph/client.py, with additional write transactions in app/canonical/store.py and generation/export callers in app/canonical. Domain knowledge uses a separate disabled GraphDomainProvider: named read queries and inert schema/load plans only. Checked-in graph/schema CSVs are the schema reference; no live schema inspection is performed. No independently verified development graph is available for this work. Separate instance credentials and operation-specific authorization remain prerequisites; DK labels alone do not establish isolation.

Claude and Deepgram had disabled provider contracts when this milestone was written, and it did not enable external integrations based merely on key presence. (Superseded later the same day: the owner explicitly asked for voice and a conversational assistant, so speech and the language model are now enabled by deliberate configuration with kill switches; see STUDIO_VOICE_FIRST_2026_10_15.md.) A deterministic, explicitly labeled assistant can support a bounded workflow without inventing policy or claiming language-model reasoning.

The complete requested production milestone remains larger than the verified local capability. This report will distinguish implemented work, inherited capabilities, external blockers, and remaining implementation gaps.
