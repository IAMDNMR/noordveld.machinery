# Design Studio end-to-end audit — 20 October 2026

Follow-up implementation: see `STUDIO_RELEASE_STORAGE_AND_MIGRATIONS_2026_10_20.md` for retained releases/test history, dashboard status, backup/migration tooling, PostgreSQL activation wiring, CI definitions and corrected source-test discovery. The findings below are the original audit snapshot.

## Verdict

The local Studio and generated runtime have substantial verified functionality. They are **not yet a complete production app-building and hosting platform**. Passing synthetic suites does not establish customer acceptance, comprehensive domain knowledge, or production readiness.

This pass inspected the stage pipeline, approvals, generated code and tests, permissions, persisted TMS records, graph references, mobile navigation, and deployment boundaries. It did not deploy publicly, activate PostgreSQL, change customer policies, or create test projects in the real workspace.

## Fixed during this audit

1. Generated date-rule fixtures used numeric arithmetic on ISO date strings. This broke after-sales warranty and workforce leave tests. Date/datetime fixtures now use calendar arithmetic; presence rules bypass comparison operands. Equality-at-threshold assertions also exercise inclusive/exclusive decisions. Both exported domain suites now pass; a backend regression runs them independently.
2. Failed generated tests exposed only their last 25 output lines, hiding earlier errors. The backend now supplies bounded detailed output (100,000 characters), a truncation indicator, and the existing short tail. The Studio failure view uses the detailed output.
3. At mobile widths the sidebar and its navigation button were both hidden. A compact, labeled stage selector now exposes the same reviewed/current stages; future stages remain disabled. The Generate action retains an accessible name and a compact mobile icon.
4. Stage changes reset the outer main element, but the nested content container actually owned scrolling. The reset now targets that container. A regression checks revisiting a stage resets scroll without advancing or approving it.
5. Added `backend/scripts/audit_studio_blueprints.py` to compile every shared process blueprint and run its exported independent tests in temporary workspaces. It exits unsuccessfully for generation failures or failed suites. It does not modify customer projects or Neo4j.

## Verification and limits

| Area | Result | Limit |
| --- | --- | --- |
| Backend offline suite | 654 passed, 316 skipped; one existing multipart deprecation warning | Real external/model/graph tests are intentionally excluded by this isolation mode |
| Frontend suite | 419 passed in 30 files | Component tests are not full browser acceptance |
| Frontend checks | TypeScript, lint, formatting, production build passed | Does not deploy backend services |
| Shared blueprint generation | 21 runnable packs compiled; 586 exported checks passed, zero failed, 67 skipped | Two additional packs are shared data foundations, not standalone workflow apps |
| Saved Transport Operations, revision 12 | 52 files; 43 generated tests passed, seven skipped; zero blocking process/design findings | Six rule assumptions remain warnings; one carrier connection requires customer mapping/configuration |
| Live generated runtime | Six workflow instances and five shipment records preserved across launch | Read-only check; no new operational records or workflow actions were submitted |
| Dashboard | One active project, one reviewed design, one ready to build | Compilation/test/deployment history is not a durable release ledger |
| Browser review | Dashboard, Generate results and tests, connection details, mobile stage switching, data-model connections | Focused TMS review; not every screen in every generated domain |
| Neo4j process references | 23 versions, 27 source records, 138 claims, 32 relationship claims; zero claims missing evidence links | All 23 references are draft, zero reviewed; narrow sourced examples do not cover all vendor systems or EU/India business requirements |

The 67 exported skips concern fixture creation for read-only Stock count, Stock movement, Work order, Credit note, Pick list, Pick line, or Pack unit entities. They need approved data-import fixtures or an explicit source. Customer write permissions were not widened to manufacture test success. The seven saved-TMS skips concern Pick list/Pack unit fixtures and dependent relationships.

The live project stayed at revision 12 with eight entities, nine relationships, nine screens, six roles, and six rules. Its runtime was originally stopped and was stopped again after verification. The reference download ZIP was refreshed; operational databases were preserved.

## Remaining work, in order

