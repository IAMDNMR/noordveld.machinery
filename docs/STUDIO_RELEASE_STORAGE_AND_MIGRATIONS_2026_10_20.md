# Studio gap fixes — releases, storage and upgrades

Scope update: the owner has since confirmed a view-only demo without worker hosting. See `STUDIO_DEMO_SCOPE_2026_10_20.md`. Provider selection requests below are historical and no longer block the demo.

This follows the end-to-end audit. It records implemented changes and remaining dependencies; it does not certify production deployment or claim that every audit finding is closed.

## Implemented

- Retained generated ZIPs, keyed by the complete file-content fingerprint, with their archive SHA-256, revision, creation time and actor. Repeated retention is idempotent and cannot overwrite an earlier package.
- Independent test runs saved against that exact release: running, passed, partial, failed and interrupted. Lost workers expire after their deadline. A new generation at the same project revision does not inherit tests from different files.
- Test results restored on reopening Generate. Saved releases have their own downloads. Partial coverage is amber and remains explicit. A newer failed worker run cannot be replaced by an older successful result in the restored view.
- Dashboard release status for the saved revision. Failed/interrupted tests count under Needs attention even if design validation has no errors.
- Owner/project scoping and existing organization permissions on release APIs. Retention and package downloads require generation access; authorized reviewers can inspect history. Stale revision retention is refused.
- Local release storage under `%LOCALAPPDATA%/Noordveld/Studio/releases.sqlite`, outside source and temporary build workspaces. Archive size is limited to 50 MB. History currently displays the latest 50 releases and ten test runs per release; backup retains all rows. Retention is not an automatic purge policy.
- Consistent local backup with SQLite integrity and per-archive digest checks. Existing backup files are never overwritten. Restart and copy/restore tests cover retained packages and failed/partial runs.
- Opt-in PostgreSQL project/draft and release-store wiring, with a separate manual release schema, dictionary rows, connection/query timeouts, TLS hostname/certificate verification, and safe service-unavailable errors. No hosted database was contacted or migrated. PostgreSQL release behavior was checked through the offline SQL contract, not a live server.
- Exported `runtime/migrate.py`: preview first; copy compatible data into a new database without changing the old one; validate stored records; clear sessions; record migration events. Optional field additions are supported. Removed/changed fields, required-field backfills, changed workflow/rule/permission/reference contracts and runtime versions are refused pending a custom migration. Rollback retains the previous package/database; post-promotion writes need reconciliation.
- Repository CI definitions for Studio and each generated archive. They run independent Python tests, generated JavaScript syntax checks and TypeScript/build checks. No repository was connected, pushed, published or deployed, and GitHub Actions itself was not run from this local session.
- Two concurrent local test workers maximum, with explicit retry feedback when occupied.
- Frontend test discovery restricted to source tests. Temporary exported-app verification workspaces are excluded from development watching. This fixes inflated/nondeterministic component-test totals and unwanted page reloads.

## Verification

- Full offline backend suite: **661 passed, 316 skipped**; one existing multipart deprecation warning. Additional focused regressions passed after strengthening expiry, failed-worker/dashboard and optional-field migration assertions.
- Frontend: **423 source tests in 31 files passed**; TypeScript, lint, formatting and production build passed. Earlier intermediate 520-test totals included temporary exported validation suites and are not the Studio component-test count.
- All 21 runnable shared blueprints compile: **586 independent generated checks passed, 67 skipped, zero failed**. The two remaining shared packs are data foundations.
- Live Transport Operations remains revision 12: eight entities, nine relationships, nine screens, six roles and six rules. Current archive has **54 files**, including the migration tool and generated CI workflow. Its exported suite has **43 passed, seven skipped, zero failed**.
- Page reload and backend restart preserved the retained release/test history. The current downloaded retained package matched its recorded SHA-256. A backup containing both saved releases passed integrity/digest checks. See `STUDIO_RELEASE_VERIFICATION_2026_10_20.json` for hashes and the local backup path.
- The generated application remained stopped. No operational data migration, record edit, role change, rule confirmation or approval change was applied to the user's project.

The migration tool was exercised on a separate synthetic database: preview did not create a target; optional-field migration preserved records and source bytes; copied sessions were cleared; audit entries were present; existing destinations and breaking permission changes were refused.

## Local operations

Run the normal Studio start command; it selects the local release database automatically. To back up releases and test history:

```powershell
python backend/scripts/backup_studio_releases.py --source "$env:LOCALAPPDATA/Noordveld/Studio/releases.sqlite" --target "D:/Backups/studio-releases-new.sqlite"
```

Use an existing destination directory and a new filename. To restore a local release database, stop the backend, point `DESIGN_STUDIO_RELEASE_DB` to the verified backup/copy, then restart and verify release downloads. This does not restore Neo4j project histories or generated application operational records; those are separate stores.

## Hosted PostgreSQL activation — prepared, not performed

1. Provision an isolated Studio database and establish provider backup/restore ownership. Keep Neo4j reusable knowledge and existing project histories intact until a verified migration is completed.
2. Apply `backend/app/design_studio/postgres_schema.sql`, followed by `postgres_release_schema.sql`, explicitly against that database. Request handlers never create these schemas.
3. Set backend-only `DESIGN_STUDIO_DATABASE_URL`, `DESIGN_STUDIO_STORAGE_BACKEND=postgres`, and `DESIGN_STUDIO_POSTGRES_ENABLED=1`. If needed, set `DESIGN_STUDIO_PG_CA_FILE` to the trusted provider CA file. Never place database credentials in Vite variables.
4. Restart the backend. Verify actual PostgreSQL connectivity, ownership/history migration, transaction conflicts, cross-tenant access, retained ZIP downloads and backup restoration before public use.

The loopback local website continues to use its configured Neo4j project namespace and local release store. Production identity is still required independently of database selection. Connections follow [Psycopg connection/transaction semantics](https://www.psycopg.org/psycopg3/docs/basic/usage.html) and its [dictionary row factory](https://www.psycopg.org/psycopg3/docs/api/rows.html).

## Still open

| Remaining work | Dependency or limit |
| --- | --- |
| Trusted production sign-in and organization provisioning | Identity provider details requested; no production identity integration has been activated |
| Online build/execution service and generated-app operational storage | Hosting/worker provider details requested; Vercel does not replace the current loopback runtime with hosted apps |
| Actual PostgreSQL activation and migration of existing graph project history | Hosted access explicitly deferred by the user; wiring and offline contracts are not a live migration |
| GitHub synchronization and deployment promotion/rollback | CI files are prepared; repository/account integration and deployment lifecycle remain to implement |
| Production artifact retention/backups/monitoring and recovery exercises | PostgreSQL release adapter exists; real provider configuration, policies and operational verification remain |
| Universal automatic business-data migrations | Only conservative compatible copies are implemented; breaking changes require an explicit tested migration |
| Read-only/external domain fixture coverage | 67 generated checks still skip, including seven in the saved TMS; permissions were not broadened or checks silently removed |
| Reviewed vendor/region knowledge and customer policies | All 23 source-reference versions remain draft. Evidence links do not establish expert business review or resolve customer-specific assumptions |
| Full browser acceptance across every generated domain/role | Component/runtime suites and focused live TMS review are verified; comprehensive browser journeys remain |

Customer integrations remain schema/provider driven. Generated apps do not automatically connect to Noordveld catalogue/order APIs. No existing assumption was promoted into confirmed policy.
