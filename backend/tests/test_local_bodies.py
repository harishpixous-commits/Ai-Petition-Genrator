"""The local-body directory, tested against the real government data.

THESE ARE REAL-DATA TESTS, not fixtures. They run against
`var/local_bodies.sqlite`, built by `scripts/build_directory.py` from the
Rural Development and Panchayat Raj Department's own published datasets —
12,525 village panchayats, 561 town panchayats, 388 blocks, 152
municipalities, 37 districts and 10 corporations.

They SKIP when that file has not been built, because a developer who has not
run the build has not got the data and a synthetic stand-in would prove
nothing about it. The skip says exactly which command to run.

WHAT IS BEING PROTECTED. A citizen acts on a jurisdiction answer by travelling
to an office. So the assertions that matter most here are the ones about
refusing: a shared name must never silently resolve to one of its claimants,
and a name that is not in the department's list must never be matched to
something that merely sounds like it.
"""

from __future__ import annotations

import pytest

from app.domain import local_bodies as lb

pytestmark = pytest.mark.skipif(
    not lb.available(),
    reason="the local-body directory has not been built — run "
           "`python scripts/build_directory.py` (it needs var/directory/*.raw, "
           "fetched from tnrd.tn.gov.in)")


class TestTheDataIsWhatTheDepartmentPublished:
    def test_every_kind_of_body_is_present(self):
        counts = lb.stats()
        for kind in ("village_panchayat", "town_panchayat", "block_panchayat",
                     "municipality", "municipal_corporation", "district"):
            assert counts.get(kind), f"no {kind} records"

    def test_the_counts_are_the_right_order_of_magnitude(self):
        """Tamil Nadu has roughly 12,500 village panchayats, ~500 town
        panchayats, ~390 blocks, ~140 municipalities and ~21 corporations.
        A build that silently dropped a file would show up here as a count
        that is an order of magnitude out, which no other test would catch.
        """
        counts = lb.stats()
        assert 12_000 <= counts["village_panchayat"] <= 13_500
        assert 400 <= counts["town_panchayat"] <= 700
        assert 350 <= counts["block_panchayat"] <= 420
        assert 100 <= counts["municipality"] <= 200
        assert 5 <= counts["municipal_corporation"] <= 30
        assert 30 <= counts["district"] <= 40

    def test_every_record_can_be_traced_to_a_government_file(self):
        """A jurisdiction finding has to be citable. A record with no source
        is a record nobody can check."""
        answer = lb.find("Chennai")
        assert answer.resolved
        assert answer.body.source_url.startswith("https://www.tnrd.tn.gov.in/")
        assert answer.body.source_dataset


class TestItAnswersWhenItCan:
    def test_a_corporation_is_found(self):
        answer = lb.find("Chennai")
        assert answer.resolved
        assert answer.body.body_type == "municipal_corporation"
        assert "Municipal Corporation" in answer.body.described()

    def test_a_tamil_name_finds_the_same_body(self):
        """The department publishes each list twice with identical LGD codes,
        so the Tamil name is joined by code and is exact — not transliterated.
        """
        english = lb.find("KANCHEEPURAM", body_type="block_panchayat")
        tamil = lb.find("காஞ்சிபுரம்", body_type="block_panchayat")
        assert english.resolved and tamil.resolved
        assert english.body.lgd_code == tamil.body.lgd_code

    def test_a_village_panchayat_carries_its_block(self):
        """Which panchayat union a village sits under is how an officer
        escalates, so it has to survive into the record."""
        found = [lb.find(name) for name in ("Angambakkam", "Arpaakkam")]
        resolved = [a for a in found if a.resolved]
        assert resolved, "neither known village resolved"
        assert resolved[0].body.parent


class TestItRefusesWhenItCannot:
    def test_a_name_shared_by_several_villages_is_never_resolved(self):
        """THE ONE THAT MATTERS. "Ganapathipalayam" is four different village
        panchayats across two districts, three of them inside Tiruppur alone.
        Returning any single one of them sends a citizen to the wrong office.
        """
        answer = lb.find("Ganapathipalayam")
        assert not answer.resolved
        assert answer.ambiguous
        assert len(answer.candidates) >= 3
        assert "share this name" in answer.reason

    def test_naming_the_district_does_not_force_an_answer(self):
        """Narrowing helps, and when it is not enough it must still refuse.
        Three of the four are in Tiruppur, so the district does not settle it.
        """
        answer = lb.find("Ganapathipalayam", district="TIRUPPUR")
        assert not answer.resolved
        assert answer.ambiguous

    def test_a_name_shared_across_body_types_is_ambiguous(self):
        """Oddanchatram is both a Panchayat Union and a Town Panchayat. They
        are different offices with different officers, and a petition sent to
        the wrong one is a wasted journey — the fact that it was the right
        TOWN is no help to the citizen."""
        answer = lb.find("Oddanchatram")
        assert not answer.resolved
        kinds = {c.body_type for c in answer.candidates}
        assert len(kinds) > 1, kinds

    def test_a_name_that_is_not_in_the_list_is_not_matched_to_a_near_one(self):
        """No fuzzy matching, on purpose. "Kulathur" and "Kulithalai" are
        different places, and an edit-distance match between them is a day's
        wages and a wasted journey."""
        for invented in ("Nowhere At All", "Kulathurr", "Chennaai",
                         "Ganapathipalayamm"):
            answer = lb.find(invented)
            assert not answer.resolved, f"{invented} matched {answer.body}"

    def test_an_empty_query_is_refused_quietly(self):
        for empty in ("", "   ", None):
            answer = lb.find(empty)
            assert not answer.resolved
            assert not answer.ambiguous


