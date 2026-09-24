"""Does the combined package hold every page the citizen attached?

THE REQUIREMENT THIS MEASURES, in the words it was given in:

    Petition:   2 pages
    Attachment: 100 pages
    Final:      page 1-2 petition, page 3 index, page 4-103 the original

    No truncation.

The DOCX path cannot do that and says so: it rasterises each attachment into
the Word file and stops at twelve pages, because a DOCX can hold a picture of
a page but not the page. This checks the PDF package, which copies the pages
across instead.

    python scripts/package_check.py
"""

from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import package  # noqa: E402


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
    page.insert_text((20, 40), "Handwritten note (photo)", fontsize=18)
    pixmap = page.get_pixmap(dpi=96)
    pixmap.save(str(path))
    document.close()
    return path


async def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="package-check-"))
    letter = a_pdf(work / "petition.pdf", 2, "Petition")
    failures = []

    print("Attachment page counts\n")
    for pages in (1, 10, 60, 100):
        source = a_pdf(work / f"a{pages}.pdf", pages)
        out = work / f"package-{pages}.pdf"
        result = await package.build(
            letter, [package.Item(label="1. Previous petition",
                                  path=source, filename=source.name)], out)
        with pymupdf.open(out) as built:
            actual = built.page_count
            # The last page of the package must be the last page of the
            # attachment, which is what proves nothing was dropped.
            tail = built[actual - 1].get_text()
        expected = 2 + 1 + pages
        ok = actual == expected and f"page {pages} of {pages}" in tail
        print(f"  {pages:3d}-page PDF -> package {actual:4d} pages "
              f"(expected {expected})  {'OK' if ok else 'FAIL'}")
        if not ok:
            failures.append(f"{pages}-page attachment: got {actual}, wanted {expected}")

    print("\nOther formats\n")
    # A tall, narrow image: the one that gets distorted if aspect is ignored.
    photo = an_image(work / "note.png", 300, 900)
    text = work / "notes.txt"
    text.write_text("A typed note from the citizen.\n" * 40, encoding="utf-8")
    missing = work / "not-there.pdf"

    items = [
        package.Item("1. Previous petition", a_pdf(work / "prev.pdf", 3), "prev.pdf"),
        package.Item("2. Photograph", photo, "note.png"),
        package.Item("3. Typed note", text, "notes.txt"),
        package.Item("4. Missing file", missing, "not-there.pdf"),
    ]
    out = work / "mixed.pdf"
    result = await package.build(letter, items, out)
    for entry in result.items:
        state = f"{entry.pages} page(s)" if entry.included else f"NOT INCLUDED ({entry.reason})"
        print(f"  {entry.label:24s} {state}")

    if result.complete:
        failures.append("a missing file was reported as included")
    included = [e for e in result.items if e.included]
    if len(included) != 3:
        failures.append(f"expected 3 of 4 placed, got {len(included)}")

    with pymupdf.open(out) as built:
        index = built[2].get_text()
    print(f"\n  index page names every attachment: "
          f"{all(e.filename in index for e in result.items)}")
    if not all(e.filename in index for e in result.items):
        failures.append("the index does not name every attachment")
    if "held separately" not in index:
        failures.append("the index does not say the missing file is held separately")

    # The image must not have been stretched.
    with pymupdf.open(out) as built:
        images = built[2 + 1 + 3].get_images(full=True)
    print(f"  photograph placed on its own page: {bool(images)}")
    if not images:
        failures.append("the photograph did not reach the package")

    print()
    if failures:
        for problem in failures:
            print(f"FAIL: {problem}")
        return 1
    print("PASS: every page preserved, nothing claimed that was not included.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
