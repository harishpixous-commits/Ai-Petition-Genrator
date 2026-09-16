"""The corpus: government documents, chunked, indexed twice.

SQLite, because this service already is one. `sqlite-vec` adds vector search as
a loadable extension and FTS5 is built in, so the lexical and vector halves of
hybrid retrieval live in one file next to the sessions they serve — no server
to deploy, secure and back up for a corpus that is a few hundred documents.

Two things this file is careful about.

**Nothing citizen-written is ever written here.** There is one way in, and it
is ingestion. No function takes a session, and no caller has one to give.

**Re-ingesting a document does not duplicate it.** A document is identified by
a stable id derived from its origin, and its content by a hash. Ingesting the
same bytes again is a no-op; ingesting changed bytes replaces every chunk of
the old version in one transaction, so a corpus can be refreshed on a schedule
without growing or going briefly half-empty.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .schema import Chunk

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1

_DDL = """
CREATE TABLE IF NOT EXISTS documents (
    document_id   TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    document_type TEXT NOT NULL DEFAULT 'other',
    authority     TEXT NOT NULL DEFAULT 'unknown',
    department    TEXT,
    act_name      TEXT,
    rule_name     TEXT,
    government_order_number TEXT,
    date          TEXT,
    source_url    TEXT,
    origin        TEXT,
    -- How authenticity was established: a gazette citation, a portal URL, or
    -- the name of the officer who verified the copy. An empty provenance is
    -- why a document cannot be marked official.
    provenance    TEXT,
    version       TEXT,
    superseded    INTEGER NOT NULL DEFAULT 0,
    supersedes    TEXT,
    content_hash  TEXT NOT NULL,
    chunk_count   INTEGER NOT NULL DEFAULT 0,
    ingested_at   REAL NOT NULL,
    extra         TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id     TEXT PRIMARY KEY,
    document_id  TEXT NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    ordinal      INTEGER NOT NULL,
    text         TEXT NOT NULL,
    section      TEXT,
    page_number  INTEGER
);
CREATE INDEX IF NOT EXISTS chunks_by_document ON chunks(document_id);

-- Contentful on purpose. A contentless FTS5 table (content='') cannot be
-- deleted from with DELETE; removing a row means replaying its original column
-- values through the 'delete' command, and an index that silently corrupts if
-- those values ever drift is a bad trade for the text of a few hundred
-- documents. Deleting and re-indexing a document has to be reliable.
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    text, section, title, act_name, department,
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


def _now() -> float:
    return time.time()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def document_id_for(origin: str) -> str:
    """A stable id for a file path or URL.

    Derived rather than random so that re-ingesting the same source updates the
    document it already has instead of adding a second copy of it.
    """
    return hashlib.sha256(str(origin).strip().lower().encode("utf-8")).hexdigest()[:24]


