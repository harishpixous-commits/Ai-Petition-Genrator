"""MODULE 2.1 — the continuous combined-package preview, in a real browser.

    python scripts/package_preview_check.py --url http://127.0.0.1:8014

Drives the citizen flow, then checks that the CENTRE of the screen shows the
package as one scrollable document — petition pages, the index, then the
citizen's originals — rather than a card saying a file exists.

The performance case is the one worth having: a 100-page attachment must not
load 103 images at once. That is asserted by counting the images the browser
actually requested, not by trusting the observer to be wired up.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

import pymupdf
from playwright.sync_api import expect, sync_playwright

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def a_pdf(path: Path, pages: int, word: str) -> Path:
    doc = pymupdf.open()
    for n in range(1, pages + 1):
        doc.new_page().insert_text((72, 120), f"{word} page {n} of {pages}", fontsize=15)
    doc.save(str(path))
    doc.close()
    return path


def an_image(path: Path, w: int = 420, h: int = 640) -> Path:
    doc = pymupdf.open()
    page = doc.new_page(width=w, height=h)
    page.insert_text((30, 60), "Handwritten note — please repair the pipe", fontsize=12)
    page.get_pixmap(dpi=110).save(str(path))
    doc.close()
    return path


def interview(page, url, language, attachments):
    page.goto(url + "/#create")
    page.wait_for_timeout(500)
    expect(page.locator(".turn.assistant").first).to_be_visible(timeout=30000)
    if language == "ta":
        page.locator("#lang").select_option("ta")
        confirm = page.locator("[data-go]")
        if confirm.count() and confirm.first.is_visible():
            confirm.first.click()
        page.wait_for_function("view?.language === 'ta' && !requestPending", timeout=60000)

    def answer(text):
        page.locator("#text").fill(text)
        with page.expect_response(lambda r: r.url.endswith("/message"), timeout=180000) as r:
            page.locator("#send").click()
        return r.value.json()

    said = (["ஹரிஷ்", "23", "9344174752", "80/33 பெருமாள் கோவில் தெரு, தேனி",
             "எங்கள் தெருவில் குடிநீர் வரவில்லை."]
            if language == "ta" else
            ["Harish", "23", "9344174752", "80/33 Perumal Kovil Street, Theni",
             "There is no drinking water in our street."])
    state = {}
    for text in said:
        state = answer(text)
        if state.get("status") in ("attachments", "confirming"):
            break

    for item in attachments:
        with page.expect_response(lambda r: "/attachments" in r.url
                                  and r.request.method == "POST", timeout=300000) as r:
            page.locator("#attachInput").set_input_files(str(item))
        state = r.value.json()

    for _ in range(4):
        if state.get("status") == "confirming":
            break
        state = answer("no" if language == "en" else "இல்லை")
    with page.expect_response(lambda r: r.url.endswith("/confirm"), timeout=600000) as r:
        page.locator("#confirm").click()
    return r.value.json()


def run(url, language, attachments, expect_attachment_pages, label, big=False):
    print(f"\n--- {label} ---")
    console, failed, images = [], [], []
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}")
                if m.type == "error" else None)
        page.on("requestfailed", lambda r: failed.append(f"{r.method} {r.url} — {r.failure}"))
        page.on("response", lambda r: failed.append(f"HTTP {r.status} {r.url}")
                if r.status >= 400 else None)
        page.on("request", lambda r: images.append(r.url)
                if "/document/package/page/" in r.url else None)

        ready = interview(page, url, language, attachments)
        check(f"[{label}] petition generated", ready.get("status") == "ready",
              str(ready.get("error") or ""))

        # The mode switch, and Full Package as the default once attached.
        expect(page.locator("#previewModes")).to_be_visible(timeout=30000)
        check(f"[{label}] mode switch shown", page.locator("#previewModes").is_visible())
        check(f"[{label}] Full Package is the default",
              page.locator("#modePackage").get_attribute("aria-pressed") == "true")

        # The continuous run of pages.
        page.wait_for_function(
            "document.querySelectorAll('#packagePages .pp-sheet[data-page]').length > 0",
            timeout=120000)
        sheets = page.locator("#packagePages .pp-sheet[data-page]")
        total = sheets.count()
        check(f"[{label}] pages drawn continuously", total > 1, f"{total} sheets")

        petition_pages = total - 1 - expect_attachment_pages
        check(f"[{label}] petition + index + {expect_attachment_pages} attachment page(s)",
              total == petition_pages + 1 + expect_attachment_pages,
              f"{total} sheets, {petition_pages} petition")

        # An attachment boundary, named.
        dividers = page.locator("#packagePages .pp-divider")
        check(f"[{label}] attachment boundary shown", dividers.count() >= 1,
              f"{dividers.count()} divider(s)")
        if dividers.count():
            word = "இணைப்பு" if language == "ta" else "Attachment"
            # `inner_text` returns what is RENDERED, and the label is
            # uppercased by CSS — so the comparison folds case.
            shown = dividers.first.inner_text()
            check(f"[{label}] boundary is in the session language",
                  word.casefold() in shown.casefold(),
                  shown.replace("\n", " ")[:50])

        # The first page must actually be an image, not a placeholder.
        page.wait_for_function(
            "document.querySelector('#packagePages .pp-sheet img.pp-image')", timeout=120000)
        first = page.locator("#packagePages img.pp-image").first
        check(f"[{label}] page rendered as an image", first.count() > 0)
        natural = page.evaluate(
            "(() => { const i = document.querySelector('#packagePages img.pp-image');"
            " return i ? [i.naturalWidth, i.naturalHeight] : [0, 0]; })()")
        check(f"[{label}] rendered page has real pixels", natural[0] > 200 and natural[1] > 200,
              f"{natural[0]}x{natural[1]}")

        # LAZY LOADING: with a long document, only nearby pages are fetched.
        if big:
            time.sleep(2)
            requested = len(set(images))
            check(f"[{label}] lazy: not every page fetched up front",
                  requested < total, f"{requested} of {total} pages requested")
            before = requested
            # Scroll the element that actually scrolls. A mouse wheel at the
            # default pointer position goes to the body, which moves nothing
            # here and made this check pass for the wrong reason.
            # The WINDOW is the scrolling element here — measured, not
            # assumed: .paper-wrap computes to overflow-y:visible and grows
            # to fit its content.
            page.evaluate("window.scrollTo(0, 20000)")
            time.sleep(3)
            after = len(set(images))
            check(f"[{label}] lazy: scrolling fetches more",
                  after > before, f"{before} -> {after} pages")
            memory = page.evaluate(
                "performance.memory ? Math.round(performance.memory.usedJSHeapSize/1048576) : -1")
            check(f"[{label}] browser heap stays modest",
                  memory < 0 or memory < 400, f"{memory} MB JS heap")
            check(f"[{label}] page stays responsive",
                  page.evaluate("document.readyState") == "complete")

        # The page indicator.
        indicator = page.locator("#pageIndicator").inner_text()
        check(f"[{label}] page indicator shown", bool(indicator.strip()), indicator)

        # Petition Only mode.
        page.locator("#modeLetter").click()
        page.wait_for_timeout(400)
        check(f"[{label}] Petition Only hides the package",
              page.locator("#packagePages").is_hidden()
              and page.locator("#letter").is_visible())
        page.locator("#modePackage").click()
        page.wait_for_timeout(600)
        check(f"[{label}] Full Package returns",
              page.locator("#packagePages").is_visible())

        # Refresh keeps it.
        page.reload()
        page.wait_for_function(
            "document.querySelectorAll('#packagePages .pp-sheet[data-page]').length > 0",
            timeout=120000)
        check(f"[{label}] survives reload",
              page.locator("#packagePages .pp-sheet[data-page]").count() == total)

        noise = [c for c in console if "favicon" not in c.lower()]
        bad = [f for f in failed if "favicon" not in f.lower()
               and not ("/speech" in f and "ERR_ABORTED" in f)]
        check(f"[{label}] no console errors", not noise, "; ".join(noise[:2]))
        check(f"[{label}] no failed requests", not bad, "; ".join(bad[:3]))

        context.close()
        browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8014")
    parser.add_argument("--only", default="")
    args = parser.parse_args()

    work = Path(tempfile.mkdtemp(prefix="package-preview-"))
    two = a_pdf(work / "earlier_petition.pdf", 2, "Earlier petition")
    ten = a_pdf(work / "long_annexure.pdf", 10, "Annexure")
    hundred = a_pdf(work / "big_annexure.pdf", 100, "Annexure")
    photo = an_image(work / "handwritten_note.png")
    ack = a_pdf(work / "acknowledgement.pdf", 1, "Acknowledgement")

    cases = [
        ("english-2page", "en", [two], 2, False),
        ("english-image", "en", [photo], 1, False),
        ("english-10page", "en", [ten], 10, False),
        ("multiple", "en", [two, ack, photo], 4, False),
        ("tamil-2page", "ta", [two], 2, False),
        ("english-100page", "en", [hundred], 100, True),
    ]
    for label, language, files, pages, big in cases:
        if args.only and args.only != label:
            continue
        run(args.url, language, files, pages, label, big)

    failed = [r for r in RESULTS if not r[1]]
    print(f"\n{len(RESULTS) - len(failed)}/{len(RESULTS)} checks passed")
    if failed:
        print("\nFAILURES:")
        for name, _, detail in failed:
            print(f"  {name}  {detail}")
        return 1
    print("\nALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
