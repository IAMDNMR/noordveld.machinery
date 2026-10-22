# Studio gap audit — 20 October 2026

This records a verified local audit pass. It does not certify public deployment or universal domain coverage. Hosted PostgreSQL access is deliberately deferred until the next phase, as requested.

## Fixed in this pass

- Approved projects reconstruct their generated package on reopening Generate. Checks, source files, downloads and generated tests no longer depend on a previous visit's component memory. The stage summary is refreshed from the same saved revision.
- Application launch/stop uses `can.launch`; generation, package downloads and generated tests retain `can.generate`. Reviewers with launch permission do not need generation privileges to run an approved app.
- Runtime status distinguishes loading, unreachable, stopped, running and unavailable hosting. Failed status checks do not enable a speculative launch. Focus and periodic refresh update status; saved revision changes invalidate runtime freshness.
- Compilation results, displayed files and test results belong to a specific project and revision. Workspace views remount on project changes.
- Out-of-order project-open responses cannot overwrite a newer project or reopen a project after leaving. Late access, assistant, apply and restore results are excluded from a different project's view.
- Local launch and stop are serialized, avoiding concurrent deletion/start of the same generated code directory. Concurrent generated tests receive separate temporary workspaces.
- Vercel environments explicitly report local preview execution as unavailable and refuse local launch/test subprocesses. This prevents advertising loopback servers as publicly hosted apps; it does not implement hosted app execution.
- The compiler fixture now explicitly uses local reference knowledge. The voice fixture stubs both conversation and status provider resolution. Neither silently depends on the developer's configured Neo4j/model credentials.
- Approval wording reports valid approval without claiming a separate human approver in the owner-only demo. A new demo revision is described as using its own database, preserving older revision data rather than claiming an automatic data migration.

## Verification

- Frontend: 413 tests passed in 29 files; typecheck, lint, formatting and production build passed.
- Backend offline suite: 643 passed, 316 skipped. Live graph/provider tests were not exercised; graph writes and real model calls were disabled for this run. One existing `python_multipart` deprecation warning remains.
- Exported Transport Operations revision 12: its three independent generated runtime tests passed.
- Live restart check: six existing workflow instances and five shipment records were present. Existing workflow IDs/revisions survived launch. The runtime was stopped before the check and returned to stopped afterward. See `STUDIO_AUDIT_LIVE_2026_10_20.json` for evidence.
- The local backend was restarted with graph project namespace `studio-local-site`. No Studio project or domain-knowledge migration was performed.

## Next deployment phase — still required

1. Activate and test durable project storage against the supplied hosted PostgreSQL, apply the isolated schema, and migrate/verify project histories and ownership. The existing PostgreSQL adapter is not yet selected in the production request dependency.
2. Adapt generated application operational storage and hosting for online execution. The working local runtime uses a per-application, per-revision SQLite database and a loopback process. A PostgreSQL URL alone does not convert this into a publicly hosted app. Schema/data migrations across app revisions must be explicit and tested.
3. Configure trusted production identity, organization/project access, secure session settings and allowed origins. Local demo identities are not a production login system; deployed access currently fails closed without trusted identity.
4. Select durable storage for retained generated release packages and uploaded document bytes. Current document integration contracts exchange metadata, not binary file storage. Local download generation is not a hosted artifact-retention service.
5. Configure customer-specific integration mappings/providers only when supplied. Legacy packs remain sourced references; reusable blueprints remain generation inputs. Structural completeness does not establish vendor-specific correctness, regulatory compliance or customer acceptance.

These are deployment implementation/configuration tasks, not a claim that PostgreSQL credentials are the only remaining step.