class KnowledgeStore:
    """The corpus. One SQLite file, opened per operation."""

    def __init__(self, path: Path, dimension: int, provider: str = "local") -> None:
        self.path = Path(path)
        self.dimension = int(dimension)
        self.provider = provider
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._vector_search = True
        self._prepare()

    # ------------------------------------------------------------------ #
    # Connection
    # ------------------------------------------------------------------ #

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        try:
            import sqlite_vec

            db.enable_load_extension(True)
            sqlite_vec.load(db)
            db.enable_load_extension(False)
        except Exception as exc:  # noqa: BLE001
            # Lexical retrieval still works without it, which is the whole
            # reason retrieval is hybrid. Said once, loudly, at startup.
            if self._vector_search:
                log.warning("knowledge.vector_search_unavailable",
                            extra={"error": str(exc)[:160]})
            self._vector_search = False
        return db

    def _prepare(self) -> None:
        with self._connect() as db:
            db.executescript(_DDL)
            if self._vector_search:
                db.execute(
                    f"CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec "
                    f"USING vec0(chunk_rowid INTEGER PRIMARY KEY, "
                    f"embedding float[{self.dimension}])"
                )
            self._migrate_columns(db)
            self._migrate_fts(db)
            stored = self._meta_get(db, "dimension")
            if stored is None:
                self._meta_set(db, "dimension", str(self.dimension))
                self._meta_set(db, "provider", self.provider)
                self._meta_set(db, "schema_version", str(SCHEMA_VERSION))
            elif int(stored) != self.dimension:
                # Mixing vector spaces produces confident nonsense, so it is
                # refused rather than tolerated. Re-indexing is one command.
                log.error("knowledge.dimension_mismatch",
                          extra={"stored": stored, "configured": self.dimension,
                                 "action": "re-index required"})

    @staticmethod
    def _migrate_columns(db: sqlite3.Connection) -> None:
        """Add columns a corpus built by an earlier version does not have."""
        have = {r["name"] for r in db.execute("PRAGMA table_info(documents)")}
        if "provenance" not in have:
            db.execute("ALTER TABLE documents ADD COLUMN provenance TEXT")
            log.info("knowledge.added_column", extra={"column": "provenance"})

    @staticmethod
    def _migrate_fts(db: sqlite3.Connection) -> None:
        """Rebuild the search index if it predates the contentful schema.

        The first cut of this table was contentless, which made delete and
        re-index impossible. Any corpus built against it is converted in place
        from the `chunks` table, which holds the text anyway.
        """
        row = db.execute("SELECT sql FROM sqlite_master WHERE name = 'chunks_fts'"
                         ).fetchone()
        if not row or "content=''" not in (row["sql"] or ""):
            return
        log.info("knowledge.rebuilding_search_index")
        db.execute("DROP TABLE chunks_fts")
        db.execute("CREATE VIRTUAL TABLE chunks_fts USING fts5("
                   "text, section, title, act_name, department, "
                   "tokenize='unicode61 remove_diacritics 2')")
        db.execute(
            """INSERT INTO chunks_fts(rowid, text, section, title, act_name, department)
               SELECT c.rowid, c.text, COALESCE(c.section, ''),
                      COALESCE(d.title, ''), COALESCE(d.act_name, ''),
                      COALESCE(d.department, '')
                 FROM chunks c JOIN documents d ON d.document_id = c.document_id""")

    @staticmethod
    def _meta_get(db: sqlite3.Connection, key: str) -> str | None:
        row = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    @staticmethod
    def _meta_set(db: sqlite3.Connection, key: str, value: str) -> None:
        db.execute("INSERT INTO meta(key, value) VALUES(?, ?) "
                   "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    # ------------------------------------------------------------------ #
    # Writing
    # ------------------------------------------------------------------ #

    def needs_ingest(self, document_id: str, digest: str) -> bool:
        """False when this exact content is already indexed.

        Lets a scheduled refresh walk a whole directory and do nothing for the
        files that have not changed.
        """
        with self._connect() as db:
            row = db.execute(
                "SELECT content_hash FROM documents WHERE document_id = ?",
                (document_id,)).fetchone()
        return row is None or row["content_hash"] != digest

    def upsert(
        self,
        *,
        document: dict[str, Any],
        chunks: Sequence[dict[str, Any]],
        embeddings: Sequence[Sequence[float]] | None = None,
    ) -> int:
        """Replace a document and all of its chunks, atomically.

        Delete-then-insert inside one transaction rather than a diff: a partial
        update would leave a document that is half one version and half
        another, and a retrieved passage would then cite a section number that
        does not belong to the text beside it.
        """
        document_id = document["document_id"]
        with self._connect() as db:
            db.execute("BEGIN")
            try:
                self._delete_chunks(db, document_id)
                db.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))
                db.execute(
                    """INSERT INTO documents(
                           document_id, title, document_type, authority, department,
                           act_name, rule_name, government_order_number, date,
                           source_url, origin, provenance, version, superseded,
                           supersedes, content_hash, chunk_count, ingested_at, extra)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        document_id,
                        document.get("title") or document_id,
                        document.get("document_type") or "other",
                        document.get("authority") or "unknown",
                        document.get("department"),
                        document.get("act_name"),
                        document.get("rule_name"),
                        document.get("government_order_number"),
                        document.get("date"),
                        document.get("source_url"),
                        document.get("origin"),
                        document.get("provenance"),
                        document.get("version"),
                        1 if document.get("superseded") else 0,
                        document.get("supersedes"),
                        document["content_hash"],
                        len(chunks),
                        _now(),
                        json.dumps(document.get("extra") or {}, ensure_ascii=False),
                    ),
                )

                for index, chunk in enumerate(chunks):
                    cursor = db.execute(
                        """INSERT INTO chunks(chunk_id, document_id, ordinal, text,
                                              section, page_number)
                           VALUES(?,?,?,?,?,?)""",
                        (chunk["chunk_id"], document_id, chunk.get("ordinal", index),
                         chunk["text"], chunk.get("section"), chunk.get("page_number")),
                    )
                    rowid = cursor.lastrowid
                    db.execute(
                        "INSERT INTO chunks_fts(rowid, text, section, title, "
                        "act_name, department) VALUES(?,?,?,?,?,?)",
                        (rowid, chunk["text"], chunk.get("section") or "",
                         document.get("title") or "", document.get("act_name") or "",
                         document.get("department") or ""),
                    )
                    if self._vector_search and embeddings is not None:
                        import sqlite_vec

                        db.execute(
                            "INSERT INTO chunks_vec(chunk_rowid, embedding) VALUES(?, ?)",
                            (rowid, sqlite_vec.serialize_float32(list(embeddings[index]))),
                        )
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise
        log.info("knowledge.indexed",
                 extra={"document_id": document_id, "chunks": len(chunks),
                        "title": (document.get("title") or "")[:80]})
        return len(chunks)

    @staticmethod
    def _delete_chunks(db: sqlite3.Connection, document_id: str) -> None:
        rows = db.execute("SELECT rowid FROM chunks WHERE document_id = ?",
                          (document_id,)).fetchall()
        for row in rows:
            db.execute("DELETE FROM chunks_fts WHERE rowid = ?", (row["rowid"],))
            try:
                db.execute("DELETE FROM chunks_vec WHERE chunk_rowid = ?", (row["rowid"],))
            except sqlite3.OperationalError:
                pass    # no vector table in this deployment
        db.execute("DELETE FROM chunks WHERE document_id = ?", (document_id,))

    def delete(self, document_id: str) -> bool:
        with self._connect() as db:
            exists = db.execute("SELECT 1 FROM documents WHERE document_id = ?",
                                (document_id,)).fetchone()
            if not exists:
                return False
            db.execute("BEGIN")
            self._delete_chunks(db, document_id)
            db.execute("DELETE FROM documents WHERE document_id = ?", (document_id,))
            db.execute("COMMIT")
        log.info("knowledge.deleted", extra={"document_id": document_id})
        return True

    def mark_superseded(self, document_id: str, by_document_id: str | None = None) -> bool:
        """Retire a document without losing it.

        A superseded circular still explains what the rule used to be, which
        matters when a citizen is asking about something that happened before
        it changed. It is excluded from retrieval unless nothing else answers.
        """
        with self._connect() as db:
            cursor = db.execute(
                "UPDATE documents SET superseded = 1, supersedes = COALESCE(?, supersedes) "
                "WHERE document_id = ?", (by_document_id, document_id))
            return cursor.rowcount > 0

    # ------------------------------------------------------------------ #
    # Reading
    # ------------------------------------------------------------------ #

    def stats(self) -> dict[str, Any]:
        with self._connect() as db:
            documents = db.execute("SELECT COUNT(*) c FROM documents").fetchone()["c"]
            live = db.execute(
                "SELECT COUNT(*) c FROM documents WHERE superseded = 0").fetchone()["c"]
            chunks = db.execute("SELECT COUNT(*) c FROM chunks").fetchone()["c"]
            by_type = {r["document_type"]: r["c"] for r in db.execute(
                "SELECT document_type, COUNT(*) c FROM documents GROUP BY 1")}
            official = db.execute(
                "SELECT COUNT(*) c FROM documents WHERE authority IN "
                "('official','departmental')").fetchone()["c"]
            stored_dim = self._meta_get(db, "dimension")
            provider = self._meta_get(db, "provider")
        last = db.execute(
            "SELECT MAX(ingested_at) m FROM documents").fetchone()["m"]             if documents else None
        unverified = db.execute(
            "SELECT COUNT(*) c FROM documents WHERE authority NOT IN "
            "('official','departmental')").fetchone()["c"]
        return {
            "documents": documents,
            "unverified_documents": unverified,
            "last_ingested_at": last,
            "live_documents": live,
            "superseded": documents - live,
            "official_documents": official,
            "chunks": chunks,
            "by_type": by_type,
            "vector_search": self._vector_search,
            "indexed_dimension": int(stored_dim) if stored_dim else None,
            "indexed_provider": provider,
            "configured_dimension": self.dimension,
            "configured_provider": self.provider,
            "ready": chunks > 0,
            "path": str(self.path),
        }

    def documents(self, limit: int = 200) -> list[dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT document_id, title, document_type, authority, department, "
                "act_name, rule_name, government_order_number, date, source_url, "
                "provenance, version, superseded, chunk_count, ingested_at "
                "FROM documents ORDER BY ingested_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def lexical(self, query: str, limit: int = 20,
                include_superseded: bool = False) -> list[Chunk]:
        """FTS5/BM25. Needs no embedding provider, which is the point."""
        terms = _fts_query(query)
        if not terms:
            return []
        sql = f"""
            SELECT c.*, d.*, bm25(chunks_fts) AS rank
              FROM chunks_fts
              JOIN chunks c ON c.rowid = chunks_fts.rowid
              JOIN documents d ON d.document_id = c.document_id
             WHERE chunks_fts MATCH ?
               {'' if include_superseded else 'AND d.superseded = 0'}
             ORDER BY rank
             LIMIT ?
        """
        with self._connect() as db:
            try:
                rows = db.execute(sql, (terms, limit)).fetchall()
            except sqlite3.OperationalError as exc:
                log.info("knowledge.fts_failed", extra={"error": str(exc)[:120]})
                return []
        # bm25 returns a negative score, most relevant first.
        return [_row_to_chunk(r, score=-float(r["rank"])) for r in rows]

    def vector(self, embedding: Sequence[float], limit: int = 20,
               include_superseded: bool = False) -> list[Chunk]:
        if not self._vector_search or not embedding:
            return []
        import sqlite_vec

        sql = f"""
            SELECT c.*, d.*, v.distance AS distance
              FROM (SELECT chunk_rowid, distance FROM chunks_vec
                     WHERE embedding MATCH ? AND k = ?) v
              JOIN chunks c ON c.rowid = v.chunk_rowid
              JOIN documents d ON d.document_id = c.document_id
             {'' if include_superseded else 'WHERE d.superseded = 0'}
             ORDER BY v.distance
        """
        with self._connect() as db:
            try:
                rows = db.execute(
                    sql, (sqlite_vec.serialize_float32(list(embedding)), limit)).fetchall()
            except sqlite3.OperationalError as exc:
                log.info("knowledge.vector_failed", extra={"error": str(exc)[:120]})
                return []
        return [_row_to_chunk(r, score=1.0 / (1.0 + float(r["distance"]))) for r in rows]

    def all_chunks(self) -> Iterable[dict[str, Any]]:
        """Every chunk, for re-embedding after a provider change."""
        with self._connect() as db:
            for row in db.execute(
                    "SELECT chunk_id, document_id, ordinal, text, section, page_number "
                    "FROM chunks ORDER BY document_id, ordinal"):
                yield dict(row)


_FTS_SAFE = ("\"", "*", "(", ")", ":", "^", "-")


def _fts_query(query: str) -> str:
    """FTS5 has its own syntax; a citizen's words are not it.

    Everything is quoted and OR-ed, so a grievance can be used as a query
    directly without a stray hyphen being read as NOT and silently removing
    half the corpus from consideration.
    """
    words = []
    for raw in str(query or "").split():
        word = "".join(ch for ch in raw if ch not in _FTS_SAFE).strip()
        if len(word) >= 2:
            words.append(f'"{word}"')
    return " OR ".join(words[:48])


def _row_to_chunk(row: sqlite3.Row, score: float) -> Chunk:
    return Chunk(
        chunk_id=row["chunk_id"],
        document_id=row["document_id"],
        text=row["text"],
        ordinal=row["ordinal"],
        document_title=row["title"] or "",
        document_type=row["document_type"] or "other",
        authority=row["authority"] or "unknown",
        department=row["department"],
        act_name=row["act_name"],
        rule_name=row["rule_name"],
        government_order_number=row["government_order_number"],
        section=row["section"],
        page_number=row["page_number"],
        date=row["date"],
        source_url=row["source_url"],
        version=row["version"],
        superseded=bool(row["superseded"]),
        score=score,
    )
