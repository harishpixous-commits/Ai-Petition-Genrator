"""Putting the citizen's enclosures into the petition itself.

A petition that lists "1. Acknowledgement receipt" and arrives with nothing
behind it is a petition the officer has to chase. So the files the citizen
attached are appended to the document as real pages, after the letter, each
behind a caption saying which enclosure it is.

**Every attachment becomes an image.** A PDF is rasterised page by page, a
photograph is placed as it is, and a text file is typeset. One mechanism for
everything, and it has one consequence worth stating plainly:

    **A rasterised page has no text layer.** An enclosed PDF that was
    searchable on its own stops being searchable inside the petition. For a
    scanned acknowledgement slip — which is what these usually are — it made no
    difference; for a born-digital PDF it is a real loss. The alternative is
    merging PDF streams, which cannot be done into a DOCX at all, and DOCX is
    the format this service guarantees.

The PDF gets them for free: it is converted from the DOCX, so whatever is here
is in both.

Nothing in this module reads a field or a session. It is handed paths and
captions and it appends pages.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

# 150 DPI. Enough that a photographed slip stays legible when an officer zooms
# in, low enough that six enclosures do not make a document nobody can email.
RASTER_DPI = 150

# Per attachment. A citizen who attaches a 200-page report has attached the
# wrong thing, and a petition that runs to 200 pages will not be read.
MAX_PAGES_PER_ATTACHMENT = 12

IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic"})
TEXT_SUFFIXES = frozenset({".txt", ".md"})


@dataclass
class Enclosure:
    """One attachment, ready to be appended."""

    label: str              # "1. Acknowledgement receipt"
    path: Path
    filename: str = ""
    # One line of what the document actually says — a reference number, a
    # date — for the index page. Built only from values the citizen has
    # CONFIRMED, so the index never asserts something the petition itself
    # would not. Empty is normal and prints nothing.
    detail: str = ""


@dataclass
class Appended:
    pages: int = 0
    failures: list[str] = None      # captions we could not render

    def __post_init__(self) -> None:
        if self.failures is None:
            self.failures = []


def _pdf_page_images(path: Path, workspace: Path) -> list[Path]:
    """Rasterise a PDF into PNGs, one per page, capped."""
    import pymupdf

    out: list[Path] = []
    with pymupdf.open(path) as document:
        for number, page in enumerate(document):
            if number >= MAX_PAGES_PER_ATTACHMENT:
                break
            pixmap = page.get_pixmap(dpi=RASTER_DPI)
            image = workspace / f"{path.stem}-p{number + 1}.png"
            pixmap.save(str(image))
            out.append(image)
    return out


def _normalised_image(path: Path, workspace: Path) -> Path:
    """A format python-docx will actually embed.

    It handles PNG and JPEG; HEIC and WebP it does not. Converting through
    PyMuPDF keeps one dependency doing the work rather than adding Pillow for
    the two formats a phone camera produces.
    """
    if path.suffix.lower() in (".png", ".jpg", ".jpeg"):
        return path
    import pymupdf

    target = workspace / f"{path.stem}-converted.png"
    with pymupdf.open(path) as document:
        document[0].get_pixmap(dpi=RASTER_DPI).save(str(target))
    return target


def _index_page(document, enclosures: list[Enclosure], *, title: str,
                caption_font: str) -> None:
    """A contents page for the documents that follow.

    An officer receiving a petition with six scans stapled behind it should be
    able to see what is there without leafing through. The list is built from
    the enclosures actually being appended, so it cannot name a file that is
    not in the envelope — which is the same rule the enclosure section in the
    letter follows.
    """
    from docx.shared import Pt

    document.add_page_break()
    head = document.add_paragraph()
    run = head.add_run(title)
    run.bold = True
    run.font.name = caption_font
    run.font.size = Pt(13)

    for enclosure in enclosures:
        line = document.add_paragraph()
        line.paragraph_format.space_after = Pt(2)
        label = line.add_run(enclosure.label)
        label.bold = True
        label.font.name = caption_font
        label.font.size = Pt(10.5)

        if enclosure.filename:
            name = document.add_paragraph()
            name.paragraph_format.left_indent = Pt(14)
            name.paragraph_format.space_after = Pt(1)
            run = name.add_run(enclosure.filename)
            run.font.name = caption_font
            run.font.size = Pt(9)
            run.font.color.rgb = _grey()

        if enclosure.detail:
            extra = document.add_paragraph()
            extra.paragraph_format.left_indent = Pt(14)
            extra.paragraph_format.space_after = Pt(8)
            run = extra.add_run(enclosure.detail)
            run.font.name = caption_font
            run.font.size = Pt(9)
            run.font.color.rgb = _grey()


def _grey():
    from docx.shared import RGBColor

    return RGBColor(0x77, 0x77, 0x77)


def append_to_document(document, enclosures: list[Enclosure], *,
                       heading: str, caption_font: str,
                       note: str = "", index_title: str = "") -> Appended:
    """Append each enclosure to an open python-docx document.

    Failures are collected rather than raised. An enclosure that cannot be
    rendered must not cost the citizen their petition — it stays listed in the
    enclosure section, which is still true: it IS in the envelope.

    `index_title` adds a contents page before the documents. Only worth a page
    of its own when there is more than one thing to index; with a single
    enclosure the caption on its own page already says everything the index
    would.
    """
    import tempfile

    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt, Twips

    if not enclosures:
        return Appended()

    if index_title and len(enclosures) > 1:
        _index_page(document, enclosures, title=index_title,
                    caption_font=caption_font)

    result = Appended()
    section = document.sections[0]
    usable = section.page_width - section.left_margin - section.right_margin
    # Leave room for the caption and a little breathing space, so a tall scan
    # does not push itself onto a second page and leave a blank one behind.
    # Caption line, note line, and the spacing around them. Measured by
    # rendering: at 900 twips the image cleared the caption but Word still
    # broke the page under it.
    max_height = (section.page_height - section.top_margin
                  - section.bottom_margin - Twips(1500))

    with tempfile.TemporaryDirectory(prefix="enclosures-") as temporary:
        workspace = Path(temporary)

        for enclosure in enclosures:
            document.add_page_break()
            title = document.add_paragraph()
            title.alignment = WD_ALIGN_PARAGRAPH.LEFT
            run = title.add_run(f"{heading}: {enclosure.label}")
            run.bold = True
            run.font.name = caption_font
            run.font.size = Pt(11)

            if note:
                hint = document.add_paragraph()
                hint_run = hint.add_run(note)
                hint_run.italic = True
                hint_run.font.size = Pt(8)
                hint_run.font.name = caption_font

            # Rendering AND placing are both inside the guard. A file with a
            # valid header and a truncated body converts happily and then
            # throws when python-docx embeds it — and with only the conversion
            # guarded, one corrupt photograph took down the render of the whole
            # petition. A citizen does not lose their document because a file
            # they uploaded from a phone was cut short.
            try:
                images = _render(enclosure.path, workspace, document, caption_font)
                # No explicit break between the pages of ONE enclosure. Each
                # image is nearly a full page, so it flows to the next by
                # itself; forcing a break as well produced a blank page between
                # every pair of scanned pages.
                for image in images:
                    holder = document.add_paragraph()
                    holder.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    _place(holder, image, usable, max_height)
                    result.pages += 1
            except Exception as exc:  # noqa: BLE001
                log.warning("enclosure.render_failed",
                            extra={"suffix": enclosure.path.suffix,
                                   "error": str(exc)[:160]})
                result.failures.append(enclosure.label)
                missing = document.add_paragraph()
                missing_run = missing.add_run(
                    "This enclosure is submitted with the petition as a separate "
                    "file; it could not be reproduced here.")
                missing_run.italic = True
                missing_run.font.size = Pt(9)
                missing_run.font.name = caption_font

    return result


def _render(path: Path, workspace: Path, document, caption_font) -> list[Path]:
    """The images this enclosure becomes. Raises if it cannot become any."""
    from docx.shared import Pt

    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _pdf_page_images(path, workspace)
    if suffix in IMAGE_SUFFIXES:
        return [_normalised_image(path, workspace)]
    if suffix in TEXT_SUFFIXES:
        # Typeset rather than rasterised: it is already text, and keeping it as
        # text keeps it searchable and selectable in the finished petition.
        body = path.read_text(encoding="utf-8", errors="replace")
        for line in body.splitlines()[:400]:
            paragraph = document.add_paragraph()
            run = paragraph.add_run(line)
            run.font.name = caption_font
            run.font.size = Pt(10)
        return []
    if suffix == ".docx":
        import docx as docx_module

        attached = docx_module.Document(str(path))
        for paragraph in attached.paragraphs[:400]:
            if not paragraph.text.strip():
                continue
            new = document.add_paragraph()
            run = new.add_run(paragraph.text)
            run.font.name = caption_font
            run.font.size = Pt(10)
        return []
    raise ValueError(f"cannot reproduce {suffix!r} inside the petition")


def _natural_size(image: Path) -> tuple[int, int] | None:
    """The image's own pixel dimensions, or None if they cannot be read."""
    try:
        import pymupdf

        with pymupdf.open(image) as document:
            page = document[0]
            return int(page.rect.width), int(page.rect.height)
    except Exception:  # noqa: BLE001
        return None


def _place(paragraph, image: Path, usable_width, max_height) -> None:
    """Fit the image to the page without distorting it.

    The size is decided BEFORE the picture is added, not patched into the XML
    afterwards. Post-editing `wp:extent` left the stored dimensions inconsistent
    enough that Word laid the picture out at its unscaled height, decided it did
    not fit under the caption, and pushed it to the following page — so every
    enclosure arrived one page away from the caption naming it.
    """
    run = paragraph.add_run()
    size = _natural_size(image)
    if size is None:
        run.add_picture(str(image), width=usable_width)
        return

    natural_width, natural_height = size
    if natural_width <= 0 or natural_height <= 0:
        run.add_picture(str(image), width=usable_width)
        return

    # Fit to the width, then fall back to fitting the height when that would
    # make it too tall — a portrait scan is the common case and is the one that
    # overflows.
    height_at_full_width = int(usable_width) * natural_height / natural_width
    if height_at_full_width <= int(max_height):
        run.add_picture(str(image), width=usable_width)
    else:
        run.add_picture(str(image), height=int(max_height))
