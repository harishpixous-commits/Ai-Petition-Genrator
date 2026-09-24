"""Submitting a petition: what it records, and what it does not claim.

WHAT IT IS. The citizen saying they are finished. It stamps the moment,
the officer portal shows the petition as submitted, and the screen says so.

WHAT IT IS NOT, and the distinction is the whole reason this is recorded
rather than only displayed. Nothing is transmitted to a department. No office
is written to, no authority issues an acknowledgement, and the printed
petition still has to reach the office the way any petition does. A button
that said "Successfully submitted" with nothing behind it would tell somebody
at a counter that their grievance had been filed with the Collector, and they
would go home and wait.

THE PETITION STAYS EDITABLE afterwards, by request. Submitting is the citizen
saying they are done, not the record being frozen.
"""

from __future__ import annotations

import inspect
import pathlib

from app.api import rest
from app.graph.state import new_state


class TestWhatIsRecorded:

    def test_a_fresh_petition_has_not_been_submitted(self):
        assert new_state("en")["submitted_at"] is None

    def test_the_route_exists_and_is_a_post(self):
        paths = {r.path: r.methods for r in rest.router.routes if hasattr(r, "path")}
        assert "/api/sessions/{session_id}/submit" in paths
        assert "POST" in paths["/api/sessions/{session_id}/submit"]

    def test_it_refuses_before_there_is_a_petition(self):
        """Nothing to be finished with yet."""
        source = inspect.getsource(rest.submit_petition)
        assert 'state.get("status") != "ready"' in source
        assert "409" in source

    def test_it_keeps_the_first_timestamp(self):
        """Pressing it twice does not move the moment they finished."""
        source = inspect.getsource(rest.submit_petition)
        assert 'already = state.get("submitted_at")' in source
        assert "if not already:" in source

    def test_it_writes_through_the_checkpoint(self):
        """The same path every other out-of-band edit takes, so a submitted
        petition survives a reload like everything else."""
        source = inspect.getsource(rest.submit_petition)
        assert ".update(session_id, {\"submitted_at\"" in source

    def test_it_does_not_freeze_the_petition(self):
        """Editable afterwards, by request. Nothing here touches status."""
        source = inspect.getsource(rest.submit_petition)
        assert '"status":' not in source
        assert "locked" not in source.lower()


class TestWhatIsShown:

    @staticmethod
    def script():
        return (pathlib.Path(__file__).resolve().parent.parent
                / "app" / "static" / "app.js").read_text(encoding="utf-8")

    @staticmethod
    def page():
        return (pathlib.Path(__file__).resolve().parent.parent
                / "app" / "static" / "index.html").read_text(encoding="utf-8")

    def test_the_button_sits_under_the_document(self):
        """Where a citizen arrives after reading it — and OUTSIDE
        `.paper-wrap`, which is a row flex container. Placed inside, the
        confirmation became a column beside the paper and stretched to the
        full height of the scroll area. Measured at 710x78 once moved."""
        page = self.page()
        card = page.index('id="docCard"')
        wrap = page.index('class="paper-wrap"', card)
        row = page.index('id="submitRow"')

        assert row > wrap, "the submit row must come after the preview"
        assert "</div>" in page[wrap:row], "it must sit outside .paper-wrap"

    def test_the_confirmation_replaces_the_button(self):
        script = self.script()
        assert 'Boolean(submitted)' in script
        assert '$("submittedMark").hidden = !hasLetter || !submitted' in script

    def test_the_date_is_formatted_without_reaching_across_files(self):
        """`dateLabel` lives in navigation.js, a separate script. Reaching
        for it at paint time is the load-order gamble that already broke this
        page once, when a painter used a bare `t`."""
        script = self.script()
        assert "function submittedOn(" in script
        assert "readableDate(" not in script

    def test_an_unparseable_date_is_not_invented(self):
        script = self.script()
        block = script[script.index("function submittedOn("):]
        assert "Number.isNaN" in block[:400]

    def test_both_languages_have_every_string(self):
        script = self.script()
        for key in ("submit", "submitNote", "submitting", "submittedTitle",
                    "submittedText", "submitFailed"):
            assert script.count(f"{key}:") >= 2, f"{key} has no Tamil translation"

    def test_the_note_does_not_claim_an_office_received_it(self):
        """The one sentence that has to stay true."""
        script = self.script()
        line = next(l for l in script.splitlines() if "submitNote:" in l and "office" in l)
        assert "still has to reach the office" in line

    def test_it_is_not_printed(self):
        css = (pathlib.Path(__file__).resolve().parent.parent
               / "app" / "static" / "app.css").read_text(encoding="utf-8")
        printed = css[css.index("@media print"):]
        assert ".submit-row,.submitted-mark{display:none!important}" in printed
