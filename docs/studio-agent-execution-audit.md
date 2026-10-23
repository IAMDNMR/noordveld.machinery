# Design Studio execution audit — 23 October 2026

## Outcome and scope

This change strengthens the existing Studio action engine rather than replacing it with a second agent framework. It adds durable project conversation context, request receipts, focused decision handling, backend continuation, targeted retained-source editing, and conversational dispatch to the existing generated-test endpoint.

This is not a claim that every natural-language instruction, domain, integration or application has been proven correct. The tests use controlled model responses to verify execution and boundaries; the configured model still determines many business interpretations. No production project policies were answered or deferred during this work. No commit, push or deployment was performed.

## What already worked

| Path | Existing implementation and practical limit |
|---|---|
| Chat and voice | Voice transcription feeds the same workspace submit path as typed text. Speech transcription and reply synthesis have separate provider checks. |
| Project context | The model receives a compact definition, domain references, findings and client-supplied recent messages. The active project is reused. |
| Editing | Validated typed actions implement entities, attributes, required fields, roles, process steps, rule bindings, exceptions and decisions. Unsupported operations are rejected by the action engine. |
| Domain knowledge | Existing providers expose sourced packs and reusable blueprints. Availability of a pack does not establish the correctness or completeness of a generated application. |
| Generation | The compiler builds contracts, runtime schemas, artifacts and independent runtime tests. React generation builds and reviews an interface through existing tools. |
| Approval | Project and organization access, independent formal approvals, content digests and decision authority already exist. A chat message cannot grant formal approval. |
| Runtime | Generated applications have server-owned identities, record and workflow checks, persistence, release archives and a local test/launch service. |

## Gaps traced and changes made

1. **Browser-only conversation memory:** new clients now send a request identifier. The server retains bounded conversation history, selection, pending question, proposal, operation and outcome in the existing project store. Studio recovers that history on open. Legacy callers without a request identifier retain their previous API contract.
2. **Duplicate or interrupted requests:** a receipt is reserved before planning. Reusing an identifier with different input is rejected. Completed requests replay their result without redispatching a tool. Running or failed receipts require inspection before a new attempt. Business writes still use the existing revision checks.
3. **Chat updates invalidating applications:** private context uses an independent compare-and-swap counter. Context-only writes do not increment application revisions, replace business content, change approval digests, invalidate frontend input hashes, or create misleading application-history entries. Existing SQL transaction locks, graph workspace locking and the in-memory lock protect those updates. No database schema migration is required.
4. **Silent guided action filtering:** actions outside the available stage vocabulary now produce an explicit refusal. Conversational edits may use the vocabulary of reviewed stages. Viewing a reviewed stage does not itself revoke its review; content digests reopen stages that actually change.
5. **Continuation handled before pending work:** the browser no longer intercepts continuation ahead of the task context. New-client continuation executes the existing backend phase service, including its readiness checks. A pending proposal is applied through the existing reviewed-proposal endpoint and authority checks. An unresolved question or failed task does not silently advance the project.
6. **Decision answers losing their target:** the server remembers the focused question. Short answers to that decision become reviewable changes. Generic agreement does not invent a policy. A request to decide later without a reason asks for the reason, and the next answer resumes that deferral.
7. **Deferrals bypassing review:** deferral changes an approval blocker into a warning. The conversation integration now treats it as a decision-sensitive action, requiring review and business-owner authority just like an answer.
8. **Whole-interface replacement:** when source already exists, the frontend generation endpoint edits retained source. It merges only returned files, preserves unrelated files, validates page bindings, checks source paths and business limits, runs the real TypeScript builder, and invokes the existing browser review. Failed checks retain the previous artifact. An empty regeneration brief requests synchronization with the latest business contract rather than an unconditional fresh design.
9. **Missing reference context during UI edits:** the retained-source editor receives the saved selection, recent conversation, business contract, workflow definitions, page bindings and SDK contract.
10. **Text-only test requests:** “run generated tests” dispatches to the existing protected runtime-test endpoint. The frontend reports actual returned counts. The backend retains success or failure in the task context; generation prerequisites and the `studio.generate` permission still apply.
11. **Misleading failures:** frontend network failures now reload saved state and avoid asserting that nothing changed. The server records interrupted task outcomes where possible. An interface build is marked complete only after its actual checks and save.
12. **Private discussion in downloads:** assistant context is excluded from the exported definition.

