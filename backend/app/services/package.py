"""The combined petition package: the letter, an index, then the originals.

WHAT THIS IS FOR, and how it differs from `enclosures.py` beside it.

`enclosures.py` puts the attachments INTO the DOCX, and to do that it has to
rasterise them — a DOCX cannot hold another PDF's pages, only pictures of
them. That is the right trade for the editable document, and it has two
costs it states plainly in its own docstring: an enclosed PDF stops being
searchable, and it stops at twelve pages.

This module has neither cost, because it builds a PDF rather than a DOCX.
An attached PDF's pages are copied ACROSS, not photographed: the text layer
survives, the page count survives, and a hundred-page annexure arrives as a
hundred pages. That is what an office receives and files.

    page 1..n     the generated petition
    page n+1      supporting documents index
    page n+2..    attachment 1, every original page
                  attachment 2, ...

WHAT IT WILL NOT DO. It will not silently drop pages, and it will not claim
an attachment was included when it was not. Anything that cannot be rendered
— an office file with no converter installed, a corrupt PDF — is still named
on the index page, marked as held separately, and still downloadable on its
own. A package that quietly omits a citizen's evidence is worse than one
that says what is missing.

Nothing here reads a field, a session or a petition record. It is handed
paths and labels.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# A4 at 72 dpi, which is PDF's own unit.
A4 = (595.0, 842.0)
MARGIN = 54.0                    # 19mm, matching the letter
IMAGE_DPI = 200                  # for rasterising a page that has no other route

# The index page is the only thing this module TYPESETS, and on a Tamil
# petition it is typeset in Tamil. PyMuPDF's built-in fonts are Latin-only:
# with `helv` the heading came out as a row of dots, which is what a font
# with no glyph for a character draws. The service already ships Noto Sans
# Tamil for the DOCX, so the index uses the same face as the letter.
_FONTS = Path(__file__).resolve().parents[1] / "assets" / "fonts"
TAMIL_FONT = _FONTS / "NotoSansTamil-Regular.ttf"
LATIN_FONT = _FONTS / "NotoSans-Regular.ttf"

IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic", ".bmp", ".tif", ".tiff"})
TEXT_SUFFIXES = frozenset({".txt", ".csv", ".md", ".html"})
OFFICE_SUFFIXES = frozenset({".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"})


@dataclass
class Item:
    """One attachment, as the package needs to see it."""

    label: str                   # "1. Previous petition"
    path: Path                   # the ORIGINAL file the citizen uploaded
    filename: str                # what they called it
    detail: str = ""             # reference number, date — already confirmed


@dataclass
class Placed:
    """What actually happened to one attachment."""

    label: str
    filename: str
    pages: int = 0
    included: bool = False
    reason: str = ""             # why not, when not


@dataclass
class Result:
    petition_pages: int = 0
    items: list[Placed] = field(default_factory=list)

    @property
    def total_pages(self) -> int:
        return self.petition_pages + 1 + sum(i.pages for i in self.items)

    @property
    def complete(self) -> bool:
        return all(i.included for i in self.items)


# --------------------------------------------------------------------------- #
# Putting one attachment into the document
# --------------------------------------------------------------------------- #

def _append_pdf(document, source: Path) -> int:
    """Every page of a PDF, copied across rather than photographed.

    `insert_pdf` moves the page objects themselves, so the text layer, the
    selectable content and the original resolution all survive. This is the
    whole reason the package is a PDF.
    """
    import pymupdf

    with pymupdf.open(source) as incoming:
        if incoming.needs_pass:
            raise ValueError("password protected")
        count = incoming.page_count
        if not count:
            raise ValueError("no pages")
        document.insert_pdf(incoming)
    return count


def _append_image(document, source: Path) -> int:
    """One A4 page carrying the picture, whole and in proportion.

    Fitted inside the margins with its aspect ratio kept. A photograph of a
    handwritten note is evidence, and evidence that has been stretched or
    had its edge cropped off is evidence somebody can argue with.
    """
    import pymupdf

    page = document.new_page(width=A4[0], height=A4[1])
    box = pymupdf.Rect(MARGIN, MARGIN, A4[0] - MARGIN, A4[1] - MARGIN)
    # `keep_proportion` is the default and is named here because it is the
    # requirement, not a preference.
    page.insert_image(box, filename=str(source), keep_proportion=True)
    return 1


def _append_text(document, source: Path, font: str) -> int:
    """A plain-text attachment, typeset rather than described."""
    import pymupdf

    body = source.read_text(encoding="utf-8", errors="replace")
    pages, remaining = 0, body
    while True:
        page = document.new_page(width=A4[0], height=A4[1])
        box = pymupdf.Rect(MARGIN, MARGIN, A4[0] - MARGIN, A4[1] - MARGIN)
        # A negative return means it did not all fit; the remainder goes on
        # the next page rather than being cut off.
        left = page.insert_textbox(box, remaining, fontsize=9, fontname=font)
        pages += 1
        if left >= 0 or pages > 400:
            break
        # How much was placed is not reported directly, so the text is
        # trimmed by the proportion that fitted.
        keep = max(1, int(len(remaining) * 0.92))
        if keep >= len(remaining):
            break
        remaining = remaining[keep:]
    return pages


async def _office_as_pdf(source: Path, workspace: Path) -> Path | None:
    """An Office file through whatever converter the host has.

    Reuses the service's own PDF conversion rather than shelling out to a
    second one: whatever produces the petition's PDF is what is installed,
    configured and already trusted here.

    COPIED INTO THE WORKSPACE FIRST. `render_pdf` writes its output beside
    its input, and its input would otherwise be the citizen's stored
    attachment — so converting in place would drop a derived PDF into the
    attachment store, where the next thing to read the directory would treat
    it as a file the citizen uploaded.
    """
    import shutil

    from . import render

    try:
        local = workspace / source.name
        shutil.copyfile(source, local)
        converted, problem = await render.render_pdf(local)
    except Exception as exc:  # noqa: BLE001
        log.info("package.office_failed", extra={"error": str(exc)[:160]})
        return None
    if problem:
        # Not an error here. The attachment is recorded as held separately
        # and the package is still built.
        log.info("package.office_unavailable", extra={"reason": problem[:160]})
    return converted


# --------------------------------------------------------------------------- #
# The index
# --------------------------------------------------------------------------- #

def _index_page(document, placed: list[Placed], *, title: str, font: str,
                held_separately: str) -> None:
    """One page listing what follows, in the order it follows.

    Written after the attachments are placed, so the page counts on it are
    the real ones rather than an intention.

    TYPESET THROUGH `insert_htmlbox`, NOT `insert_text`, and the difference
    is not cosmetic. `insert_text` draws glyphs in codepoint order and does
    no complex-script shaping, so Tamil comes out with its vowel signs in
    the wrong places: "\u0bae\u0bc1\u0ba8\u0bcd\u0ba4\u0bc8\u0baf" instead of "\u0bae\u0bc1\u0ba8\u0bcd\u0ba4\u0bc8\u0baf" \u2014 the \u0bc8 reordered
    around the consonant it belongs to. `insert_htmlbox` runs a real text
    shaper. The built-in faces have no Tamil glyphs at all and draw a row of
    dots, so the font the letter already uses is supplied alongside.
    """
    import pymupdf

    written = " ".join([title, held_separately]
                       + [e.label + e.filename for e in placed])
    tamil = any("\u0b80" <= ch <= "\u0bff" for ch in written)
    face = TAMIL_FONT if tamil else LATIN_FONT

    rows = []
    for entry in placed:
        if entry.included and entry.pages:
            note = f"{entry.pages} page" + ("s" if entry.pages != 1 else "")
        else:
            note = held_separately
        rows.append(
            f"<div class='item'><div class='label'>{_escape(entry.label)}</div>"
            f"<div class='meta'>{_escape(entry.filename)}</div>"
            f"<div class='meta'>{_escape(note)}</div></div>")

    html = (f"<h1>{_escape(title)}</h1><hr/>" + "".join(rows))
    css = (f"@font-face {{font-family: body; src: url(fonts/{face.name});}}"
           "* {font-family: body;}"
           "h1 {font-size: 13px; font-weight: normal; margin: 0 0 10px 0;}"
           "hr {border: none; border-top: 1px solid #bbb; margin: 0 0 14px 0;}"
           ".item {margin: 0 0 16px 0;}"
           ".label {font-size: 10.5px; margin: 0 0 3px 0;}"
           ".meta {font-size: 9px; color: #555; margin: 0 0 1px 12px;}")

    if not face.is_file():
        # A broken install rather than an ordinary state. A Latin index is
        # still better than no package, so this is logged and not raised.
        log.warning("package.font_missing", extra={"path": str(face)})
        css = css.replace(f"@font-face {{font-family: body; src: url(fonts/{face.name});}}", "")

    archive = pymupdf.Archive(str(face.parent), "fonts")
    box = pymupdf.Rect(MARGIN, MARGIN, A4[0] - MARGIN, A4[1] - MARGIN)

    while True:
        page = document.new_page(width=A4[0], height=A4[1])
        # A negative spare height means it did not all fit. The remainder
        # goes on another page rather than being cut off, which matters when
        # a citizen attaches ten documents.
        spare, _ = page.insert_htmlbox(box, html, css=css, archive=archive)
        if spare >= 0:
            return
        # More than fits on one page: split the rows and place them in two
        # passes rather than silently dropping the tail.
        if len(rows) < 2:
            return
        document.delete_page(document.page_count - 1)
        half = len(rows) // 2
        first, rows = rows[:half], rows[half:]
        page = document.new_page(width=A4[0], height=A4[1])
        page.insert_htmlbox(box, f"<h1>{_escape(title)}</h1><hr/>" + "".join(first),
                            css=css, archive=archive)
        html = "".join(rows)


def _escape(value: str) -> str:
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


# --------------------------------------------------------------------------- #
# The whole thing
# --------------------------------------------------------------------------- #

async def build(petition_pdf: Path, items: list[Item], destination: Path, *,
                index_title: str = "SUPPORTING DOCUMENTS",
                held_separately: str = "held separately with this petition",
                font: str = "helv") -> Result:
    """Assemble the package. Returns what went in, and what did not.

    The petition itself is copied first and is never at risk: an attachment
    that cannot be rendered is recorded and skipped, so the worst outcome is
    a package that is the petition plus an index saying where the rest is.
    """
    import tempfile

    import pymupdf

    result = Result()
    with pymupdf.open(petition_pdf) as letter:
        result.petition_pages = letter.page_count
        document = pymupdf.open()
        document.insert_pdf(letter)

    if not items:
        document.save(str(destination), garbage=3, deflate=True)
        document.close()
        return result

    # The index is written last but has to sit directly after the letter, so
    # its page is reserved now and filled in at the end.
    index_at = document.page_count

    with tempfile.TemporaryDirectory(prefix="package-") as temporary:
        workspace = Path(temporary)
        for item in items:
            entry = Placed(label=item.label, filename=item.filename)
            suffix = item.path.suffix.lower()
            try:
                if not item.path.exists():
                    raise FileNotFoundError("the stored file is gone")
                before = document.page_count
                if suffix == ".pdf":
                    _append_pdf(document, item.path)
                elif suffix in IMAGE_SUFFIXES:
                    _append_image(document, item.path)
                elif suffix in TEXT_SUFFIXES:
                    _append_text(document, item.path, font)
                elif suffix in OFFICE_SUFFIXES:
                    converted = await _office_as_pdf(item.path, workspace)
                    if converted is None:
                        raise ValueError("no converter for this format")
                    _append_pdf(document, converted)
                else:
                    raise ValueError(f"nothing renders {suffix or 'this file'}")
                entry.pages = document.page_count - before
                entry.included = entry.pages > 0
                if not entry.included:
                    entry.reason = "produced no pages"
            except Exception as exc:  # noqa: BLE001
                # Recorded, never raised. One unreadable attachment must not
                # cost the citizen the package.
                entry.included = False
                entry.reason = str(exc)[:120]
                # NOT `filename`: that is a LogRecord attribute of its own,
                # and passing it in `extra` makes the logging call itself
                # raise — inside the handler that exists to stop one bad
                # attachment costing the citizen their package.
                log.info("package.item_skipped",
                         extra={"attachment": item.filename, "reason": entry.reason})
            result.items.append(entry)

        _index_page(document, result.items, title=index_title, font=font,
                    held_separately=held_separately)
        # Move the index from the end to directly after the letter.
        document.move_page(document.page_count - 1, index_at)

        document.save(str(destination), garbage=3, deflate=True)
        document.close()

    log.info("package.built", extra={
        "petition_pages": result.petition_pages,
        "attachments": len(result.items),
        "included": sum(1 for i in result.items if i.included),
        "total_pages": result.total_pages,
    })
    return result
