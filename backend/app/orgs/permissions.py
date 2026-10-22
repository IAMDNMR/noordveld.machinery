"""Roles and permissions for the three identity layers. Every protected operation is checked server-side against these.

  platform   : the Noordveld/Pixels team. Platform roles never grant access to a customer's projects or business
               applications; support access to a customer organization needs an explicit membership there.
  organization: a customer's people. Roles are scoped to ONE organization.
  application : the people who use a generated business application (planner, dispatcher, warehouse operator, dealer…).
               These are NOT global roles: each application declares its own roles (see `app_roles` in the domain pack) and
               a user holds one only through an explicit grant for that organization and application.

Design Studio access is an organization permission (`studio.use`). A dealer or carrier who only has an application
grant therefore cannot reach Design Studio.
"""

from __future__ import annotations

PLATFORM_ROLES: dict[str, frozenset[str]] = {
    # Platform permissions administer the platform itself, never a customer's business content.
    "platform_admin": frozenset(
        {
            "platform.manage_orgs",
            "platform.manage_staff",
            "domain.propose",
            "domain.review",
            "domain.approve",
            "domain.administer",
        }
    ),
    "solution_architect": frozenset({"domain.propose", "domain.review"}),
    "business_analyst": frozenset({"domain.propose"}),
    "ux_designer": frozenset(),
    "implementation_engineer": frozenset({"domain.propose"}),
    "support_operator": frozenset(),
}

ORG_ROLES: dict[str, frozenset[str]] = {
    "org_admin": frozenset(
        {
            "org.manage_members",
            "org.invite",
            "project.create",
            "project.read",
            "studio.use",
            "studio.edit",
            "studio.review",
            "studio.generate",
            "app.launch",
        }
    ),
    "project_owner": frozenset(
        {
            "project.create",
            "project.read",
            "studio.use",
            "studio.edit",
            "studio.review",
            "studio.generate",
            "app.launch",
        }
    ),
    "business_analyst": frozenset({"project.read", "studio.use", "studio.edit", "app.launch"}),
    "process_owner": frozenset(
        {"project.read", "studio.use", "studio.edit", "studio.review", "app.launch"}
    ),
    "business_approver": frozenset(
        {"project.read", "studio.use", "studio.review", "studio.approve", "app.launch"}
    ),
    "designer": frozenset({"project.read", "studio.use", "studio.edit", "app.launch"}),
    "developer": frozenset(
        {"project.read", "studio.use", "studio.edit", "studio.generate", "app.launch"}
    ),
    "reviewer": frozenset({"project.read", "studio.use", "app.launch"}),  # read-only
}
# Who may grant which organization role. Nobody can grant a platform role through an organization.
GRANTABLE_BY: dict[str, frozenset[str]] = {
    "org_admin": frozenset(ORG_ROLES),
    "project_owner": frozenset(
        {"business_analyst", "process_owner", "designer", "developer", "reviewer"}
    ),
}

ORG_PERMISSIONS = frozenset().union(*ORG_ROLES.values())
PLATFORM_PERMISSIONS = frozenset().union(*PLATFORM_ROLES.values())
# Permissions that need an explicit second step in addition to holding them.
SEPARATE_APPROVAL = frozenset({"studio.approve", "domain.approve"})


def org_permissions(roles: set[str] | frozenset[str]) -> frozenset[str]:
    return frozenset().union(*(ORG_ROLES.get(role, frozenset()) for role in roles))


def platform_permissions(roles: set[str] | frozenset[str]) -> frozenset[str]:
    return frozenset().union(*(PLATFORM_ROLES.get(role, frozenset()) for role in roles))


# ── project-level access: who may do what inside ONE project, on top of the organization permission ──
# Levels are what an administrator assigns to a person or team. Each level carries capabilities; a request needs the organization
# permission AND the capability. Under the `assigned` policy nobody reaches a project without an assignment (not even an org admin's
# content access: administering assignments is separate from editing the project).
PROJECT_LEVELS: dict[str, frozenset[str]] = {
    "viewer": frozenset({"read"}),
    "reviewer": frozenset({"read", "review"}),
    "editor": frozenset({"read", "edit"}),
    "owner": frozenset({"read", "review", "edit", "manage"}),
}
ALL_PROJECT_CAPABILITIES = frozenset({"read", "review", "edit", "manage"})
# The capability an organization permission needs inside a project.
PERMISSION_CAPABILITY: dict[str, str] = {
    "studio.use": "read",
    "app.launch": "read",
    "project.read": "read",
    "studio.review": "review",
    "studio.approve": "review",
    "studio.edit": "edit",
    "studio.generate": "edit",
}
PROJECT_POLICIES = frozenset(
    {"assigned", "org"}
)  # assigned: least privilege (default). org: every member with the organization permission.

# ── application-level profiles ──
# An application declares its own business roles (planner, dealer, ...). Two profiles exist for every application:
APP_ADMIN = "app_admin"  # the generated-application administrator: manages THAT application's users and settings, nothing else
APP_VIEWER = "app_viewer"  # read-only use of that application
APP_PROFILE_PERMISSIONS: dict[str, frozenset[str]] = {
    APP_ADMIN: frozenset({"app.use", "app.users.manage", "app.settings.manage"}),
    APP_VIEWER: frozenset({"app.use", "app.read_only"}),
}
PROJECT_APP_PREFIX = "project:"  # the application generated from a Design Studio project is addressed as project:<project id>
PROJECT_APP_ROLES = (APP_ADMIN, "app_user", APP_VIEWER)

# Combinable profiles shown to a person, derived from what they hold; never a second source of truth for enforcement.
PROFILE_LABELS: dict[str, str] = {
    "org_admin": "Organization administrator",
    "project_owner": "Design Studio creator",
    "developer": "Design Studio creator",
    "designer": "Design Studio creator",
    "business_analyst": "Design Studio creator",
    "process_owner": "Process owner and reviewer",
    "business_approver": "Approver",
    "reviewer": "Read-only reviewer",
}
