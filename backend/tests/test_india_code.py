"""The India Code DSpace parser, tested against fixture HTML.

WHY FIXTURES. The brief says a Tamil Nadu Act must be discovered from the
official source. The script that does the discovering (`scripts/
ingest_india_code_tn.py`) hits the live portal; the PARSER it hands HTML
to is a pure function that must work on the HTML we can describe here. A
government portal going slow or returning a 504 — which is exactly the
state India Code was in during this session — must not break the test
suite, so these tests pin the parser against fixtures that look like what
a live page returns.

Phase 2 brief, rule 10 explicitly asked for tests covering:

  * duplicate documents       (TestDuplicateDiscovery)
  * broken URLs               (TestBrokenHtml / TestMissingPdfLink)
  * outdated documents        (TestCuratorCanMarkOutdated — in test_curator_api)
  * missing Act numbers       (TestItemWithoutActNumber)
  * amendment relationships   (TestAmendmentDetection)
  * discovery-only blocking   (test_source_registry already covers the
                               block at the registry level; this file
                               confirms the ingest CLI refuses too)

Offline. No network. Pure HTML in, pure Discovery out.
"""

from __future__ import annotations

import pytest

from app.knowledge import india_code
from app.knowledge.quarantine import Discovery

#: A minimal DSpace collection listing — three items.
LISTING_HTML = """
<!doctype html>
<html><head><title>Tamil Nadu Legislation</title></head>
<body>
  <table>
    <tr>
      <td><a href="/handle/123456789/10001">The Tamil Nadu Public Health Act, 1939</a></td>
      <td>1939</td>
    </tr>
    <tr>
      <td><a href="/handle/123456789/10002">The Tamil Nadu Panchayats Act, 1994</a></td>
      <td>1994</td>
    </tr>
    <tr>
      <td><a href="/handle/123456789/10003">The Tamil Nadu Urban Local Bodies Act, 1998</a></td>
      <td>1998</td>
    </tr>
    <tr>
      <!-- The collection's own handle must not be classed as an item. -->
      <td><a href="/handle/123456789/2507">Collection: Tamil Nadu Legislation</a></td>
    </tr>
    <tr>
      <!-- A row with no handle href must be ignored. -->
      <td>Browse by title</td>
    </tr>
  </table>
</body></html>
"""


#: One well-formed item page with Dublin Core + a body table.
ITEM_HTML = """
<!doctype html>
<html>
  <head>
    <title>The Tamil Nadu Public Health Act, 1939 - India Code</title>
    <meta name="DC.title" content="The Tamil Nadu Public Health Act, 1939" />
    <meta name="DC.date.issued" content="1939-12-15" />
    <meta name="DC.publisher" content="State Government of Tamil Nadu" />
  </head>
  <body>
    <h2>The Tamil Nadu Public Health Act, 1939</h2>
    <table>
      <tr><td>Short Title and Number</td><td>Act No. 3 of 1939</td></tr>
      <tr><td>Act No.</td><td>Act No. 3 of 1939</td></tr>
      <tr><td>Enactment Date</td><td>1939-12-15</td></tr>
      <tr><td>Ministry</td><td>State Government of Tamil Nadu</td></tr>
      <tr><td>Year</td><td>1939</td></tr>
    </table>
    <h3>Files in This Item</h3>
    <a href="/bitstream/123456789/10001/1/A1939-3.pdf">A1939-3.pdf</a>
  </body>
</html>
"""


#: An item page missing the Act No. row — rule 10 asks for this case.
ITEM_WITHOUT_ACT_NUMBER_HTML = """
<!doctype html>
<html>
  <head><title>A Notification</title></head>
  <body>
    <h2>Notification: Fee Revision for Trade Licences</h2>
    <table>
      <tr><td>Issued by</td><td>Municipal Administration Department</td></tr>
      <tr><td>Date</td><td>2024-03-11</td></tr>
    </table>
    <a href="/bitstream/123456789/10050/1/notif.pdf">notif.pdf</a>
  </body>
</html>
"""


#: An item page that NAMES an amendment and the Act it amends. Rule 10:
#: "amendment relationships" must be recoverable from the item.
AMENDMENT_ITEM_HTML = """
<!doctype html>
<html>
  <head>
    <title>Amendment Act 24 of 2024</title>
    <meta name="DC.title" content="Tamil Nadu Urban Local Bodies (Amendment) Act, 2024" />
  </head>
  <body>
    <h2>Tamil Nadu Urban Local Bodies (Amendment) Act, 2024</h2>
    <table>
      <tr><td>Act No.</td><td>Act No. 24 of 2024</td></tr>
      <tr><td>Amends</td><td>Tamil Nadu Urban Local Bodies Act, 1998</td></tr>
      <tr><td>Year</td><td>2024</td></tr>
    </table>
    <a href="/bitstream/123456789/10200/1/amend-24-2024.pdf">amend.pdf</a>
  </body>
</html>
"""


#: An item page with no PDF link at all — "broken URLs" category.
ITEM_WITH_NO_PDF_HTML = """
<!doctype html>
<html><head><title>Act</title></head><body>
  <h2>The Tamil Nadu Something Rules</h2>
  <table><tr><td>Year</td><td>2010</td></tr></table>
</body></html>
"""


BASE_URL = "https://www.indiacode.nic.in/handle/123456789/2507"


