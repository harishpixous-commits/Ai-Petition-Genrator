"""Small local officer identity store; petition checkpoints remain authoritative."""

from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time
from contextlib import contextmanager

from fastapi import HTTPException, Request

from ..config import get_settings

COOKIE = "petition_officer"
TTL = 8 * 60 * 60


@contextmanager
def database(settings=None):
    path = (settings or get_settings()).data_dir / "officer.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS officers(username TEXT PRIMARY KEY, name TEXT NOT NULL, salt TEXT NOT NULL, password TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1);
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
    try:
        yield db
        db.commit()
    finally:
        db.close()


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def password_hash(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def provision(username, name, password):
    if len(password) < 12:
        raise ValueError("Use a password of at least 12 characters.")
    salt = secrets.token_hex(16)
    with database() as db:
        db.execute(
            "INSERT INTO officers VALUES(?,?,?,?,1) ON CONFLICT(username) DO UPDATE SET name=excluded.name,salt=excluded.salt,password=excluded.password,enabled=1",
            (username.casefold(), name, salt, password_hash(password, salt)),
        )
        db.execute("DELETE FROM officer_sessions WHERE username=?", (username.casefold(),))


def identity(token):
    if not token:
        return None
    with database() as db:
        row = db.execute(
            "SELECT o.username,o.name FROM officer_sessions s JOIN officers o ON o.username=s.username WHERE s.token=? AND s.expires>? AND o.enabled=1",
            (digest(token), time.time()),
        ).fetchone()
    return {**dict(row), "role": "Review officer"} if row else None


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
