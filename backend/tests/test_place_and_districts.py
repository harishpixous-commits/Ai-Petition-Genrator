"""Where a petition says it was signed.

The petition carries "Place:" at its foot and the citizen is never asked for it
separately, so it is read off the address they did give. That was done by
splitting on commas and keeping the last piece, which is right for

    12 Gandhi Street, Peelamedu, Coimbatore

and wrong the moment somebody writes the pieces in another order. A street is
not a place and a state is not a town, and both were being printed.

THE RULE THESE TESTS HOLD is the one the letter builder already states: a wrong
town on a petition is worse than a missing one. So most of what follows checks
that nothing is printed rather than that something pretty is.
"""

from __future__ import annotations

import pytest

from app.domain.districts import DISTRICTS, canonical, detect_district, is_place
from app.domain.fields import validate_district
from app.domain.letter import derive_place


class TestAStreetIsNotAPlace:
    """Every one of these printed a wrong Place line before."""

    @pytest.mark.parametrize("address", [
        "80/33, perumal kovil street",
        "14 North Street, near the temple",
        "5 Main Road, opposite bus stand",
        "Door No 7, 2nd Cross",
        "12 Gandhi Street, behind the school",
        "4 First Floor, new colony",
    ])
    def test_nothing_is_printed_when_no_piece_is_a_town(self, address):
        assert derive_place(address) == "", (
            f"{address!r} put {derive_place(address)!r} on the petition")

    def test_a_state_is_passed_over_for_the_town_behind_it(self):
        """"Place: Tamil Nadu" is not where anything was signed."""
        assert derive_place("80/33 perumal kovil street, theni, tamil nadu") == "theni"


class TestTheTownIsFound:
    @pytest.mark.parametrize("address,expected", [
        ("80/33 perumal kovil street, theni", "theni"),
        ("12 Gandhi Street, Peelamedu, Coimbatore - 641004", "Coimbatore"),
        ("12 Mount Road, Chennai 600002", "Chennai"),
        ("7 Anna Salai, Madras", "Madras"),
        ("5 Main Road, Erode", "Erode"),
    ])
    def test_it_reads_the_place_off_the_address(self, address, expected):
        assert derive_place(address) == expected

    @pytest.mark.parametrize("address,expected", [
        ("4 Big Street, Trichy Dist", "Trichy"),
        ("9 East St, Theni District", "Theni"),
        ("2 Bazaar Street, Salem Dt", "Salem"),
    ])
    def test_an_administrative_label_is_dropped(self, address, expected):
        """"Theni Dist" is a town with a label after it, the same way
        "Chennai 600002" is a town with a pin after it — and the pin was
        already being dropped."""
        assert derive_place(address) == expected

    def test_the_citizens_own_spelling_is_what_is_printed(self):
        """The list is there to RECOGNISE a town, not to correct anybody.

        Somebody who writes Madras gets Madras on their petition. The entry
        exists so the line is not dropped.
        """
        assert derive_place("7 Anna Salai, Madras") == "Madras"
        assert derive_place("4 Big Street, trichy") == "trichy"

    @pytest.mark.parametrize("address,expected", [
        ("12 காந்தி தெரு, பீளமேடு, கோயம்புத்தூர்", "கோயம்புத்தூர்"),
        ("80/33 பெருமாள் கோவில் தெரு, தேனி", "தேனி"),
    ])
    def test_an_address_written_in_tamil_works_too(self, address, expected):
        assert derive_place(address) == expected


class TestTheDistrictList:
    def test_all_thirty_eight_are_there(self):
        assert len(DISTRICTS) == 38
        assert len(set(DISTRICTS)) == 38, "a district is listed twice"

    @pytest.mark.parametrize("district", DISTRICTS)
    def test_each_one_is_recognised_as_a_place(self, district):
        assert is_place(district), district
        assert canonical(district) == district

    @pytest.mark.parametrize("alias,district", [
        ("trichy", "Tiruchirappalli"),
        ("Madras", "Chennai"),
        ("ooty", "Nilgiris"),
        ("nagercoil", "Kanyakumari"),
        ("tanjore", "Thanjavur"),
        ("tuticorin", "Thoothukudi"),
        ("kanchipuram", "Kancheepuram"),
    ])
    def test_an_older_name_resolves_to_its_district(self, alias, district):
        """An officer filtering for Tiruchirappalli must find the petitions
        whose citizens wrote Trichy."""
        assert canonical(alias) == district

    @pytest.mark.parametrize("word", [
        "main road", "perumal kovil street", "near the temple",
        "2nd cross", "opposite bus stand", "tamil nadu", "india",
    ])
    def test_an_ordinary_address_word_is_not_a_place(self, word):
        assert not is_place(word), word


class TestTheValidatorDoesNotRefuseRealDistricts:
    """Deliberately not a whitelist.

    A citizen naming a district this service has not heard of — a neighbouring
    state's, a new one, a spelling nobody listed — is telling the truth about
    where they live. Refusing them because a table is short is the wrong
    answer, so the list canonicalises what it knows and gets out of the way.
    """

    def test_a_known_district_is_recorded_in_the_states_spelling(self):
        result = validate_district("trichy")
        assert result.ok and result.value == "Tiruchirappalli"

    def test_an_unknown_one_is_still_accepted(self):
        for name in ("Bengaluru", "Ernakulam", "Somewhere Nobody Listed"):
            assert validate_district(name).ok, name

    def test_what_was_already_refused_is_still_refused(self):
        assert not validate_district("").ok
        assert not validate_district("District 9").ok
        assert not validate_district("x" * 61).ok


# ---------------------------------------------------------------------------
# District detection — a new helper added 2026-10-22 so the "To" address
# on the petition can read "Theni District, Tamil Nadu." instead of a bare
# "District Collectorate" with no district named.
# ---------------------------------------------------------------------------

class TestDetectDistrict:
    def test_a_citizen_who_wrote_the_district_name_at_the_end_is_recognised(self):
        assert detect_district("80/33 perumal kovil street, theni") == "Theni"
        assert detect_district("12 Gandhi Street, Peelamedu, Coimbatore") == "Coimbatore"

    def test_a_citizen_who_used_an_alias_is_mapped_to_the_official_name(self):
        """A letter must address the Collectorate the state actually names,
        not the citizen's older spelling of it."""
        assert detect_district("5 Mount Road, Madras 600002") == "Chennai"
        assert detect_district("12 Rockfort, Trichy") == "Tiruchirappalli"
        assert detect_district("Nellai town") == "Tirunelveli"

    def test_a_district_name_without_commas_is_still_found(self):
        """A citizen may write the address in one line without punctuation."""
        assert detect_district("80/33 Perumal Kovil Street Theni") == "Theni"

    def test_an_address_with_no_matching_district_returns_empty(self):
        """If detection fails the caller leaves the line out rather than
        guessing — a wrong Collectorate on a petition routes it wrong."""
        assert detect_district("") == ""
        assert detect_district("some random street name") == ""

    def test_a_street_named_after_a_town_is_not_mistaken_for_the_town(self):
        """`is_place` matches whole pieces, not words inside them — a
        petition from "Perumal Kovil Street" must not route to Perumal
        Kovil District (which doesn't exist anyway)."""
        assert detect_district("Perumal Kovil Street") == ""
