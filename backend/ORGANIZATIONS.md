# Organizations, permissions and the workspace

Code: `app/orgs/` (permissions, directory, catalogue), `app/api/routes/workspace.py`, the gate in
`app/api/routes/design_studio.py` (`studio_gate`, `project_user`). UI: `/workspace`.

## Three identity layers

| Layer | Who | Where it lives |
|---|---|---|
| Platform | Platform administrator, solution architect, business analyst, UI/UX designer, implementation engineer, support operator | `PLATFORM_ROLES`. They carry **domain-knowledge** permissions (`domain.propose/review/approve/administer`) and platform administration. They carry **no** access to a customer's projects. |
| Organization | Organization administrator, project owner, business analyst, process owner, business approver, designer, developer, read-only reviewer | `ORG_ROLES`, scoped to ONE organization through a membership. |
| Application | Transport planner, dispatcher, carrier partner, warehouse operator, inventory manager, dealer, service technician, … | **Per application**, declared in the domain pack (`app_roles`) and the catalogue. A user holds one only through an explicit grant for an organization and that application. Never a global role. |

Consequences, all enforced server-side and tested (`tests/test_orgs.py`): a platform administrator is not a member of any
customer organization and cannot open its projects; a customer administrator cannot reach another organization's projects
(404, whatever header is sent); a dealer with only application grants has no Design Studio access (403); the approver of a
domain release (`domain.approve`) is a platform role the customer cannot grant; design approval (`studio.approve`) belongs to
its own role, and the person who created a project can never approve it.

## Enforcement

`studio_gate` runs on every Design Studio route. With a configured directory it resolves the active organization
(`X-Org-Id` header, `?org=`, or the single membership), maps the HTTP operation to a permission (`studio.use`, `studio.edit`,
`studio.approve`, `studio.generate`, `project.create`), checks the user's roles in that organization, and pins every
`/projects/{id}` request to the organization the project was registered in. `project_user` lets members reach a project
stored under its creator while approvals and audit still name the real actor.

**Local-demo fallback.** With no directory configured (`NoDirectory`), the older owner-only rules apply, still behind
`require_studio_identity` (demo identity is local/undeployed only; deployed requests get 503). A configured directory is never
bypassed. In deployed environments no directory exists, so nothing organization-scoped is allowed.

## Onboarding

No public registration path creates a platform administrator or an organization. Members join by **invitation**: an
organization administrator (or a project owner, for lower roles) creates one; the token is shown once and only its hash is
stored; accepting needs a signed-in user whose email matches; platform roles can never be invited; an organization always
keeps at least one administrator. Platform staff and organizations are seeded (`seed_*`) by whoever provisions the
environment. Delivering the invitation (email) is outside this service.

## What is not here yet

* **No production directory.** `SqliteOrgDirectory` is the isolated local implementation (a temporary file). The trusted
  identity provider must supply memberships; until then deployed environments hold nobody.
* The project store is still owner-private; sharing works through the registry, so the store's own audit trail names the
  project's creator (the approval record and the organization audit name the real actor).
* The workspace "activity" is the organization audit log (invitations, role changes, project registration), not a full
  event stream.

## Application catalogue

`app/orgs/catalogue.py` lists the systems a workspace shows and is honest about status: **operational** (exists in this repo and
runs against its own data), **in_design** (modelled in Design Studio; at most previews and contracts), **planned**. A design is
never launchable.