class TestADistrictIsNotALocalBody:
    def test_asking_for_a_district_does_not_return_a_corporation(self):
        """They share a name and are different rows with different
        responsibilities. Returning the corporation for a district query would
        answer a question the citizen did not ask."""
        answer = lb.find("KANCHEEPURAM", body_type="district")
        assert answer.resolved
        assert answer.body.body_type == "district"

    def test_the_district_list_is_the_states_own_spelling(self):
        names = lb.districts()
        assert 30 <= len(names) <= 40
        assert any("COIMBATORE" in n.upper() for n in names)
        assert any("MADURAI" in n.upper() for n in names)

    def test_chennai_is_absent_from_the_district_list_and_that_is_correct(self):
        """A REAL PROPERTY OF THE DATA, found by asserting the opposite first.

        These datasets come from the RURAL Development and Panchayat Raj
        Department, and they enumerate districts that contain village
        panchayats and blocks. Chennai district is entirely urban: it has
        neither. So it is in the corporation list and not in the district
        list, and that is the department being correct rather than the file
        being short.

        Written down because the next person to see 37 districts in a state
        with 38 will assume a parsing bug and go looking for one.
        """
        assert not any("CHENNAI" in n.upper() for n in lb.districts())
        assert lb.find("Chennai", body_type="municipal_corporation").resolved


class TestTheDescriptionAnOfficerReads:
    def test_it_names_the_kind_of_body_not_just_the_place(self):
        """"Chennai" is a district, a corporation and a city. "Chennai
        Municipal Corporation" is an office."""
        answer = lb.find("Chennai")
        assert answer.body.described().endswith("Municipal Corporation")

    def test_a_tamil_reader_gets_the_tamil_name_where_one_exists(self):
        answer = lb.find("KANCHEEPURAM", body_type="block_panchayat")
        described = answer.body.described("ta")
        assert answer.body.name_ta
        assert answer.body.name_ta in described


class TestAClaimedJurisdictionIsCheckedAgainstTheList:
    """THE GAP GROUNDING CANNOT CLOSE.

    The grounding check asks whether a value appears in a cited passage. That
    catches an invention made from nothing. It cannot catch one assembled from
    text that IS present: a passage naming Oddanchatram and a passage naming a
    municipality together ground "Oddanchatram Municipality" — grammatical,
    citable, and not a body that exists.

    The department publishes its own list, so this is checkable.
    """

    def test_a_real_body_is_confirmed(self):
        answer = lb.validate_claim("Oddanchatram Town Panchayat")
        assert answer.resolved
        assert answer.body.body_type == "town_panchayat"

    def test_the_right_place_with_a_body_that_does_not_exist_is_refused(self):
        """Oddanchatram has a Town Panchayat and a Panchayat Union. It has no
        municipality, so this claim is false even though the place is real and
        the words are all in the corpus somewhere."""
        answer = lb.validate_claim("Oddanchatram Municipality")
        assert not answer.resolved
        assert not answer.ambiguous

    def test_an_invented_place_is_refused(self):
        assert not lb.validate_claim("Imaginary Town Panchayat").resolved

    def test_a_longer_body_type_is_matched_before_a_shorter_one(self):
        """"Coimbatore City Municipal Corporation" must not be parsed as the
        place "Coimbatore City Municipal" plus the type "Corporation"."""
        answer = lb.validate_claim("Coimbatore City Municipal Corporation")
        assert answer.resolved
        assert answer.body.body_type == "municipal_corporation"

    def test_a_shared_name_is_reported_not_resolved(self):
        answer = lb.validate_claim("Ganapathipalayam Village Panchayat")
        assert not answer.resolved
        assert answer.ambiguous
        assert len(answer.candidates) >= 3


class TestTheOfficerPanelAppliesTheCheck:
    """The gate a human actually reads."""

    SOURCE = {"document_title": "Local bodies directory",
              "excerpt": "...", "authority": "official"}

    def _grounded(self, claim: str):
        from app.api.officer import grounded

        return grounded({"jurisdiction": {"value": claim,
                                          "sources": [self.SOURCE]}})

    def test_a_body_that_does_not_exist_never_reaches_an_officer(self):
        assert not self._grounded("Oddanchatram Municipality").get("jurisdiction")

    def test_a_real_body_is_kept_and_carries_its_lgd_code(self):
        finding = self._grounded("Oddanchatram Town Panchayat")["jurisdiction"]
        assert finding["directory"]["status"] == "confirmed"
        assert finding["directory"]["lgd_code"]
        assert finding["directory"]["source_url"].startswith("https://")

    def test_an_ambiguous_body_is_kept_but_flagged_for_a_human(self):
        """The place is real, so the finding is not thrown away — but the
        service must not choose between four identically named villages."""
        finding = self._grounded("Ganapathipalayam Village Panchayat")["jurisdiction"]
        assert finding["directory"]["status"] == "ambiguous"
        assert len(finding["directory"]["candidates"]) >= 3

    def test_other_findings_are_untouched_by_this_check(self):
        """Only jurisdiction is checked against the directory. A department or
        an Act has nothing to do with the local body list."""
        from app.api.officer import grounded

        out = grounded({"department": {"value": "Any Department At All",
                                       "sources": [self.SOURCE]}})
        assert out["department"]["value"] == "Any Department At All"
