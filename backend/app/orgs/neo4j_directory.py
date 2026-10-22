"""Neo4j organization directory using one atomic namespace transaction per change."""

from datetime import datetime, timedelta, timezone
import secrets
from hashlib import sha256
from app.orgs.directory import DirectoryError, Forbidden, NotFound, INVITE_DAYS
from app.orgs.permissions import (
    ORG_ROLES,
    PLATFORM_ROLES,
    GRANTABLE_BY,
    org_permissions,
    platform_permissions,
)


class Neo4jOrgDirectory:
    configured = True

    def __init__(self, documents):
        self.docs = documents

    def _state(self, tx):
        return self.docs.get(tx, "directory", "organizations") or dict(
            organizations={},
            memberships={},
            platform={},
            grants=[],
            projects={},
            invitations={},
            audit=[],
        )

    def _read(self, work):
        return self.docs.read(lambda tx: work(self._state(tx)))

    def _write(self, work):
        def apply(tx):
            state = self._state(tx)
            result = work(state)
            self.docs.put(tx, "directory", "organizations", state)
            return result

        return self.docs.write(apply)

    @staticmethod
    def _roles(state, user, org):
        return frozenset(state["memberships"].get(org, {}).get(user, []))

    @staticmethod
    def _audit(state, actor, action, org, detail):
        state["audit"].append(
            dict(
                at=datetime.now(timezone.utc).isoformat(),
                actor=actor,
                action=action,
                org_id=org,
                detail=detail,
            )
        )

    def seed_organization(self, org_id, name):
        self._write(lambda s: s["organizations"].setdefault(org_id, name))

    def seed_membership(self, user_id, org_id, role):
        if role not in ORG_ROLES:
            raise DirectoryError("Unknown organization role")

        def work(s):
            held = s["memberships"].setdefault(org_id, {}).setdefault(user_id, [])
            if role not in held:
                held.append(role)

        self._write(work)

    def seed_platform_role(self, user_id, role):
        if role not in PLATFORM_ROLES:
            raise DirectoryError("Unknown platform role")

        def work(s):
            held = s["platform"].setdefault(user_id, [])
            if role not in held:
                held.append(role)

        self._write(work)

    def seed_app_grant(self, user_id, org_id, app_id, app_role):
        def work(s):
            grant = dict(user_id=user_id, org_id=org_id, app_id=app_id, app_role=app_role)
            if grant not in s["grants"]:
                s["grants"].append(grant)

        self._write(work)

    def organizations_of(self, user_id):
        return self._read(
            lambda s: [
                dict(id=org, name=name, roles=sorted(self._roles(s, user_id, org)))
                for org, name in sorted(s["organizations"].items(), key=lambda row: row[1])
                if self._roles(s, user_id, org)
                or any(g["user_id"] == user_id and g["org_id"] == org for g in s["grants"])
            ]
        )

    def roles(self, user_id, org_id):
        return self._read(lambda s: self._roles(s, user_id, org_id))

    def platform_roles(self, user_id):
        return self._read(lambda s: frozenset(s["platform"].get(user_id, [])))

    def permissions(self, user_id, org_id):
        return self._read(
            lambda s: (
                platform_permissions(s["platform"].get(user_id, []))
                | (org_permissions(self._roles(s, user_id, org_id)) if org_id else frozenset())
            )
        )

    def app_grants(self, user_id, org_id):
        return self._read(
            lambda s: [
                dict(app_id=g["app_id"], app_role=g["app_role"])
                for g in s["grants"]
                if g["org_id"] == org_id and g["user_id"] == user_id
            ]
        )

    def project_org(self, project_id):
        return self._read(lambda s: s["projects"].get(project_id, {}).get("org_id"))

    def project_creator(self, project_id):
        return self._read(lambda s: s["projects"].get(project_id, {}).get("created_by"))

    def projects_of(self, org_id):
        return self._read(
            lambda s: sorted(
                [
                    dict(project_id=k, created_by=p["created_by"], created_at=p["created_at"])
                    for k, p in s["projects"].items()
                    if p["org_id"] == org_id
                ],
                key=lambda p: p["created_at"],
                reverse=True,
            )
        )

    def members(self, org_id):
        return self._read(
            lambda s: [
                dict(user_id=u, roles=sorted(r))
                for u, r in sorted(s["memberships"].get(org_id, {}).items())
            ]
        )

    def audit_trail(self, org_id):
        return self._read(
            lambda s: [
                {k: v for k, v in a.items() if k != "org_id"}
                for a in s["audit"]
                if a["org_id"] == org_id
            ]
        )

    def register_project(self, project_id, org_id, created_by):
        def work(s):
            if org_id not in s["organizations"]:
                raise NotFound("Unknown organization")
            existing = s["projects"].get(project_id)
            if existing and existing["org_id"] != org_id:
                raise Forbidden("Project belongs to another organization")
            s["projects"].setdefault(
                project_id,
                dict(
                    org_id=org_id,
                    created_by=created_by,
                    created_at=datetime.now(timezone.utc).isoformat(),
                ),
            )
            self._audit(s, created_by, "project.register", org_id, project_id)

        self._write(work)

    def invite(self, actor, org_id, email, role):
        token = secrets.token_urlsafe(32)

        def work(s):
            mine = self._roles(s, actor, org_id)
            if role not in ORG_ROLES:
                raise DirectoryError("Unknown organization role")
            if "org.invite" not in org_permissions(mine) or not any(
                role in GRANTABLE_BY.get(r, []) for r in mine
            ):
                raise Forbidden("You may not invite this role")
            s["invitations"][sha256(token.encode()).hexdigest()] = dict(
                org_id=org_id,
                email=email.strip().lower(),
                role=role,
                expires_at=(datetime.now(timezone.utc) + timedelta(days=INVITE_DAYS)).isoformat(),
                accepted_by=None,
            )
            self._audit(s, actor, "invite.create", org_id, role)

        self._write(work)
        return token

    def accept(self, user_id, user_email, token):
        def work(s):
            invite = s["invitations"].get(sha256(token.encode()).hexdigest())
            if (
                not invite
                or invite["accepted_by"]
                or datetime.fromisoformat(invite["expires_at"]) < datetime.now(timezone.utc)
            ):
                raise NotFound("Invitation is invalid, expired or used")
            if invite["email"] != user_email.strip().lower():
                raise Forbidden("Invitation is for a different email address")
            invite["accepted_by"] = user_id
            held = s["memberships"].setdefault(invite["org_id"], {}).setdefault(user_id, [])
            if invite["role"] not in held:
                held.append(invite["role"])
            self._audit(s, user_id, "invite.accept", invite["org_id"], invite["role"])
            return dict(org_id=invite["org_id"], role=invite["role"])

        return self._write(work)

    def set_roles(self, actor, org_id, user_id, roles):
        def work(s):
            mine = self._roles(s, actor, org_id)
            if "org.manage_members" not in org_permissions(mine):
                raise Forbidden("You may not change members")
            if not roles or any(r not in ORG_ROLES for r in roles):
                raise DirectoryError("Valid roles required")
            before = self._roles(s, user_id, org_id)
            allowed = frozenset().union(*(GRANTABLE_BY.get(r, frozenset()) for r in mine))
            if (set(roles) ^ before) - allowed:
                raise Forbidden("You may not change one of these roles")
            if (
                "org_admin" in before
                and "org_admin" not in roles
                and sum("org_admin" in r for r in s["memberships"].get(org_id, {}).values()) <= 1
            ):
                raise DirectoryError("At least one administrator is required")
            s["memberships"].setdefault(org_id, {})[user_id] = sorted(set(roles))
            self._audit(s, actor, "members.set_roles", org_id, user_id)
            return sorted(set(roles))

        return self._write(work)

    def grant_app(self, actor, org_id, user_id, app_id, app_role):
        def work(s):
            if "org.manage_members" not in org_permissions(self._roles(s, actor, org_id)):
                raise Forbidden("You may not grant application access")
            grant = dict(user_id=user_id, org_id=org_id, app_id=app_id, app_role=app_role)
            if grant not in s["grants"]:
                s["grants"].append(grant)
            self._audit(s, actor, "app.grant", org_id, f"{user_id}:{app_id}/{app_role}")

        self._write(work)
