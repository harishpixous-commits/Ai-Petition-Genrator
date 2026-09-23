"""Where does the text actually start on page two of a printed petition?

THE DEFECT THIS EXISTS FOR, reported from a sheet of paper. A two-page
petition printed with a proper margin at the top of page one and almost none
at the top of page two: the first line sat hard against the edge of the
sheet.

`padding` cannot fix it — padding opens at the top of the FIRST page and
closes at the bottom of the LAST, and the pages between get neither. The
usual answer, `@page{margin}`, is the one thing not available here: Chrome
draws its own header and footer inside the page margin, and those were
removed on request.

WHY A BROWSER IS THE ONLY WAY TO CHECK THIS. Every other test in this
repository reads the CSS and asserts the rules are present. Not one of them
can tell whether Chrome HONOURS them — and the mechanism in question,
a repeating table part built out of a pseudo-element, is exactly the kind of
thing a browser may quietly ignore. So this drives Chrome's real print path
through `page.pdf()` and measures the first mark on every sheet.

    python scripts/print_margin_check.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import fitz
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8000/"
MM = 72 / 25.4                      # PDF points per millimetre
WANTED_MM = 12.0                    # the least top margin worth calling a margin

# Long enough to run past one sheet whatever the font metrics do.
LETTER = "\n".join(
    ["From,", "Ravi Kumar", "12 Gandhi Street, Coimbatore", "", "To,",
     "The concerned officer", "", "Subject: Street lighting", ""]
    + [f"Paragraph {n}. " + ("The street light outside my house has not "
                             "worked for three months and I have complained "
                             "twice at the panchayat office. ") * 3
       for n in range(1, 26)]
    + ["", "Thanking you,", "", "Yours faithfully,", "", "Ravi Kumar"])


def first_mark_mm(page) -> float | None:
    """Millimetres from the top of the sheet to the highest thing drawn."""
    top = None
    for block in page.get_text("blocks"):
        y0 = block[1]
        if block[4].strip() and (top is None or y0 < top):
            top = y0
    return None if top is None else top / MM


def main() -> int:
    out = Path(tempfile.gettempdir()) / "petition-print.pdf"
    with sync_playwright() as play:
        browser = play.chromium.launch()
        page = browser.new_page()
        page.goto(URL, wait_until="networkidle")
        # Put a long letter on the page and show it the way a finished
        # petition is shown, without needing the workflow to produce one.
        page.evaluate(
            """(text) => {
                document.getElementById('letter').textContent = text;
                document.querySelector('main.workspace')?.classList.add('done');
                const card = document.getElementById('docCard');
                if (card) card.hidden = false;
            }""", LETTER)
        page.wait_for_timeout(300)
        page.pdf(path=str(out), format="A4", print_background=True,
                 prefer_css_page_size=True)
        browser.close()

    document = fitz.open(out)
    print(f"{document.page_count} page(s) in {out}\n")
    worst, failures = None, []
    for number, page in enumerate(document, start=1):
        top = first_mark_mm(page)
        if top is None:
            print(f"  page {number}: blank")
            continue
        print(f"  page {number}: first mark {top:5.1f} mm from the top")
        if worst is None or top < worst:
            worst = top
        if top < WANTED_MM:
            failures.append((number, top))

    print()
    if document.page_count < 2:
        print("FAIL: one page only — this measures the break between sheets.")
        return 1
    if failures:
        for number, top in failures:
            print(f"FAIL: page {number} starts {top:.1f} mm from the edge "
                  f"(want at least {WANTED_MM:.0f} mm)")
        return 1
    print(f"PASS: every page starts at least {worst:.1f} mm down.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
