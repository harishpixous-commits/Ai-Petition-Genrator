"""Whether every chunk has exactly one correct vector, and repairing it when not.

WHY THIS EXISTS — the incident it was written after, recorded exactly.

`Ingestor.reindex()` re-embedded the corpus by calling `store.upsert()` once
per document. `upsert` deletes a document's chunks and vectors and re-inserts
them, and `_embed()` returns None for a whole document if any one of its
batches fails. So when the embedding provider rate-limited part-way through, a
2,510-chunk Act lost every vector it had because one batch of 32 failed — and
`reindex()` added `len(chunks)` to its total either way. It printed

    Re-embedded 8344 chunks.

over a vector table that held ZERO rows. Three defects, each reasonable alone:
an all-or-nothing embed, a delete-before-replace write, and a counter that
counted attempts. Lexical search kept working throughout, so the service looked
healthy while cross-language retrieval was gone entirely.

WHAT THIS MODULE GUARANTEES, and how:

    nothing is deleted before its replacement exists
        A vector is replaced inside the same transaction that inserts its new
        value, and only after the new value has been computed. An embedding
        failure therefore leaves the old vector exactly where it was.

    progress survives an interruption
        Each batch commits on its own. Killing the process loses at most one
        batch of work, and running `repair` again continues from what is
        still missing — no chunk is embedded twice and none is skipped.

    a count is a count of what was WRITTEN
        `RepairReport.written` is incremented after the commit, never before.

    coverage is measured, never inferred
        `inspect()` reads the chunks table and the vector table and compares
        them row by row. It does not trust a progress log, a document's
        declared chunk_count, or the number a previous job printed.

    a vector knows where it came from
        `chunk_vectors` records the model, dimension and the hash of the exact
        text that was embedded. A vector whose text has since changed, or
        that a different model produced, is STALE and is never counted as
        correct coverage — a vector from another model is a point in another
        space, and comparing against it returns confident nonsense.

    two jobs cannot interleave
        A lock file, refreshed after every batch, makes a second repair or
        reindex refuse to start while one is running. A lock whose heartbeat
        stopped long ago is treated as abandoned. (Process liveness is NOT
        probed with os.kill(pid, 0): on Windows that call terminates the
        process rather than testing it.)
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import time
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: A lock whose heartbeat is older than this belonged to a job that died.
_LOCK_STALE_SECONDS = 30 * 60

_SIDECAR_DDL = """
CREATE TABLE IF NOT EXISTS chunk_vectors (
    chunk_id     TEXT PRIMARY KEY,
    chunk_rowid  INTEGER NOT NULL,
    model        TEXT NOT NULL,
    dimension    INTEGER NOT NULL,
    text_hash    TEXT NOT NULL,
    embedded_at  REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS chunk_vectors_by_rowid ON chunk_vectors(chunk_rowid);
"""


def text_hash(text: str) -> str:
    """The hash of exactly what was embedded. Same text, same hash, any machine."""
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Inspection
# --------------------------------------------------------------------------- #

@dataclass
class IntegrityReport:
    """Every number here is counted from rows, not reported by a job."""

    chunks: int = 0
    vectors: int = 0
    #: A chunk with a vector whose metadata matches its current text and the
    #: configured model. This is the only thing that counts as coverage.
    correct: int = 0
    missing: int = 0
    #: A vector row whose chunk no longer exists.
    orphaned: int = 0
    #: A vector whose text hash no longer matches the chunk it belongs to.
    stale: int = 0
    #: A vector produced by a different model than the one configured.
    model_mismatch: int = 0
    #: A vector with no record of what produced it — from before the sidecar
    #: existed, or written by something that bypassed it.
    unknown_provenance: int = 0
    configured_model: str = ""
    configured_dimension: int = 0
    stored_dimension: int = 0
    vector_search: bool = True
    problems: list[str] = field(default_factory=list)

    @property
    def coverage(self) -> float:
        return self.correct / self.chunks if self.chunks else 0.0

    @property
    def needs_repair(self) -> int:
        """Chunks that must be (re)embedded for coverage to be complete."""
        return self.chunks - self.correct

    @property
    def state(self) -> str:
        """healthy / degraded / unhealthy — for a health endpoint.

        Unhealthy when semantic retrieval is effectively absent; degraded when
        it works but not for everything. A corpus with no chunks at all is
        reported separately by the knowledge status, not here.
        """
        if not self.vector_search:
            return "unhealthy"
        if self.stored_dimension and self.configured_dimension \
                and self.stored_dimension != self.configured_dimension:
            return "unhealthy"
        if not self.chunks:
            return "healthy"
        if self.coverage >= 0.999 and not self.orphaned:
            return "healthy"
        if self.coverage >= 0.5:
            return "degraded"
        return "unhealthy"

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out.update(coverage=round(self.coverage, 6), state=self.state,
                   needs_repair=self.needs_repair)
        return out


def ensure_sidecar(db: sqlite3.Connection) -> None:
    db.executescript(_SIDECAR_DDL)


def _sidecar(db: sqlite3.Connection) -> dict[str, tuple[int, str, str, int]]:
    """chunk_id -> (chunk_rowid, model, text_hash, dimension).

    KEYED BY chunk_id, NOT BY ROWID, deliberately. SQLite reuses rowids once
    rows are deleted, and every re-ingest deletes and re-inserts a document's
    chunks. A record keyed by rowid could therefore describe a chunk that no
    longer exists while sitting on the rowid of one that does. `chunk_id` is
    content-addressed — a hash of the document, the position and the text —
    so it identifies exactly one piece of text, and a record is trusted only
    when its rowid ALSO matches where that text lives now.
    """
    return {row[0]: (row[1], row[2], row[3], row[4]) for row in db.execute(
        "SELECT chunk_id, chunk_rowid, model, text_hash, dimension "
        "FROM chunk_vectors")}


def inspect(store: Any, *, model: str, dimension: int) -> IntegrityReport:
    """Compare the chunks table with the vector table, row by row."""
    report = IntegrityReport(configured_model=model,
                             configured_dimension=int(dimension))
    with store._connect() as db:
        ensure_sidecar(db)
        report.vector_search = bool(getattr(store, "_vector_search", True))
        stored = db.execute(
            "SELECT value FROM meta WHERE key = 'dimension'").fetchone()
        report.stored_dimension = int(stored[0]) if stored else 0
        if report.stored_dimension and report.stored_dimension != int(dimension):
            report.problems.append(
                f"the index was built at {report.stored_dimension} dimensions "
                f"and the configured model produces {dimension}")

        report.chunks = db.execute("SELECT count(*) FROM chunks").fetchone()[0]
        if not report.vector_search:
            report.problems.append("sqlite-vec is not loadable; no vector search")
            report.missing = report.chunks
            return report

        present = {row[0] for row in db.execute("SELECT chunk_rowid FROM chunks_vec")}
        report.vectors = len(present)

        meta = _sidecar(db)

        live_rowids = set()
        for rowid, chunk_id, text in db.execute(
                "SELECT rowid, chunk_id, text FROM chunks"):
            live_rowids.add(rowid)
            if rowid not in present:
                report.missing += 1
                continue
            recorded = meta.get(chunk_id)
            if recorded is None or recorded[0] != rowid:
                report.unknown_provenance += 1
                continue
            _, recorded_model, recorded_hash, recorded_dim = recorded
            if recorded_model != model or int(recorded_dim) != int(dimension):
                report.model_mismatch += 1
            elif recorded_hash != text_hash(text):
                report.stale += 1
            else:
                report.correct += 1

        report.orphaned = len(present - live_rowids)

    if report.missing:
        report.problems.append(f"{report.missing} chunks have no vector")
    if report.stale:
        report.problems.append(f"{report.stale} vectors no longer match their text")
    if report.model_mismatch:
        report.problems.append(
            f"{report.model_mismatch} vectors came from a different model")
    if report.unknown_provenance:
        report.problems.append(
            f"{report.unknown_provenance} vectors have no record of what "
            f"produced them")
    if report.orphaned:
        report.problems.append(f"{report.orphaned} vectors belong to no chunk")
    return report


# --------------------------------------------------------------------------- #
# The lock
# --------------------------------------------------------------------------- #

class JobLocked(RuntimeError):
    """Another ingest, reindex or repair is already running on this corpus."""


class JobLock:
    """One writer at a time, with a heartbeat so a dead job does not block forever."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._held = False

    def __enter__(self) -> JobLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            age = time.time() - self.path.stat().st_mtime
            if age < _LOCK_STALE_SECONDS:
                try:
                    holder = self.path.read_text(encoding="utf-8").strip()
                except OSError:
                    holder = "unknown"
                raise JobLocked(
                    f"another job holds {self.path.name} ({holder}); its "
                    f"heartbeat is {int(age)}s old. Wait for it, or remove the "
                    f"file if you are certain it is dead.")
            log.warning("vector_integrity.stale_lock_taken",
                        extra={"age_seconds": int(age)})
            self.path.unlink(missing_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError as exc:
            raise JobLocked(f"{self.path.name} was taken by another job") from exc
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(f"pid={os.getpid()} started={int(time.time())}")
        self._held = True
        return self

    def heartbeat(self) -> None:
        if self._held:
            os.utime(self.path, None)

    def __exit__(self, *exc_info: object) -> None:
        if self._held:
            self.path.unlink(missing_ok=True)
            self._held = False


# --------------------------------------------------------------------------- #
# Repair
# --------------------------------------------------------------------------- #

@dataclass
class RepairReport:
    """What a repair actually did. Counted after each commit, never before."""

    started_at: float = 0.0
    finished_at: float = 0.0
    model: str = ""
    dimension: int = 0
    candidates: int = 0
    batches_attempted: int = 0
    batches_committed: int = 0
    written: int = 0
    failed: int = 0
    orphans_removed: int = 0
    interrupted: bool = False
    errors: list[str] = field(default_factory=list)
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _candidates(db: sqlite3.Connection, *, model: str, dimension: int,
                force: bool) -> list[tuple[int, str, str]]:
    """(rowid, chunk_id, text) for every chunk that lacks a correct vector."""
    present = {row[0] for row in db.execute("SELECT chunk_rowid FROM chunks_vec")}
    meta = _sidecar(db)
    out: list[tuple[int, str, str]] = []
    for rowid, chunk_id, text in db.execute(
            "SELECT rowid, chunk_id, text FROM chunks ORDER BY rowid"):
        if force:
            out.append((rowid, chunk_id, text))
            continue
        if rowid not in present:
            out.append((rowid, chunk_id, text))
            continue
        recorded = meta.get(chunk_id)
        if recorded is None or recorded[0] != rowid:
            out.append((rowid, chunk_id, text))
            continue
        _, recorded_model, recorded_hash, recorded_dim = recorded
        if (recorded_model != model or int(recorded_dim) != int(dimension)
                or recorded_hash != text_hash(text)):
            out.append((rowid, chunk_id, text))
    return out


def _write_batch(store: Any, rows: Sequence[tuple[int, str, str]],
                 vectors: Sequence[Sequence[float]], *, model: str,
                 dimension: int) -> int:
    """Replace these vectors in ONE transaction. Returns how many were written.

    The new vectors already exist when this is called — that ordering is the
    entire guarantee. A failure here rolls back and leaves the old vectors.
    """
    import sqlite_vec

    if len(rows) != len(vectors):
        raise ValueError(f"{len(rows)} chunks but {len(vectors)} vectors")
    now = time.time()
    with store._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            for (rowid, chunk_id, text), vector in zip(rows, vectors, strict=True):
                if len(vector) != int(dimension):
                    raise ValueError(
                        f"chunk {chunk_id}: got a {len(vector)}-dimension vector, "
                        f"the index holds {dimension}")
                # Still a chunk? An ingest may have replaced the document since
                # the candidates were read; a vector for a vanished rowid would
                # be an orphan the moment it was written.
                alive = db.execute("SELECT 1 FROM chunks WHERE rowid = ? "
                                   "AND chunk_id = ?", (rowid, chunk_id)).fetchone()
                if not alive:
                    continue
                db.execute("DELETE FROM chunks_vec WHERE chunk_rowid = ?", (rowid,))
                db.execute(
                    "INSERT INTO chunks_vec(chunk_rowid, embedding) VALUES(?, ?)",
                    (rowid, sqlite_vec.serialize_float32(list(vector))))
                db.execute(
                    "INSERT INTO chunk_vectors(chunk_id, chunk_rowid, model, "
                    "dimension, text_hash, embedded_at) VALUES(?,?,?,?,?,?) "
                    "ON CONFLICT(chunk_id) DO UPDATE SET "
                    "chunk_rowid=excluded.chunk_rowid, model=excluded.model, "
                    "dimension=excluded.dimension, text_hash=excluded.text_hash, "
                    "embedded_at=excluded.embedded_at",
                    (chunk_id, rowid, model, int(dimension), text_hash(text), now))
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    return len(rows)


def _remove_orphans(store: Any) -> int:
    with store._connect() as db:
        db.execute("BEGIN IMMEDIATE")
        try:
            orphans = [row[0] for row in db.execute(
                "SELECT chunk_rowid FROM chunks_vec WHERE chunk_rowid NOT IN "
                "(SELECT rowid FROM chunks)")]
            for rowid in orphans:
                db.execute("DELETE FROM chunks_vec WHERE chunk_rowid = ?", (rowid,))
            db.execute("DELETE FROM chunk_vectors WHERE chunk_id NOT IN "
                       "(SELECT chunk_id FROM chunks)")
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
    return len(orphans)


async def repair(store: Any, provider: Any, *, model: str, force: bool = False,
                 batch_size: int = 32, max_batches: int | None = None,
                 lock_path: Path | None = None,
                 report_dir: Path | None = None) -> RepairReport:
    """Embed every chunk that lacks a correct vector. Resumable and non-destructive.

    `force` re-embeds everything (a model change) — still batch by batch, still
    replacing each vector only once its successor exists.

    `max_batches` stops early on purpose; the next call continues. Used by the
    interruption tests, and useful for spreading a large job over a rate limit.
    """
    dimension = int(provider.dimension)
    report = RepairReport(started_at=time.time(), model=model, dimension=dimension)
    report.before = inspect(store, model=model, dimension=dimension).as_dict()

    lock = JobLock(lock_path or Path(store.path).with_suffix(".lock"))
    with lock:
        with store._connect() as db:
            ensure_sidecar(db)
            todo = _candidates(db, model=model, dimension=dimension, force=force)
        report.candidates = len(todo)

        try:
            for start in range(0, len(todo), batch_size):
                if max_batches is not None and report.batches_attempted >= max_batches:
                    report.interrupted = True
                    break
                rows = todo[start:start + batch_size]
                report.batches_attempted += 1
                try:
                    vectors = await provider.embed([text for _, _, text in rows])
                except Exception as exc:  # noqa: BLE001
                    # The batch is skipped, not the job. Its chunks keep
                    # whatever vectors they had; the next run retries them.
                    report.failed += len(rows)
                    report.errors.append(f"batch {start // batch_size}: "
                                         f"{type(exc).__name__}: {str(exc)[:160]}")
                    log.warning("vector_integrity.batch_failed",
                                extra={"batch": start // batch_size,
                                       "error": str(exc)[:160]})
                    lock.heartbeat()
                    continue
                written = _write_batch(store, rows, vectors, model=model,
                                       dimension=dimension)
                report.batches_committed += 1
                report.written += written
                lock.heartbeat()
        finally:
            report.orphans_removed = _remove_orphans(store)
            report.finished_at = time.time()
            report.after = inspect(store, model=model, dimension=dimension).as_dict()

    if report_dir is not None:
        write_report(report, report_dir)
    return report


def write_report(report: RepairReport, directory: Path) -> Path:
    """A machine-readable record of the run, for whoever audits the corpus."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(report.finished_at or time.time()))
    path = directory / f"vector-repair-{stamp}.json"
    path.write_text(json.dumps(report.as_dict(), indent=2, default=str),
                    encoding="utf-8")
    return path
