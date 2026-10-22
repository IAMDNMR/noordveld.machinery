# Design Studio refinement — 15 October 2026

Continues [STUDIO_VOICE_FIRST_2026_10_15.md](STUDIO_VOICE_FIRST_2026_10_15.md). Nothing was rebuilt; the conversation engine, approvals,
generator and runtime were kept and extended. Nothing was committed, pushed or deployed. Neo4j was not written to.

## What changed

### Studio workspace (`frontend/src/pages/StudioWorkspacePage.*`, `frontend/src/components/studio/`)

- **Top bar** across the workspace and assistant: back to projects, breadcrumb (project › stage), whether the language model is
  active, save state (`Saved · revision N`; every change is already a server revision, so there is no manual save), History,
  Preview (the Screens visual preview) and **Generate application**. Generate always opens the Generate stage, which says what is
  still missing; it runs the generator immediately only when the design approval is valid and screens exist.
- **Project heading and pipeline**: domain icon, name, phase badge (Draft / Process approved / Design approved / Generated — from
  approvals and the generator's result only) and a horizontal nine-stage pipeline showing each server-computed status.
- **Requirements** is no longer a 12-input form. It shows *What I'm building for you* (goal, key modules, main users, domain and
  adopted reference knowledge), a preview of the main process path, and *Still to clarify* as a list where **Answer** hands the
  question to the assistant (typing inline remains a secondary option).
- **Assistant panel tabs**: AI Assistant, Project context (next step, domain, adopted packs, which services are really connected),
  Validation (blocking count, approvals, stages waiting on you, fix-with-assistant).
- **Live voice strip** in the workspace while listening, transcribing or speaking, with a level-driven waveform and Stop. It only
  appears for real microphone/speech states; unavailable voice is still shown as unavailable.
- **Process designer**: the diagram fits the width and grows to 640px instead of shrinking everything into 440px (labels are
  readable for 20-step processes); a floating **step inspector** edits the step through the same typed actions the assistant uses
  (rename, responsible role, inputs/outputs, linked requirements, approval before, step after) and shows transitions with
  conditions, rules (confirmed/assumption), exceptions and pending business decisions. Structural, role and data-access edits come
  back as reviewable proposals.
- Fixed defects: a CSS reset (`.sw button { color: inherit }`) out-ranked button classes, so primary buttons had dark text on green,
  the send icon was invisible and the microphone glyph was dark; role permission chips stretched into blobs; an approver who
  cannot edit got a permission error when the page tried to prepare screens on their behalf (now explained as a hand-off); the
  coverage check printed all unsupported items twice. Phone layout hides the sidebar (the pipeline replaces it).

### Assistant and prompts (`backend/app/assistant/`)

- New typed action **`set_step_data{step, reads[], writes[]}`** — a step's inputs and outputs. Unknown entities are refused, not
  dropped; order-only changes are recognised as no change; it is review-gated because it changes access boundaries.
- The planner prompt (`studio_agent.SYSTEM`, the only language-model prompt for Studio turns) now also says: only the listed
  actions exist and unsupported edits must not be faked with near-duplicates; external systems are recorded as dependencies and
  never claimed as connected; changes to process, roles or data access are explained in one sentence. A test asserts the prompt
  documents every action the engine accepts. `assistant/design.py` is the model-free helper of the structured editor, not a
  competing prompt; it was left as is.

### Generated application (`backend/app/design_studio/runtime_*`, `compiler.py`)

- The generator writes a deterministic **presentation profile** into `schema.json` (archetype `operations` / `service` /
  `requests` / `workspace` from the domain and goal; the specification's own accent colour when it is not the default). The running
  application uses it for its navigation vocabulary (e.g. *Control tower* and *My work queue* for transport), layout defaults (board
  vs list) and visual identity. Role display names come from the server.
- New client: role-aware home (in progress / mine / exceptions / completed, my queue, where work is per process), process **boards**
  by step, an instance page with a progress stepper, record links, the explicit next paths with their conditions and a readable
  history, filterable record lists, record forms with client-side required-field messages plus the server's validation, and clear
  loading, empty, success and error states. Sign-in lists identities as buttons.
- New compiler check **`runtime_records_creatable`** (warning): reports records that need a related record no role in the
  application can create. For the conversation-built TMS it reports Transport request → Order, Transport plan → Carrier and
  Pick task → OrderLine/Warehouse: on a fresh database those records cannot be created inside this application. This was found by
  using the generated application, and is now said at generation time instead.

## Verified

- Backend: full offline suite 544 passed, 316 skipped (baseline 540 / 316); new tests for `set_step_data`, prompt/engine alignment,
  the presentation profile and the creatability check.
- Frontend: all tests pass (baseline 411; 3 new workspace tests: pipeline/top bar, conversational answering, inspector typed edits); typecheck
  clean; lint has no errors (warnings only, as before); production build succeeds.
- Browser (headless Edge, 1440×900, plus 1024×768 and 390×844): a real language-model turn (NVIDIA), decisions recorded, process
  approved by a second person, screens generated by the editor, design approved, application generated from the top bar
  (9/9 stages complete), its 3 independent tests passed, launched on 127.0.0.1. The synthetic TMS runtime was driven through its UI:
  validation message, carrier/vehicle/shipment created, transport started and advanced with linked records, reload keeps state,
  board view, and the dispatcher's role-limited view.

## Not verified / known limits

- Voice end to end was not re-run (needs a microphone or recorded fixture and spends Deepgram credit); the strip and states were
  checked visually and the existing voice tests pass.
- The conversation-built TMS has 84 items without executable bindings (system-managed attributes, prose rules) and the
  creatability gaps above, so many of its actions are refused by design. Closing them needs value providers and rule bindings in
  the specification, not UI work. Follow-up: [TMS_RUNTIME_COVERAGE_2026_10_15.md](TMS_RUNTIME_COVERAGE_2026_10_15.md) (now 67 items; records creatable).
- The ER diagram still draws straight relationship lines that cross on dense models.

## Database and Neo4j review (no writes)

- Ownership is already separated: reusable domain knowledge = versioned packs (content SHA-256, approval workflow) in the domain
  store; project specifications = immutable revisions with actor/operation audit and digest-bound approvals (SQLite locally;
  PostgreSQL adapter present but not activated, see `backend/DESIGN_STUDIO_ACTIVATION.md`); operational transactions = each
  generated application's own SQLite with tenant scoping and an audit table; generated artefacts = manifest with per-file digests
  and source traces. Commerce demo data lives in AuraDB.
- `design_studio/neo4j_store.py` (namespaced `DS*` documents) is not wired to any route. The earlier read-only inspection
  (`docs/STUDIO_GRAPH_INSPECTION_2026_10_15.json`) found no Studio or domain-knowledge labels, one constraint, and duplicate
  part/machine keys, with `environment_verified: false`.
- The only configured Neo4j is the shared AuraDB behind the live commerce demo; no isolated development graph exists. Writing Studio
  or domain-knowledge structure there would mix reusable knowledge and design documents into the operational demo graph, so it was
  not done. Before any graph change: provision a separate development instance, run the `neo4j_store` contract tests against it,
  take an export of AuraDB, and resolve the duplicate part/machine keys with a uniqueness constraint in that environment first.
