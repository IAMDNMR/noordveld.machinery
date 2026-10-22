# Design Studio stage and generated-application audit

Audit date: 19 October 2026. Scope: stages 5–9, assistant mutations, runtime authorization, validation, export contents, and saved TMS revision history. This is an inspection report; no project data, approvals, or application code was changed during this audit.

## Main conclusion

The system produces a useful local demonstration application, but the polished Studio prototype, exported React preview, and operational Python application are three different rendering paths. It does not yet deliver the reviewed screen experience as a production application. Rules and access also have mismatches between their Studio presentation and runtime behavior.

## Saved TMS evidence

Project: `app_6bcc2933-1345-47c2-9ead-25381a238270`, revision 10. Read from the existing local SQLite store in read-only mode.

- 16 entities, 8 roles, 1 workflow, 7 actionable steps, 10 saved screens (including the additional starter screen).
- Stages 1–7 recorded as reviewed. Neither formal process nor design approval exists.
- 12 rules, all assumptions. Six have executable bindings. Six are unused prose duplicates.
- Revision 3 introduced roles, rules, and step assignments. Revision 7 changed the rules. Revisions 4–6 and 8–10 did not change roles or step role/permission assignments. There is no evidence that the later roles stage rewrote the TMS roles.
- Five design errors: two `EXCEPTION_NO_RESOLUTION`, two `REQ_UNCOVERED`, and `PROCESS_NOT_APPROVED`. Design approval is also absent; it is a separate gate.
- A dry compilation in memory, using the local reference provider, returned `blocked` and produced 56 inspectable file entries. Nothing was approved, launched, deployed, or written into the project by this compilation.
- Static checks: 10 pass, one warning (`runtime_business_coverage`). The warning identifies six unbound rules and the missing carrier tracking integration. Passing static checks does not override design blockers.
- Coverage reports 7/7 actionable steps with bound rules. That is structural coverage, not proof of business completeness: the six newly added prose rules are unused and therefore do not block those steps.

## Findings in priority order

### 1. Reviewed UI is not the generated operational UI — high

`frontend/src/components/studio/views/ApplicationPreview.tsx` and `BusinessScreenPreview.tsx` implement the Studio prototype. `backend/app/design_studio/codegen.py:24` contains a separate basic React mockup with disabled inputs. `runtime_generation.py:161` builds a runtime schema from entities, workflows, roles, and rules, but does not include the screen component tree. `runtime_app.js:333` constructs process pages itself.

Consequences: layout edits, the new application shell, preview-only theme choices, and component-level screen design are not faithfully reproduced in the operational export. The runtime uses whole-record editing through “Open record”; it does not consume the task-specific `input_fields` / `input_relationships` contracts to render the same focused forms as the Studio preview.

Recommended correction: one shared application renderer and saved presentation configuration, with the same navigation and task forms used by preview and runtime. Keep simulation mode explicit, and test an export against the reviewed screens.

### 2. Rules stage adds prose instead of completing executable logic — high

`backend/app/assistant/studio_actions.py:464` creates every conversational rule with `execution=None`, always as an assumption, with no equivalent-rule deduplication or step linkage. The guided rules stage permits `add_rule`, `add_exception`, and `answer_decision`, not a general update/bind-rule action (`guided.py:11`).

This happened in the saved TMS: six existing executable transport rules acquired six prose counterparts at revision 7. All six new rules are unused. They do not replace or strengthen the original executable rules. A user can therefore see a requirement expressed as a rule without it affecting application behavior.

Recommended correction: reconcile existing rules by stable identity; add typed operations to edit executable bindings, link rules to steps, and update decision routes. Explain explicitly when a rule remains documentation. Validate duplicate and unused rules before calling the stage complete.

### 3. Access matrix does not describe effective runtime access — high

`RolesView.tsx:12` derives R/W only from the steps assigned to a role. `runtime_server.py:109` additionally grants access to entity owner roles, and requires matching role plus a held step permission for step-derived access. Field ownership is separately enforced in `save_record`.

Concrete TMS omissions: owner access for Customer, Supplier, Item, Location (Master data steward); Stock level (Stock clerk); Customer order and Order line (Order agent) is absent from the step-only matrix.

The matrix also conflates create/update access and does not show field restrictions. A step assignment lacking its permission can appear to allow data access in Studio although the runtime refuses it. Conversely, owner access can work despite no visible matrix entry.

Recommended correction: compute a shared effective-access contract showing read, create, update, step execution, and field ownership, including the reason for each grant. Use it for UI explanations and runtime checks.

### 4. “Completed” means draft reviewed, not currently valid — medium/high

`guided.py:40` overwrites computed statuses for reviewed stages with `completed` and clears finding counts. Readiness is shallow: rules requires a workflow; roles requires at least one role. Later edits do not automatically revoke those draft review markers.

Formal approval is better protected: `approval.py:19` hashes the business/process content and entire design, so changes make approvals stale. However, earlier sidebar stages can remain green while those approvals are stale or defects exist.

Recommended correction: retain separate reviewed/valid/approved states, show current findings, and mark affected reviews outdated after changes. Regenerate impacted screens after rules or role edits, preserving manual edits and identifying conflicts.

### 5. Generation success is not an execution or deployment certificate — high for release

`compiler.py:430` checks JSON, references, permission contracts, hashes, and Python syntax. It explicitly does not execute generated code. Unsupported runtime capabilities and missing record-creation dependencies are warnings. `compile_project` can return `generated` with those warnings if other gates pass.

Generated tests can be run separately, but compiler success does not prove each required business journey or every nonfunctional requirement works. The current TMS is blocked for actual design/approval reasons, independently of these static passes.

