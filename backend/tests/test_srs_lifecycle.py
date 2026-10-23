"""The SRS-aligned status label, derived from the internal state.

TWO VOCABULARIES. The service runs on an internal seven-word status set
(collecting, attachments, confirming, generating, ready, cancelled,
failed) because every node, test and petition record is written against
it. The SRS §3.3 asks for a different, ten-word set (Draft, Capturing,
Transcribing, Needs clarification, Ready for review, Approved by citizen,
Exported, Submitted/Received, Failed, Interrupted) because that is the
vocabulary an officer, a reviewer or a policy document reads.

`srs_label` keeps the internal word as the single source of truth and
answers "what does that correspond to in the SRS wording". It must NOT
influence behaviour, only labelling.

This matters most for the two SRS states that are not status values at
all. "Exported" is a petition whose document has been produced; the
status is still "ready". "Submitted/Received" is a citizen who pressed
Submit; the status is still "ready" and `submitted_at` carries the time.
A UI that read only `status` would miss both.
"""

from __future__ import annotations

from app.domain.lifecycle import srs_label


class TestEveryInternalStatusMapsToTheSrsLabel:
    def test_collecting_is_a_draft(self):
        assert srs_label({"status": "collecting"})["srs"] == "Draft"

    def test_attachments_is_capturing(self):
        assert srs_label({"status": "attachments"})["srs"] == "Capturing"

    def test_confirming_is_needs_clarification(self):
        assert srs_label({"status": "confirming"})["srs"] == "Needs clarification"

    def test_generating_is_transcribing(self):
        assert srs_label({"status": "generating"})["srs"] == "Transcribing"

    def test_ready_is_ready_for_review(self):
        assert srs_label({"status": "ready"})["srs"] == "Ready for review"

    def test_failed_is_failed(self):
        assert srs_label({"status": "failed"})["srs"] == "Failed"

    def test_cancelled_is_interrupted(self):
        assert srs_label({"status": "cancelled"})["srs"] == "Interrupted"


class TestExportedAndSubmittedAreDerivedNotStored:
    def test_a_ready_petition_with_a_document_is_exported(self):
        payload = srs_label({"status": "ready", "document": {"docx": "p.docx"}})
        assert payload["srs"] == "Exported"
        assert payload["exported"] is True
        assert payload["submitted"] is False

    def test_a_ready_petition_with_no_document_stays_at_ready_for_review(self):
        payload = srs_label({"status": "ready"})
        assert payload["srs"] == "Ready for review"
        assert payload["exported"] is False

    def test_submission_label_names_itself_as_a_LOCAL_record_only(self):
        """FR-016. The citizen pressed Submit — the record is local; nothing
        has been filed with a department. The label must say so, so a UI
        cannot show a bare "Submitted" and read as a government filing."""
        payload = srs_label({"status": "ready",
                             "document": {"docx": "p.docx"},
                             "submitted_at": "2026-10-13T09:00:00+00:00"})
        assert "local record" in payload["srs"].lower()
        assert "not an official filing" in payload["srs"].lower()
        assert payload["submitted"] is True
        assert payload["exported"] is True


class TestTheHelperDoesNotMutate:
    def test_the_input_state_is_untouched(self):
        state = {"status": "ready", "document": {"docx": "x.docx"}}
        before = dict(state)
        srs_label(state)
        assert state == before

    def test_a_none_state_returns_a_safe_label(self):
        payload = srs_label(None)
        assert payload["internal"] is None
        assert payload["exported"] is False
        assert payload["submitted"] is False
