"""Main workspace: the signed-in user's organizations, the systems they may open, their projects and what needs their attention.

Everything is computed server-side from the organization directory. The browser may *hide* things for convenience, but
each protected application route enforces its own permissions independently.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.dependencies import CurrentUser
from app.orgs import directory as orgs
from app.orgs.catalogue import APPLICATIONS, BY_ID
from app.orgs.directory import DirectoryError, Forbidden, NotFound, OrgDirectory, get_org_directory
from app.orgs.permissions import (
    APP_ADMIN,
    APP_VIEWER,
    ORG_ROLES,
    PLATFORM_ROLES,
    PROFILE_LABELS,
    org_permissions,
)

router = APIRouter(
    prefix="/workspace", tags=["workspace"], 
)
Directory = Annotated[OrgDirectory, Depends(get_org_directory)]


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def _guard(call):
    try:
        return call()
    except Forbidden as exc:
        raise _error(403, "forbidden", str(exc)) from None
    except NotFound as exc:
        raise _error(404, "not_found", str(exc)) from None
    except DirectoryError as exc:
        raise _error(422, "invalid", str(exc)) from None


class AppGrantItem(BaseModel):
    model_config = {"extra": "forbid"}
    app_id: str = Field(min_length=1, max_length=90)
    app_role: str = Field(min_length=1, max_length=60)




class InviteBody(BaseModel):
    """What an invitation carries: an organization role, application access, project access and a team, in any combination."""

    model_config = {"extra": "forbid"}
    email: str = Field(min_length=3, max_length=200, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    role: str | None = Field(default=None, min_length=1, max_length=40)
    app_grants: list[AppGrantItem] = Field(default_factory=list, max_length=20)
    team_id: str | None = Field(default=None, max_length=40)


class TeamBody(BaseModel):
    model_config = {"extra": "forbid"}
    name: str = Field(min_length=1, max_length=80)


class TeamMemberBody(BaseModel):
    model_config = {"extra": "forbid"}
    user_id: str = Field(min_length=1, max_length=120)






class AcceptBody(BaseModel):
    token: str = Field(min_length=20, max_length=200)


class RolesBody(BaseModel):
    roles: list[str] = Field(min_length=1, max_length=8)


class GrantBody(BaseModel):
    user_id: str = Field(min_length=1, max_length=120)
    app_id: str = Field(min_length=1, max_length=60)
    app_role: str = Field(min_length=1, max_length=60)


def application_roles(directory: OrgDirectory, org_id: str, app_id: str) -> list[str] | None:
    """The roles an application can be granted, or None when it is not an application of this organization."""
    app = BY_ID.get(app_id)
    return None if app is None else [*app["app_roles"], APP_ADMIN, APP_VIEWER]


def profiles_of(
    roles: list[str] | frozenset[str], grants: list[dict], platform: list[str]
) -> list[str]:
    """Combinable profiles shown to a person. Derived from what they hold, never used for enforcement."""
    labels = [PROFILE_LABELS[role] for role in sorted(roles) if role in PROFILE_LABELS]
    labels += [
        f"Administrator of {BY_ID[item['app_id']]['name'] if item['app_id'] in BY_ID else item['app_id']}"
        for item in grants
        if item["app_role"] == APP_ADMIN
    ]
    if any(item["app_role"] != APP_ADMIN for item in grants):
        labels.append("Business user")
    labels += ["Platform " + role.replace("_", " ") for role in platform]
    return list(dict.fromkeys(labels))


def _member_org(
    directory: OrgDirectory, user_id: str, org: str | None
) -> tuple[list[dict], dict | None]:
    memberships = directory.organizations_of(user_id)
    if org is None:
        return memberships, (memberships[0] if len(memberships) == 1 else None)
    chosen = next((item for item in memberships if item["id"] == org), None)
    if chosen is None:
        raise _error(404, "organization_not_found", "You do not belong to that organization.")
    return memberships, chosen


@router.get("")
def workspace(
    user: CurrentUser,
    directory: Directory,
    org: str | None = Query(default=None, max_length=80),
):
    memberships, active = _member_org(directory, user.id, org)
    platform = sorted(directory.platform_roles(user.id))
    result: dict = {
        "user": {"id": user.id, "name": user.name, "email": user.email},
        "directory_configured": directory.configured,
        "platform_roles": platform,
        "organizations": memberships,
        "active_organization": active["id"] if active else None,
        "permissions": [],
        "applications": [],
        "activity": [],
        "onboarding": [],
    }
    if not directory.configured:
        result["onboarding"] = [
            "No organization directory is configured in this environment, so no organization workspace is available."
        ]
        return result
    if active is None:
        result["onboarding"] = (
            ["You have no organization yet. Ask an organization administrator for an invitation."]
            if not memberships
            else ["Choose an organization."]
        )
        return result
    org_id = active["id"]
    held = directory.permissions(user.id, org_id)
    result["permissions"] = sorted(
        permission for permission in held if not permission.startswith(("platform.", "domain."))
    )
    grants = directory.app_grants(user.id, org_id)
    granted = {item["app_id"]: [] for item in grants}
    for item in grants:
        granted[item["app_id"]].append(item["app_role"])
    can_launch = "app.launch" in held
    for app in APPLICATIONS:
        roles = granted.get(app["id"], [])
        usable = (
            app["status"] == "operational"
            and app["route"] is not None
            and (bool(roles) or can_launch)
        )
        reason = (
            None
            if usable
            else (
                "Not available for operational use yet: it is being designed."
                if app["status"] == "in_design"
                else "Planned; no project exists yet."
                if app["status"] == "planned"
                else "You have not been given access to this system."
            )
        )
        result["applications"].append(
            {
                **{key: app[key] for key in ("id", "name", "description", "domain", "status")},
                "route": app["route"] if usable else None,
                "launchable": usable,
                "your_roles": roles,
                "reason": reason,
            }
        )
    result["journeys"] = {"business_user": any(item["launchable"] for item in result["applications"])}
    result["profiles"] = profiles_of(directory.roles(user.id, org_id), grants, platform)
    admin = "org.manage_members" in held
    for item in result["applications"]:
        item["can_manage_users"] = admin or any(
            g["app_id"] == item["id"] and g["app_role"] == APP_ADMIN for g in grants
        )
    result["can_administer"] = admin
    result["activity"] = (
        list(reversed(directory.audit_trail(org_id)[-8:]))
        if hasattr(directory, "audit_trail") and "org.manage_members" in held
        else []
    )
    return result


@router.post("/organizations/{org_id}/invitations")
def invite(org_id: str, body: InviteBody, user: CurrentUser, directory: Directory):
    """A one-time token is returned once (only its hash is stored). Delivery of the invitation is outside this service."""
    if not directory.configured:
        raise _error(503, "directory_unavailable", "No organization directory is configured.")
    for item in body.app_grants:
        allowed = application_roles(directory, org_id, item.app_id)
        if allowed is None or item.app_role not in allowed:
            raise _error(422, "invalid", "Unknown application or role for that application.")
    token = _guard(
        lambda: directory.invite(
            user.id,
            org_id,
            body.email,
            body.role,
            app_grants=[item.model_dump() for item in body.app_grants],  # type: ignore[attr-defined]
            team_id=body.team_id,
        )
    )
    return {
        "organization": org_id,
        "email": body.email.lower(),
        "role": body.role,
        "app_grants": [item.model_dump() for item in body.app_grants],
        "token": token,
        "expires_in_days": orgs.INVITE_DAYS,
    }


@router.post("/invitations/accept")
def accept(body: AcceptBody, user: CurrentUser, directory: Directory):
    if not directory.configured:
        raise _error(503, "directory_unavailable", "No organization directory is configured.")
    return _guard(lambda: directory.accept(user.id, user.email, body.token))  # type: ignore[attr-defined]


@router.get("/organizations/{org_id}/members")
def members(org_id: str, user: CurrentUser, directory: Directory):
    if "org.manage_members" not in directory.permissions(user.id, org_id) or not directory.roles(
        user.id, org_id
    ):
        raise _error(403, "forbidden", "You may not view this organization's members.")
    return directory.members(org_id)  # type: ignore[attr-defined]


@router.put("/organizations/{org_id}/members/{member_id}")
def set_roles(
    org_id: str, member_id: str, body: RolesBody, user: CurrentUser, directory: Directory
):
    return {"roles": _guard(lambda: directory.set_roles(user.id, org_id, member_id, body.roles))}  # type: ignore[attr-defined]


@router.post("/organizations/{org_id}/application-grants")
def grant(org_id: str, body: GrantBody, user: CurrentUser, directory: Directory):
    allowed = application_roles(directory, org_id, body.app_id)
    if allowed is None or body.app_role not in allowed:
        raise _error(422, "invalid", "Unknown application or role for that application.")
    _guard(lambda: directory.grant_app(user.id, org_id, body.user_id, body.app_id, body.app_role))  # type: ignore[attr-defined]
    return {"granted": True}


@router.delete("/organizations/{org_id}/application-grants")
def revoke(org_id: str, body: GrantBody, user: CurrentUser, directory: Directory):
    _guard(lambda: directory.revoke_app(user.id, org_id, body.user_id, body.app_id, body.app_role))  # type: ignore[attr-defined]
    return {"revoked": True}


def _member_of(directory: OrgDirectory, user_id: str, org_id: str) -> None:
    """Any route that names an organization requires belonging to it; the answer for outsiders is the same as for an unknown organization."""
    if not any(item["id"] == org_id for item in directory.organizations_of(user_id)):
        raise _error(404, "organization_not_found", "You do not belong to that organization.")


@router.get("/organizations/{org_id}/applications/{app_id}/users")
def application_users(org_id: str, app_id: str, user: CurrentUser, directory: Directory):
    """The people and teams with access to ONE application. For its administrators and the organization's administrators."""
    _member_of(directory, user.id, org_id)
    if "org.manage_members" not in directory.permissions(
        user.id, org_id
    ) and not directory.is_app_admin(user.id, org_id, app_id):  # type: ignore[attr-defined]
        raise _error(403, "forbidden", "You may not view this application's users.")
    if application_roles(directory, org_id, app_id) is None:
        raise _error(404, "not_found", "No such application in this organization.")
    return {
        "application": app_id,
        "users": directory.app_users(org_id, app_id),
        "roles": application_roles(directory, org_id, app_id),
    }  # type: ignore[attr-defined]