## End-to-end paths covered

- Clear request → validated action → saved entity, across transport, warehouse and after-sales examples.
- Focused question → saved question identifier → answer after reload → corrected answer → reviewed role change → application of that proposal.
- Open policy → continuation refused → supplied policy answer → reviewed decision.
- Decide later → focused request for a reason → supplied reason → reviewed deferral → warning instead of an open-decision error.
- Continue → existing stage service → next stage, with duplicate delivery unable to advance twice.
- Old-stage viewing → unchanged reviews; unavailable action → explicit refusal rather than silent omission.
- Provider failure → saved failed receipt → same-request replay rejected → new request can recover.
- Retained source edit → dependent component and consumer changes → TypeScript build → current saved preview. Missing consumer updates fail the build.
- Failed source edit → previous saved frontend retained.
- Designer attempts decision deferral → owner-authority refusal; authorized owner application succeeds.
- Conversation metadata → durable storage with its own CAS across four adapter seams, without a new application revision.
- Test command → existing test tool dispatch; missing generation prerequisites are reported without treating the command as a new application goal.

## Roles matrix review

The matrix's record-level rights were traced against `runtime_server.Runtime.entity_access`, `save_record` and `view`. Entity ownership grants record maintenance; a role must both own a step and hold its permission for step-derived access. Reading follows reads or writes, creation of an owned entity belongs to its owner, and deletion is unavailable. Field ownership adds narrower write restrictions. The matrix remains a summary, not the authorization mechanism. Its existing frontend regression and the independent generated-runtime permission/lifecycle tests were included in verification.

## Remaining limits

- Studio is not an always-on cloud agent. Work does not automatically survive a process restart as a queued background job. Interrupted receipts are retained and refused rather than blindly re-executed.
- Receipt/history retention is bounded: 24 messages and eight recent receipts. This is project context, not unlimited cross-project personal memory.
- General interpretation still depends on the configured model. Deterministic controls cover a small set of task commands; arbitrary language, typos and references are not universally proven.
- The typed action vocabulary still limits business edits. Destructive schema changes, arbitrary business algorithms and external integration implementations are not automatically supported by this patch.
- Answering a policy does not automatically turn prose into a verified executable rule. Existing rule binding, evidence, review, formal approval and compiler checks still apply.
- Business-contract edits can stale an existing custom frontend. Regeneration now edits it in place, but this change does not introduce a general background dependency scheduler that rebuilds everything after every mutation.
- The independent test/launch service needs the supported local/build environment. A serverless website alone does not provide persistent application execution.
- No production CockroachDB or Neo4j write was performed to verify credentials or migrate existing policies. Adapter tests use isolated storage or contract seams.
- The specific OpenAI Dots introduction video was not available in this chat. Comparison used the official documentation: https://learn.chatgpt.com/docs/dots . A similar collaboration pattern is a useful target; broad tool access, persistent background workers, isolated execution and cross-channel memory remain separate infrastructure work.

## Additional requested website correction

The public and end-user Agentic E-Commerce navbar link now opens `/agentic-commerce/`, the video introduction. Its examples still open `/agentic-shopping`. This was verified in the local browser by clicking from Aftersales to the video webpage. Nothing was deployed to the public site.

## Verification

Final results:

| Check | Actual result |
|---|---|
| Backend regression selection: conversation, context/storage, targeted editing, frontend generation, guided stages, platform quality, roles, standalone runtime, identity boundary, SQL adapters and releases | **77 passed**, one warning, 185.27 seconds. |
| Focused test-command prerequisite regression | **1 passed**, one warning, 29.71 seconds. This is a separate run, not added to the regression count as unique coverage. |
| Touched frontend regression files | **26 passed** across five files. |
| `npm run check` | TypeScript and lint pass. Formatting fails on untouched `frontend/src/components/studio/views/ScreenWorkbench.test.tsx` from concurrent work. |
| `npm test` | Initial run: **134 passed, one failed**, the existing commerce retry timing case. |
| `npm test -- --maxWorkers=2` | **135 passed** across 42 files, 77.22 seconds. Worker limit was command-only; no test configuration was changed. |
| `npm run build` | Passed; Vite built 2,280 modules successfully. |
| Ruff on every changed Python source/test | Passed. |
| `git diff --check` | Passed; Git emitted only line-ending conversion notices. |
| Restarted local backend `/health` | HTTP 200. |
| Local Agentic E-Commerce video webpage | HTTP 200; clicked and verified in the browser. |

