"""Small local officer identity store; petition checkpoints remain authoritative."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager

from fastapi import HTTPException, Request

from ..config import get_settings

COOKIE = "petition_officer"
TTL = 8 * 60 * 60


ADMIN = "admin"
OFFICER = "officer"

# -------------------------------------------------------------------- #
# Privilege catalogue. Hardcoded in Python by design: an admin can mix
# and match privileges on a custom role, but cannot invent new names
# that nothing enforces. Add a new privilege here first, then wire its
# check into the endpoint it gates — never the other direction.
# -------------------------------------------------------------------- #
#   manage_users      — admin panel: create, edit, delete officers,
#                       reset other officers' passwords. Also includes
#                       seeing the user list.
#   manage_roles      — the roles tab of the admin panel: create,
#                       edit, delete custom roles.
#   review_petitions  — the base review workflow: list petitions, open
#                       one, update its status, write a reply, assign a
#                       department. Every working officer needs this.
#   delete_petitions  — remove a petition from the service. Rare, and
#                       deliberately split so a reviewer-only role
#                       cannot destroy the citizen's record.
PRIV_MANAGE_USERS = "manage_users"
PRIV_MANAGE_ROLES = "manage_roles"
PRIV_MANAGE_FEATURES = "manage_features"
PRIV_REVIEW_PETITIONS = "review_petitions"
PRIV_DELETE_PETITIONS = "delete_petitions"

PRIVILEGES: dict[str, str] = {
    PRIV_MANAGE_USERS:     "Manage officers (create, edit, delete, reset password)",
    PRIV_MANAGE_ROLES:     "Manage roles (create and edit custom roles)",
    PRIV_MANAGE_FEATURES:  "Manage feature switches (turn parts of the service on and off)",
    PRIV_REVIEW_PETITIONS: "Review petitions (list, open, update, reply)",
    PRIV_DELETE_PETITIONS: "Delete petitions (remove a citizen record permanently)",
}

# The seed rows for `admin` and `officer`. Shipped so a fresh database
# comes up with a working two-tier split without a bootstrap step.
_BUILTIN_ROLES = (
    (ADMIN, "Administrator",
     [PRIV_MANAGE_USERS, PRIV_MANAGE_ROLES, PRIV_MANAGE_FEATURES,
      PRIV_REVIEW_PETITIONS, PRIV_DELETE_PETITIONS]),
    (OFFICER, "Review officer",
     [PRIV_REVIEW_PETITIONS]),
)

# -------------------------------------------------------------------- #
# Feature switches. The admin panel's "Features" tab exposes these as
# on/off toggles; both the citizen and officer front-ends read the
# live state to show or hide gated UI pieces. A flag not in this
# catalogue is nothing the service recognises; a toggle in the UI
# that nothing enforces would be a lie, so new flags must be defined
# here first and read by the pages that gate on them.
# -------------------------------------------------------------------- #

FEATURE_FLAGS: dict[str, dict] = {
    "citizen_voice_dictation": {
        "label": "Voice dictation on the citizen portal",
        "description": "Show the microphone button so a citizen can speak "
                       "their grievance rather than type it. Depends on an "
                       "ASR provider being configured.",
        "default": True,
        "audience": "citizen",
    },
    "citizen_multi_language": {
        "label": "Multi-language citizen portal",
        "description": "Show the language switcher (English, Tamil, "
                       "Malayalam, Telugu, Hindi). Off makes the citizen "
                       "portal English-only.",
        "default": True,
        "audience": "citizen",
    },
    "citizen_attachments": {
        "label": "Attachment uploads",
        "description": "Let the citizen attach supporting documents to "
                       "their petition (PDFs, photographs, slips).",
        "default": True,
        "audience": "citizen",
    },
    "officer_delete_petition": {
        "label": "Delete button in officer workspace",
        "description": "Show a delete action on the petition detail page. "
                       "Still subject to the 'delete_petitions' privilege "
                       "on the officer's role.",
        "default": True,
        "audience": "officer",
    },
    "officer_dictation": {
        "label": "Dictation on the officer portal",
        "description": "Show the dictation controls when an officer is "
                       "writing a reply.",
        "default": True,
        "audience": "officer",
    },
    "operator_screen": {
        "label": "Operator status screen",
        "description": "Serve the /operator technical status page. When "
                       "off the route returns 404.",
        "default": True,
        "audience": "operator",
    },
}


@contextmanager
def database(settings=None):
    path = (settings or get_settings()).data_dir / "officer.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS officers(username TEXT PRIMARY KEY, name TEXT NOT NULL, salt TEXT NOT NULL, password TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1, role TEXT NOT NULL DEFAULT 'officer');
    CREATE TABLE IF NOT EXISTS officer_sessions(token TEXT PRIMARY KEY, username TEXT NOT NULL, expires REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS officer_reviews(session_id TEXT PRIMARY KEY, status TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS officer_notes(id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, text TEXT NOT NULL, author TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS officer_audit(id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, status TEXT NOT NULL, author TEXT NOT NULL, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS login_attempts(host TEXT PRIMARY KEY, attempts INTEGER NOT NULL, since REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS citizen_sessions(session_id TEXT PRIMARY KEY, owner TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS officer_acknowledgements(
        session_id TEXT PRIMARY KEY,
        reference TEXT NOT NULL UNIQUE,
        acknowledged_by TEXT NOT NULL,
        acknowledged_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS officer_roles(
        name TEXT PRIMARY KEY,
        label TEXT NOT NULL,
        privileges TEXT NOT NULL,
        builtin INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS officer_feature_flags(
        name TEXT PRIMARY KEY,
        enabled INTEGER NOT NULL DEFAULT 1
    );
    """)
    # Existing deployments already have a two-column officer_reviews table.
    # Extend it in place so review metadata and the public tracking projection
    # stay in the same SQLite database and use the same busy timeout/locking.
    review_columns = {row[1] for row in db.execute("PRAGMA table_info(officer_reviews)")}
    for name, declaration in (
        ("assigned_department", "TEXT NOT NULL DEFAULT ''"),
        ("assigned_authority", "TEXT NOT NULL DEFAULT ''"),
        ("priority", "TEXT NOT NULL DEFAULT 'Normal'"),
        ("sla_target", "TEXT NOT NULL DEFAULT '15 Days'"),
        ("reply", "TEXT NOT NULL DEFAULT ''"),
    ):
        if name not in review_columns:
            db.execute(f"ALTER TABLE officer_reviews ADD COLUMN {name} {declaration}")
    # Role column migration. Deployments created before the admin panel have
    # a two-tier officer table whose column list omits `role` entirely. Add
    # the column, then grandfather every pre-existing officer to admin: before
    # roles existed, every provisioned officer was fully trusted, and
    # dropping a live service's only user down to a role that cannot manage
    # users would lock the operator out of their own portal. New officers
    # created from the admin panel default to the plain `officer` role.
    officer_columns = {row[1] for row in db.execute("PRAGMA table_info(officers)")}
    if "role" not in officer_columns:
        db.execute("ALTER TABLE officers ADD COLUMN role TEXT NOT NULL DEFAULT 'officer'")
        db.execute("UPDATE officers SET role='admin'")
    # Keep the two builtin role rows aligned with the live privilege
    # catalogue — a privilege added here reaches `admin` on the next
    # restart without a dedicated migration. Custom roles (builtin=0)
    # created by the admin panel are left alone.
    for name, label, privs in _BUILTIN_ROLES:
        db.execute(
            "INSERT INTO officer_roles(name,label,privileges,builtin) "
            "VALUES(?,?,?,1) "
            "ON CONFLICT(name) DO UPDATE SET label=excluded.label,"
            "privileges=excluded.privileges,builtin=1",
            (name, label, json.dumps(privs)),
        )
    # Seed every feature flag with its catalogue default — new flags
    # added to Python ship on by default (or off, as the catalogue
    # declares), without a dedicated migration. Flags the admin has
    # already toggled are left alone.
    for name, meta in FEATURE_FLAGS.items():
        db.execute(
            "INSERT OR IGNORE INTO officer_feature_flags(name,enabled) "
            "VALUES(?,?)",
            (name, 1 if meta["default"] else 0),
        )
    # And prune feature-flag rows for names that no Python code reads
    # any more, so the admin panel doesn't offer toggles that do
    # nothing.
    db.execute(
        "DELETE FROM officer_feature_flags WHERE name NOT IN ("
        + ",".join("?" * len(FEATURE_FLAGS)) + ")",
        tuple(FEATURE_FLAGS),
    ) if FEATURE_FLAGS else db.execute(
        "DELETE FROM officer_feature_flags")
    try:
        yield db
        db.commit()
    finally:
        db.close()


