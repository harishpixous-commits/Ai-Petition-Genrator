"""The citizen can see that their attachment is actually attached.

THE REPORT THIS COMES FROM, and it was a fair one:

    "i attached attachement but it not attached there only showing text
     only enclosure and petititon number"

The attachment WAS attached. Measured on the session in question: a two-page
letter plus a two-page enclosure produced a four-page document, the enclosure
index on page three and the attached pages carried as images behind it. The
package PDF carries the originals with their text layer intact.

But none of that was visible. The preview drew `letter_text` and nothing
else, so the only trace of an attached file was the line the letter itself
prints — "Enclosures: 1. Copy of earlier petition" — and the only way to find
out whether the file had gone anywhere was to download the document and open
it. Somebody standing at a counter cannot do that.

So the defect was real and it was in the preview, not the pipeline. These
tests cover the three things that had to become true:

    the page can fetch the citizen's own file, and only their own
    the view says how many pages it will add
    the preview draws it, and printing does not
"""

from __future__ import annotations

import pathlib
import tempfile

import pymupdf
import pytest

from app.api.views import _page_count, attachments_view
from app.domain.attachments import Attachment, AttachmentSet
from app.services import attachment_store


@pytest.fixture
def session(monkeypatch):
    """A session directory with one two-page PDF in it."""
    with tempfile.TemporaryDirectory(prefix="enclosure-") as directory:
        root = pathlib.Path(directory)
        monkeypatch.setattr(attachment_store, "session_dir",
                            lambda sid, settings=None: root)
        document = pymupdf.open()
        for n in (1, 2):
            document.new_page().insert_text((72, 100), f"page {n}", fontsize=14)
        document.save(str(root / "stored.pdf"))
        document.close()
        yield root


def an_attachment(**kwargs):
    base = dict(attachment_id="a1", filename="earlier-petition.pdf",
                stored_name="stored.pdf", content_type="application/pdf",
                size=2048, kind="previous_petition", confirmed=True)
    base.update(kwargs)
    return Attachment(**base)


def view_for(attachment, session_id="s1"):
    state = {"session_id": session_id, "status": "ready", "language": "en",
             "fields": {}, "attachments": AttachmentSet(items=[attachment]).as_state()}
    return attachments_view(state, "en", None)


# ---------------------------------------------------------------------------
# How many pages, and where to get them
# ---------------------------------------------------------------------------

class TestTheViewSaysWhatIsAttached:

    def test_it_counts_the_pages_of_a_pdf(self, session):
        """The count is the part that answers the citizen's question. It is
        read from the file rather than guessed, because they will check it
        against the paper in their hand."""
        assert _page_count(an_attachment(), "s1") == 2

    def test_a_photograph_is_one_page(self, session):
        assert _page_count(an_attachment(content_type="image/png"), "s1") == 1

    def test_an_unreadable_file_reports_nothing_rather_than_guessing(self, session):
        """A wrong count is worse than no count. The page shows nothing."""
        broken = an_attachment(stored_name="not-there.pdf")
        assert _page_count(broken, "s1") == 0

    def test_a_corrupt_pdf_does_not_cost_the_citizen_their_petition(self, session):
        (session / "broken.pdf").write_bytes(b"%PDF-1.4 not really a pdf")
        assert _page_count(an_attachment(stored_name="broken.pdf"), "s1") == 0

    def test_the_view_carries_the_count_and_a_way_to_fetch_the_file(self, session):
        item = view_for(an_attachment())["items"][0]

        assert item["pages"] == 2
        assert item["content_type"] == "application/pdf"
        assert item["file_url"] == "/api/sessions/s1/attachments/a1/file"

    def test_the_url_is_scoped_to_the_session_that_owns_it(self, session):
        item = view_for(an_attachment(), session_id="other-session")["items"][0]
        assert item["file_url"].startswith("/api/sessions/other-session/")


# ---------------------------------------------------------------------------
# The endpoint
# ---------------------------------------------------------------------------

class TestFetchingTheFile:

    def test_the_route_exists_and_is_a_get(self):
        from app.api.rest import router

        paths = {r.path: r.methods for r in router.routes if hasattr(r, "path")}
        route = "/api/sessions/{session_id}/attachments/{attachment_id}/file"
        assert route in paths
        assert "GET" in paths[route]

    def test_it_resolves_the_session_the_same_way_every_other_route_does(self):
        """The guard is `_require_state`, which is what scopes every session
        route in this file. An attachment may carry an Aadhaar card, so this
        must not be the one endpoint that reaches across sessions."""
        import inspect

        from app.api import rest

        source = inspect.getsource(rest.attachment_file)
        assert "_require_state" in source
        assert "session_context" in source

    def test_it_is_served_sandboxed_and_never_cached(self):
        import inspect

        from app.api import rest

        source = inspect.getsource(rest.attachment_file)
        assert "no-store" in source
        assert "sandbox" in source

    def test_an_attachment_from_another_petition_is_not_found(self, session):
        """The lookup goes through the session's own attachment set, so an
        id that is not on this petition cannot be fetched by guessing it."""
        enclosed = AttachmentSet(items=[an_attachment()])
        assert enclosed.get("a1") is not None
        assert enclosed.get("somebody-elses-id") is None


