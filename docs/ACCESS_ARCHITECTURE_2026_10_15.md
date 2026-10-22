# Unified accounts, access and onboarding — 15 October 2026

Extends the existing identity model (`backend/ORGANIZATIONS.md`); nothing was replaced. The signed-session cookie, the demo sign-in,
`CurrentUser`, the organization directory, `studio_gate`, invitations and application grants are all still the mechanism. Nothing is
committed or deployed. The user's message describing this task arrived cut off in section 4 ("Assign…"); sections 1–3 and the onboarding
experience are implemented, the rest is listed under *Not done*.

## The two journeys

| | Platform creator | Business user |
|---|---|---|
| Where | Design Studio, projects | Workspace → applications |
| Granted by | an organization role with `studio.use` **and** a project assignment | an application grant (or the application's own profile) |
| Sees | Design Studio only if `studio.use`; only projects assigned to them | only applications granted to them; never Design Studio |
| Server enforcement | `studio_gate`: organization permission + project capability | `require_app(app_id)`: grant in the active organization |

`/workspace` returns `journeys` (`creator`, `business_user`), `profiles` (combinable labels derived from what the person holds, for display only),
`can_administer`, and per application `can_manage_users`. An ordinary account grants nothing: no role, no grant → no Design Studio and no applications.

## Model (all in `app/orgs/directory.py`, stable ids, tenant-scoped)

organizations (+ `project_policy`) · memberships (roles) · **teams** and team members · platform staff · application grants (direct and via teams) ·
**invitations** carrying role / application access / project access / team · projects · **project_access** (person or team → level) · audit.
An existing directory file is upgraded in place (`COLUMNS`), and the upgrade never widens access (default policy `assigned`).

## Permission profiles (kept separate, combinable)

- Platform administrator: platform and domain-knowledge permissions only; never customer content (unchanged).
- Design Studio creator: `project_owner`, `developer`, `designer`, `business_analyst` — and only within assigned projects.
- Organization administrator: `org_admin` — members, invitations, teams, application access, project *assignments* and the project policy. Administering access is
  **not** content access: under the default policy an administrator without an assignment gets 404 on a project's content.
- Generated-application administrator: application role `app_admin` — manages that one application's users (cannot create another administrator, cannot touch other applications, cannot read members or audit).
- Business end user: the application's own roles. Read-only: `app_viewer` (applications) and `reviewer` (Studio); read-only profiles cannot write.
- Approver: `business_approver` (`studio.approve`); the creator of a project still cannot approve it.

Project levels: `viewer` (read) · `reviewer` (read, review/approve) · `editor` (read, edit, generate) · `owner` (all + manage access). A request needs the organization
permission **and** the capability. Policy per organization: `assigned` (default; nobody reaches a project unassigned) or `org` (explicit organization choice; the demo
organization uses it so a single-browser walkthrough works).

## Enforcement

- `studio_gate` (every Design Studio route): organization → permission → project belongs to the organization → project capability. A person with no access at all gets the
  same 404 as for a project that does not exist (no id probing); someone with some access but not this capability gets 403 naming what is missing.
- `require_app` (`app/api/app_access.py`) on Agentic Shopping, Parts Intelligence, orders and checkout: signed-in, member of the active organization (`X-Org-Id`, or the only one),
  holds a grant for that application (or the creator permission `app.launch`), read-only profile never writes.
- Every workspace route that names an organization requires membership first; outsiders get the answer for an unknown organization.
- Audit: invitations (create, accept, revoke), role/team/application/project access changes, policy changes, **authorized sensitive operations** (approve, generate/test/launch, apply/revert, create)
  and **refusals** (`access.denied`). Readable only by organization administrators (`GET /workspace/organizations/{org}/audit`).

## Onboarding

`/invite?token=…`: verifies the invitation without revealing anything for an unusable one (uniform 404 for unknown, expired, used or revoked), shows exactly what it gives (organization, role or
application access, project access, expiry, masked email), sends a signed-out person through sign-in and back, accepts it (email must match; one use; everything applied in one transaction), and lands on a
workspace welcome that says which journeys the person has. A wrong account gets a plain message and a Switch account action. Administrators create, list and revoke invitations and manage project access in
the workspace. The navigation now follows the active organization (it showed Design Studio from a previous organization before).

## Verified

Backend `tests/test_access_architecture.py` (12) + `tests/test_orgs.py` (12). Frontend: invitation page (5), workspace journey (1), nav. Browser (isolated local Studio, synthetic people): invitation preview → sign in → accept →
welcome; business user sees Agentic Shopping and no Design Studio, server answers 403 on Design Studio; reuse of a token 404; invitation for another account refused; revoked invitation reveals nothing; administrator invites
from the workspace; invitation page on a phone without horizontal overflow.

## Not done / limits (be explicit)

1. **No real authentication.** Sign-in is still the local demo identity (no password, local only); a production identity provider is still the open prerequisite in `DESIGN_STUDIO_ACTIVATION.md`. Invitations bind to a verified email only once such a provider supplies it.
2. **Without a configured directory (every environment today except the local Studio) the business-application routes behave as before: public demo.** `require_app` enforces grants only when a directory exists. Deciding to make the public demo require sign-in is a product decision not taken here.
3. **Generated applications still use their own demo identities.** One platform login → app access is designed (a signed launch ticket mapping the person's application roles to the generated app's roles, role ids `project:<id>` with `app_admin/app_user/app_viewer`) and the grant model supports it (`project:` applications), but the runtime is not yet wired to it.
4. Record-level isolation inside the operational commerce data (orders belong to customers by the existing service rules) was not re-audited; generated apps isolate by tenant already.
5. Business units are teams; there is no deeper business-unit hierarchy. Request-access (as opposed to invite) workflow is not built. Project owners cannot issue organization-role invitations (only organization administrators hold `org.invite`, as before).
6. The org audit records authorized attempts and refusals, not outcomes (the project's own audit holds those).
