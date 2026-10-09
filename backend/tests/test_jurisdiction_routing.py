"""Which office a petition belongs to, across the four kinds of local body.

Tamil Nadu's urban and rural local bodies are not one thing. A grievance in a
corporation goes to a Commissioner; the same grievance a few kilometres away
goes to a Block Development Officer through a village panchayat, and the
citizen cannot tell which from the address alone. `jurisdiction` is the field
that answers it, and `test_knowledge.py` already holds the basic contract: it
is strict, so the value has to appear verbatim in a retrieved passage.

WHAT THIS FILE ADDS is the part that is actually hard — the cases where a
directory is present but does not settle the question:

    a town that two passages place in different bodies
    a town named in an Act rather than in a directory
    a body named for a DIFFERENT town in the same district
    a reclassification, where yesterday's town panchayat is today's municipality

In all of those the right answer is silence. A jurisdiction that is merely
plausible is worse than none, because the citizen acts on it: they travel.

NO REAL DIRECTORY IS SHIPPED, and no list of local bodies is invented here.
The passages below are written as a directory would be written, to exercise
the rule; `docs/knowledge-base-population.md` records that the real directory
has to come from the department.
"""

from __future__ import annotations

import pytest

from app.knowledge.analyst import grounded
from app.knowledge.schema import Chunk


def directory(text: str, title: str = "Local bodies directory") -> Chunk:
    """A passage from a department's own local body directory."""
    return Chunk(chunk_id="c1", document_id="d1", text=text,
                 document_title=title,
                 document_type="local_body_directory", authority="official")


def act(text: str) -> Chunk:
    """A passage from an Act, which may mention a town without placing it."""
    return Chunk(chunk_id="c2", document_id="d2", text=text,
                 document_title="Tamil Nadu Urban Local Bodies Act, 1998",
                 document_type="act", authority="official")


# --------------------------------------------------------------------------- #
# The four kinds of body
# --------------------------------------------------------------------------- #

BODIES = [
    ("Coimbatore City Municipal Corporation",
     "Coimbatore City Municipal Corporation covers the Coimbatore city area. "
     "The Commissioner is the officer for grievances within those limits."),
    ("Theni Allinagaram Municipality",
     "Theni Allinagaram Municipality covers the Theni and Allinagaram town "
     "areas. The Commissioner is the officer for grievances arising there."),
    ("Oddanchatram Town Panchayat",
     "Oddanchatram Town Panchayat covers the Oddanchatram town area. The "
     "Executive Officer is the officer for grievances arising there."),
    ("Kadamalaikundu Village Panchayat",
     "Kadamalaikundu Village Panchayat covers the revenue village of the same "
     "name. The President and the Block Development Officer are responsible."),
]


class TestEachKindOfBodyIsRecognised:
    """All four exist, all four are different offices, and a service that
    handles only corporations is a service for Chennai."""

    @pytest.mark.parametrize("name,passage", BODIES)
    def test_a_body_the_directory_names_is_accepted(self, name, passage):
        assert grounded(name, [directory(passage)], strict=True), name

    @pytest.mark.parametrize("name,passage", BODIES)
    def test_the_same_name_without_the_directory_is_refused(self, name, passage):
        """The name alone proves nothing. Remove the passage and the finding
        must go with it, or the model is being trusted rather than the
        corpus."""
        assert not grounded(name, [], strict=True), name


class TestWhereTheDirectoryDoesNotSettleIt:
    """The cases that make this worth testing at all."""

    def test_a_body_in_the_same_district_is_not_close_enough(self):
        """Periyakulam and Theni are both in Theni district. A citizen sent to
        the wrong one has still lost a day."""
        passage = directory(BODIES[1][1])
        assert not grounded("Periyakulam Municipality", [passage], strict=True)

    def test_the_right_town_with_the_wrong_kind_of_body_is_refused(self):
        """"Theni Village Panchayat" and "Theni Allinagaram Municipality" name
        the same place and two different offices. Matching on the town would
        accept both."""
        passage = directory(BODIES[1][1])
        assert not grounded("Theni Village Panchayat", [passage], strict=True)
        assert not grounded("Theni Town Panchayat", [passage], strict=True)
        assert not grounded("Theni Municipal Corporation", [passage], strict=True)

    def test_a_town_named_in_an_act_is_not_a_jurisdiction(self):
        """An Act mentions towns in passing — in a schedule, in an example, in
        a definition. That is not a statement about which office covers an
        address, and reading it as one is how a confident wrong answer gets
        made."""
        passage = act(
            "This Act extends to all municipalities in the State including "
            "Coimbatore and Madurai, and shall come into force on such date "
            "as the Government may appoint.")
        assert not grounded("Coimbatore City Municipal Corporation",
                            [passage], strict=True)

    def test_a_partial_name_is_not_the_body(self):
        """"Coimbatore" is a city, a district and a taluk. Only the full name
        of a body identifies an office."""
        passage = directory(BODIES[0][1])
        assert not grounded("Coimbatore Municipality", [passage], strict=True)
        assert not grounded("Coimbatore Town Panchayat", [passage], strict=True)