| Priority | Gap and evidence | Concrete completion condition |
| --- | --- | --- |
| P0 before public use | Production identity is intentionally unavailable: `require_studio_identity` admits only local demo requests | Trusted sign-in, organization provisioning, server-owned membership, secure sessions/origins, and cross-tenant tests on the deployed environment |
| P0 before public use | Default production request dependencies return disabled project/draft stores; PostgreSQL adapter is not selected | Wire the chosen hosted store, run schema migrations, migrate ownership/history, and verify restart/backup/restore with integration tests. PostgreSQL access remains deferred at the user's request |
| P0 for online generated apps | Local runtime is a loopback subprocess with SQLite; Vercel paths reject local execution/tests | A separate authenticated build/execution service with quotas, isolation, job status, logs, and reachable application URLs; front-end hosting alone does not provide this |
| P1 before releases | Generated operational databases are scoped to revisions; no demonstrated automatic schema/data migration | Versioned migration plans, preview/diff, tested data preservation, rollback and restore procedure |
| P1 before releases | Downloads are reconstructed; generated test results live in the view, without retained release/deployment records | Durable artifact storage and revision/hash-linked build, test and deployment records, including failures, retries, retention and rollback |
| P1 quality | Read-only data fixtures leave 67 exported checks skipped | Isolated import/integration fixtures and successful permission-preserving process runs for every declared supported blueprint; keep true provider dependencies explicit |
| P1 product | No built-in complete GitHub-to-deployment lifecycle is demonstrated | Repository export/sync, protected secrets, CI checks, preview deployment, production promotion, release link and rollback |
| P1 knowledge | Sourced vendor references are draft and domain depth varies considerably | Expert review/versioning, explicit applicability and gaps, richer happy/exception processes, customer policy confirmation and region-specific evidence where needed |
| P1 UX assurance | Individual components and focused TMS browser inspection do not prove all generated applications have usable task-specific screens | Independent browser journeys per supported domain/role, mobile and keyboard checks, error/empty/loading states and customer acceptance criteria |
| P1 operations | Production backup, monitoring, error reporting, rate limits and recovery have not been demonstrated | Measured and tested operational controls with service ownership and recovery exercises |

Carrier tracking and document storage stay customer-configured. Generated apps must not automatically connect to Noordveld catalogue/order APIs. Existing rule assumptions must be confirmed from actual customer policy or evidence; graph availability alone cannot make those policy choices true.

## Comparison with other app builders

Official documentation was used to identify concrete product expectations, not to claim complete feature parity:

- [Lovable browser testing](https://docs.lovable.dev/features/browser-testing) documents interacting with a running app in a browser. Studio's independent runtime tests are useful but do not replace browser acceptance across generated roles/screens.
- [Lovable GitHub integration](https://docs.lovable.dev/integrations/github) and [publishing](https://docs.lovable.dev/features/publish) demonstrate repository and hosting workflows. Studio currently has downloadable generated packages and a local runtime, so retained releases and a deployment lifecycle remain necessary.
- [Replit application testing](https://docs.replit.com/features/agent/app-testing) and [checkpoints/rollbacks](https://docs.replit.com/features/version-control/checkpoints-and-rollbacks) provide useful reference points. Studio has specification revision restore, but application data migration, deployment rollback and durable build history are separate capabilities still to implement.

The next milestone should be a complete, retained and independently tested local release, followed by production identity/storage and an online execution service. Another visual redesign alone will not close these platform gaps.

## Evidence

- `STUDIO_BLUEPRINT_EXECUTION_2026_10_20.json`: final shared-blueprint compilation and exported suite results.
- `STUDIO_DOMAIN_REGRESSIONS_2026_10_20.json`: after-sales/workforce results after fixing date fixtures.
- `STUDIO_STAGE_VERIFICATION_2026_10_20.json`: actual saved TMS revision, stage checks and generated tests.
- `STUDIO_AUDIT_LIVE_2026_10_20.json`: runtime launch and persisted records.
- `STUDIO_PROCESS_REFERENCES_2026_10_20.json`: live graph coverage and evidence-link integrity.

Earlier same-day reports are historical snapshots. In particular, older three-test counts are superseded by this pass's 50-test saved-TMS suite.
