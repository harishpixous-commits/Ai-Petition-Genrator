"""Is the petition still on screen when the officer reaches the last card?

THE DEFECT THIS EXISTS FOR. The review page put the petition preview and
the assistance panel in two grid columns at their own content heights. The
preview ended around 1100px; the panel ran past 1900. So an officer reading
the Acts & Rules card had scrolled the petition off the top of the screen a
thousand pixels earlier — and the entire point of the layout is that the two
are read against each other. Under the preview sat a screen and a half of
empty page.

A full-page screenshot cannot show this: it flattens the document and draws
a sticky element at its unscrolled position, so the broken layout and the
fixed one look identical. This scrolls a real viewport to the bottom and
measures where the petition actually is.
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path("artifacts/officer")
OUT.mkdir(parents=True, exist_ok=True)
URL = "http://127.0.0.1:8020/officer/petitions/sample-1?preview=1"

with sync_playwright() as play:
    browser = play.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.goto(URL)
    page.wait_for_timeout(350)

    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    page.wait_for_timeout(350)
    page.screenshot(path=str(OUT / "review-scrolled-1440.png"))

    # Where the paper is, relative to the window, at the foot of the page.
    box = page.evaluate(
        "() => { const r = document.querySelector('.paper').getBoundingClientRect();"
        " return {top: r.top, bottom: r.bottom, h: innerHeight}; }")
    visible = min(box["bottom"], box["h"]) - max(box["top"], 0)
    share = visible / box["h"]
    print(f"petition visible at the foot of the page: {share:.0%} of the viewport")
    assert share > 0.5, f"the petition scrolled away: {box}"

    # And its toolbar is not tucked under the sticky page header. A sticky
    # element cannot be drawn below the bottom of its grid row, so at the
    # foot of the page it rides up by however much it overhangs.
    tucked = page.evaluate(
        "() => { const h = document.querySelector('header.app').getBoundingClientRect(),"
        " t = document.querySelector('.preview-tools').getBoundingClientRect();"
        " return h.bottom - t.top; }")
    print(f"preview toolbar clears the header by {-tucked:.0f}px")
    assert tucked <= 0, f"the Print row is {tucked:.0f}px under the header"

    # And the two columns end at roughly the same place, so there is no
    # dead area under the shorter one.
    gap = page.evaluate(
        "() => { const l = document.querySelector('.review-grid > section')"
        ".getBoundingClientRect(), r = document.querySelector('.review-side')"
        ".getBoundingClientRect(); return Math.abs(l.bottom - r.bottom); }")
    print(f"column feet differ by {gap:.0f}px")

    # The narrow layout stacks, and the petition must come FIRST there.
    page.set_viewport_size({"width": 390, "height": 900})
    page.goto(URL)
    page.wait_for_timeout(300)
    order = page.evaluate(
        "() => { const l = document.querySelector('.paper').getBoundingClientRect().top,"
        " r = document.querySelector('.review-side').getBoundingClientRect().top;"
        " return l < r; }")
    assert order, "the assistance panel was placed above the petition on mobile"
    assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), "sideways scroll"
    print("mobile: petition first, no sideways scroll")

    browser.close()
print("scroll check passed")