class TestReclassification:
    """A town panchayat promoted to a municipality is a real and frequent
    event — G.O.(Ms) No.208 of 2010 did exactly that to Oddanchatram — and
    for a while BOTH descriptions are in the corpus.
    """

    OLD = directory("Oddanchatram Town Panchayat covers the Oddanchatram town "
                    "area. The Executive Officer is responsible.")
    NEW = directory("Oddanchatram Town Panchayat, Dindigul District, is "
                    "classified as a Second Grade Municipality with effect "
                    "from the date of this notification.",
                    title="G.O.(Ms) No.208")

    def test_both_descriptions_are_individually_grounded(self):
        """Neither passage is wrong; they describe different moments. The
        grounding check is not where this is resolved — supersession is — so
        what must NOT happen here is a silent preference for one."""
        assert grounded("Oddanchatram Town Panchayat", [self.OLD], strict=True)
        assert grounded("Oddanchatram Town Panchayat", [self.NEW], strict=True)

    def test_a_body_neither_passage_names_is_still_refused(self):
        """FOUND BY THIS TEST, and it was a real hole.

        "Second Grade Municipality" is a grade, not a name, and "Oddanchatram
        Municipality" appears in neither passage. The strict check accepted it
        anyway: when the exact phrase is absent it falls back to asking whether
        every word is present SOMEWHERE in the cited passages, and both
        "Oddanchatram" and "Municipality" are — in different sentences, meaning
        different things.

        That fallback is right for an Act, which gets cited with a trailing
        year or a bracketed qualifier. It is wrong for a body name, so
        jurisdiction is checked verbatim now.
        """
        assert not grounded("Oddanchatram Municipality",
                            [self.OLD, self.NEW], strict=True, verbatim=True)

    def test_jurisdiction_is_configured_to_be_checked_that_way(self):
        """The assertion above only means something if the application asks
        for it. Without this, the check could be switched off and the test
        above would still pass by passing the flag itself."""
        from app.knowledge.analyst import _STRICT_FIELDS, _VERBATIM_FIELDS

        assert "jurisdiction" in _VERBATIM_FIELDS
        assert "jurisdiction" in _STRICT_FIELDS

    def test_an_act_is_still_allowed_its_usual_variation(self):
        """The verbatim rule must not spread. An Act cited with a bracketed
        qualifier the passage writes differently is a real citation, and
        dropping it would empty the panel of the thing it exists to show."""
        passage = act("Under the Tamil Nadu Land Encroachment Act, 1905 "
                      "(Tamil Nadu Act III of 1905) the Tahsildar may act.")
        assert grounded("Tamil Nadu Land Encroachment Act 1905",
                        [passage], strict=True)


class TestTheOfficerOnlySeesWhatIsCited:
    """The last gate before a human acts on it."""

    def test_a_finding_with_no_source_never_reaches_the_panel(self):
        from app.api.officer import grounded as officer_grounded

        assert not officer_grounded(
            {"jurisdiction": {"value": "Coimbatore City Municipal Corporation",
                              "sources": []}}).get("jurisdiction")

    def test_an_unofficial_source_does_not_count_as_evidence(self):
        from app.api.officer import grounded as officer_grounded

        blog = {"document_title": "A helpful blog", "authority": "unknown",
                "excerpt": "Theni Allinagaram Municipality covers Theni."}
        assert not officer_grounded(
            {"jurisdiction": {"value": "Theni Allinagaram Municipality",
                              "sources": [blog]}}).get("jurisdiction")

    def test_this_gate_checks_provenance_and_the_analyst_checks_content(self):
        """WHERE EACH CHECK LIVES, written down because the division is not
        obvious and guessing at it produces the wrong fix.

        `officer.grounded` asks whether a finding is backed by an OFFICIAL,
        QUOTED source. It does not re-check that the quote contains the value,
        and should not: `excerpt` is a short snippet of a longer passage, so a
        value that was properly grounded upstream can legitimately fall outside
        it, and re-checking here would drop real findings on a formatting
        accident.

        The content check is `analyst.grounded`, against the whole chunk, before
        the finding ever becomes a Finding. That is the test above.
        """
        from app.api.officer import grounded as officer_grounded

        official = {"document_title": "Local bodies directory",
                    "excerpt": "... covers the Theni and Allinagaram areas.",
                    "authority": "official"}
        kept = officer_grounded(
            {"jurisdiction": {"value": "Theni Allinagaram Municipality",
                              "sources": [official]}})
        assert kept.get("jurisdiction", {}).get("value") == (
            "Theni Allinagaram Municipality")
