"""The combined package: the letter, an index, then the citizen's originals.

WHAT THIS IS FOR. A petition that says "1. Copy of earlier petition" and
arrives with nothing behind it is a petition the officer has to chase. The
DOCX already appends attachments, and it does it the only way a Word file
can — as pictures — which costs the text layer and stops at twelve pages per
attachment. Both are stated plainly in `enclosures.py`.

The package is a PDF, so it can do what the DOCX cannot: copy the pages
across. Every page, with its text layer, however many there are.

THE THREE RULES HERE, in the order they matter:

    nothing is dropped         100 pages in, 100 pages out
    nothing is claimed         a file that could not be rendered is named on
                               the index as held separately, not omitted
    the original is the thing  pages are copied, never re-photographed
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pymupdf
import pytest

from app.services import package


@pytest.fixture
def work():
    with tempfile.TemporaryDirectory(prefix="package-test-") as directory:
        yield Path(directory)


def a_pdf(path: Path, pages: int, word: str = "Attachment") -> Path:
    document = pymupdf.open()
    for n in range(1, pages + 1):
        page = document.new_page()
        page.insert_text((72, 100), f"{word} page {n} of {pages}", fontsize=14)
    document.save(str(path))
    document.close()
    return path


def an_image(path: Path, width: int, height: int) -> Path:
    document = pymupdf.open()
    page = document.new_page(width=width, height=height)
    page.insert_text((20, 40), "photograph", fontsize=16)
    page.get_pixmap(dpi=96).save(str(path))
    document.close()
    return path


async def build(work: Path, letter_pages: int, items, **kwargs):
    letter = a_pdf(work / "letter.pdf", letter_pages, "Petition")
    out = work / "package.pdf"
    result = await package.build(letter, items, out, **kwargs)
    return result, out


# ---------------------------------------------------------------------------
# Nothing is dropped
# ---------------------------------------------------------------------------

class TestEveryPageArrives:

    @pytest.mark.parametrize("pages", [1, 10, 60, 100])
    async def test_an_attachment_of_any_length(self, work, pages):
        """The requirement in the words it was given in: a 2-page petition
        and a 100-page attachment make a 103-page package."""
        source = a_pdf(work / f"a{pages}.pdf", pages)
        result, out = await build(
            work, 2, [package.Item("1. Previous petition", source, source.name)])

        with pymupdf.open(out) as built:
            assert built.page_count == 2 + 1 + pages
            # The LAST page of the package is the LAST page of the
            # attachment, which is what proves the tail was not cut off.
            assert f"page {pages} of {pages}" in built[built.page_count - 1].get_text()

    async def test_the_text_layer_survives(self, work):
        """A rasterised page is a picture of a document. An officer cannot
        search it, copy a reference number out of it, or have a screen
        reader read it."""
        source = a_pdf(work / "a.pdf", 3)
        _, out = await build(
            work, 1, [package.Item("1. Previous petition", source, source.name)])

        with pymupdf.open(out) as built:
            assert "Attachment page 2 of 3" in built[3].get_text()

    async def test_several_attachments_keep_their_order(self, work):
        items = [
            package.Item("1. First", a_pdf(work / "1.pdf", 2, "First"), "1.pdf"),
            package.Item("2. Second", a_pdf(work / "2.pdf", 3, "Second"), "2.pdf"),
            package.Item("3. Third", a_pdf(work / "3.pdf", 1, "Third"), "3.pdf"),
        ]
        result, out = await build(work, 1, items)

        assert [e.pages for e in result.items] == [2, 3, 1]
        with pymupdf.open(out) as built:
            assert "First" in built[2].get_text()
            assert "Second" in built[4].get_text()
            assert "Third" in built[7].get_text()


# ---------------------------------------------------------------------------
# Nothing is claimed
# ---------------------------------------------------------------------------

class TestItSaysWhatItCouldNotInclude:

    async def test_a_missing_file_does_not_cost_the_package(self, work):
        """One unreadable attachment must not lose the citizen everything
        else they brought."""
        good = a_pdf(work / "good.pdf", 2)
        items = [
            package.Item("1. Previous petition", good, "good.pdf"),
            package.Item("2. Gone", work / "not-here.pdf", "gone.pdf"),
        ]
        result, out = await build(work, 1, items)

        assert result.items[0].included is True
        assert result.items[1].included is False
        assert result.complete is False
        with pymupdf.open(out) as built:
            assert built.page_count == 1 + 1 + 2

    async def test_and_the_index_says_so(self, work):
        items = [package.Item("1. Gone", work / "not-here.pdf", "gone.pdf")]
        _, out = await build(work, 1, items,
                             held_separately="held separately with this petition")

        with pymupdf.open(out) as built:
            index = built[1].get_text()
        assert "gone.pdf" in index
        assert "held separately" in index

    async def test_a_corrupt_pdf_is_recorded_not_raised(self, work):
        broken = work / "broken.pdf"
        broken.write_bytes(b"%PDF-1.4 this is not a pdf")
        result, _ = await build(
            work, 1, [package.Item("1. Broken", broken, "broken.pdf")])

        assert result.items[0].included is False
        assert result.items[0].reason


# ---------------------------------------------------------------------------
# The index
# ---------------------------------------------------------------------------

class TestTheIndex:

    async def test_it_sits_between_the_letter_and_the_attachments(self, work):
        source = a_pdf(work / "a.pdf", 2)
        _, out = await build(
            work, 3, [package.Item("1. Previous petition", source, source.name)],
            index_title="SUPPORTING DOCUMENTS")

        with pymupdf.open(out) as built:
            assert "Petition page 3 of 3" in built[2].get_text()
            assert "SUPPORTING DOCUMENTS" in built[3].get_text()
            assert "Attachment page 1 of 2" in built[4].get_text()

    async def test_it_counts_the_pages_that_were_actually_placed(self, work):
        source = a_pdf(work / "a.pdf", 7)
        _, out = await build(
            work, 1, [package.Item("1. Previous petition", source, source.name)])

        with pymupdf.open(out) as built:
            assert "7 pages" in built[1].get_text()

    async def test_tamil_reaches_the_index_page(self, work):
        """Two things went wrong here in turn, and the second is subtle.

        FIRST, the built-in faces have no Tamil glyphs, so the heading drew
        as a row of dots. SECOND, `insert_text` draws glyphs in codepoint
        order and does no complex-script shaping, so முந்தைய came out with
        its vowel sign around the wrong consonant. Both were seen on a
        rendered page. `insert_htmlbox` with the shipped font fixes both.

        WHAT THIS CANNOT ASSERT, and it is worth stating rather than
        pretending. A shaped Tamil run does not come back out of the PDF as
        the string that went in — the glyphs are reordered and substituted
        and the reverse mapping is not faithful. So the test checks the
        signatures of the two failures instead: that something was drawn at
        all, and that it is not the fallback's dots. Whether the vowel signs
        sit correctly is a thing only an eye settles, and
        `scripts/package_check.py` renders the page for one.

        The attachments themselves are unaffected: their pages are copied
        across whole and keep their own text layers.
        """
        source = a_pdf(work / "a.pdf", 1)
        _, out = await build(
            work, 1, [package.Item("1. முந்தைய மனு நகல்", source, "old.pdf")],
            index_title="இணைக்கப்பட்ட ஆவணங்கள்")

        with pymupdf.open(out) as built:
            page = built[1]
            index = page.get_text()
            fonts = page.get_fonts(full=True)

        # The fallback's signature: a face with no glyph draws dots.
        assert "···" not in index, "the font fell back and drew dots"
        # Tamil codepoints did reach the page, even if reordered coming back.
        assert any("஀" <= ch <= "௿" for ch in index), index
        # An embedded face, not one of the built-in Latin-only ones.
        assert fonts, "no font was embedded"
        assert any("Noto" in str(entry) for entry in fonts), fonts
        # The Latin parts are unaffected and still extract cleanly.
        assert "old.pdf" in index
        assert "1 page" in index


# ---------------------------------------------------------------------------
# Images
# ---------------------------------------------------------------------------

class TestPhotographs:

    async def test_a_photograph_becomes_its_own_page(self, work):
        photo = an_image(work / "note.png", 400, 700)
        result, out = await build(
            work, 1, [package.Item("1. Photograph", photo, "note.png")])

        assert result.items[0].pages == 1
        with pymupdf.open(out) as built:
            assert built[2].get_images(full=True)

    async def test_a_tall_narrow_photograph_is_not_stretched(self, work):
        """Evidence that has been distorted is evidence somebody can argue
        with. The placed image keeps the proportions of the file."""
        photo = an_image(work / "tall.png", 200, 800)
        _, out = await build(
            work, 1, [package.Item("1. Photograph", photo, "tall.png")])

        with pymupdf.open(out) as built:
            page = built[2]
            placed = page.get_image_rects(page.get_images(full=True)[0][0])[0]
        source_ratio = 800 / 200
        assert abs((placed.height / placed.width) - source_ratio) < 0.15

    async def test_it_stays_inside_the_margins(self, work):
        photo = an_image(work / "wide.png", 900, 300)
        _, out = await build(
            work, 1, [package.Item("1. Photograph", photo, "wide.png")])

        with pymupdf.open(out) as built:
            page = built[2]
            placed = page.get_image_rects(page.get_images(full=True)[0][0])[0]
        assert placed.x0 >= package.MARGIN - 1
        assert placed.x1 <= package.A4[0] - package.MARGIN + 1


# ---------------------------------------------------------------------------
# The petition itself
# ---------------------------------------------------------------------------

class TestThePetitionIsNeverAtRisk:

    async def test_with_no_attachments_the_package_is_the_letter(self, work):
        result, out = await build(work, 2, [])

        assert result.petition_pages == 2
        with pymupdf.open(out) as built:
            assert built.page_count == 2

    async def test_the_letter_comes_first_and_whole(self, work):
        source = a_pdf(work / "a.pdf", 2)
        _, out = await build(
            work, 3, [package.Item("1. Previous petition", source, source.name)])

        with pymupdf.open(out) as built:
            for n in range(3):
                assert f"Petition page {n + 1} of 3" in built[n].get_text()
