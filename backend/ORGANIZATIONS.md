# Organizations and application access

`app/orgs/` contains the organization directory, application catalogue, role permissions and invitation handling. `app/api/routes/workspace.py` exposes the signed-in workspace and membership administration.

An application checks its access grant on the server for the selected organization. Read-only grants cannot write. Membership in another organization does not grant access.

The workspace lists only the operational catalogue, orders, parts intelligence and shopping applications. Invitations require a matching signed-in identity and are single use.

Organization identity storage is retained independently of removed application-generation features. Existing directory records are preserved; this removal performs no database migration.