Earlier intermediate counts are not combined into a larger claimed result. Model behavior is exercised through controlled responses, while source editing uses the real TypeScript builder. Browser-review calls in the focused source-edit tests are stubbed; the live browser check in this task verified website navigation, not every generated application's visual quality.

The first mandatory frontend check passed TypeScript and lint but failed formatting on the untouched `ScreenWorkbench.test.tsx` from concurrent work. An initial full frontend run had 134 passes and one failure in the existing commerce network-retry timing test. Neither unrelated file was edited to hide those failures. No frontend test cases were added; existing cases were extended. The existing suite contains 135 tests, already above the earlier requested ceiling of 100.

## Files changed by this task

| File | Why |
|---|---|
| `backend/app/api/routes/design_studio.py` | Strip client-supplied private context on create and preserve server context on ordinary updates. |
| `backend/app/api/routes/studio_conversation.py` | Durable turn lifecycle, explicit action refusals, phase continuation, proposal acceptance/dismissal, deferral authority and real test dispatch/outcomes. |
| `backend/app/api/routes/studio_frontend.py` | Select retained-source editing and retain actual interface task outcomes. |
| `backend/app/assistant/studio_task_planner.py` | Deterministic continuation, preview, test and focused decision controls before the existing model planner. |
| `backend/app/design_studio/task_context.py` | Request fingerprints, bounded memory, receipts, proposal resolution and real tool outcomes. |
| `backend/app/design_studio/frontend_edit.py` | Targeted source merge through shared build, binding and browser checks. |
| `backend/app/design_studio/projects.py` | Server-owned context preservation and its independent CAS operation. |
| `backend/app/design_studio/sqlite_store.py` | Persist context without a new application revision. |
| `backend/app/design_studio/postgres_store.py` | Same metadata persistence through the existing transactional SQL adapter. |
| `backend/app/design_studio/neo4j_store.py` | Keep current context on the mutable project head without rewriting immutable graph revisions. |
| `backend/app/design_studio/approval.py` | Exclude private context from design approval hashes. |
| `backend/app/design_studio/codegen.py` | Exclude private context from application downloads. |
| `backend/app/schemas/application_definition.py` | Optional server-owned context field. |
| `backend/app/schemas/studio_task.py` | Validated context, message and receipt shapes. |
| `backend/tests/test_studio_task_execution.py` | Authenticated conversation, clarification, continuation, replay, recovery, deferral and test-dispatch regressions. |
| `backend/tests/test_studio_targeted_edit.py` | Retained-source, real builder, dependency and failed-save checks. |
| `backend/tests/test_studio_task_storage.py` | Independent context CAS across memory, SQLite, PostgreSQL contract and graph-document seams. |
| `frontend/src/api/studio.ts` | Request identifiers, recovered task state, dismissal and test command types. |
| `frontend/src/components/studio/useStudio.ts` | Server history recovery, honest failures, persisted dismissal and actual test execution. |
| `frontend/src/pages/StudioWorkspacePage.tsx` | Remove premature continuation interception and dispatch generated tests. |
| `frontend/src/components/studio/views/GeneratedFrontendView.tsx` | Show the actual retained-source editing phase. |
| `frontend/src/components/studio/useStudio.test.tsx` | Extend recovery verification within the existing race test. |
| `frontend/src/pages/StudioWorkspacePage.test.tsx` | Check request identifiers and a real frontend test-tool call in the existing conversation test. |
| `frontend/src/data/content.ts` | Correct public/end-user navigation to the video webpage. |
| `frontend/src/components/orders/roles.test.tsx` | Assert both navbar variants target the introduction page. |
| `docs/studio-agent-execution-audit.md` | This trace, scope, file list, verification record and handoff. |
