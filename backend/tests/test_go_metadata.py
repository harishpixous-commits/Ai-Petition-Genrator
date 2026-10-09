"""Reading a Government Order's own header, not the orders it cites.

FOUND ON A REAL DOCUMENT. G.O.(Ms) No.208 dated 02.09.2010 — Oddanchatram Town
Panchayat reclassified as a Second Grade Municipality, downloaded from
www.tn.gov.in — was indexed as belonging to the "Supply (Election) Department"
and dated 14.07.2006. Both of those belong to a different, older order that
this one cites in its opening "Read:" list, which is how every Government Order
begins.

The fixtures below reproduce the SHAPE of that page rather than quoting it: a
reference list first, then a header the scan has run together. They are written
here, not copied, and no real G.O. text is stored in this repository.

WHY THESE ASSERTIONS ARE MOSTLY NEGATIVE. The expensive outcome is not a
missing department, it is a confident wrong one. An officer who sees no
department goes and looks it up; an officer who sees the wrong department has
no reason to.
"""

from __future__ import annotations

from app.knowledge.ingest import detect_metadata

# A Government Order as a scanner renders it: the citation list comes first,
# the issuing header is run together without a space, and the section code
# carries a digit.
SCANNED_ORDER = """,
ABSTRACT
Town Panchayat - Ondipudur Town Panchayat, Example District - Classified
as Second Grade Municipality - Ordered - Notification - Issued.
------------------------------------------------------------------------
Municipal Administration &Water Supply (M.A.5)Department
~
. ~G.O.(Ms) No.208 (.., I ~ Dated:O~.09.2010>;':~'
Read:
\\ Supply (Election) Department, dated 14.07.2006.
,.,./ ,// Water Supply Department, dated 02.12.2008.
:: Na.Ka.No.2371/2006/T.P.2. dated 26.7.2006
ORDER:
Under section 4 of the Tamil Nadu District Municipalities Act, 1920
(Tamil Nadu Act V of 1920), the State Government may classify a town.
To
The Finance Department, Chennai-9
The Law Department, Chennai-9
"""

# The same order, but with a date the scan did not mangle.
CLEAN_ORDER = """ABSTRACT
Water Supply - Drinking water - Instructions - Issued.
Municipal Administration and Water Supply (MA1) Department
G.O.(Ms) No.123 Dated: 02.09.2010
Read:
Revenue (LA) Department, dated 14.07.2006.
ORDER:
Under the Tamil Nadu Urban Local Bodies Act, 1998 the following is ordered.
"""


class TestTheIssuingOfficeIsNotTheCitedOne:
    def test_the_department_is_read_from_the_header(self):
        """The exact failure: "Supply (Election) Department" is the FIRST
        department named on the page, and it belongs to a 2006 order."""
        found = detect_metadata(SCANNED_ORDER)
        department = found.get("department", "")
        assert "Election" not in department, (
            f"read the cited order's department: {department!r}")
        assert "Municipal Administration" in department, department

    def test_a_header_run_together_by_a_scan_is_still_read(self):
        """"(M.A.5)Department" has no space before "Department" and a digit
        inside the section code. Requiring a space, or forbidding the digit,
        made the issuing office invisible and let a citation win by default."""
        found = detect_metadata(SCANNED_ORDER)
        assert found.get("department"), "the run-together header matched nothing"

    def test_the_department_does_not_run_across_a_line_break(self):
        """The line above the header is a rule of dashes. A pattern that
        crosses the newline swallows it and files the petition under a
        department whose name begins "Issued.------"."""
        department = detect_metadata(SCANNED_ORDER).get("department", "")
        assert "\n" not in department, repr(department)
        assert "---" not in department, repr(department)
        assert department.startswith("Municipal"), repr(department)

    def test_a_distribution_list_is_not_the_issuing_office(self):
        """"The Finance Department, Chennai-9" is who gets a copy."""
        department = detect_metadata(SCANNED_ORDER).get("department", "")
        assert "Finance" not in department, department
        assert "Law" not in department, department


#: The other header format, and the one that makes this delicate: number,
#: department and date all on ONE line, carrying ", dated" exactly as a
#: citation does.
ONE_LINE_HEADER = (
    "G.O. (Ms) No. 145, Revenue and Disaster Management Department, "
    "dated 03.07.2021. Under the Tamil Nadu Land Encroachment Act, 1905 ...")


class TestTheTwoHeaderFormatsBothWork:
    """A rule that fixes one of these breaks the other if it is written
    carelessly, which is what happened: filtering every line containing
    ", dated" removed the citation AND the single-line header with it.
    """

    def test_a_single_line_header_is_read_despite_saying_dated(self):
        found = detect_metadata(ONE_LINE_HEADER)
        assert found["department"] == "Revenue and Disaster Management Department"
        assert found["government_order_number"] == "145"
        assert found["date"] == "2021-07-03"

    def test_a_connector_word_does_not_truncate_the_name(self):
        """"Revenue and Disaster Management Department" — the lowercase "and"
        broke the chain of capitalised words and the name was read as
        "Disaster Management Department", quietly dropping the department that
        actually issued it."""
        department = detect_metadata(ONE_LINE_HEADER)["department"]
        assert department.startswith("Revenue"), department

    def test_both_formats_still_exclude_the_cited_order(self):
        """Whichever shape the header takes, the "Read:" list is never it."""
        assert "Election" not in detect_metadata(SCANNED_ORDER)["department"]
        assert "Revenue" not in detect_metadata(CLEAN_ORDER)["department"]


class TestTheDate:
    def test_a_cited_order_s_date_is_never_used(self):
        """THE ONE THAT MATTERS. The order is from 2010 and cites one from
        2006. Recording 2006 puts a four-year-old date on a current order."""
        found = detect_metadata(SCANNED_ORDER)
        assert found.get("date") != "2006-07-14", (
            "took the date off the order being cited")
        assert not str(found.get("date", "")).startswith("2006"), found.get("date")

    def test_an_unreadable_date_is_left_out_rather_than_guessed(self):
        """The scan rendered it "Dated:O~.09.2010", which is not a date. No
        date is a question an officer can resolve; a wrong one is not."""
        assert "date" not in detect_metadata(SCANNED_ORDER)

    def test_a_readable_date_on_the_order_line_is_used(self):
        """The fallback must not be so cautious that it never reads anything."""
        assert detect_metadata(CLEAN_ORDER).get("date") == "2010-09-02"


class TestWhatWasAlreadyWorkingStillWorks:
    def test_the_act_and_order_number_are_still_read(self):
        found = detect_metadata(SCANNED_ORDER)
        assert found["government_order_number"] == "208"
        assert found["document_type"] == "government_order"
        assert "District Municipalities Act, 1920" in found["act_name"]

    def test_a_clean_order_reads_completely(self):
        found = detect_metadata(CLEAN_ORDER)
        assert found["government_order_number"] == "123"
        assert "Municipal Administration" in found["department"]
        assert "Election" not in found["department"]
        assert "Revenue" not in found["department"]
        assert "Urban Local Bodies Act, 1998" in found["act_name"]
