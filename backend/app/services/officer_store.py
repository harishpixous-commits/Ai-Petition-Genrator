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
    """)
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


def citizen_scope(request):
    """Office mode stops the public catalogue revealing other browsers' session IDs."""
    with database() as db:
        if not db.execute("SELECT 1 FROM officers LIMIT 1").fetchone():
            return None  # Preserve existing single-machine deployments until provisioned.
        owner = digest(request.cookies.get("petition_citizen", ""))
        return {
            r["session_id"]
            for r in db.execute("SELECT session_id FROM citizen_sessions WHERE owner=?", (owner,))
        }


def require_citizen_session(request: Request):
    sid = request.path_params.get("session_id")
    if sid:
        allowed = citizen_scope(request)
        if allowed is not None and sid not in allowed:
            raise HTTPException(
                403,
                "This petition belongs to another browser. Use the officer portal for office review.",
            )


def forget_petition(session_id, settings=None):
    with database(settings) as db:
        for table in ("officer_reviews", "officer_notes", "officer_audit", "citizen_sessions"):
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