# ---------------------------------------------------------------------------
# The preview
# ---------------------------------------------------------------------------

class TestTheTwoDownloadsAreDifferentThings:
    """The petition on its own, and the petition with the originals behind
    it. They used to be one file with a checkbox."""

    @pytest.fixture
    def script(self):
        return (pathlib.Path(__file__).resolve().parent.parent
                / "app" / "static" / "app.js").read_text(encoding="utf-8")

    def test_the_plain_downloads_carry_the_petition_alone(self, script):
        """`?enclosures=0`, always. The alternative appended the
        attachments RASTERISED — pictures of pages, twelve per file, no text
        layer — which is a worse package offered beside the real one."""
        assert 'const form = (url) => (url ? `${url}?enclosures=0` : url);' in script

    def test_the_package_link_does_not_depend_on_the_pdf_having_converted(self, script):
        """It was built by rewriting `pdf_url`, so while the PDF was still
        converting the link came out empty and the button vanished — taking
        with it the only download that carries the citizen's documents."""
        assert "v.session_id" in script
        assert "/document/package.pdf" in script
        # The old derivation must not come back.
        assert 'doc.pdf_url.replace(/\\/document\\.pdf' not in script

    def test_the_button_still_hides_when_nothing_is_attached(self, script):
        """With no attachments the package and the letter are the same file
        and the choice would be a control that does nothing."""
        assert "enclosedCount === 0" in script


class TestThePackageEndpoint:

    def test_it_no_longer_requires_the_ordinary_pdf_to_exist(self):
        """It renders the letter itself from `letter_text`, so gating on a
        file it does not use refused the package exactly when the main
        conversion was slow — which is when somebody is at a counter
        pressing the button again."""
        import inspect

        from app.api import rest

        # The guard moved into `_package_for` when the build was extracted
        # so the page renderer could share it. Same rule, one place.
        source = inspect.getsource(rest._package_for)
        assert 'document.get("docx")' in source
        assert 'not document.get("pdf")' not in source

    def test_it_builds_the_letter_from_the_text_not_the_generated_pdf(self):
        import inspect

        from app.api import rest

        source = inspect.getsource(rest._build_package)
        assert "_letter_only(state, \"pdf\")" in source

    def test_a_conversion_failure_says_so_rather_than_pretending(self):
        """"Do not pretend it was merged if it was not." A server with no
        PDF engine cannot build a combined package, and says which files are
        still available instead of returning a petition without them."""
        import inspect

        from app.api import rest

        source = inspect.getsource(rest._build_package)
        assert "503" in source
        assert "still available" in source


class TestThePreviewShowsIt:

    @pytest.fixture
    def script(self):
        return (pathlib.Path(__file__).resolve().parent.parent
                / "app" / "static" / "app.js").read_text(encoding="utf-8")

    def test_there_is_a_renderer_and_it_is_called(self, script):
        assert "function drawEnclosures(" in script
        assert "drawEnclosures(v.attachments)" in script

    def test_it_shows_the_page_count(self, script):
        assert "item.pages" in script
        assert "onePage" in script and "manyPages" in script

    def test_it_renders_the_file_itself_not_just_its_name(self, script):
        """A filename is another claim. The file is the evidence."""
        assert "item.file_url" in script
        # A photograph is rendered inline: one cheap request, and a citizen
        # recognises their own photograph instantly.
        assert 'createElement("img")' in script
        # A PDF is NOT embedded. It may be a hundred pages, and Chromium's
        # PDF plugin re-issued its own request every time it was, which
        # showed up as aborted fetches in the browser. It gets a card and a
        # View action that opens it in its own tab.
        assert 'createElement("iframe")' not in script

    def test_an_unreadable_attachment_still_says_it_is_attached(self, script):
        """The citizen brought it for a reason. A file this service could
        not parse is still going to the office with them."""
        assert "enclosureUnreadable" in script

    def test_both_languages_have_the_strings(self, script):
        for key in ("enclosuresHeading", "onePage", "manyPages",
                    "enclosureIncluded", "enclosureUnreadable"):
            assert script.count(f"{key}:") >= 2, f"{key} is missing a translation"

    def test_the_tamil_strings_are_in_tamil(self, script):
        line = next(l for l in script.splitlines() if "enclosuresHeading:" in l
                    and any("஀" <= c <= "௿" for c in l))
        assert line

    def test_the_container_exists_on_the_page(self):
        page = (pathlib.Path(__file__).resolve().parent.parent
                / "app" / "static" / "index.html").read_text(encoding="utf-8")
        assert 'id="enclosures"' in page
        # Inside the same table cell as the letter, so the print gutters
        # that `thead`/`tfoot` provide still apply to the sheet.
        assert 'id="letter"' in page
        assert page.index('id="letter"') < page.index('id="enclosures"')

    def test_it_is_not_printed(self):
        """Printing it would put a framed screenshot of the attachment in
        the middle of a government letter. The downloaded document carries
        the real pages, and the package PDF carries the originals."""
        css = (pathlib.Path(__file__).resolve().parent.parent
               / "app" / "static" / "app.css").read_text(encoding="utf-8")
        printed = css[css.index("@media print"):]
        assert ".enclosures{display:none!important}" in printed


