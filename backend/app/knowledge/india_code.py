"""Parse India Code's Tamil Nadu collection into quarantine `Discovery` rows.

INDIA CODE IS A DSPACE INSTANCE. Each state collection has a `handle`
page listing items by title/year, each item has its own `handle` page
with metadata rows and a PDF link. The HTML is reasonably stable: items
are addressed by `/handle/123456789/XXXX`, metadata rows live in table
cells near the DOM root. This module reads that structure.

TWO ENTRY POINTS:

  `parse_collection_listing(html, base_url)`
      Reads a collection page and returns the item handles it lists.

  `parse_item_page(html, handle_url)`
      Reads an item's metadata page and returns a `Discovery` ready for
      the quarantine store.

Everything here is a PURE FUNCTION over HTML. The CLI
(`scripts/ingest_india_code_tn.py`) is the thing that actually hits the
network. These parsers are tested with HTML fixtures so a government
portal going down does not break the test suite.

WHAT THIS WILL NOT INFER. The amendment status, "current law" claim and
jurisdiction specifics are LEFT BLANK or marked UNKNOWN. The brief is
explicit: do not claim a document is current unless its current status
is verified. A curator sets `amendment_status` when they read the actual
Gazette or the India Code "Enforcement Date" column, not us.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse

from lxml import html

from .quarantine import Discovery

#: The TN state collection on India Code. Named here so the parser and the
#: CLI stay in sync; a future state would get its own module.
TN_COLLECTION_HANDLE = "/handle/123456789/2507"

#: Fallback classification. India Code's "Act" documents all land as `act`;
#: subordinate rules land as `rule`; everything else is UNKNOWN and the
#: curator decides. We never auto-promote a row with document_type=unknown
#: into the corpus — the quarantine schema enforces one of the DOCUMENT_TYPES.
_YEAR_RE = re.compile(r"\b(1[89]\d{2}|20\d{2}|21\d{2})\b")
_ACT_NO_RE = re.compile(
    r"(?:Act\s*(?:No\.?|Number)?\s*[:\-]?\s*)([A-Z]*\s*\d+[A-Z]*)\s*of\s*(\d{4})",
    re.IGNORECASE)


class ParseError(ValueError):
    """The HTML did not look like what the parser expected."""


# --------------------------------------------------------------------------- #
# Collection listing — the handle page that lists items.
# --------------------------------------------------------------------------- #

def parse_collection_listing(doc_html: str, base_url: str) -> list[str]:
    """Return the absolute URLs of items the listing links to.

    The listing is DSpace's "list items" view. Each `<a>` with an href like
    `/handle/123456789/XXXX` where XXXX is a different id from the
    collection's own is one item. The parser DEDUPES so a listing that
    repeats a title across columns does not inflate the discovery count.
    """
    tree = html.fromstring(doc_html)
    collection_id = _handle_tail(TN_COLLECTION_HANDLE)
    seen: list[str] = []
    for anchor in tree.xpath("//a[@href]"):
        href = anchor.get("href") or ""
        match = re.match(r"^(?:/)?handle/123456789/(\d+)(?:/.*)?$", href.strip("/"))
        if not match:
            continue
        if match.group(1) == collection_id:
            continue
        resolved = urljoin(base_url, "/handle/123456789/" + match.group(1))
        if resolved not in seen:
            seen.append(resolved)
    return seen


# --------------------------------------------------------------------------- #
# Item page — one Act's metadata.
# --------------------------------------------------------------------------- #

def parse_item_page(doc_html: str, handle_url: str) -> Discovery:
    """Read one item page into a Discovery.

    DSpace renders metadata EITHER as a `<meta name="DC.*">` block in the
    head OR as `<tr><td>Label</td><td>Value</td></tr>` in the body. Modern
    India Code uses both; we read both. Where the two disagree the body
    wins because it is what a curator looking at the page sees.
    """
    try:
        tree = html.fromstring(doc_html)
    except Exception as exc:  # noqa: BLE001
        raise ParseError(f"item page at {handle_url!r} is not HTML: {exc}") from exc
    meta = _read_dublin_core(tree)
    rows = _read_table_rows(tree)

    # A real item page has either DC.* metadata or body-table rows. A 200
    # response with an H1 saying "404 Not Found" and nothing else is one of
    # the broken-URL classes the brief flagged — refuse it rather than
    # inventing a document from its error page.
    if not meta and not rows:
        raise ParseError(
            f"item page at {handle_url!r} carries no metadata; "
            "cannot distinguish an Act from an error page")

    title = (rows.get("title")
             or meta.get("DC.title")
             or _text(tree, "//h2") or _text(tree, "//h1")
             or "").strip()
    if not title:
        raise ParseError(f"item page at {handle_url!r} carries no title")

    act_label = (rows.get("act no.")
                 or rows.get("act number")
                 or rows.get("short title and number")
                 or "")
    act_number, year_from_act = _read_act_number(act_label or title)

    year_raw = (rows.get("year") or rows.get("year of enactment")
                or meta.get("DC.date.issued") or "")
    year = _read_year(year_raw) or year_from_act

    publication_date = (rows.get("enactment date")
                        or rows.get("date of publication")
                        or meta.get("DC.date.issued") or "").strip() or None
    issuing_authority = (rows.get("ministry")
                         or rows.get("department")
                         or rows.get("state")
                         or "Tamil Nadu").strip()

    pdf_url = _find_pdf(tree, handle_url)

    return Discovery(
        source_id="indiacode-tn",
        official_url=handle_url,
        title=title,
        document_type=_guess_document_type(title, rows),
        source_tier="tier_2_repository",
        act_number=act_number,
        year=year,
        issuing_authority=issuing_authority,
        publication_date=publication_date,
        pdf_url=pdf_url,
        amendment_status="unknown",   # NEVER inferred — a curator fills this in
        extra={"dublin_core": meta, "detail_rows": rows} if (meta or rows) else {},
    )


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _handle_tail(handle: str) -> str:
    return handle.rstrip("/").rsplit("/", 1)[-1]


def _text(tree, xpath: str) -> str:
    for element in tree.xpath(xpath):
        if hasattr(element, "text_content"):
            text = element.text_content()
            if text and text.strip():
                return text.strip()
    return ""


def _read_dublin_core(tree) -> dict[str, str]:
    out: dict[str, str] = {}
    for meta in tree.xpath("//meta[@name and @content]"):
        name = (meta.get("name") or "").strip()
        if name.startswith("DC."):
            out.setdefault(name, (meta.get("content") or "").strip())
    return out


def _read_table_rows(tree) -> dict[str, str]:
    """Pairs of (label, value) from any 2-column tables on the page."""
    rows: dict[str, str] = {}
    for row in tree.xpath("//tr"):
        cells = row.xpath("./td|./th")
        if len(cells) < 2:
            continue
        label = (cells[0].text_content() or "").strip().rstrip(":").lower()
        value = (cells[1].text_content() or "").strip()
        if label and value and label not in rows:
            rows[label] = value
    return rows


def _read_act_number(label: str) -> tuple[str | None, int | None]:
    """Pull an "Act No. 5 of 1972" style tag out of free text."""
    if not label:
        return None, None
    match = _ACT_NO_RE.search(label)
    if not match:
        return None, None
    number, year_str = match.groups()
    return f"Act No. {number.strip()} of {year_str.strip()}", int(year_str)


def _read_year(raw: str) -> int | None:
    if not raw:
        return None
    match = _YEAR_RE.search(raw)
    return int(match.group(1)) if match else None


def _guess_document_type(title: str, rows: dict[str, str]) -> str:
    """A conservative mapper. The curator is the final word."""
    label = " ".join([title, rows.get("type", ""), rows.get("category", "")]).lower()
    # Order matters here. The Amendment check runs BEFORE Act because an
    # "Amendment Act" is still fundamentally an amendment for curator
    # purposes — the officer page relates them differently from a fresh
    # Act. The brief's rule 10 explicitly asks for amendment relationships
    # to be recoverable, which means they must land in quarantine as
    # `amendment`, not quietly as `act`.
    if "(amendment)" in label or "amendment act" in label or (
            "amendment" in label and rows.get("amends")):
        return "amendment"
    if "regulation" in label:
        return "regulation"
    if "ordinance" in label:
        return "ordinance"
    if "rules" in label or " rule " in label:
        return "rule"
    if "notification" in label:
        return "notification"
    if "government order" in label or "g.o." in label:
        return "government_order"
    # Default: items under the India Code TN state collection are Acts.
    return "act"


def _find_pdf(tree, base_url: str) -> str | None:
    """Pick the first PDF the item page links to.

    India Code item pages carry a "Files in This Item" block that
    contains the PDF; the href ends in `.pdf` and typically includes
    `/bitstream/` or `/retrieve`. We take the first PDF link in document
    order, which is reliably the Act itself; "Files" is below "Metadata"
    on every DSpace page we have seen.
    """
    for anchor in tree.xpath("//a[@href]"):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        if urlparse(href).path.lower().endswith(".pdf"):
            return urljoin(base_url, href)
    return None
