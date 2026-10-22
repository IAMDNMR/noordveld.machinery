# Design Studio production activation gate

Current state: **disabled**. The backend still selects `DisabledDraftStore` and
`DisabledProjectStore`. The deployed Design Studio routes reject demo identity.
This document is a rollout checklist, not authorization to provision, migrate,
or deploy anything.

For the evidence, conditional provider recommendations, and decisions to be
approved before rollout, see
[DESIGN_STUDIO_PRODUCTION_APPROVAL.md](DESIGN_STUDIO_PRODUCTION_APPROVAL.md).

## Verified repository state

- `/auth/login` selects a seeded user by ID and issues a signed `nv_session`
  cookie. A signature proves that the cookie came from this backend, **not**
  that the person authenticated. Demo login and the user list are now limited
  to local, undeployed requests. `VERCEL`/`VERCEL_ENV` or a non-local `APP_ENV`
  disable them.
- Design Studio uses `CurrentUser`, which resolves the cookie against the
  server-side user record. It never uses a client-supplied ID or role. Its
  routes are now local-demo-only until a trusted identity integration exists.
- The checked-in `vercel.json` declares FastAPI/Vite services, but the actual
  project framework setting, deployed backend runtime, number of instances,
  persistent storage, and current production version have **not** been
  verified. It uses a `services` block and `/api` rewrite; no committed file
  proves that the Vercel project is set to Services or that this revision is
  deployed. Vercel's Services documentation and guide currently describe
  different configuration keys (`experimentalServices` and `services`). The
  deployment owner must verify the dashboard, build logs and live routing.
- No PostgreSQL driver or approved production PostgreSQL service is configured
  in `backend/requirements.txt` or the repository deployment configuration.
  No persistent volume or transactional Design Studio database is declared.
  The unselected PostgreSQL adapter is in
  `app/design_studio/postgres_store.py`; it requires dict-row connections,
  transactions, and the exact schema marker in `postgres_schema.sql`. It never
  migrates or creates tables. The SQLite adapter is isolated-test/local only.
- `CurrentUser` verifies the signed cookie, then loads a user through
  `OrdersService` / `GraphOrdersRepository`. This does not make demo login
  trustworthy: a local demo visitor can choose a seeded user ID. Existing
  commerce endpoints also use `CurrentUser`; the Design Studio deployed-mode
  guard does **not** replace commerce authentication.
- Schema and adapter align on draft revision integers, global project IDs,
  owner IDs, revision rows, and a current-revision pointer. Project update
  locks its row with `FOR UPDATE`, checks the expected revision, inserts a
  new revision with actor/operation/timestamp, then advances the pointer in
  one transaction. Owner checks precede reads and writes. Revision rows are
  immutable by adapter behavior, but the schema does not stop a privileged
  SQL user from editing them. Drafts have a revision counter, not a separate
  immutable draft-history table.

## Required owner decisions and configuration

1. Select the existing approved identity provider or approve one. Confirm its
   issuer, application/client ID, callback URL, scopes/audience, signing-key
   rotation, logout/session policy, and how its immutable subject maps to an
   application user, including deleted/renamed users and tenant boundaries.
   Approve whether the change affects only Design Studio or also replaces
   the wider commerce demo-session flow. The current seeded-user login
   **must not** establish that mapping. No IdP SDK, OIDC verifier, or provider credentials
   are present, so no provider-specific variables are active. Proposed names
   after provider selection: `DESIGN_STUDIO_OIDC_ISSUER`,
   `DESIGN_STUDIO_OIDC_CLIENT_ID`, `DESIGN_STUDIO_OIDC_CLIENT_SECRET`,
   `DESIGN_STUDIO_OIDC_AUDIENCE`, and `DESIGN_STUDIO_OIDC_REDIRECT_URI`.
   Merely setting these variables does nothing today.
2. Confirm the actual hosting account/project, Services eligibility and
   framework setting if applicable, deployed commit, API routing, backend
   runtime/region, worker concurrency and instance topology. Confirm that
   `VERCEL`/`VERCEL_ENV` are exposed at runtime, or set `APP_ENV=production`
   explicitly. Approve a managed PostgreSQL provider, dedicated database or
   schema, connection pooling, network/TLS policy, cost, and migration owner.
   A local SQLite path is not an approved multi-instance storage solution.
3. Approve backup frequency and retention, point-in-time recovery, restore
   test cadence, recovery-point objective (RPO), recovery-time objective
   (RTO), encryption/access controls, and incident and rollback owners.
4. `DESIGN_STUDIO_STORAGE_BACKEND=postgres` and
   `DESIGN_STUDIO_DATABASE_URL=<provider-approved PostgreSQL URL>` are
   **preflight-only names**. `storage_candidate()` checks their syntax without
   connecting or logging the URL. They do not enable saves. `sqlite` is
   deliberately rejected as a production candidate. A future approved
   integration must add a PostgreSQL driver, create the connection factory,
   and explicitly wire both store dependencies only after live validation.
5. Authorize isolated integration tests against the approved IdP and a
   non-production PostgreSQL database. Provide two owner identities, an
   unauthorized identity, and an isolated restore target. This does not
   authorize tests against Neo4j or production customer data.
   `SESSION_SECRET` signs the *demo* cookie only and is not a replacement
   for provider authentication.

## Controlled rollout after separate approval

1. Obtain the deployment owner's confirmation of the actual deployed commit,
   runtime and instance topology, environment-variable exposure, approved
   PostgreSQL service, IdP, commerce-authentication scope, and recovery
   objectives. Keep both production store dependencies disabled until the
   identity and durability gates have been independently verified.
2. Back up the approved empty or dedicated database. Review
   `postgres_schema.sql` and apply it manually in a change window. Never run
   it against Neo4j or an existing SQLite draft database. Confirm the schema
   marker and table access using a read-only connection; test backup restore
   in an isolated environment. Do not migrate v1 SQLite drafts implicitly.
3. Integrate and test the chosen IdP with issuer/audience/signature/expiry
   verification, subject-to-user mapping, session rotation, logout and CSRF
   protection. Verify that demo cookies cannot authorize deployed Design
   Studio operations. Review the wider commerce login before removing it:
   current commerce endpoints still use the demo session model.
4. Install the approved PostgreSQL driver and wire the adapter behind an
   explicit production feature gate. Use pooled, TLS-protected connections.
   Verify schema version and a read-only query as a storage health check;
   `/health` only proves the API process is alive, while `/health/ready`
   checks the graph and is not a Design Studio storage check.
5. After explicit authorization for isolated integration testing, run cross-user,
   forged/expired session, concurrent update, interrupted-write, restart,
   multi-instance, backup/restore, and redeployment tests. Verify ZIP contents
   and that no generated mockup executes commerce actions. Record the results
   and get a separate activation decision; then enable save routes with
   monitoring and a tested switch back to disabled stores.

No production identity, database access, migration or activation is configured
by this document or by setting the preflight variables.
