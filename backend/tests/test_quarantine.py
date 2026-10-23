"""The quarantine store: discovered → curator → either approved or rejected.

WHAT THIS GUARDS. Phase 2 of the brief says every discovered document
must land in a staging table first, go through a human review, and reach
the corpus only when a curator explicitly approves it. These tests pin
the four behaviours the schema exists for:

  * duplicate inserts don't accumulate rows — the (source, URL) key is
    unique, and a second discovery returns the first row's id;
  * state transitions follow the state diagram: discovered →
    pdf_fetched → one of approved/rejected/duplicate/outdated;
  * a reject, a duplicate and an outdated review all REQUIRE a reason;
  * marking duplicate also requires an existing row to point at.

Offline. No network, no live scraping.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.knowledge import quarantine as q


@pytest.fixture
def settings(tmp_path):
    s = Settings(data_dir=tmp_path)
    s.ensure_dirs()
    return s


def _discovery(**over) -> q.Discovery:
    base = dict(
        source_id="indiacode-tn",
        official_url="https://www.indiacode.nic.in/handle/123456789/9999",
        title="A Tamil Nadu Act",
        document_type="act",
        source_tier="tier_2_repository",
        act_number="Act No. 5 of 1972",
        year=1972,
        issuing_authority="Tamil Nadu",
    )
    base.update(over)
    return q.Discovery(**base)


class TestInsertAndIdempotency:
    def test_a_discovery_lands_as_a_row(self, settings):
        row_id = q.record(_discovery(), settings=settings)
        stored = q.get_row(row_id, settings=settings)
        assert stored["title"] == "A Tamil Nadu Act"
        assert stored["verification_status"] == "discovered"
        assert stored["amendment_status"] == "unknown"
        assert stored["retrieved_at"], "retrieved_at must be stamped"

    def test_the_same_url_twice_returns_the_first_id(self, settings):
        """Rule 10 — 'duplicate documents' must not accumulate rows. A
        second discovery of the same URL from the same source is a no-op."""
        first = q.record(_discovery(), settings=settings)
        second = q.record(_discovery(title="RE-DISCOVERED"), settings=settings)
        assert first == second
        # And the stored title stays the first one — the second discovery
        # does not quietly overwrite a row the curator may already have
        # started reading.
        stored = q.get_row(first, settings=settings)
        assert stored["title"] == "A Tamil Nadu Act"


class TestTypeValidation:
    def test_an_unknown_document_type_is_refused(self, settings):
        with pytest.raises(q.QuarantineError, match="document_type"):
            q.record(_discovery(document_type="bare_act_pdf"),
                     settings=settings)

    def test_a_non_http_url_is_refused(self, settings):
        with pytest.raises(q.QuarantineError, match="official_url"):
            q.record(_discovery(official_url="ftp://example/x.pdf"),
                     settings=settings)


class TestStateTransitions:
    def test_set_status_flips_a_discovered_row(self, settings):
        row_id = q.record(_discovery(), settings=settings)
        q.set_status(row_id, "pdf_fetched",
                     pdf_sha256="a" * 64, settings=settings)
        stored = q.get_row(row_id, settings=settings)
        assert stored["verification_status"] == "pdf_fetched"
        assert stored["pdf_sha256"] == "a" * 64

    def test_set_status_refuses_a_terminal_state(self, settings):
        """Approvals go through `review`, not through `set_status`.
        Allowing both would mean an operator could silently approve a row
        without a reviewer attribution — SRS §10.4 forbids that."""
        row_id = q.record(_discovery(), settings=settings)
        with pytest.raises(q.QuarantineError, match="terminal"):
            q.set_status(row_id, "approved", settings=settings)

    def test_set_status_on_an_unknown_id_raises(self, settings):
        with pytest.raises(q.QuarantineError, match="no quarantine row"):
            q.set_status("not-a-real-id", "pdf_fetched", settings=settings)


class TestReviewActions:
    def test_a_reviewer_can_approve(self, settings):
        row_id = q.record(_discovery(), settings=settings)
        row = q.review(row_id, "approve", reviewer="curator1", settings=settings)
        assert row["verification_status"] == "approved"
        assert row["reviewer"] == "curator1"
        assert row["reviewed_at"]

    def test_a_reject_needs_a_reason(self, settings):
        row_id = q.record(_discovery(), settings=settings)
        with pytest.raises(q.QuarantineError, match="reason"):
            q.review(row_id, "reject", reviewer="curator1", settings=settings)
        row = q.review(row_id, "reject", reviewer="curator1",
                       reason="PDF is a scan of a different Act",
                       settings=settings)
        assert row["verification_status"] == "rejected"
        assert "scan of a different Act" in row["review_reason"]

    def test_outdated_needs_a_reason_too(self, settings):
        row_id = q.record(_discovery(), settings=settings)
        with pytest.raises(q.QuarantineError, match="reason"):
            q.review(row_id, "outdated", reviewer="c", settings=settings)
        row = q.review(row_id, "outdated", reviewer="c",
                       reason="repealed by Act 12 of 2003",
                       settings=settings)
        assert row["verification_status"] == "outdated"

    def test_marking_duplicate_needs_an_existing_row(self, settings):
        first = q.record(_discovery(), settings=settings)
        second = q.record(_discovery(
            official_url="https://www.indiacode.nic.in/handle/123456789/9998"),
            settings=settings)
        with pytest.raises(q.QuarantineError, match="duplicate_of"):
            q.review(second, "duplicate", reviewer="c",
                     reason="reprint of first", settings=settings)
        row = q.review(second, "duplicate", reviewer="c",
                       reason="reprint of first", duplicate_of=first,
                       settings=settings)
        assert row["verification_status"] == "duplicate"
        assert row["duplicate_of"] == first

    def test_a_row_that_is_already_terminal_cannot_be_reviewed_again(
            self, settings):
        row_id = q.record(_discovery(), settings=settings)
        q.review(row_id, "approve", reviewer="c", settings=settings)
        with pytest.raises(q.QuarantineError, match="already"):
            q.review(row_id, "reject", reviewer="c",
                     reason="second thoughts", settings=settings)


class TestPendingAndListing:
    def test_pending_shows_discovered_and_pdf_fetched_and_unreachable(
            self, settings):
        a = q.record(_discovery(), settings=settings)
        b = q.record(_discovery(
            official_url="https://www.indiacode.nic.in/handle/123456789/9998"),
            settings=settings)
        c = q.record(_discovery(
            official_url="https://www.indiacode.nic.in/handle/123456789/9997"),
            settings=settings)
        q.set_status(a, "pdf_fetched", pdf_sha256="a" * 64, settings=settings)
        q.set_status(b, "unreachable", settings=settings)
        q.review(c, "approve", reviewer="c", settings=settings)

        pending = {row["id"] for row in q.pending(settings=settings)}
        assert pending == {a, b}

    def test_filter_by_status(self, settings):
        a = q.record(_discovery(), settings=settings)
        q.review(a, "approve", reviewer="c", settings=settings)
        approved = q.all_rows(status="approved", settings=settings)
        assert [row["id"] for row in approved] == [a]
        rejected = q.all_rows(status="rejected", settings=settings)
        assert rejected == []


class TestHashing:
    def test_the_hash_is_sha256(self):
        assert q.hash_bytes(b"") == (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4"
            "649b934ca495991b7852b855")
        assert q.hash_bytes(b"x") == (
            "2d711642b726b04401627ca9fbac32f5c8530fb1"
            "903cc4db02258717921a4881")

    def test_destination_lives_under_the_data_dir(self, settings):
        dest = q.pdf_destination("deadbeef" * 8, settings=settings)
        assert str(dest).endswith(".pdf")
        assert str(dest).startswith(str(settings.data_dir))