Recommended correction: distinguish artifact generated, automated tests passed, business journeys passed, and deployable. Mandatory unimplemented requirements should block a production release even if a demo artifact is allowed.

### 6. Runtime record permissions are broader than the active task — explicit policy gap

`runtime_server.py:109` grants entity writes if any permitted step for the role writes that entity, or if the role owns it. `save_record` does not require a workflow instance/current-state context. Field owner and system-managed restrictions are enforced, but task `input_fields` are not server-side permission restrictions.

Thus a task-specific form does not imply that the same role is technically limited to those fields at that process stage. This is an intentional current model, but insufficient if requirements say “editable only before dispatch” or “only the assigned shipment.” Tenant isolation exists; per-record assignment/state policies are not generated by this model.

Recommended correction: explicitly model and enforce stage-dependent writes and record-level policies where required, and retain separate master-data maintenance permissions.

### 7. Local runtime is not a production hosting package — high for deployment

The runtime uses Python standard-library HTTP, SQLite, synthetic demo identities, and loopback hosting. `runtime_server.py:494` requires `--demo` and a dedicated temporary-directory data path. The generated README documents these limits.

Not generated here: production identity integration, a production PostgreSQL data layer/migrations, production deployment configuration, automatic GitHub publishing, Vercel provisioning, App Store packaging, backup/restore operations, or external carrier adapters. An OpenAPI contract is included, but its process-derived operation paths are not automatically separate implemented endpoints; the operational server exposes generic record/process routes.

Existing SQLite data survives restarts when the same directory and specification are used. A changed design fingerprint refuses the existing database rather than migrating it. This protects data from silent reinterpretation, but leaves a real upgrade/migration requirement. Temporary storage is not a durable hosting plan.

### 8. Audit logging exists but lacks a full record-change trail in the UI — medium

`runtime_server.py:126` records tenant, actor, resource, action, and timestamp transactionally. Process events include the path and rule outputs; process history is exposed. Record events currently record the new revision, not field-level before/after values (`save_record`). There is no equivalent generated record-history endpoint/UI in the inspected routes.

Recommended correction: add appropriately redacted record change details and record history views, plus retention/export requirements. Do not describe the current log as complete field-level auditability.

## How stages actually run

1. Knowledge adoption can populate roles, rules, entities, and workflows together. Sequential review does not mean those definitions are first created at their named stage.
2. “Continue” records the reviewed stage and asks the model to prepare the next draft (`studio_conversation.py:470`). Stage-specific allowlists filter the model's proposed actions.
3. In guided mode most allowed changes are saved as editable drafts immediately. Validation-stage policy decisions retain a separate proposal/review path. Schema validation and expected revision checks protect the save.
4. Screens are generated from the process. During guided execution screens are regenerated in screen/check stages, not every role/rule change. Existing manually modified generated screens are preserved.
5. Assigning a role to a step grants the required permission to the new role (`studio_actions.py:605`). It does not remove the permission string from the old role. Runtime step execution still requires both role identity and permission, so the leftover permission alone does not let the old role perform that reassigned step. There is no general guided permission-revocation action in the inspected allowlist.
6. Validation combines graph/reference/coverage findings with formal process/design approval. Unsupported runtime behavior is additionally reported during compilation. These are different layers and should be presented separately.
7. Generation creates deterministic source/configuration files and manifests, then static checks. Tests and local launch are separate operations.

## What the 56-file TMS output includes

| Area | Included | Current boundary |
| --- | --- | --- |
| UI | React design mockup; separate operational HTML/JS/CSS | Neither faithfully exports the new Studio application prototype |
| Backend | Standalone Python HTTP server | Local demo target |
| Storage | SQLite records, process instances, sessions, audit events | No automatic migrations or production database adapter |
| Data contracts | 16 JSON Schemas, TypeScript models, validation and relationship libraries | Contracts do not imply all business integrations exist |
| Process | States, transitions, role/permission checks, executable comparisons/value decisions | No arbitrary prose execution; no general calculation engine |
| Access | Tenant sessions, role/permission checks, entity and attribute ownership | Synthetic login; no generated record-level assignment policy |
| Quality | Generated runtime tests, validation tests, static compiler checks | Full business coverage and deployment readiness remain separate |
| Documentation | README, BUILD guide, specification, rules, roles, traceability, provenance, manifests | No automatic hosting or production rollout |

## Verification

Command run from `backend/`:

```text
python -m pytest tests/test_generated_runtime.py tests/test_studio_roles.py tests/test_studio_guided.py tests/test_task_screen_inputs.py tests/test_tms_runtime_fresh_database.py tests/test_transport_template.py -q
```

Result: 40 passed, 1 failed. The failure is `test_discovery_finds_the_transport_domain_and_its_pack`: it expects `noordveld_transport` in the identified domain's pack list, but gets an empty list. This is a test/behavior discrepancy to resolve; it does not establish that all domain adoption fails. No code was changed during this audit.

Passing tests cover synthetic generated-runtime lifecycles, persistence, denied actions, tenant separation, exception recovery, changed-specification refusal, guided stages, and task screen inputs. They use synthetic/reference projects and do not prove the saved revision-10 TMS is approved or runnable end to end. Its read-only compilation remains blocked.

## Recommended work order

1. Reconcile duplicate/unbound rules and resolve the actual TMS exception/requirement findings. Keep approval explicit.
2. Share effective permissions between the Studio matrix and runtime; define any stage/record restrictions the business needs.
3. Unify reviewed screens and runtime rendering, including task-specific input contracts and persisted theme settings.
4. Make review freshness and executable coverage visible; require complete business-journey tests for release readiness.
5. Build production identity, durable storage, migrations, adapters, and deployment packaging before presenting exports as production deployments.