_ROLE_LABEL = {ADMIN: "Administrator", OFFICER: "Review officer"}


def _role_label(role: str) -> str:
    return _ROLE_LABEL.get(role, "Review officer")


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


_USERNAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


def _valid_username(raw: str) -> str:
    """Return a casefolded username or raise. A username ends up in a URL
    path (/api/officer/users/{username}), in SQL rows and in audit entries,
    so bind what it can be here rather than everywhere it is read."""
    value = (raw or "").strip().casefold()
    if not _USERNAME_PATTERN.match(value):
        raise ValueError(
            "Username must be 3–64 characters, lowercase letters, digits, "
            "and `._-` only, and must start with a letter or digit."
        )
    return value


_ROLE_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{2,31}$")


def _valid_role_name(raw: str) -> str:
    """A role name ends up in URLs and SQL rows. Bind it here, once."""
    value = (raw or "").strip().casefold()
    if not _ROLE_NAME_PATTERN.match(value):
        raise ValueError(
            "Role name must be 3–32 characters, lowercase letters, digits, "
            "`_` and `-` only, and must start with a letter or digit."
        )
    return value


def _valid_role_label(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        raise ValueError("Role label is required.")
    if len(value) > 80:
        raise ValueError("Role label is at most 80 characters.")
    return value


def _valid_privileges(raw) -> list[str]:
    """Accepts a list OR a comma-separated string. Returns a de-duped list
    of valid privilege names. Unknown privilege names are refused — the
    catalogue in Python is the floor; a role cannot grant something no
    endpoint checks."""
    if isinstance(raw, str):
        items = [p.strip() for p in raw.split(",") if p.strip()]
    elif isinstance(raw, (list, tuple)):
        items = [str(p).strip() for p in raw if str(p).strip()]
    else:
        raise ValueError("Privileges must be a list.")
    unknown = [p for p in items if p not in PRIVILEGES]
    if unknown:
        raise ValueError(
            f'Unknown privilege(s): {", ".join(sorted(set(unknown)))}. '
            f"Allowed: {', '.join(sorted(PRIVILEGES))}."
        )
    return sorted(set(items))


def _valid_role(raw: str) -> str:
    """Validate a role NAME against the live roles table. Falls back to
    `admin`/`officer` for cases where the DB has not yet been consulted
    — the migration seeds those two on first open, so this short-circuit
    only matters inside a transaction that is about to run the migration
    itself."""
    value = _valid_role_name(raw)
    if value in (ADMIN, OFFICER):
        return value
    with database() as db:
        row = db.execute(
            "SELECT 1 FROM officer_roles WHERE name=?", (value,)
        ).fetchone()
    if not row:
        raise ValueError(f'No such role "{value}".')
    return value


def _valid_password(raw: str) -> str:
    if raw is None or len(raw) < 12:
        raise ValueError("Use a password of at least 12 characters.")
    return raw


def _valid_name(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        raise ValueError("Display name is required.")
    if len(value) > 150:
        raise ValueError("Display name is at most 150 characters.")
    return value


def provision(username, name, password, role=OFFICER):
    """Create a new officer or reset an existing one.

    `role` defaults to the plain officer role. The CLI entry point and the
    GitHub workflow that bootstrap the first account on an empty database
    override it to `admin` so that the operator who stood the service up
    can reach the admin panel without a second provisioning step. From the
    admin panel itself, a new user defaults to `officer` and is only made
    admin by an explicit action.
    """
    username = _valid_username(username)
    name = _valid_name(name)
    password = _valid_password(password)
    role = _valid_role(role)
    salt = secrets.token_hex(16)
    with database() as db:
        existed = db.execute(
            "SELECT role FROM officers WHERE username=?", (username,)
        ).fetchone()
        # On an UPDATE path keep the stored role: this entry point is used
        # by the Create Officer Account workflow which still passes the
        # default, and we must not silently demote the admin that account
        # already is. Explicit role changes go through `set_role` instead.
        role = existed["role"] if existed else role
        db.execute(
            "INSERT INTO officers(username,name,salt,password,enabled,role) VALUES(?,?,?,?,1,?)"
            " ON CONFLICT(username) DO UPDATE SET name=excluded.name,salt=excluded.salt,"
            "password=excluded.password,enabled=1",
            (username, name, salt, password_hash(password, salt), role),
        )
        db.execute("DELETE FROM officer_sessions WHERE username=?", (username,))


def identity(token):
    if not token:
        return None
    with database() as db:
        row = db.execute(
            "SELECT o.username,o.name,o.role,r.label,r.privileges "
            "FROM officer_sessions s "
            "JOIN officers o ON o.username=s.username "
            "LEFT JOIN officer_roles r ON r.name=o.role "
            "WHERE s.token=? AND s.expires>? AND o.enabled=1",
            (digest(token), time.time()),
        ).fetchone()
    if not row:
        return None
    role = row["role"] or OFFICER
    label = row["label"] or _role_label(role)
    try:
        privs = json.loads(row["privileges"]) if row["privileges"] else []
    except (TypeError, ValueError):
        privs = []
    return {
        "username": row["username"],
        "name": row["name"],
        "role": role,
        "title": label,
        "privileges": privs,
    }


def has_privilege(user: dict | None, privilege: str) -> bool:
    """True when the signed-in officer's role grants `privilege`."""
    return bool(user and privilege in (user.get("privileges") or []))


def list_officers():
    """Every officer, newest-friendly order (admins first, then alphabetical)."""
    with database() as db:
        rows = db.execute(
            "SELECT username,name,role,enabled FROM officers "
            "ORDER BY role='admin' DESC, username"
        ).fetchall()
    return [
        {
            "username": r["username"],
            "name": r["name"],
            "role": r["role"] or OFFICER,
            "title": _role_label(r["role"] or OFFICER),
            "enabled": bool(r["enabled"]),
        }
        for r in rows
    ]


def _count_user_managers(db) -> int:
    """How many enabled officers currently hold `manage_users`.

    Counts by PRIVILEGE, not by literal role name — a custom role that
    grants `manage_users` is just as much "an admin" for the purpose of
    the last-admin rule as the builtin `admin` role is."""
    rows = db.execute(
        "SELECT r.privileges FROM officers o "
        "JOIN officer_roles r ON r.name=o.role "
        "WHERE o.enabled=1"
    ).fetchall()
    count = 0
    for r in rows:
        try:
            privs = json.loads(r["privileges"]) if r["privileges"] else []
        except (TypeError, ValueError):
            privs = []
        if PRIV_MANAGE_USERS in privs:
            count += 1
    return count


# Backwards-compatible aliases. The `admin` concept is now spelled
# "an officer with `manage_users`"; nothing outside this module should
# call these.
def _count_admins(db) -> int:
    return _count_user_managers(db)


def count_admins() -> int:
    with database() as db:
        return _count_user_managers(db)


def exists(username) -> bool:
    username = _valid_username(username)
    with database() as db:
        row = db.execute(
            "SELECT 1 FROM officers WHERE username=? LIMIT 1", (username,)
        ).fetchone()
    return row is not None


def create(username, name, password, role=OFFICER):
    """Create a new officer. Raises if the username is already taken."""
    username = _valid_username(username)
    name = _valid_name(name)
    password = _valid_password(password)
    role = _valid_role(role)
    salt = secrets.token_hex(16)
    with database() as db:
        clash = db.execute(
            "SELECT 1 FROM officers WHERE username=? LIMIT 1", (username,)
        ).fetchone()
        if clash:
            raise ValueError(f'Username "{username}" is already taken.')
        db.execute(
            "INSERT INTO officers(username,name,salt,password,enabled,role) VALUES(?,?,?,?,1,?)",
            (username, name, salt, password_hash(password, salt), role),
        )


def set_password(username, new_password):
    """Change an officer's password. Revokes every existing session."""
    username = _valid_username(username)
    new_password = _valid_password(new_password)
    salt = secrets.token_hex(16)
    with database() as db:
        found = db.execute(
            "UPDATE officers SET salt=?,password=? WHERE username=?",
            (salt, password_hash(new_password, salt), username),
        )
        if found.rowcount == 0:
            raise LookupError(f'No officer "{username}".')
        db.execute("DELETE FROM officer_sessions WHERE username=?", (username,))


def verify_password(username, password) -> bool:
    """Confirm the given password matches the stored hash.

    Used by the change-own-password endpoint so an officer must enter their
    current password before setting a new one — a stolen cookie alone is not
    enough to take the account over."""
    username = _valid_username(username)
    with database() as db:
        row = db.execute(
            "SELECT salt,password FROM officers WHERE username=? AND enabled=1",
            (username,),
        ).fetchone()
    if not row:
        return False
    actual = password_hash(password or "", row["salt"])
    return secrets.compare_digest(actual, row["password"])


def set_name(username, name):
    username = _valid_username(username)
    name = _valid_name(name)
    with database() as db:
        found = db.execute(
            "UPDATE officers SET name=? WHERE username=?", (name, username)
        )
        if found.rowcount == 0:
            raise LookupError(f'No officer "{username}".')


def _role_grants(db, role_name: str, privilege: str) -> bool:
    row = db.execute(
        "SELECT privileges FROM officer_roles WHERE name=?", (role_name,)
    ).fetchone()
    if not row:
        return False
    try:
        return privilege in json.loads(row["privileges"] or "[]")
    except (TypeError, ValueError):
        return False


def set_role(username, role):
    """Promote or demote an officer. Refuses the change when it would
    leave zero officers holding `manage_users` — the admin panel would
    be unreachable the next request."""
    username = _valid_username(username)
    role = _valid_role(role)
    with database() as db:
        row = db.execute(
            "SELECT role FROM officers WHERE username=?", (username,)
        ).fetchone()
        if not row:
            raise LookupError(f'No officer "{username}".')
        old_had = _role_grants(db, row["role"], PRIV_MANAGE_USERS)
        new_has = _role_grants(db, role, PRIV_MANAGE_USERS)
        if old_had and not new_has and _count_user_managers(db) <= 1:
            raise ValueError(
                "Cannot demote the last administrator — promote another "
                "officer first."
            )
        db.execute("UPDATE officers SET role=? WHERE username=?", (role, username))


def rename(username, new_username):
    """Change a login name in place. Cascades to the officer's live sessions
    and to the audit rows they already wrote, so an officer who changed
    their username keeps their review history under the new one."""
    username = _valid_username(username)
    new_username = _valid_username(new_username)
    if username == new_username:
        return
    with database() as db:
        row = db.execute(
            "SELECT 1 FROM officers WHERE username=? LIMIT 1", (username,)
        ).fetchone()
        if not row:
            raise LookupError(f'No officer "{username}".')
        clash = db.execute(
            "SELECT 1 FROM officers WHERE username=? LIMIT 1", (new_username,)
        ).fetchone()
        if clash:
            raise ValueError(f'Username "{new_username}" is already taken.')
        db.execute(
            "UPDATE officers SET username=? WHERE username=?",
            (new_username, username),
        )
        for table in ("officer_sessions", "officer_notes", "officer_audit"):
            # Mapped via raw name match; author / username columns are
            # text equal to the officer's username.
            column = "author" if table in ("officer_notes", "officer_audit") else "username"
            db.execute(
                f"UPDATE {table} SET {column}=? WHERE {column}=?",
                (new_username, username),
            )


def delete_officer(username):
    """Remove an officer and every session they still hold. Refuses the
    delete when it would leave zero officers holding `manage_users`."""
    username = _valid_username(username)
    with database() as db:
        row = db.execute(
            "SELECT role FROM officers WHERE username=?", (username,)
        ).fetchone()
        if not row:
            raise LookupError(f'No officer "{username}".')
        if (_role_grants(db, row["role"], PRIV_MANAGE_USERS)
                and _count_user_managers(db) <= 1):
            raise ValueError(
                "Cannot delete the last administrator — promote another "
                "officer first."
            )
        db.execute("DELETE FROM officers WHERE username=?", (username,))
        db.execute("DELETE FROM officer_sessions WHERE username=?", (username,))


# -------------------------------------------------------------------- #
# Role management. The two builtin rows (admin, officer) are shipped
# and cannot be renamed or deleted; custom rows are freely editable
# except where their deletion would orphan an existing officer.
# -------------------------------------------------------------------- #


def list_roles():
    """Every role, builtins first, then alphabetical. Each row carries the
    full privilege list and a count of officers using it."""
    with database() as db:
        rows = db.execute("""
            SELECT r.name, r.label, r.privileges, r.builtin,
                   (SELECT COUNT(*) FROM officers o
                    WHERE o.role = r.name) AS member_count
            FROM officer_roles r
            ORDER BY r.builtin DESC, r.name
        """).fetchall()
    out = []
    for r in rows:
        try:
            privs = json.loads(r["privileges"] or "[]")
        except (TypeError, ValueError):
            privs = []
        out.append({
            "name": r["name"],
            "label": r["label"],
            "privileges": sorted(privs),
            "builtin": bool(r["builtin"]),
            "member_count": r["member_count"],
        })
    return out


def get_role(name: str):
    name = _valid_role_name(name)
    with database() as db:
        row = db.execute(
            "SELECT name,label,privileges,builtin FROM officer_roles "
            "WHERE name=?",
            (name,),
        ).fetchone()
    if not row:
        return None
    try:
        privs = json.loads(row["privileges"] or "[]")
    except (TypeError, ValueError):
        privs = []
    return {
        "name": row["name"],
        "label": row["label"],
        "privileges": sorted(privs),
        "builtin": bool(row["builtin"]),
    }


def create_role(name: str, label: str, privileges):
    name = _valid_role_name(name)
    label = _valid_role_label(label)
    privileges = _valid_privileges(privileges)
    with database() as db:
        clash = db.execute(
            "SELECT 1 FROM officer_roles WHERE name=? LIMIT 1", (name,)
        ).fetchone()
        if clash:
            raise ValueError(f'A role named "{name}" already exists.')
        db.execute(
            "INSERT INTO officer_roles(name,label,privileges,builtin) "
            "VALUES(?,?,?,0)",
            (name, label, json.dumps(privileges)),
        )
    return get_role(name)


def update_role(name: str, *, label=None, privileges=None):
    """Change a role's display label or privilege set. The builtin
    `admin` and `officer` rows cannot be edited — they are the floor
    the privilege system is wired against; changing them silently would
    be a surprise. The admin panel disables these fields when the row
    is builtin, and this re-asserts the rule server-side."""
    name = _valid_role_name(name)
    with database() as db:
        row = db.execute(
            "SELECT builtin,privileges FROM officer_roles WHERE name=?",
            (name,),
        ).fetchone()
        if not row:
            raise LookupError(f'No role "{name}".')
        if row["builtin"]:
            raise ValueError(
                f'The "{name}" role ships with the service and cannot be '
                f"edited. Create a custom role instead."
            )
        try:
            current_privs = json.loads(row["privileges"] or "[]")
        except (TypeError, ValueError):
            current_privs = []
        if label is not None:
            label = _valid_role_label(label)
            db.execute(
                "UPDATE officer_roles SET label=? WHERE name=?", (label, name)
            )
        if privileges is not None:
            new_privs = _valid_privileges(privileges)
            # When the privilege change takes `manage_users` away from a role
            # whose current members include every remaining administrator,
            # refuse — same reasoning as the last-admin rule on officers.
            lost_manage = (PRIV_MANAGE_USERS in current_privs
                           and PRIV_MANAGE_USERS not in new_privs)
            if lost_manage:
                members = db.execute(
                    "SELECT COUNT(*) AS n FROM officers "
                    "WHERE role=? AND enabled=1",
                    (name,),
                ).fetchone()["n"]
                if members and _count_user_managers(db) <= members:
                    raise ValueError(
                        f'Removing "manage_users" from "{name}" would '
                        f"leave no officer able to reach the admin panel. "
                        f"Reassign the officers holding this role first."
                    )
            db.execute(
                "UPDATE officer_roles SET privileges=? WHERE name=?",
                (json.dumps(new_privs), name),
            )
    return get_role(name)


def delete_role(name: str):
    name = _valid_role_name(name)
    with database() as db:
        row = db.execute(
            "SELECT builtin FROM officer_roles WHERE name=?", (name,)
        ).fetchone()
        if not row:
            raise LookupError(f'No role "{name}".')
        if row["builtin"]:
            raise ValueError(
                f'The "{name}" role ships with the service and cannot be '
                f"deleted."
            )
        in_use = db.execute(
            "SELECT COUNT(*) AS n FROM officers WHERE role=?", (name,)
        ).fetchone()["n"]
        if in_use:
            raise ValueError(
                f'The "{name}" role is assigned to {in_use} officer(s). '
                f"Reassign them before deleting the role."
            )
        db.execute("DELETE FROM officer_roles WHERE name=?", (name,))


# -------------------------------------------------------------------- #
# Feature switches. Admin → "Features" tab → on/off toggles. The
# citizen and officer front-ends fetch /api/features to decide what
# to show; the catalogue is in Python so a toggle in the admin UI
# that nothing enforces is impossible.
# -------------------------------------------------------------------- #


def list_feature_flags():
    """Every known flag, with its live enabled state and the metadata
    the catalogue carries about it. Alphabetical by name — the admin
    UI groups further by `audience`."""
    with database() as db:
        rows = {
            r["name"]: bool(r["enabled"])
            for r in db.execute(
                "SELECT name,enabled FROM officer_feature_flags"
            ).fetchall()
        }
    out = []
    for name, meta in sorted(FEATURE_FLAGS.items()):
        out.append({
            "name": name,
            "enabled": rows.get(name, meta["default"]),
            "label": meta["label"],
            "description": meta["description"],
            "audience": meta["audience"],
            "default": meta["default"],
        })
    return out


def feature_enabled(name: str) -> bool:
    """Fast check for route-level enforcement (e.g. the /operator route
    checks this before rendering). Returns the catalogue default when
    the row is missing (first-start race, deleted catalogue entry) so
    the service never becomes less functional under corrupted state."""
    meta = FEATURE_FLAGS.get(name)
    if meta is None:
        return False
    with database() as db:
        row = db.execute(
            "SELECT enabled FROM officer_feature_flags WHERE name=?", (name,)
        ).fetchone()
    return bool(row["enabled"]) if row else bool(meta["default"])


def set_feature_flag(name: str, enabled: bool):
    """Flip a flag on or off. Unknown flag names are refused — the
    catalogue is the floor."""
    if name not in FEATURE_FLAGS:
        raise LookupError(f'No feature flag "{name}".')
    with database() as db:
        db.execute(
            "INSERT INTO officer_feature_flags(name,enabled) VALUES(?,?) "
            "ON CONFLICT(name) DO UPDATE SET enabled=excluded.enabled",
            (name, 1 if enabled else 0),
        )


def feature_flags_for(audience: str) -> dict[str, bool]:
    """Just the on/off map for the front-end that asks. The citizen
    page needs only `citizen_*`; the officer page needs `officer_*`
    AND `citizen_*` (so it can render the citizen view faithfully in a
    preview); the operator page needs `operator_screen`."""
    flags = {}
    for row in list_feature_flags():
        if audience == "all" or row["audience"] == audience:
            flags[row["name"]] = row["enabled"]
    return flags


def login(username, password, host):
    now = time.time()
    with database() as db:
        db.execute("DELETE FROM officer_sessions WHERE expires<=?", (now,))
        db.execute("DELETE FROM login_attempts WHERE since<?", (now - 900,))
        attempt = db.execute("SELECT attempts FROM login_attempts WHERE host=?", (host,)).fetchone()
        if attempt and attempt["attempts"] >= 10:
            return None, "limited"
        row = db.execute(
            "SELECT * FROM officers WHERE username=? AND enabled=1", (username.casefold(),)
        ).fetchone()
        actual = password_hash(password, row["salt"] if row else "00" * 16)
        if not row or not secrets.compare_digest(actual, row["password"]):
            db.execute(
                "INSERT INTO login_attempts VALUES(?,1,?) ON CONFLICT(host) DO UPDATE SET attempts=attempts+1",
                (host, now),
            )
            return None, "invalid"
        db.execute("DELETE FROM login_attempts WHERE host=?", (host,))
        token = secrets.token_urlsafe(32)
        db.execute(
            "INSERT INTO officer_sessions VALUES(?,?,?)",
            (digest(token), row["username"], now + TTL),
        )
    return token, None


def owned_sessions(request):
    """The petitions THIS browser created. Never a wildcard.

    Kept apart from `citizen_scope` because listing and deleting ask a
    different question from opening a petition whose id you already hold.

    Before any officer account exists `citizen_scope` deliberately answers
    "do not restrict", so that a single-machine deployment keeps working.
    Applied to the catalogue, that meant an anonymous caller could list every
    petition on the service, open each one using the session id the listing
    handed over, and then delete the lot — `remove_sessions` takes the
    checkpoints, the generated documents and the attachments, and there is no
    undo. Measured against the live service on 5 October 2026: 31 petitions,
    petitioner names included.

    So these two uses never widen. A browser lists and deletes its own work,
    whether or not the office has been set up yet.
    """
    with database() as db:
        owner = digest(request.cookies.get("petition_citizen", ""))
        return {
            r["session_id"]
            for r in db.execute("SELECT session_id FROM citizen_sessions WHERE owner=?", (owner,))
        }


def can_access(request, session_id: str) -> bool:
    """Whether this browser may reach the petition behind `session_id`.

    TWO MODES, selected by whether any officer has been provisioned:

      office deployment — any officer row exists:
          only sessions this browser owns.

      single-machine deployment — no officer row exists:
          sessions this browser owns, OR sessions with no owner row at all
          (grandfathered). The oldest petitions on the live service predate
          session recording (23 September 2026) and have no owner recorded;
          closing them would lock their owners out of their own bookmarks.

    The earlier rule said "no officer provisioned → do not restrict",
    full stop. An anonymous caller used that to list every saved petition,
    open each one by id and delete the lot (measured 5 October 2026 on the
    live service, 31 petitions with petitioner names). The listing path
    moved to `owned_sessions` then; this closes the opening path too, and
    now the grandfather carve-out is tight to pre-office deployments so
    that an office-side session created directly by an officer (no POST
    /sessions, so no citizen_sessions row) is NOT taken for a legacy
    bookmark.
    """
    own = owned_sessions(request)
    if session_id in own:
        return True
    with database() as db:
        has_officer = db.execute("SELECT 1 FROM officers LIMIT 1").fetchone()
        if has_officer:
            return False
        row = db.execute(
            "SELECT 1 FROM citizen_sessions WHERE session_id=? LIMIT 1",
            (session_id,),
        ).fetchone()
    return row is None


def citizen_scope(request):
    """The browser's own session ids. Never a wildcard, never grandfathered.

    Kept for callers that still ask the question as a set. Grandfathered
    sessions are not enumerable from an officer-store standpoint — they are
    the ones with no row at all — so the per-session answer is in
    `can_access`, which is what new code should use.
    """
    return owned_sessions(request)


def require_citizen_session(request: Request):
    sid = request.path_params.get("session_id")
    if sid and not can_access(request, sid):
        raise HTTPException(
            403,
            "This petition belongs to another browser. Use the officer portal for office review.",
        )


def forget_petition(session_id, settings=None):
    with database(settings) as db:
        for table in (
            "officer_reviews", "officer_notes", "officer_audit",
            "officer_acknowledgements", "citizen_sessions",
        ):
            db.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))


def remember_citizen(request, response, session_id):
    owner = request.cookies.get("petition_citizen") or secrets.token_urlsafe(32)
    with database() as db:
        db.execute(
            "INSERT OR IGNORE INTO citizen_sessions VALUES(?,?)", (session_id, digest(owner))
        )
    response.set_cookie(
        "petition_citizen",
        owner,
        max_age=365 * 86400,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="strict",
        path="/",
    )
