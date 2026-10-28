"""Organization directory: organizations, teams, memberships, platform staff, application grants, invitations, project registry and access.

`SqliteOrgDirectory` is the isolated local implementation (a temporary file, never a production database). There is no
production directory yet: the trusted identity provider must supply memberships through the organization directory, so
the default directory is `NoDirectory`, which holds nobody and answers every question with "no access".

Invitations are the only way into an organization. A token is shown once and only its hash is stored; accepting needs a
signed-in user whose verified email matches the invitation, and an invitation can never carry a platform role. An invitation
can carry an organization role, application access, project access and a team; accepting applies all of it in one transaction.

Project access has two policies per organization. `assigned` (the default) means nobody reaches a project without an explicit
assignment, directly or through a team; `org` means every member with the organization permission does (a convenience that the
organization chooses, never the default). Whatever the policy, the organization permission is checked as well.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import secrets
import sqlite3
from pathlib import Path
from typing import Protocol

from app.orgs.permissions import (
    ALL_PROJECT_CAPABILITIES,
    APP_ADMIN,
    GRANTABLE_BY,
    ORG_ROLES,
    PLATFORM_ROLES,
    PROJECT_LEVELS,
    PROJECT_POLICIES,
    org_permissions,
    platform_permissions,
)

INVITE_DAYS = 7


class DirectoryError(Exception):
    """A refused directory operation; the message is safe to show."""


class Forbidden(DirectoryError):
    pass


class NotFound(DirectoryError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def _stamp() -> str:
    return _now().isoformat(timespec="seconds")


def mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:1]}{'•' * max(2, len(name) - 1)}@{domain}"


class OrgDirectory(Protocol):
    configured: bool

    def organizations_of(self, user_id: str) -> list[dict]: ...
    def roles(self, user_id: str, org_id: str) -> frozenset[str]: ...
    def platform_roles(self, user_id: str) -> frozenset[str]: ...
    def permissions(self, user_id: str, org_id: str | None) -> frozenset[str]: ...
    def app_grants(self, user_id: str, org_id: str) -> list[dict]: ...
    def project_org(self, project_id: str) -> str | None: ...
    def project_creator(self, project_id: str) -> str | None: ...
    def register_project(self, project_id: str, org_id: str, created_by: str) -> None: ...
    def projects_of(self, org_id: str) -> list[dict]: ...
    def project_capabilities(
        self, user_id: str, org_id: str, project_id: str
    ) -> frozenset[str]: ...
    def record(
        self,
        actor: str,
        action: str,
        org_id: str | None,
        detail: str,
        *,
        target: str | None = None,
        outcome: str = "success",
    ) -> None: ...


class NoDirectory:
    """Deployed default: nobody belongs to anything, so nothing organization-scoped is allowed."""

    configured = False

    def organizations_of(self, user_id: str) -> list[dict]:
        return []

    def roles(self, user_id: str, org_id: str) -> frozenset[str]:
        return frozenset()

    def platform_roles(self, user_id: str) -> frozenset[str]:
        return frozenset()

    def permissions(self, user_id: str, org_id: str | None) -> frozenset[str]:
        return frozenset()

    def app_grants(self, user_id: str, org_id: str) -> list[dict]:
        return []

    def project_org(self, project_id: str) -> str | None:
        return None

    def project_creator(self, project_id: str) -> str | None:
        return None

    def register_project(self, project_id: str, org_id: str, created_by: str) -> None:
        raise Forbidden("No organization directory is configured")

    def projects_of(self, org_id: str) -> list[dict]:
        return []

    def project_capabilities(self, user_id: str, org_id: str, project_id: str) -> frozenset[str]:
        return frozenset()

    def record(
        self,
        actor: str,
        action: str,
        org_id: str | None,
        detail: str,
        *,
        target: str | None = None,
        outcome: str = "success",
    ) -> None:
        return None


SCHEMA = """
CREATE TABLE IF NOT EXISTS organizations (id TEXT PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS memberships (user_id TEXT NOT NULL, org_id TEXT NOT NULL, role TEXT NOT NULL, PRIMARY KEY(user_id, org_id, role));
CREATE TABLE IF NOT EXISTS platform_staff (user_id TEXT NOT NULL, role TEXT NOT NULL, PRIMARY KEY(user_id, role));
CREATE TABLE IF NOT EXISTS app_grants (user_id TEXT NOT NULL, org_id TEXT NOT NULL, app_id TEXT NOT NULL, app_role TEXT NOT NULL, PRIMARY KEY(user_id, org_id, app_id, app_role));
CREATE TABLE IF NOT EXISTS invitations (token_hash TEXT PRIMARY KEY, org_id TEXT NOT NULL, email TEXT NOT NULL, role TEXT NOT NULL, invited_by TEXT NOT NULL,
    expires_at TEXT NOT NULL, accepted_by TEXT, accepted_at TEXT);
CREATE TABLE IF NOT EXISTS projects (project_id TEXT PRIMARY KEY, org_id TEXT NOT NULL, created_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS audit (seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, org_id TEXT, detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS teams (id TEXT PRIMARY KEY, org_id TEXT NOT NULL, name TEXT NOT NULL, UNIQUE(org_id, name));
CREATE TABLE IF NOT EXISTS team_members (team_id TEXT NOT NULL, user_id TEXT NOT NULL, PRIMARY KEY(team_id, user_id));
CREATE TABLE IF NOT EXISTS team_app_grants (team_id TEXT NOT NULL, org_id TEXT NOT NULL, app_id TEXT NOT NULL, app_role TEXT NOT NULL, PRIMARY KEY(team_id, app_id, app_role));
CREATE TABLE IF NOT EXISTS project_access (project_id TEXT NOT NULL, org_id TEXT NOT NULL, subject_kind TEXT NOT NULL, subject_id TEXT NOT NULL, level TEXT NOT NULL,
    PRIMARY KEY(project_id, subject_kind, subject_id));
"""
# Columns added after the first version; applied to existing databases too, so a directory file is never discarded to upgrade it.
COLUMNS = {
    "organizations": [("project_policy", "TEXT NOT NULL DEFAULT 'assigned'")],
    "audit": [("target", "TEXT"), ("outcome", "TEXT NOT NULL DEFAULT 'success'")],
    "invitations": [("grants_json", "TEXT NOT NULL DEFAULT '{}'"), ("revoked_at", "TEXT")],
}


class SqliteOrgDirectory:
    configured = True

    def __init__(self, path: Path):
        self.path = Path(path)
        setup = sqlite3.connect(self.path, isolation_level=None)
        try:
            setup.executescript(SCHEMA)
            for table, columns in COLUMNS.items():
                present = {row[1] for row in setup.execute(f"PRAGMA table_info({table})")}
                for name, definition in columns:
                    if name not in present:
                        setup.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        finally:
            setup.close()

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=5, isolation_level=None)
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.execute("COMMIT")
        except BaseException:
            db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    # ── seeding (local demo and tests only; no public operation creates platform staff or organizations) ──
    def seed_organization(self, org_id: str, name: str, project_policy: str = "assigned") -> None:
        if project_policy not in PROJECT_POLICIES:
            raise DirectoryError("Unknown project access policy")
        with self._db() as db:
            db.execute(
                "INSERT OR IGNORE INTO organizations (id, name, project_policy) VALUES (?,?,?)",
                (org_id, name, project_policy),
            )

    def seed_membership(self, user_id: str, org_id: str, role: str) -> None:
        if role not in ORG_ROLES:
            raise DirectoryError(f"Unknown organization role {role}")
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO memberships VALUES (?,?,?)", (user_id, org_id, role))

    def seed_platform_role(self, user_id: str, role: str) -> None:
        if role not in PLATFORM_ROLES:
            raise DirectoryError(f"Unknown platform role {role}")
        with self._db() as db:
            db.execute("INSERT OR IGNORE INTO platform_staff VALUES (?,?)", (user_id, role))

    def seed_app_grant(self, user_id: str, org_id: str, app_id: str, app_role: str) -> None:
        with self._db() as db:
            db.execute(
                "INSERT OR IGNORE INTO app_grants VALUES (?,?,?,?)",
                (user_id, org_id, app_id, app_role),
            )

    # ── reads ──
    def organizations_of(self, user_id: str) -> list[dict]:
        with self._db() as db:
            rows = db.execute(
                """SELECT o.id, o.name FROM organizations o WHERE o.id IN (SELECT org_id FROM memberships WHERE user_id=?
                                 UNION SELECT org_id FROM app_grants WHERE user_id=?
                                 UNION SELECT t.org_id FROM teams t JOIN team_members m ON m.team_id=t.id WHERE m.user_id=?) ORDER BY o.name""",
                (user_id, user_id, user_id),
            ).fetchall()
        return [
            {"id": row[0], "name": row[1], "roles": sorted(self.roles(user_id, row[0]))}
            for row in rows
        ]

    def organization(self, org_id: str) -> dict | None:
        with self._db() as db:
            row = db.execute(
                "SELECT id, name, project_policy FROM organizations WHERE id=?", (org_id,)
            ).fetchone()
        return {"id": row[0], "name": row[1], "project_policy": row[2]} if row else None

    def roles(self, user_id: str, org_id: str) -> frozenset[str]:
        with self._db() as db:
            return frozenset(
                row[0]
                for row in db.execute(
                    "SELECT role FROM memberships WHERE user_id=? AND org_id=?", (user_id, org_id)
                )
            )

    def platform_roles(self, user_id: str) -> frozenset[str]:
        with self._db() as db:
            return frozenset(
                row[0]
                for row in db.execute("SELECT role FROM platform_staff WHERE user_id=?", (user_id,))
            )

    def permissions(self, user_id: str, org_id: str | None) -> frozenset[str]:
        """Organization permissions in `org_id` only, plus platform permissions. A platform role adds nothing inside an organization."""
        held = platform_permissions(self.platform_roles(user_id))
        return held | (org_permissions(self.roles(user_id, org_id)) if org_id else frozenset())

    def teams_of(self, user_id: str, org_id: str) -> list[str]:
        with self._db() as db:
            return [
                row[0]
                for row in db.execute(
                    "SELECT t.id FROM teams t JOIN team_members m ON m.team_id=t.id WHERE m.user_id=? AND t.org_id=? ORDER BY t.id",
                    (user_id, org_id),
                )
            ]

    def app_grants(self, user_id: str, org_id: str) -> list[dict]:
        """Direct grants and the grants of the user's teams, in this organization only."""
        with self._db() as db:
            rows = db.execute(
                "SELECT app_id, app_role FROM app_grants WHERE user_id=? AND org_id=?",
                (user_id, org_id),
            ).fetchall()
            rows += db.execute(
                """SELECT g.app_id, g.app_role FROM team_app_grants g JOIN team_members m ON m.team_id=g.team_id
                                  WHERE m.user_id=? AND g.org_id=?""",
                (user_id, org_id),
            ).fetchall()
        return [{"app_id": app, "app_role": role} for app, role in sorted(set(rows))]

    def is_app_admin(self, user_id: str, org_id: str, app_id: str) -> bool:
        return any(
            item["app_id"] == app_id and item["app_role"] == APP_ADMIN
            for item in self.app_grants(user_id, org_id)
        )

    def app_users(self, org_id: str, app_id: str) -> list[dict]:
        with self._db() as db:
            direct = db.execute(
                "SELECT user_id, app_role FROM app_grants WHERE org_id=? AND app_id=? ORDER BY user_id, app_role",
                (org_id, app_id),
            ).fetchall()
            teams = db.execute(
                "SELECT team_id, app_role FROM team_app_grants WHERE org_id=? AND app_id=? ORDER BY team_id, app_role",
                (org_id, app_id),
            ).fetchall()
        return [{"subject": "user", "id": user, "app_role": role} for user, role in direct] + [
            {"subject": "team", "id": team, "app_role": role} for team, role in teams
        ]

    def project_org(self, project_id: str) -> str | None:
        with self._db() as db:
            row = db.execute(
                "SELECT org_id FROM projects WHERE project_id=?", (project_id,)
            ).fetchone()
        return row[0] if row else None

    def project_creator(self, project_id: str) -> str | None:
        with self._db() as db:
            row = db.execute(
                "SELECT created_by FROM projects WHERE project_id=?", (project_id,)
            ).fetchone()
        return row[0] if row else None

    def projects_of(self, org_id: str) -> list[dict]:
        with self._db() as db:
            rows = db.execute(
                "SELECT project_id, created_by, created_at FROM projects WHERE org_id=? ORDER BY created_at DESC",
                (org_id,),
            ).fetchall()
        return [{"project_id": row[0], "created_by": row[1], "created_at": row[2]} for row in rows]

    def project_capabilities(self, user_id: str, org_id: str, project_id: str) -> frozenset[str]:
        """What this person may do inside ONE project: empty means no access at all. Evaluated on the server for every request."""
        subjects = [("user", user_id)] + [("team", team) for team in self.teams_of(user_id, org_id)]
        is_member = bool(self.roles(user_id, org_id))
        with self._db() as db:
            policy = db.execute(
                "SELECT o.project_policy FROM organizations o JOIN projects p ON p.org_id=o.id WHERE p.project_id=? AND o.id=?",
                (project_id, org_id),
            ).fetchone()
            if policy is None:
                return frozenset()  # unknown project, or a project of another organization
            levels = [
                row[0]
                for kind, subject in subjects
                for row in db.execute(
                    "SELECT level FROM project_access WHERE project_id=? AND subject_kind=? AND subject_id=?",
                    (project_id, kind, subject),
                )
            ]
        capabilities = (
            frozenset().union(
                *(PROJECT_LEVELS[level] for level in levels if level in PROJECT_LEVELS)
            )
            if levels
            else frozenset()
        )
        if policy[0] == "org" and is_member:
            return (
                ALL_PROJECT_CAPABILITIES - ({"manage"} if "manage" not in capabilities else set())
                | capabilities
            )
        return capabilities

    def can_manage_project_access(self, user_id: str, org_id: str, project_id: str) -> bool:
        """The project's owners and the organization's administrators assign access; administering access is not content access."""
        return "org.manage_members" in org_permissions(
            self.roles(user_id, org_id)
        ) or "manage" in self.project_capabilities(user_id, org_id, project_id)

    def projects_visible_to(self, user_id: str, org_id: str) -> list[dict]:
        return [
            entry
            for entry in self.projects_of(org_id)
            if "read" in self.project_capabilities(user_id, org_id, entry["project_id"])
        ]

    def project_access(self, org_id: str, project_id: str) -> list[dict]:
        with self._db() as db:
            rows = db.execute(
                "SELECT subject_kind, subject_id, level FROM project_access WHERE org_id=? AND project_id=? ORDER BY subject_kind, subject_id",
                (org_id, project_id),
            ).fetchall()
        return [{"subject": row[0], "id": row[1], "level": row[2]} for row in rows]

    def members(self, org_id: str) -> list[dict]:
        with self._db() as db:
            rows = db.execute(
                "SELECT user_id, role FROM memberships WHERE org_id=? ORDER BY user_id, role",
                (org_id,),
            ).fetchall()
        result: dict[str, list[str]] = {}
        for user_id, role in rows:
            result.setdefault(user_id, []).append(role)
        return [{"user_id": user, "roles": roles} for user, roles in result.items()]

    def teams(self, org_id: str) -> list[dict]:
        with self._db() as db:
            teams = db.execute(
                "SELECT id, name FROM teams WHERE org_id=? ORDER BY name", (org_id,)
            ).fetchall()
            return [
                {
                    "id": tid,
                    "name": name,
                    "members": [
                        row[0]
                        for row in db.execute(
                            "SELECT user_id FROM team_members WHERE team_id=? ORDER BY user_id",
                            (tid,),
                        )
                    ],
                }
                for tid, name in teams
            ]

    def audit_trail(
        self, org_id: str, limit: int | None = None, prefix: str | None = None
    ) -> list[dict]:
        with self._db() as db:
            rows = db.execute(
                "SELECT at, actor, action, detail, target, outcome FROM audit WHERE org_id=? AND (? IS NULL OR action LIKE ?) ORDER BY seq",
                (org_id, prefix, f"{prefix}%" if prefix else None),
            ).fetchall()
        trail = [
            {
                "at": row[0],
                "actor": row[1],
                "action": row[2],
                "detail": row[3],
                "target": row[4],
                "outcome": row[5],
            }
            for row in rows
        ]
        return trail[-limit:] if limit else trail

    def record(
        self,
        actor: str,
        action: str,
        org_id: str | None,
        detail: str,
        *,
        target: str | None = None,
        outcome: str = "success",
    ) -> None:
        with self._db() as db:
            self._audit(db, actor, action, org_id, detail, target, outcome)

    # ── writes: projects and their access ──
    def register_project(self, project_id: str, org_id: str, created_by: str) -> None:
        with self._db() as db:
            if db.execute("SELECT 1 FROM organizations WHERE id=?", (org_id,)).fetchone() is None:
                raise NotFound("Unknown organization")
            existing = db.execute(
                "SELECT org_id FROM projects WHERE project_id=?", (project_id,)
            ).fetchone()
            if existing and existing[0] != org_id:
                raise Forbidden("That project ID belongs to another organization")
            if existing is None:
                db.execute(
                    "INSERT INTO projects VALUES (?,?,?,?)",
                    (project_id, org_id, created_by, _stamp()),
                )
                db.execute(
                    "INSERT OR IGNORE INTO project_access VALUES (?,?,?,?,?)",
                    (project_id, org_id, "user", created_by, "owner"),
                )  # the creator owns it
            self._audit(db, created_by, "project.register", org_id, project_id, project_id)

    def set_project_policy(self, actor: str, org_id: str, policy: str) -> None:
        if "org.manage_members" not in org_permissions(self.roles(actor, org_id)):
            raise Forbidden("Only an organization administrator changes how projects are shared")
        if policy not in PROJECT_POLICIES:
            raise DirectoryError("Unknown project access policy")
        with self._db() as db:
            db.execute("UPDATE organizations SET project_policy=? WHERE id=?", (policy, org_id))
            self._audit(db, actor, "projects.policy", org_id, policy, org_id)

    def assign_project(
        self, actor: str, org_id: str, project_id: str, subject: str, subject_id: str, level: str
    ) -> None:
        if level not in PROJECT_LEVELS:
            raise DirectoryError("Unknown project access level")
        if subject not in ("user", "team"):
            raise DirectoryError("Assign access to a person or a team")
        if self.project_org(project_id) != org_id:
            raise NotFound("No such project in this organization")
        if not self.can_manage_project_access(actor, org_id, project_id):
            raise Forbidden(
                "Only the project's owners and the organization's administrators assign access"
            )
        if subject == "team" and not any(team["id"] == subject_id for team in self.teams(org_id)):
            raise NotFound("No such team in this organization")
        if subject == "user" and not (
            self.roles(subject_id, org_id) or self.app_grants(subject_id, org_id)
        ):
            raise DirectoryError(
                "That person is not a member of this organization. Invite them first."
            )
        with self._db() as db:
            owners = db.execute(
                "SELECT COUNT(*) FROM project_access WHERE project_id=? AND level='owner'",
                (project_id,),
            ).fetchone()[0]
            current = db.execute(
                "SELECT level FROM project_access WHERE project_id=? AND subject_kind=? AND subject_id=?",
                (project_id, subject, subject_id),
            ).fetchone()
            if current and current[0] == "owner" and level != "owner" and owners <= 1:
                raise DirectoryError("A project needs at least one owner")
            db.execute(
                "INSERT OR REPLACE INTO project_access VALUES (?,?,?,?,?)",
                (project_id, org_id, subject, subject_id, level),
            )
            self._audit(
                db,
                actor,
                "project.assign",
                org_id,
                f"{project_id}: {subject} {subject_id} as {level}",
                project_id,
            )

    def unassign_project(
        self, actor: str, org_id: str, project_id: str, subject: str, subject_id: str
    ) -> None:
        if self.project_org(project_id) != org_id:
            raise NotFound("No such project in this organization")
        if not self.can_manage_project_access(actor, org_id, project_id):
            raise Forbidden(
                "Only the project's owners and the organization's administrators assign access"
            )
        with self._db() as db:
            current = db.execute(
                "SELECT level FROM project_access WHERE project_id=? AND subject_kind=? AND subject_id=?",
                (project_id, subject, subject_id),
            ).fetchone()
            if (
                current
                and current[0] == "owner"
                and db.execute(
                    "SELECT COUNT(*) FROM project_access WHERE project_id=? AND level='owner'",
                    (project_id,),
                ).fetchone()[0]
                <= 1
            ):
                raise DirectoryError("A project needs at least one owner")
            db.execute(
                "DELETE FROM project_access WHERE project_id=? AND subject_kind=? AND subject_id=?",
                (project_id, subject, subject_id),
            )
            self._audit(
                db,
                actor,
                "project.unassign",
                org_id,
                f"{project_id}: {subject} {subject_id}",
                project_id,
            )

    # ── writes: teams ──
    def create_team(self, actor: str, org_id: str, name: str) -> str:
        if "org.manage_members" not in org_permissions(self.roles(actor, org_id)):
            raise Forbidden("You may not manage teams")
        name = " ".join(name.split())
        if not name:
            raise DirectoryError("A team needs a name")
        team_id = f"team_{secrets.token_hex(5)}"
        with self._db() as db:
            if db.execute(
                "SELECT 1 FROM teams WHERE org_id=? AND name=?", (org_id, name)
            ).fetchone():
                raise DirectoryError("A team with that name already exists")
            db.execute("INSERT INTO teams VALUES (?,?,?)", (team_id, org_id, name))
            self._audit(db, actor, "team.create", org_id, f"{team_id}: {name}", team_id)
        return team_id

    def set_team_member(
        self, actor: str, org_id: str, team_id: str, user_id: str, present: bool = True
    ) -> None:
        if "org.manage_members" not in org_permissions(self.roles(actor, org_id)):
            raise Forbidden("You may not manage teams")
        known = present and bool(self.roles(user_id, org_id) or self.app_grants(user_id, org_id))
        with self._db() as db:
            if (
                db.execute(
                    "SELECT 1 FROM teams WHERE id=? AND org_id=?", (team_id, org_id)
                ).fetchone()
                is None
            ):
                raise NotFound("No such team in this organization")
            if present:
                if not known:
                    raise DirectoryError(
                        "That person is not a member of this organization. Invite them first."
                    )
                db.execute("INSERT OR IGNORE INTO team_members VALUES (?,?)", (team_id, user_id))
            else:
                db.execute(
                    "DELETE FROM team_members WHERE team_id=? AND user_id=?", (team_id, user_id)
                )
            self._audit(
                db,
                actor,
                "team.member_add" if present else "team.member_remove",
                org_id,
                f"{team_id}: {user_id}",
                team_id,
            )

    # ── writes: invitations ──
    def invite(
        self,
        actor: str,
        org_id: str,
        email: str,
        role: str | None = None,
        *,
        app_grants: list[dict] | None = None,
        project_access: list[dict] | None = None,
        team_id: str | None = None,
    ) -> str:
        """Returns the one-time token. The inviter must be allowed to grant everything the invitation carries; platform roles can never be invited."""
        app_grants, project_access = app_grants or [], project_access or []
        if not (role or app_grants or project_access):
            raise DirectoryError(
                "An invitation must carry a role, application access or project access"
            )
        mine = self.roles(actor, org_id)
        administrator = "org.manage_members" in org_permissions(mine)
        if role:
            if role not in ORG_ROLES:
                raise DirectoryError("That is not an organization role")
            if "org.invite" not in org_permissions(mine) or not any(
                role in GRANTABLE_BY.get(held, frozenset()) for held in mine
            ):
                raise Forbidden("You may not invite someone to that role")
        for grant in app_grants:
            if not administrator and not (
                self.is_app_admin(actor, org_id, grant["app_id"]) and grant["app_role"] != APP_ADMIN
            ):
                raise Forbidden(
                    "You may only invite people to applications you administer, and only an organization administrator grants the administrator profile"
                )
        for item in project_access:
            if (
                item.get("level") not in PROJECT_LEVELS
                or self.project_org(item.get("project_id", "")) != org_id
            ):
                raise DirectoryError("Unknown project or access level")
            if not self.can_manage_project_access(actor, org_id, item["project_id"]):
                raise Forbidden("You may not give access to that project")
        if team_id and (
            not administrator or not any(team["id"] == team_id for team in self.teams(org_id))
        ):
            raise Forbidden("Only an organization administrator adds people to a team")
        token = secrets.token_urlsafe(32)
        carried = {"app_grants": app_grants, "project_access": project_access, "team_id": team_id}
        with self._db() as db:
            db.execute(
                "INSERT INTO invitations (token_hash, org_id, email, role, invited_by, expires_at, accepted_by, accepted_at, grants_json) VALUES (?,?,?,?,?,?,NULL,NULL,?)",
                (
                    _hash(token),
                    org_id,
                    email.strip().lower(),
                    role or "",
                    actor,
                    (_now() + timedelta(days=INVITE_DAYS)).isoformat(timespec="seconds"),
                    json.dumps(carried),
                ),
            )
            self._audit(
                db,
                actor,
                "invite.create",
                org_id,
                f"{email.strip().lower()} as {role or 'application user'}: {json.dumps(carried, sort_keys=True)}",
                email.strip().lower(),
            )
        return token

    def preview(self, token: str) -> dict:
        """What an invitation offers, for the page a person lands on before signing in. One uniform error for anything not usable."""
        with self._db() as db:
            row = db.execute(
                """SELECT i.org_id, o.name, i.email, i.role, i.expires_at, i.accepted_by, i.revoked_at, i.grants_json
                                FROM invitations i JOIN organizations o ON o.id=i.org_id WHERE i.token_hash=?""",
                (_hash(token),),
            ).fetchone()
        if (
            row is None
            or row[5] is not None
            or row[6] is not None
            or datetime.fromisoformat(row[4]) < _now()
        ):
            raise NotFound("This invitation is invalid, expired or already used")
        carried = json.loads(row[7])
        return {
            "organization": {"id": row[0], "name": row[1]},
            "email_hint": mask_email(row[2]),
            "role": row[3] or None,
            "app_grants": carried.get("app_grants", []),
            "project_access": [
                {"project_id": item["project_id"], "level": item["level"]}
                for item in carried.get("project_access", [])
            ],
            "team": carried.get("team_id"),
            "expires_at": row[4],
        }

    def accept(self, user_id: str, user_email: str, token: str) -> dict:
        with self._db() as db:
            row = db.execute(
                "SELECT org_id, email, role, expires_at, accepted_by, revoked_at, grants_json FROM invitations WHERE token_hash=?",
                (_hash(token),),
            ).fetchone()
            if (
                row is None
                or row[4] is not None
                or row[5] is not None
                or datetime.fromisoformat(row[3]) < _now()
            ):
                raise NotFound("This invitation is invalid, expired or already used")
            if row[1] != user_email.strip().lower():
                raise Forbidden("This invitation was issued to a different email address")
            org_id, role, carried = row[0], row[2], json.loads(row[6])
            db.execute(
                "UPDATE invitations SET accepted_by=?, accepted_at=? WHERE token_hash=?",
                (user_id, _stamp(), _hash(token)),
            )
            if role:
                db.execute(
                    "INSERT OR IGNORE INTO memberships VALUES (?,?,?)", (user_id, org_id, role)
                )
            for grant in carried.get("app_grants", []):
                db.execute(
                    "INSERT OR IGNORE INTO app_grants VALUES (?,?,?,?)",
                    (user_id, org_id, grant["app_id"], grant["app_role"]),
                )
            for item in carried.get("project_access", []):
                if db.execute(
                    "SELECT 1 FROM projects WHERE project_id=? AND org_id=?",
                    (item["project_id"], org_id),
                ).fetchone():
                    db.execute(
                        "INSERT OR REPLACE INTO project_access VALUES (?,?,?,?,?)",
                        (item["project_id"], org_id, "user", user_id, item["level"]),
                    )
            if (
                carried.get("team_id")
                and db.execute(
                    "SELECT 1 FROM teams WHERE id=? AND org_id=?", (carried["team_id"], org_id)
                ).fetchone()
            ):
                db.execute(
                    "INSERT OR IGNORE INTO team_members VALUES (?,?)", (carried["team_id"], user_id)
                )
            self._audit(
                db,
                user_id,
                "invite.accept",
                org_id,
                role or "application access",
                _hash(token)[:12],
            )
        return {
            "org_id": org_id,
            "role": role or None,
            "app_grants": carried.get("app_grants", []),
            "project_access": carried.get("project_access", []),
        }

    def invitations(self, actor: str, org_id: str) -> list[dict]:
        if "org.manage_members" not in org_permissions(self.roles(actor, org_id)):
            raise Forbidden("You may not view invitations")
        with self._db() as db:
            rows = db.execute(
                "SELECT token_hash, email, role, invited_by, expires_at, accepted_by, revoked_at, grants_json FROM invitations WHERE org_id=? ORDER BY expires_at DESC",
                (org_id,),
            ).fetchall()
        now = _now()
        return [
            {
                "id": row[0][:12],
                "email": row[1],
                "role": row[2] or None,
                "invited_by": row[3],
                "expires_at": row[4],
                "app_grants": json.loads(row[7]).get("app_grants", []),
                "status": "accepted"
                if row[5]
                else "revoked"
                if row[6]
                else "expired"
                if datetime.fromisoformat(row[4]) < now
                else "pending",
            }
            for row in rows
        ]

    def revoke_invitation(self, actor: str, org_id: str, invitation_id: str) -> None:
        if "org.manage_members" not in org_permissions(self.roles(actor, org_id)):
            raise Forbidden("You may not revoke invitations")
        with self._db() as db:
            row = db.execute(
                "SELECT token_hash, accepted_by FROM invitations WHERE org_id=? AND substr(token_hash,1,12)=?",
                (org_id, invitation_id),
            ).fetchone()
            if row is None or row[1] is not None:
                raise NotFound("No pending invitation with that id in this organization")
            db.execute("UPDATE invitations SET revoked_at=? WHERE token_hash=?", (_stamp(), row[0]))
            self._audit(db, actor, "invite.revoke", org_id, invitation_id, invitation_id)

    # ── writes: roles and application access ──
    def set_roles(self, actor: str, org_id: str, user_id: str, roles: list[str]) -> list[str]:
        """Replace a member's roles. Needs org.manage_members; the actor can only grant or remove roles they may grant."""
        mine = self.roles(actor, org_id)
        if "org.manage_members" not in org_permissions(mine):
            raise Forbidden("You may not change members")
        if not roles or any(role not in ORG_ROLES for role in roles):
            raise DirectoryError("Give one or more valid organization roles")
        allowed = frozenset().union(*(GRANTABLE_BY.get(held, frozenset()) for held in mine))
        before = self.roles(user_id, org_id)
        if (set(roles) ^ before) - allowed:
            raise Forbidden("You may not grant or remove one of those roles")
        if "org_admin" in before and "org_admin" not in roles and self._admin_count(org_id) <= 1:
            raise DirectoryError("An organization needs at least one administrator")
        with self._db() as db:
            db.execute("DELETE FROM memberships WHERE user_id=? AND org_id=?", (user_id, org_id))
            db.executemany(
                "INSERT INTO memberships VALUES (?,?,?)",
                [(user_id, org_id, role) for role in sorted(set(roles))],
            )
            self._audit(
                db, actor, "members.set_roles", org_id, f"{user_id}: {sorted(set(roles))}", user_id
            )
        return sorted(set(roles))

    def _may_administer_app(self, actor: str, org_id: str, app_id: str, app_role: str) -> bool:
        if "org.manage_members" in org_permissions(self.roles(actor, org_id)):
            return True
        return (
            self.is_app_admin(actor, org_id, app_id) and app_role != APP_ADMIN
        )  # an app administrator never creates another administrator

    def grant_app(self, actor: str, org_id: str, user_id: str, app_id: str, app_role: str) -> None:
        if not self._may_administer_app(actor, org_id, app_id, app_role):
            raise Forbidden("You may not grant that application role")
        if not (self.roles(user_id, org_id) or self.app_grants(user_id, org_id)):
            raise DirectoryError(
                "That person is not a member of this organization. Invite them first."
            )
        with self._db() as db:
            db.execute(
                "INSERT OR IGNORE INTO app_grants VALUES (?,?,?,?)",
                (user_id, org_id, app_id, app_role),
            )
            self._audit(db, actor, "app.grant", org_id, f"{user_id}: {app_id}/{app_role}", user_id)

    def revoke_app(self, actor: str, org_id: str, user_id: str, app_id: str, app_role: str) -> None:
        if not self._may_administer_app(actor, org_id, app_id, app_role):
            raise Forbidden("You may not revoke that application role")
        organization_admin = "org.manage_members" in org_permissions(self.roles(actor, org_id))
        with self._db() as db:
            remaining = db.execute(
                "SELECT COUNT(DISTINCT user_id) FROM app_grants WHERE org_id=? AND app_id=? AND app_role=? AND user_id<>?",
                (org_id, app_id, APP_ADMIN, user_id),
            ).fetchone()[0]
            if app_role == APP_ADMIN and remaining == 0 and not organization_admin:
                raise DirectoryError("An application needs at least one administrator")
            db.execute(
                "DELETE FROM app_grants WHERE user_id=? AND org_id=? AND app_id=? AND app_role=?",
                (user_id, org_id, app_id, app_role),
            )
            self._audit(db, actor, "app.revoke", org_id, f"{user_id}: {app_id}/{app_role}", user_id)

    def grant_team_app(
        self, actor: str, org_id: str, team_id: str, app_id: str, app_role: str
    ) -> None:
        if "org.manage_members" not in org_permissions(self.roles(actor, org_id)):
            raise Forbidden("Only an organization administrator gives a team application access")
        with self._db() as db:
            if (
                db.execute(
                    "SELECT 1 FROM teams WHERE id=? AND org_id=?", (team_id, org_id)
                ).fetchone()
                is None
            ):
                raise NotFound("No such team in this organization")
            db.execute(
                "INSERT OR IGNORE INTO team_app_grants VALUES (?,?,?,?)",
                (team_id, org_id, app_id, app_role),
            )
            self._audit(
                db, actor, "app.grant_team", org_id, f"{team_id}: {app_id}/{app_role}", team_id
            )

    def _admin_count(self, org_id: str) -> int:
        with self._db() as db:
            return db.execute(
                "SELECT COUNT(DISTINCT user_id) FROM memberships WHERE org_id=? AND role='org_admin'",
                (org_id,),
            ).fetchone()[0]

    @staticmethod
    def _audit(
        db,
        actor: str,
        action: str,
        org_id: str | None,
        detail: str,
        target: str | None = None,
        outcome: str = "success",
    ) -> None:
        db.execute(
            "INSERT INTO audit (at, actor, action, org_id, detail, target, outcome) VALUES (?,?,?,?,?,?,?)",
            (_stamp(), actor, action, org_id, detail, target, outcome),
        )


def get_org_directory() -> OrgDirectory:
    return NoDirectory()
