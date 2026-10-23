"""Where discovered legal documents wait until a curator has looked at them.

TWO STORES, DELIBERATELY SEPARATE.

  `corpus/tamil_nadu.yaml` + `var/knowledge.sqlite`
      the active corpus. Everything here is a document a human curator has
      read and approved as authoritative. Citizens get citations from here.

  `var/quarantine.sqlite` (this file)
      the staging table. Every row is a document DISCOVERED from an official
      source and awaiting review. Nothing in here reaches the citizen
      page, the analyst, retrieval or the compose node until the curator
      approves it — which is a separate, deliberate action that writes the
      new entry into the corpus manifest.

THE SHAPE OF ONE ROW is dictated by the Phase 2 brief: title, Act or Rule
number, year, document type, issuing authority, official URL, source tier,
publication date, retrieval date, amendment status, checksum/hash,
verification status. One extra column — `review_reason` — because a curator
rejecting a row owes the next reviewer an explanation.

WHAT A CURATOR MAY DO. One of:
  approve     the row survives, marked `approved`. A separate operator step
              writes it into `corpus/tamil_nadu.yaml`. Approval HERE is not
              auto-ingest, by design.
  reject      the row survives for audit, status `rejected`.
  duplicate   the row names an existing corpus entry (or an existing
              quarantine row). Marked `duplicate` with the existing id.
  outdated    the row names something that is no longer current law
              (repealed, substituted, merged into another instrument).
              Status `outdated`.

The states are explicit so the UI can show them, the audit log carries
them, and a Phase-3 periodic re-check can re-visit `discovered` and
`pdf_fetched` rows without disturbing the approved set.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import Settings, get_settings

#: Allowed verification states. Enforced in `record()` and `review()`.
STATES = (
    "discovered",     # URL and metadata captured; PDF not fetched yet.
    "pdf_fetched",    # PDF fetched into var/quarantine/pdfs/, hash recorded.
    "unreachable",    # the official URL timed out or returned 4xx/5xx.
    "approved",       # curator approved; eligible for a later corpus write.
    "rejected",       # curator rejected; reason recorded.
    "duplicate",      # curator marked as duplicate of an existing row.
    "outdated",       # curator marked as superseded or repealed.
)

REVIEW_ACTIONS = frozenset({"approve", "reject", "duplicate", "outdated"})
TERMINAL_STATES = frozenset({"approved", "rejected", "duplicate", "outdated"})

#: Documents we accept at all. Anything else is dropped at ingest time.
DOCUMENT_TYPES = frozenset({
    "act", "ordinance", "rule", "regulation", "notification",
    "circular", "government_order", "guideline", "procedure",
    "amendment",
})

#: Where PDFs live on disk when fetched. Keyed by sha256 so a duplicate
#: fetch is free.
QUARANTINE_PDF_SUBDIR = "quarantine/pdfs"


@dataclass
class Discovery:
    """One row before it goes to the database.

    `title` and `official_url` are the only required fields; everything
    else may be None at discovery time. The India Code parser fills in
    `act_number`, `year`, `publication_date` and `pdf_url` when the item
    page carries them; others are left blank for the curator.
    """

    source_id: str
    official_url: str
    title: str
    document_type: str
    source_tier: str
    act_number: str | None = None
    year: int | None = None
    issuing_authority: str | None = None
    publication_date: str | None = None
    pdf_url: str | None = None
    amendment_status: str | None = None   # "unknown" until a curator reads it
    extra: dict[str, Any] = field(default_factory=dict)


class QuarantineError(ValueError):
    """A caller gave the quarantine store something it refused."""


@contextmanager
def database(settings: Settings | None = None):
    settings = settings or get_settings()
    path = Path(settings.data_dir) / "quarantine.sqlite"
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE IF NOT EXISTS quarantine (
            id                  TEXT PRIMARY KEY,
            source_id           TEXT NOT NULL,
            official_url        TEXT NOT NULL,
            title               TEXT NOT NULL,
            act_number          TEXT,
            year                INTEGER,
            document_type       TEXT NOT NULL,
            issuing_authority   TEXT,
            source_tier         TEXT NOT NULL,
            publication_date    TEXT,
            retrieved_at        TEXT NOT NULL,
            amendment_status    TEXT,
            pdf_url             TEXT,
            pdf_sha256          TEXT,
            verification_status TEXT NOT NULL,
            reviewer            TEXT,
            review_reason       TEXT,
            reviewed_at         TEXT,
            duplicate_of        TEXT,
            extra               TEXT,
            UNIQUE(source_id, official_url)
        );
        CREATE INDEX IF NOT EXISTS idx_q_status ON quarantine(verification_status);
        CREATE INDEX IF NOT EXISTS idx_q_source ON quarantine(source_id);
    """)
    try:
        yield db
        db.commit()
    finally:
        db.close()


