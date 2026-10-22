# Studio persistent application storage

The local Studio now uses the dedicated `noordveld_studio` database in CockroachDB.
The website was restarted after migration. No public deployment was performed.

## What is saved

- Project definitions, including screens, workflow, data model, rules and permissions.
- Every saved project revision, its original audit actor and timestamp, approvals and lifecycle state.
- Immutable generated application ZIPs containing code, configuration and build instructions.
- Release hashes, archive checksums and independent generated-test results.

Six project heads, 40 historical revisions, two generated ZIPs and two existing test runs
were copied and verified. Archived/trashed projects were retained. Visibility still follows
the existing owner and organization access checks; these six records are not all shown to
every user. The current Transport Operations project remains at revision 12.

Generating an application now automatically retains its successful package. Opening a
preview remains read-only. Saved releases remain available after a newer revision is
created, and the existing Save release control can retry a failed storage request.
Generation cannot save an unapproved package. Packages use their content hash as identity;
repeating the same generation does not replace its original archive or audit actor.

Neo4j continues to store reusable domain/process knowledge. Source Neo4j project documents
and SQLite databases were left intact as rollback sources; they are no longer the primary
Studio project/release stores. SQL Server settings were retained but are not selected.

## Migration and rollback

The verified snapshot is outside the repository:
`%LOCALAPPDATA%/Noordveld/Studio/backups/cockroach-migration-20261021.json`.
It contains exact project/audit rows and base64-encoded ZIP bytes. Treat it as private data.
Its SHA-256 is `5a3677bde30778a3e16c462e5e02cef9f4cfaf4aee9f5677265e724716e4b25c`.

The migration script defaults to a read-only preflight, requires explicit acknowledgement
that writers are paused for an apply, uses only the dedicated database, and refuses a
nonempty unrelated target. All data rows and the completion marker commit together after
read-back verification. Conflicting history or corrupt archive bytes abort the import.
Do not rerun the original migration after users have made new SQL-backed edits.

For immediate rollback *before new SQL-backed changes*, stop the backend, set
`DESIGN_STUDIO_STORAGE_BACKEND=disabled` and `DESIGN_STUDIO_POSTGRES_ENABLED=0`, retain
the original `DESIGN_STUDIO_LOCAL_GRAPH_NAMESPACE=studio-local-site`, and restart using
`backend/scripts/serve_studio.py`. This selects the untouched original graph projects and
local releases. If new edits have occurred, first export and reconcile them; switching back
without reconciliation would hide those new edits. Do not delete the CockroachDB database.
Ongoing disaster recovery requires a separately configured CockroachDB backup/restore policy;
the migration snapshot is a point-in-time source backup, not continuous backup.

## Connection and deployment settings

The existing `backend/.env` contains the verified credentials. The connection uses
`sslmode=verify-full`; certificate and hostname verification remain enabled.

Backend environment variables:

| Variable | Purpose |
| --- | --- |
| `DESIGN_STUDIO_STORAGE_BACKEND=cockroach` | Select the compatible SQL adapter |
| `DESIGN_STUDIO_POSTGRES_ENABLED=1` | Explicit activation of that adapter |
| `DESIGN_STUDIO_DATABASE_URL` | Private URL pointing to `noordveld_studio` |
| `DESIGN_STUDIO_PG_CA_FILE` | Local path to the downloaded public cluster CA |
| `DESIGN_STUDIO_PG_CA_PEM` | Hosted alternative: multiline PEM certificate contents |
| `DESIGN_STUDIO_SQL_POOL_SIZE` | Optional bounded pool, default 5 connections; 0 disables pooling |

For a hosted backend, set the URL and CA PEM in its environment. The Windows certificate
path will not work on Vercel. Never expose these variables through a frontend `VITE_` key.
Existing identity and authorization guards remain in place. Saving to CockroachDB does not
provide hosted sign-in or a service that executes generated applications.

The database connections have timeouts, explicit transactions, and bounded retries of
complete database-only operations on SQLSTATE 40001. Network errors, unknown commit results
and revision conflicts are not replayed. Stored archives are checksum-verified on download.

## Limits

The generated app's running business records (for example, live shipments in its local
runtime SQLite database) are separate from Studio's saved source packages. Those operational
databases were not moved or reset. The exported app includes its own persistence setup.
The demo retains ZIPs directly in SQL under the existing 50 MB archive limit. Large binary
releases should use object storage before scaling this approach; no object-store account
or worker host was provisioned here.

Live concurrency, ownership, durable-package and test-history results are recorded in
`STUDIO_COCKROACH_VERIFICATION_2026_10_21.json`. The temporary verification records were
removed without touching any migrated projects or releases.

## Navigation and Trash controls

The public landing page now prioritizes **Open Design Studio**, linking to the dashboard;
the demo remains a secondary link and offers its own direct return to Studio. Hero links
use aligned text/icons and the heading wraps within its available width.

The SQL-backed dashboard offers **Delete permanently** for trashed projects that the user
owns/manages. It requires the exact name, current revision and no running app/test. One SQL
transaction removes the project, revision history, saved archives and test results. A minimal
deletion receipt reserves the ID and records actor/time so stale directory access cannot be
inherited by a newly created project. Directory audit history, migration backups and standalone
runtime databases are not erased. The verification used a disposable test project; existing
user projects were not deleted by the agent. Subsequent user deletions legitimately change the
migration-time inventory; the six-project count describes the verified migration snapshot.
