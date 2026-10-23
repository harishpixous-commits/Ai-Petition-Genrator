"""Vector-index integrity: the incident, reproduced, and each guarantee held.

THE INCIDENT these tests exist for. A reindex of the Tamil Nadu corpus deleted
every vector it had and printed "Re-embedded 8344 chunks." over a vector table
holding zero rows. Three defects combined: an embed that failed a whole
document when one batch failed, a write that deleted before it replaced, and a
counter that counted attempts instead of writes. Lexical search kept working,
so nothing looked wrong.

Every test here is OFFLINE and DETERMINISTIC. The integrity logic does not
depend on which embedder is used, so a hashed local embedder — plus a provider
that fails exactly when told to — exercises all of it without a network.
"""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.knowledge import vector_integrity as vi
from app.knowledge.embeddings import LocalEmbeddings
from app.knowledge.ingest import Ingestor
from app.knowledge.store import KnowledgeStore

DIM = 64
MODEL = "local-test"

ACT = """The Tamil Nadu Example Act, 2000

Section 1. Short title.
This Act may be called the Tamil Nadu Example Act, 2000, and shall extend to
the whole of the State and come into force on such date as notified.

Section 2. Definitions.
In this Act, unless the context otherwise requires, a local body means a
municipal corporation, a municipality, a town panchayat or a village panchayat.

Section 3. Duties of the local body.
Every local body shall provide drinking water, maintain streets and lighting,
and remove rubbish, within the limits of the funds available to it.

Section 4. Complaints.
A complaint about any duty in section 3 shall be registered and acknowledged
within seven days, and disposed of within thirty days of registration.
""" * 3


class Local(LocalEmbeddings):
    """The hashed local embedder, with a model name for provenance."""

    model = MODEL


class Flaky:
    """An embedder that fails on chosen calls — the rate limit, on demand."""

    semantic = False
    name = "flaky"
    model = MODEL

    def __init__(self, fail_on: set[int] | None = None, always: bool = False):
        self.inner = Local(dimension=DIM)
        self.dimension = DIM
        self.fail_on = fail_on or set()
        self.always = always
        self.calls = 0

    async def embed(self, texts):
        self.calls += 1
        if self.always or self.calls in self.fail_on:
            raise RuntimeError("429 quota exceeded")
        return await self.inner.embed(texts)


@pytest.fixture
def store(tmp_path):
    return KnowledgeStore(tmp_path / "k.sqlite", dimension=DIM, provider="local")


async def ingest(store, provider, tmp_path, name="act.txt", text=ACT):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    ingestor = Ingestor(store=store, provider=provider, settings=get_settings())
    await ingestor.ingest(path, metadata={"authority": "official",
                                          "document_type": "act",
                                          "provenance": "TEST DATA"})
    return ingestor


def counts(store) -> vi.IntegrityReport:
    return vi.inspect(store, model=MODEL, dimension=DIM)


# --------------------------------------------------------------------------- #

class TestTheIncidentCannotRecur:
    async def test_a_failing_reindex_no_longer_destroys_the_vectors(self, store, tmp_path):
        """THE INCIDENT. A complete, correct index; a reindex whose provider
        fails on every call. Before: every vector deleted, success reported.
        Now: every vector survives, and the reported count is zero."""
        await ingest(store, Local(dimension=DIM), tmp_path)
        before = counts(store)
        assert before.chunks and before.correct == before.chunks

        broken = Ingestor(store=store, provider=Flaky(always=True),
                          settings=get_settings())
        written = await broken.reindex()

        after = counts(store)
        assert written == 0, "the count must be what was written, not attempted"
        assert after.vectors == before.vectors, "a failed reindex deleted vectors"
        assert after.correct == before.correct

    async def test_the_reported_count_is_what_is_actually_in_the_table(
            self, store, tmp_path):
        await ingest(store, Flaky(always=True), tmp_path)   # lexical only
        assert counts(store).vectors == 0

        flaky = Flaky(fail_on={2})          # one batch of several fails
        report = await vi.repair(store, flaky, model=MODEL, batch_size=8)

        after = counts(store)
        assert report.written == after.vectors, (
            f"reported {report.written}, table holds {after.vectors}")
        assert report.failed > 0
        assert after.missing == report.failed


class TestRepairFillsWhatIsMissing:
    async def test_a_corpus_with_no_vectors_is_repaired_completely(self, store, tmp_path):
        await ingest(store, Flaky(always=True), tmp_path)
        assert counts(store).missing == counts(store).chunks

        report = await vi.repair(store, Local(dimension=DIM), model=MODEL)

        after = counts(store)
        assert after.missing == 0
        assert after.correct == after.chunks
        assert after.state == "healthy"
        assert report.written == after.chunks

    async def test_repair_is_idempotent(self, store, tmp_path):
        await ingest(store, Flaky(always=True), tmp_path)
        await vi.repair(store, Local(dimension=DIM), model=MODEL)

        second = await vi.repair(store, Local(dimension=DIM), model=MODEL)
        assert second.candidates == 0
        assert second.written == 0

    async def test_repair_changes_only_the_records_that_need_it(self, store, tmp_path):
        """A healthy chunk's vector must not be touched — the repair rewrites
        what is wrong, not everything."""
        await ingest(store, Local(dimension=DIM), tmp_path)
        healthy = counts(store).correct

        report = await vi.repair(store, Local(dimension=DIM), model=MODEL)
        assert report.candidates == 0, (
            f"{report.candidates} healthy chunks were scheduled for re-embedding")
        assert counts(store).correct == healthy