def record(discovery: Discovery, *, settings: Settings | None = None) -> str:
    """Store a discovery and return its id.

    IDEMPOTENT ON (source_id, official_url). A second discovery of the
    exact same URL from the same source does not create a new row — it
    returns the existing id with no side effect. That is what rule 10's
    "duplicate documents" test asks for: the pipeline must not accumulate
    one row per crawl pass for the same Act.
    """
    if discovery.document_type not in DOCUMENT_TYPES:
        raise QuarantineError(
            f"document_type {discovery.document_type!r} is not accepted")
    if not discovery.official_url.startswith(("http://", "https://")):
        raise QuarantineError(
            f"official_url must be http(s), got {discovery.official_url!r}")

    with database(settings) as db:
        existing = db.execute(
            "SELECT id FROM quarantine WHERE source_id=? AND official_url=?",
            (discovery.source_id, discovery.official_url),
        ).fetchone()
        if existing:
            return existing["id"]

        now = datetime.now(UTC).isoformat(timespec="seconds")
        row_id = str(uuid.uuid4())
        db.execute(
            """INSERT INTO quarantine
               (id, source_id, official_url, title, act_number, year,
                document_type, issuing_authority, source_tier,
                publication_date, retrieved_at, amendment_status,
                pdf_url, pdf_sha256, verification_status, extra)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (row_id, discovery.source_id, discovery.official_url,
             discovery.title, discovery.act_number, discovery.year,
             discovery.document_type, discovery.issuing_authority,
             discovery.source_tier, discovery.publication_date, now,
             discovery.amendment_status or "unknown",
             discovery.pdf_url, None, "discovered",
             json.dumps(discovery.extra or {}, ensure_ascii=False)),
        )
    return row_id


def set_status(row_id: str, status: str,
               *, pdf_sha256: str | None = None,
               settings: Settings | None = None) -> None:
    """Flip a row to a new intermediate state. Terminal states go through
    `review`."""
    if status not in STATES:
        raise QuarantineError(f"status {status!r} is not a known state")
    if status in TERMINAL_STATES:
        raise QuarantineError(
            f"status {status!r} is terminal; use review() instead")
    with database(settings) as db:
        updates = ["verification_status = ?"]
        params: list[Any] = [status]
        if pdf_sha256 is not None:
            updates.append("pdf_sha256 = ?")
            params.append(pdf_sha256)
        params.append(row_id)
        cur = db.execute(
            f"UPDATE quarantine SET {', '.join(updates)} WHERE id = ?",
            tuple(params),
        )
        if cur.rowcount == 0:
            raise QuarantineError(f"no quarantine row with id {row_id!r}")


def review(row_id: str, action: str, *, reviewer: str,
           reason: str = "", duplicate_of: str | None = None,
           settings: Settings | None = None) -> dict[str, Any]:
    """The curator decision. Returns the final row.

    `reject`, `duplicate` and `outdated` REQUIRE a reason — a terse one is
    fine; a blank one is refused. `approve` accepts an empty reason because
    "I read it and it is what the title says" is a legitimate approval.
    """
    if action not in REVIEW_ACTIONS:
        raise QuarantineError(f"action {action!r} is not a review action")
    if action != "approve" and not reason.strip():
        raise QuarantineError(
            f"a non-approve review ({action!r}) requires a reason")
    if action == "duplicate" and not duplicate_of:
        raise QuarantineError("marking duplicate needs duplicate_of")

    status_for_action = {
        "approve": "approved", "reject": "rejected",
        "duplicate": "duplicate", "outdated": "outdated",
    }[action]
    now = datetime.now(UTC).isoformat(timespec="seconds")

    with database(settings) as db:
        row = db.execute("SELECT * FROM quarantine WHERE id=?",
                         (row_id,)).fetchone()
        if row is None:
            raise QuarantineError(f"no quarantine row with id {row_id!r}")
        if row["verification_status"] in TERMINAL_STATES:
            raise QuarantineError(
                f"row {row_id} is already {row['verification_status']!r}")
        if duplicate_of:
            if not db.execute("SELECT 1 FROM quarantine WHERE id=?",
                              (duplicate_of,)).fetchone():
                raise QuarantineError(
                    f"duplicate_of {duplicate_of!r} is not a known row")

        db.execute(
            """UPDATE quarantine
               SET verification_status = ?, reviewer = ?, review_reason = ?,
                   reviewed_at = ?, duplicate_of = ?
               WHERE id = ?""",
            (status_for_action, reviewer, reason.strip() or None, now,
             duplicate_of, row_id),
        )
        updated = db.execute("SELECT * FROM quarantine WHERE id=?",
                             (row_id,)).fetchone()
    return dict(updated)


def pending(*, settings: Settings | None = None) -> list[dict[str, Any]]:
    """Rows a curator still has to decide. Oldest first."""
    with database(settings) as db:
        rows = db.execute(
            """SELECT * FROM quarantine
               WHERE verification_status IN ('discovered', 'pdf_fetched', 'unreachable')
               ORDER BY retrieved_at ASC""",
        ).fetchall()
    return [dict(row) for row in rows]


def all_rows(*, settings: Settings | None = None,
             status: str | None = None) -> list[dict[str, Any]]:
    """Every row, newest first. `status` filters when given."""
    with database(settings) as db:
        if status is not None:
            rows = db.execute(
                "SELECT * FROM quarantine WHERE verification_status=? "
                "ORDER BY retrieved_at DESC", (status,),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM quarantine ORDER BY retrieved_at DESC",
            ).fetchall()
    return [dict(row) for row in rows]


def get_row(row_id: str, *, settings: Settings | None = None) -> dict[str, Any] | None:
    with database(settings) as db:
        row = db.execute("SELECT * FROM quarantine WHERE id=?",
                         (row_id,)).fetchone()
    return dict(row) if row else None


def hash_bytes(blob: bytes) -> str:
    """SHA-256 of the fetched PDF bytes. Used as the on-disk filename and
    the content fingerprint stored on the row."""
    return hashlib.sha256(blob).hexdigest()


def pdf_destination(sha256: str, *,
                    settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    out = Path(settings.data_dir) / QUARANTINE_PDF_SUBDIR
    out.mkdir(parents=True, exist_ok=True)
    return out / f"{sha256}.pdf"
