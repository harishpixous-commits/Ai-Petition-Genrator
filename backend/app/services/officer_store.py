"""Small local officer identity store; petition checkpoints remain authoritative."""

from __future__ import annotations

import hashlib
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


def _valid_role(raw: str) -> str:
    value = (raw or "").strip().casefold()
    if value not in (ADMIN, OFFICER):
        raise ValueError(f'Role must be "{ADMIN}" or "{OFFICER}".')
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
            "SELECT o.username,o.name,o.role FROM officer_sessions s "
            "JOIN officers o ON o.username=s.username "
            "WHERE s.token=? AND s.expires>? AND o.enabled=1",
            (digest(token), time.time()),
        ).fetchone()
    if not row:
        return None
    role = row["role"] or OFFICER
    return {
        "username": row["username"],
        "name": row["name"],
        "role": role,
        "title": _role_label(role),
    }


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


def _count_admins(db) -> int:
    return db.execute(
        "SELECT COUNT(*) AS n FROM officers WHERE role='admin' AND enabled=1"
    ).fetchone()["n"]


def count_admins() -> int:
    with database() as db:
        return _count_admins(db)


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


def set_role(username, role):
    """Promote or demote an officer. Refuses to demote the last admin so
    that an operator cannot accidentally leave the admin panel unreachable
    behind their own login."""
    username = _valid_username(username)
    role = _valid_role(role)
    with database() as db:
        row = db.execute(
            "SELECT role FROM officers WHERE username=?", (username,)
        ).fetchone()
        if not row:
            raise LookupError(f'No officer "{username}".')
        if row["role"] == ADMIN and role != ADMIN and _count_admins(db) <= 1:
            raise ValueError(
                "Cannot demote the last admin — promote another officer first."
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
    """Remove an officer and every session they still hold. Refuses to leave
    the admin panel unreachable."""
    username = _valid_username(username)
    with database() as db:
        row = db.execute(
            "SELECT role FROM officers WHERE username=?", (username,)
        ).fetchone()
        if not row:
            raise LookupError(f'No officer "{username}".')
        if row["role"] == ADMIN and _count_admins(db) <= 1:
            raise ValueError(
                "Cannot delete the last admin — promote another officer first."
            )
        db.execute("DELETE FROM officers WHERE username=?", (username,))
        db.execute("DELETE FROM officer_sessions WHERE username=?", (username,))


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