@router.get("/invitations/preview")
def preview_invitation(directory: Directory, token: str = Query(min_length=20, max_length=200)):
    """What an invitation offers, for the page a person lands on from the invitation link. Reveals nothing for an unusable token."""
    if not directory.configured:
        raise _error(503, "directory_unavailable", "No organization directory is configured.")
    return _guard(lambda: directory.preview(token))  # type: ignore[attr-defined]


@router.get("/organizations/{org_id}/invitations")
def list_invitations(org_id: str, user: CurrentUser, directory: Directory):
    _member_of(directory, user.id, org_id)
    return _guard(lambda: directory.invitations(user.id, org_id))  # type: ignore[attr-defined]


@router.delete("/organizations/{org_id}/invitations/{invitation_id}")
def revoke_invitation(org_id: str, invitation_id: str, user: CurrentUser, directory: Directory):
    _member_of(directory, user.id, org_id)
    _guard(lambda: directory.revoke_invitation(user.id, org_id, invitation_id))  # type: ignore[attr-defined]
    return {"revoked": True}


@router.get("/organizations/{org_id}/teams")
def list_teams(org_id: str, user: CurrentUser, directory: Directory):
    _member_of(directory, user.id, org_id)
    if "org.manage_members" not in directory.permissions(user.id, org_id):
        raise _error(403, "forbidden", "You may not view teams.")
    return directory.teams(org_id)  # type: ignore[attr-defined]


