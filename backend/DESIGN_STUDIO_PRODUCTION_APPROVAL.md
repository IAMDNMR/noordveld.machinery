# Design Studio production approval decision

Status: **approval requested, not activation authorized**. Read with
[DESIGN_STUDIO_ACTIVATION.md](DESIGN_STUDIO_ACTIVATION.md). This records repository
evidence and conditional recommendations; it does not verify the live deployment.

## 1. Hosting evidence and verification

- Repository fact: `../vercel.json` declares a FastAPI `backend` service rooted
  at `backend`, a Vite `frontend` service, and a top-level `/api` rewrite to the
  backend. It does not establish that this revision is deployed or that the
  Vercel project uses the Services framework. No persistent disk, worker count,
  region, concurrency limit, or production environment setting is proven here.
- Owner verification: in the **Vercel project dashboard**, inspect Project
  Settings > Build and Deployment (framework and service settings); the active
  Production Deployment (commit, Build Logs, Deployment Details > Resources for
  runtime and region); and Runtime Logs plus project environment-variable
  **names/scopes**, without sharing values. Confirm actual `/api` routing and
  the maximum concurrent backend instances/workers. If the API is hosted
  elsewhere, identify that host and equivalent deployment evidence. Vercel's
  [Services guide](https://vercel.com/kb/guide/vercel-services) says the project
  framework setting is required; repository configuration alone is insufficient.
- Verification snapshot (2026-10-14): this workspace has no `vercel` CLI
  command, no `.vercel/project.json` project link, and no available Vercel
  connector. No live project metadata, environment names, deployment logs, or
  backend runtime were accessed. The owner should provide a redacted record of
  the dashboard fields above (names/metadata only, never values or tokens).

## 2. Durable database decision

- Repository fact: `app/design_studio/postgres_store.py` is an **unselected**
  adapter; `app/design_studio/postgres_schema.sql` is manual-only. Neither a
  PostgreSQL driver nor connection factory is configured. Both API store
  dependencies return disabled stores. Existing SQLite drafts remain separate.
- Conditional recommendation: if the live backend is Vercel and no already
  approved transactional PostgreSQL service meets the requirements, assess
  **Neon managed PostgreSQL through the Vercel Marketplace**. Vercel no longer
  offers first-party Vercel Postgres and documents Marketplace PostgreSQL
  integrations ([Vercel](https://vercel.com/docs/postgres)); its
  [Neon listing](https://vercel.com/marketplace/neon) describes a managed
  integration. This is a candidate, **not** provider approval or evidence of
  account access. Prefer an existing approved PostgreSQL service if its
  region, connectivity, recovery, and cost meet the same criteria.
- No approved PostgreSQL account or service can be established from the
  checked-in configuration or available project access. Until the backend
  region and recovery objectives are known, there is no defensible final
  provider ranking. Candidates for owner comparison:
  - **Existing approved managed PostgreSQL:** first choice if connectivity,
    region, pooling, isolation, backups and cost already meet the gates; its
    existence and terms remain unverified.
  - **Neon:** Vercel Marketplace integration and
    [PgBouncer pooling](https://neon.com/docs/connect/connection-pooling) make
    it a plausible short-lived-connection candidate. Confirm region, TLS,
    plan-specific restore window and usage-based
    [compute/storage/network cost](https://neon.com/docs/introduction/about-billing).
  - **Supabase PostgreSQL:** also listed in the
    [Vercel database marketplace](https://vercel.com/marketplace/category/database);
    its [connection guide](https://supabase.com/docs/guides/database/connecting-to-postgres)
    distinguishes serverless transaction pooling from direct migration
    connections. [Backups and PITR](https://supabase.com/docs/guides/platform/backups)
    depend on plan/add-ons and retention. Confirm region, transaction-mode
    driver compatibility, TLS verification and full projected cost. Its
    additional platform features are not required for this isolated store.
- Require a dedicated database or schema and separate least-privilege runtime
  and migration roles. Use short-lived, bounded connections via a provider
  pooler for concurrent instances; verify transaction-pooling compatibility
  with the Python driver and adapter's transaction context. Use a direct/admin
  connection only for controlled migrations if the provider requires it.
  [Neon documents pooled connections](https://neon.com/docs/connect/connection-pooling).
  Require TLS with server identity verification, credential rotation, and a
  region compatible with the backend and data-residency policy.
- Migrations: owner-reviewed, versioned, manually scheduled application of the
  proposed schema to an isolated target; check `studio_meta` before enabling
  reads/writes. Never auto-migrate on startup or migrate local SQLite drafts.
  Agree a tested restore path before schema changes. The current schema does
  not itself prevent privileged SQL edits to revision rows; runtime grants
  should deny update/delete on history, with stronger database enforcement
  assessed before any immutability guarantee is made.
- Approve backup frequency, independent backup/export where required,
  point-in-time restore window, retention, encryption, restore test cadence,
  RPO and RTO. Restore into an isolated target and compare revisions, ownership,
  and schema marker. Confirm plan-specific restore features and retention with
  the provider; they cannot be verified locally. Obtain a cost estimate for
  compute, storage, retained history/backups, pooled connections, data transfer,
  region, and non-production environments. No production price is assumed.

## 3. Trusted authentication

- Repository fact: `/auth/login` lets a local visitor select a seeded user ID;
  a signed demo cookie is not proof of identity. `CurrentUser` loads the user
  server-side through `OrdersService` / `GraphOrdersRepository`. The Design
  Studio deployed-mode guard rejects this demo flow; commerce endpoints still
  rely on `CurrentUser`. No configured IdP or verified subject mapping exists.
  No authorized IdP tenant access was available in this review, so an existing
  organizational provider or application registration cannot be confirmed.
- Conditional recommendation: use the organization's **existing approved OIDC
  IdP**; Microsoft Entra ID is a suitable candidate **if** Noordveld staff
  identities are already managed there. If customers or multiple organizations
  must sign in, evaluate an approved customer-identity option such as Auth0
  instead. Neither provider is selected here. Both publish OIDC guidance
  ([Entra](https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc),
  [Auth0](https://auth0.com/docs/get-started/authentication-and-authorization-flow/authorization-code-flow-with-pkce)).
- Use authorization code flow with server-side token exchange, state/nonce
  checks, issuer/audience/signature/expiry validation and key rotation. Bind
  the verified `(issuer, subject, tenant)` tuple to one provisioned application
  user ID through a trusted server-side mapping; never map by email, display
  name, chosen demo ID, or client role. Handle deprovisioning, tenant changes,
  session rotation, logout, CSRF, and secure cookies. Define whether that user
  record remains graph-backed read-only or moves to a separately approved
  identity store; this review authorizes no Neo4j write.
- Owner must decide whether to change authentication **only for Design Studio**
  or across commerce. A Studio-only IdP gate does not make commerce login safe
  for production; a wider change needs separate compatibility and regression
  approval. No ordinary commerce role becomes a platform administrator by
  default.

## 4. Security invariants

- Keep the authenticated server-derived user ID as the owner key for project
  create/list/read/update/history/export; recheck ownership on every operation.
  Continue strict schema validation, expected-revision checks, project-row
  locking, and atomic insert-then-pointer advancement. Existing revision rows
  are append-only **by adapter behavior**, not yet by database privilege or
  trigger. Reject invalid/corrupt definitions and never execute generated code.
- `app/design_studio/graph_permissions.py` has an exact-request, exact-actor
  approval contract, but no trusted approval source or Neo4j writer is wired
  to Design Studio. Keep graph writes disabled. Any future write requires a
  fresh, specific approval stating operation, target nodes/relationships,
  changes, and reason; denial or changed scope means no execution. Approval
  and outcome must be audited without secrets. This document grants none.
- `app/design_studio/activation.py` only parses preflight variable syntax.
  `get_design_store()` and `get_project_store()` still select disabled stores,
  and deployed Studio routes reject demo identity. Environment variables
  alone cannot turn on production saves. Preserve independent identity,
  storage-health, and explicit feature gates when activation is implemented.

## 5. Non-production verification and rollout gates

1. **Owner approval of hosting and infrastructure:** verify the live topology
   and select PostgreSQL and OIDC services, isolated test targets, budget,
   recovery policy, and migration/rollback operators. No Neo4j or customer-data
   tests are implied.
2. **Trusted identity integration:** only after the IdP and commerce-auth scope
   are approved, implement verified OIDC sign-in and server-side subject mapping
   behind the deployed Studio gate. Keep demo identity local and saves disabled.
3. **Non-production database and schema:** only after separate authorization,
   provision an isolated database, choose the driver/pooler, review the schema,
   and apply it to that non-production target. Never auto-migrate or touch
   existing SQLite drafts.
4. **Isolated integration tests:** with the approved IdP and database, test
   forged/expired/other-tenant sessions, deprovisioning,
   cross-owner reads/writes/exports, stale and concurrent revisions, failed
   transactions, corruption, restart, multiple instances, and redeployment.
   Verify saved definitions survive; test ZIP contents and mockup-only safety.
5. **Backup and restore rehearsal:** take a backup, write several revisions, restore to
   an isolated target, verify the selected recovery point, schema marker,
   ownership and revision history, and measure achieved RPO/RTO. Test failure
   of the database and IdP: writes must fail closed without local fallback.
6. **Independent production activation approval:** owner reviews signed-off test evidence,
   health checks, monitoring/alerts, backup evidence, and cost. Only then may
   an approved deployment wire the stores and enable saves. Keep a reversible
   feature gate. Rollback disables Studio saves and reverts application wiring
   without deleting PostgreSQL records or touching SQLite/Neo4j; restore data
   only under a separate, reviewed recovery decision.

## Decisions requiring owner approval

1. Actual production project/host, deployed commit, framework, runtime,
   region, routing, instance/worker concurrency, and environment scope.
2. Approved PostgreSQL provider/plan/region, database isolation, network/TLS,
   pooling, driver, migration role/operator, and cost ceiling.
3. Backup and restore policy: retention, PITR, independent copies, restore
   rehearsal, RPO/RTO, incident owner, and data-residency requirements.
4. Existing or new OIDC provider/tenant, trusted `(issuer, subject, tenant)`
   mapping/provisioning, administrator assignment, and Studio-only versus
   wider commerce-authentication scope.
5. Named non-production services, test identities, authorization to run
   integration and restore tests, and a **later separate approval** to deploy
   and activate production saves. Neo4j writes require per-operation approval.

No live topology, provider access, backup capability, or IdP tenancy was
verified by preparing this document.
