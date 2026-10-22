"""What the signed-in person may do in one Design Studio project, and why not where they may not.

Computed on the server from the same directory the gate uses, so the interface can show exactly what is authorized and give a useful
reason for what is not. It never grants anything: every request is still checked by the gate and by the handler.

Design Studio roles (organization roles grouped by what they are for; combinable, never implied by creating an application):
  creator   — project owner, developer, designer, business analyst, process owner: build and generate. Cannot approve their own project.
  approver  — business approver: reviews and approves what someone else created. Cannot edit or generate.
  reviewer  — read-only reviewer: reads, previews and launches for review. Cannot change or approve anything.
Organization administration is a separate profile (members, invitations, assignments); it carries no content access to a project.
"""

from __future__ import annotations

from app.orgs.directory import OrgDirectory
from app.orgs.permissions import ALL_PROJECT_CAPABILITIES, PERMISSION_CAPABILITY

STUDIO_ROLE_OF = {
    "project_owner": "creator",
    "developer": "creator",
    "designer": "creator",
    "business_analyst": "creator",
    "process_owner": "creator",
    "business_approver": "approver",
    "reviewer": "reviewer",
}
STUDIO_ROLE_LABEL = {
    "creator": "Creator",
    "approver": "Approver",
    "reviewer": "Reviewer (read-only)",
}
LEVEL_ORDER = ("viewer", "reviewer", "editor", "owner")


def studio_roles(org_roles: frozenset[str]) -> list[str]:
    return sorted({STUDIO_ROLE_OF[role] for role in org_roles if role in STUDIO_ROLE_OF})


def access_summary(
    directory: OrgDirectory, user_id: str, org_id: str | None, project_id: str
) -> dict:
    if not directory.configured or org_id is None:
        # The isolated local demo without a directory: the older owner-only rules apply, so nothing here narrows them.
        everything = sorted(ALL_PROJECT_CAPABILITIES)
        return {
            "organization": None,
            "studio_roles": [],
            "studio_role_labels": [],
            "org_roles": [],
            "project_capabilities": everything,
            "creator": True,
            "can": {
                action: True
                for action in ("edit", "generate", "review", "approve", "launch", "manage_access")
            },
            "denied": {},
            "policy": None,
        }
    permissions = directory.permissions(user_id, org_id)
    roles = directory.roles(user_id, org_id)
    held = directory.project_capabilities(user_id, org_id, project_id)
    creator = directory.project_creator(project_id) == user_id
    manage = hasattr(
        directory, "can_manage_project_access"
    ) and directory.can_manage_project_access(user_id, org_id, project_id)  # type: ignore[attr-defined]

    def allowed(permission: str) -> bool:
        return permission in permissions and PERMISSION_CAPABILITY[permission] in held

    can = {
        "edit": allowed("studio.edit"),
        "generate": allowed("studio.generate"),
        "review": allowed("studio.review"),
        "approve": allowed("studio.approve") and not creator,
        "launch": allowed("app.launch"),
        "manage_access": manage,
    }
    denied: dict[str, str] = {}

    def why(action: str, permission: str) -> None:
        if can[action]:
            return
        if permission not in permissions:
            denied[action] = f"Your organization role does not include this. {_who_can(permission)}"
        elif PERMISSION_CAPABILITY[permission] not in held:
            level = "editor" if PERMISSION_CAPABILITY[permission] == "edit" else "reviewer"
            denied[action] = (
                f"Your access to this project is read-only for this. Ask a project owner for {level} access."
            )
        elif action == "approve" and creator:
            denied[action] = (
                "You created this project, so another approver in the organization must approve it."
            )

    for action, permission in (
        ("edit", "studio.edit"),
        ("generate", "studio.generate"),
        ("review", "studio.review"),
        ("approve", "studio.approve"),
        ("launch", "app.launch"),
    ):
        why(action, permission)
    if not can["manage_access"]:
        denied["manage_access"] = (
            "Only the project's owners and the organization's administrators assign access."
        )
    organization = directory.organization(org_id) if hasattr(directory, "organization") else None  # type: ignore[attr-defined]
    return {
        "organization": org_id,
        "studio_roles": studio_roles(roles),
        "studio_role_labels": [STUDIO_ROLE_LABEL[role] for role in studio_roles(roles)],
        "org_roles": sorted(roles),
        "project_capabilities": sorted(held),
        "creator": creator,
        "can": can,
        "denied": denied,
        "policy": organization["project_policy"] if organization else None,
    }


def _who_can(permission: str) -> str:
    return {
        "studio.edit": "Editing needs a creator role.",
        "studio.generate": "Generating needs a creator role with generation rights.",
        "studio.approve": "Approval needs the approver role.",
        "studio.review": "Reviewing needs a reviewer, approver or creator role.",
        "app.launch": "Launching a generated application needs a Design Studio role.",
    }.get(permission, "Ask your organization administrator.")