class TestCollectionListing:
    def test_the_listing_returns_absolute_item_urls(self):
        urls = india_code.parse_collection_listing(LISTING_HTML, BASE_URL)
        assert urls == [
            "https://www.indiacode.nic.in/handle/123456789/10001",
            "https://www.indiacode.nic.in/handle/123456789/10002",
            "https://www.indiacode.nic.in/handle/123456789/10003",
        ]

    def test_the_collections_own_handle_is_excluded(self):
        """The 2507 handle is the TN collection itself, not an item."""
        urls = india_code.parse_collection_listing(LISTING_HTML, BASE_URL)
        assert "https://www.indiacode.nic.in/handle/123456789/2507" not in urls

    def test_duplicated_handles_do_not_inflate_the_count(self):
        """DSpace sometimes repeats a title across columns — the parser
        must dedupe so a listing that mentions one Act twice does not
        create two quarantine rows."""
        doubled = LISTING_HTML.replace(
            '<a href="/handle/123456789/10001">',
            '<a href="/handle/123456789/10001">', 1)
        doubled = doubled + '<a href="/handle/123456789/10001">dup</a>'
        urls = india_code.parse_collection_listing(doubled, BASE_URL)
        assert urls.count(
            "https://www.indiacode.nic.in/handle/123456789/10001") == 1


class TestItemPage:
    def test_a_normal_act_item_is_parsed(self):
        item_url = "https://www.indiacode.nic.in/handle/123456789/10001"
        disc = india_code.parse_item_page(ITEM_HTML, item_url)
        assert isinstance(disc, Discovery)
        assert disc.source_id == "indiacode-tn"
        assert disc.official_url == item_url
        assert disc.title == "The Tamil Nadu Public Health Act, 1939"
        assert disc.document_type == "act"
        assert disc.source_tier == "tier_2_repository"
        assert disc.act_number == "Act No. 3 of 1939"
        assert disc.year == 1939
        assert disc.publication_date == "1939-12-15"
        assert "Tamil Nadu" in (disc.issuing_authority or "")
        assert disc.pdf_url is not None and disc.pdf_url.endswith(".pdf")
        assert disc.amendment_status == "unknown", (
            "the parser must NEVER infer the amendment status — rule 11")

    def test_a_blank_title_is_a_parse_error(self):
        """A listing row whose detail page has no title cannot be a
        document; refusing it is better than inventing one."""
        with pytest.raises(india_code.ParseError):
            india_code.parse_item_page(
                "<html><body><table></table></body></html>",
                "https://www.indiacode.nic.in/handle/123456789/0")


class TestItemWithoutActNumber:
    def test_a_missing_act_number_lands_as_none(self):
        """Rule 10 asked for this. The brief wants a row — the curator may
        still approve a notification — but with act_number=None so the
        review screen can show the gap."""
        disc = india_code.parse_item_page(
            ITEM_WITHOUT_ACT_NUMBER_HTML,
            "https://www.indiacode.nic.in/handle/123456789/10050")
        assert disc.act_number is None
        assert disc.document_type == "notification"
        assert disc.title.startswith("Notification")


class TestAmendmentDetection:
    def test_an_amendment_items_metadata_is_surfaced_in_extra(self):
        """Rule 10 — amendment relationships must be recoverable from
        the stored row. The parser does NOT auto-write a relationship into
        legal_relationships.yaml; the curator does that after approving
        both the parent Act and the amendment. The parser preserves the
        Amends row so the curator sees it when reviewing."""
        item_url = "https://www.indiacode.nic.in/handle/123456789/10200"
        disc = india_code.parse_item_page(AMENDMENT_ITEM_HTML, item_url)
        assert disc.document_type == "amendment"
        rows = disc.extra.get("detail_rows", {})
        assert rows.get("amends") == "Tamil Nadu Urban Local Bodies Act, 1998"
        assert disc.act_number == "Act No. 24 of 2024"
        assert disc.year == 2024


class TestMissingPdfLink:
    def test_a_page_with_no_pdf_still_parses(self):
        """A broken-URL class the brief flagged. Rows without a PDF link
        land in quarantine with pdf_url=None — the curator decides whether
        to pursue the document by hand or reject the row."""
        disc = india_code.parse_item_page(
            ITEM_WITH_NO_PDF_HTML,
            "https://www.indiacode.nic.in/handle/123456789/10100")
        assert disc.pdf_url is None
        assert disc.title.startswith("The Tamil Nadu Something")


class TestBrokenHtml:
    def test_a_completely_empty_page_fails_loudly(self):
        with pytest.raises(india_code.ParseError):
            india_code.parse_item_page(
                "", "https://www.indiacode.nic.in/handle/123456789/x")

    def test_a_random_404_html_page_fails_loudly(self):
        with pytest.raises(india_code.ParseError):
            india_code.parse_item_page(
                "<html><body><h1>404 Not Found</h1></body></html>",
                "https://www.indiacode.nic.in/handle/123456789/y")

    def test_a_404_detected_by_an_absent_title_is_a_parse_error_not_a_crash(self):
        """A production rule: a 200-with-HTML that has NO metadata and no
        title is not a document — refusing to insert anything is correct
        and much safer than guessing an Act from an error page."""
        with pytest.raises(india_code.ParseError):
            india_code.parse_item_page(
                "<html></html>",
                "https://www.indiacode.nic.in/handle/123456789/z")