class TestAnInterruptedJobResumes:
    async def test_a_stopped_repair_continues_without_duplicates(self, store, tmp_path):
        await ingest(store, Flaky(always=True), tmp_path)
        total = counts(store).chunks

        first = await vi.repair(store, Local(dimension=DIM), model=MODEL,
                                batch_size=4, max_batches=2)
        assert first.interrupted
        partial = counts(store)
        assert 0 < partial.correct < total

        second = await vi.repair(store, Local(dimension=DIM), model=MODEL,
                                 batch_size=4)
        final = counts(store)
        assert final.correct == total
        assert final.vectors == total, "a resumed job duplicated or lost vectors"
        assert first.written + second.written == total

    async def test_a_failed_batch_keeps_its_old_vectors(self, store, tmp_path):
        """Force a full re-embed where one batch fails: that batch's chunks
        must keep the vectors they had, and still count as correct."""
        await ingest(store, Local(dimension=DIM), tmp_path)
        before = counts(store)

        report = await vi.repair(store, Flaky(fail_on={1}), model=MODEL,
                                 force=True, batch_size=8)
        after = counts(store)
        assert report.failed == 8
        assert after.vectors == before.vectors
        assert after.correct == before.correct


class TestStaleAndForeignVectorsAreNotCoverage:
    async def test_a_vector_whose_text_changed_is_stale(self, store, tmp_path):
        await ingest(store, Local(dimension=DIM), tmp_path)
        with store._connect() as db:
            db.execute("UPDATE chunk_vectors SET text_hash = 'not-the-text' "
                       "WHERE rowid = (SELECT min(rowid) FROM chunk_vectors)")
        report = counts(store)
        assert report.stale == 1
        assert report.correct == report.chunks - 1

        await vi.repair(store, Local(dimension=DIM), model=MODEL)
        assert counts(store).stale == 0

    async def test_a_vector_from_another_model_is_not_counted(self, store, tmp_path):
        """A vector from another model is a point in another space."""
        await ingest(store, Local(dimension=DIM), tmp_path)
        report = vi.inspect(store, model="some-other-model", dimension=DIM)
        assert report.correct == 0
        assert report.model_mismatch == report.chunks

    async def test_a_vector_with_no_provenance_is_not_trusted(self, store, tmp_path):
        await ingest(store, Local(dimension=DIM), tmp_path)
        with store._connect() as db:
            db.execute("DELETE FROM chunk_vectors")
        report = counts(store)
        assert report.unknown_provenance == report.chunks
        assert report.correct == 0
        assert report.state != "healthy"


class TestOrphansAndDimensions:
    async def test_an_orphaned_vector_is_found_and_removed(self, store, tmp_path):
        await ingest(store, Local(dimension=DIM), tmp_path)
        import sqlite_vec

        with store._connect() as db:
            db.execute("INSERT INTO chunks_vec(chunk_rowid, embedding) VALUES(?, ?)",
                       (999_999, sqlite_vec.serialize_float32([0.1] * DIM)))
        assert counts(store).orphaned == 1

        report = await vi.repair(store, Local(dimension=DIM), model=MODEL)
        assert report.orphans_removed == 1
        assert counts(store).orphaned == 0

    async def test_a_dimension_mismatch_is_unhealthy(self, store, tmp_path):
        await ingest(store, Local(dimension=DIM), tmp_path)
        report = vi.inspect(store, model=MODEL, dimension=DIM * 2)
        assert report.state == "unhealthy"
        assert any("dimensions" in p for p in report.problems)


class TestOneJobAtATime:
    def test_a_second_job_is_refused_while_one_holds_the_lock(self, tmp_path):
        lock_path = tmp_path / "k.lock"
        with vi.JobLock(lock_path), pytest.raises(vi.JobLocked):
            with vi.JobLock(lock_path):
                pass

    def test_the_lock_is_released_after_a_failure(self, tmp_path):
        lock_path = tmp_path / "k.lock"
        with pytest.raises(RuntimeError), vi.JobLock(lock_path):
            raise RuntimeError("the job died")
        assert not lock_path.exists()
        with vi.JobLock(lock_path):
            pass

    def test_an_abandoned_lock_is_taken_over(self, tmp_path):
        import os
        import time

        lock_path = tmp_path / "k.lock"
        lock_path.write_text("pid=1 started=0", encoding="utf-8")
        old = time.time() - vi._LOCK_STALE_SECONDS - 60
        os.utime(lock_path, (old, old))
        with vi.JobLock(lock_path):
            pass


class TestTheReportIsMachineReadable:
    async def test_a_report_file_is_written(self, store, tmp_path):
        import json

        await ingest(store, Flaky(always=True), tmp_path)
        report = await vi.repair(store, Local(dimension=DIM), model=MODEL,
                                 report_dir=tmp_path / "reports")
        files = list((tmp_path / "reports").glob("vector-repair-*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text(encoding="utf-8"))
        assert data["written"] == report.written
        assert data["after"]["state"] == "healthy"
        assert data["before"]["missing"] > 0