# ---------------------------------------------------------------------------
# Module 2.1 — the continuous package preview
# ---------------------------------------------------------------------------

class TestTheContinuousPreview:
    """The centre shows the package as one document, not a card about one."""

    @pytest.fixture
    def script(self):
        return (pathlib.Path(__file__).resolve().parent.parent
                / "app" / "static" / "app.js").read_text(encoding="utf-8")

    def test_the_page_endpoints_exist(self):
        from app.api.rest import router

        paths = {r.path for r in router.routes if hasattr(r, "path")}
        assert "/api/sessions/{session_id}/document/package/pages" in paths
        assert ("/api/sessions/{session_id}/document/package/page/{number}.png"
                in paths)

    def test_a_page_request_is_clamped_to_a_sane_resolution(self):
        """A query string must not be able to ask this server to render a
        2000 DPI bitmap of a hundred-page document."""
        import inspect

        from app.api import rest

        source = inspect.getsource(rest.package_page)
        assert "_PREVIEW_MAX_DPI" in source
        assert "max(60, min(" in source

    def test_the_package_is_built_once_per_version(self):
        """The preview asks for pages one at a time. Rebuilding the package
        on each of those would copy the attachments once per page."""
        import inspect

        from app.api import rest

        source = inspect.getsource(rest._package_for)
        assert "_PACKAGE_CACHE" in source
        assert "version" in source

    def test_the_total_comes_from_the_file_not_the_arithmetic(self):
        """`Result.total_pages` adds an index page whether or not one was
        drawn. A preview that asks for a page which is not there shows a
        citizen a broken image."""
        import inspect

        from app.api import rest

        assert "document_.page_count" in inspect.getsource(rest.package_pages)
        assert "document_.page_count" in inspect.getsource(rest.package_page)

    def test_pages_are_loaded_as_they_come_into_view(self, script):
        assert "IntersectionObserver" in script
        assert "rootMargin" in script

    def test_the_observer_watches_the_viewport(self, script):
        """Rooting it on `.paper-wrap` was tried. That element carries
        `overflow-y:auto` but computes to `visible` and grows to fit — 27535px
        tall, clientHeight == scrollHeight — so every sheet sat inside it at
        all times and all 103 pages of a hundred-page annexure loaded at
        once. Measured in the browser, both before and after."""
        assert "{ root: null, rootMargin:" in script

    def test_nothing_is_inlined_into_the_page(self, script):
        """"Do not introduce a giant base64 document into HTML/JSON." Pages
        arrive as ordinary image requests."""
        assert "data:application/pdf;base64" not in script
        assert "base64" not in script.split("function drawPackagePages")[1][:4000]

    def test_a_failed_page_does_not_cost_the_whole_preview(self, script):
        assert "packagePageFailed" in script
        assert "packageOpenOriginal" in script

    def test_there_is_a_loading_state_rather_than_a_blank_block(self, script):
        assert "packagePageLoading" in script

    def test_both_modes_exist_and_the_package_is_the_default(self, script):
        assert "let packageMode = true;" in script
        assert "modeLetter" in script and "modePackage" in script

    def test_every_new_string_is_translated(self, script):
        for key in ("modeLetter", "modePackage", "pageOf", "packagePageLoading",
                    "packagePageFailed", "packageOpenOriginal", "packageBuilding",
                    "packageUnavailable", "packageNotMerged", "attachmentWord"):
            assert script.count(f"{key}:") >= 2, f"{key} has no Tamil translation"

    def test_printing_stays_the_petition(self):
        """Printing screen-rendered images of the attachments would send a
        second-generation copy of the citizen's originals to the office. The
        Full Package download carries the real pages."""
        css = (pathlib.Path(__file__).resolve().parent.parent
               / "app" / "static" / "app.css").read_text(encoding="utf-8")
        printed = css[css.index("@media print"):]
        assert ".package-pages,.preview-modes{display:none!important}" in printed
        assert ".paper-sheet{display:table!important}" in printed