@router.post("/organizations/{org_id}/teams")
def create_team(org_id: str, body: TeamBody, user: CurrentUser, directory: Directory):
    _member_of(directory, user.id, org_id)
    return {"id": _guard(lambda: directory.create_team(user.id, org_id, body.name))}  # type: ignore[attr-defined]


@router.put("/organizations/{org_id}/teams/{team_id}/members")
def add_team_member(
    org_id: str, team_id: str, body: TeamMemberBody, user: CurrentUser, directory: Directory
):
    _member_of(directory, user.id, org_id)
    _guard(lambda: directory.set_team_member(user.id, org_id, team_id, body.user_id, True))  # type: ignore[attr-defined]
    return {"added": True}


@router.delete("/organizations/{org_id}/teams/{team_id}/members/{member_id}")
def remove_team_member(
    org_id: str, team_id: str, member_id: str, user: CurrentUser, directory: Directory
):
    _member_of(directory, user.id, org_id)
    _guard(lambda: directory.set_team_member(user.id, org_id, team_id, member_id, False))  # type: ignore[attr-defined]
    return {"removed": True}










@router.get("/organizations/{org_id}/audit")
def audit(
    org_id: str,
    user: CurrentUser,
    directory: Directory,
    limit: int = Query(default=100, ge=1, le=500),
    action: str | None = Query(default=None, max_length=40),
):
    """The organization's audit trail: invitations, role and access changes, authorized sensitive operations and refusals."""
    _member_of(directory, user.id, org_id)
    if "org.manage_members" not in org_permissions(directory.roles(user.id, org_id)):
        raise _error(403, "forbidden", "Only an organization administrator reads the audit trail.")
    return list(reversed(directory.audit_trail(org_id, limit, action)))  # type: ignore[attr-defined]


@router.get("/roles")
def role_catalogue(_: CurrentUser):
    """What each role means, for the member-management screen. Application roles are listed per application, never globally."""
    return {
        "organization": {name: sorted(perms) for name, perms in ORG_ROLES.items()},
        "platform": {name: sorted(perms) for name, perms in PLATFORM_ROLES.items()},
        "application": {app["id"]: app["app_roles"] for app in APPLICATIONS},
    }
