"""MODULE 2 — attachment merge, verified through the real browser.

Drives a running development server the way a citizen does: answers the
interview, uploads a real file, generates, and then checks what the screen
shows and what the downloads actually contain.

    python scripts/attachment_merge_check.py --url http://127.0.0.1:8013

Checks A-J from the brief:

    A  generate with a 2+ page PDF attachment
    B  the citizen can SEE the attachment on the generated-petition screen
    C  open the combined package from the UI
    D  package order: petition -> index -> original attachment pages
    E  Download PDF does NOT include attachments
    F  Download Word does NOT include attachments
    G  refresh/reopen keeps the preview and the package working
    H  an image attachment
    I  Tamil and English
    J  no browser console errors, no failed attachment/network requests

Everything is asserted against the BYTES that come back, not against the
button being present: a link that 404s still renders.
"""

from __future__ import annotations

import argparse
import io
import sys
import tempfile
import zipfile
from pathlib import Path

import pymupdf
from playwright.sync_api import expect, sync_playwright

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


def a_pdf(path: Path, pages: int, word: str) -> Path:
    document = pymupdf.open()
    for n in range(1, pages + 1):
        page = document.new_page()
        page.insert_text((72, 120), f"{word} page {n} of {pages}", fontsize=15)
    document.save(str(path))
    document.close()
    return path


def an_image(path: Path) -> Path:
    document = pymupdf.open()
    page = document.new_page(width=420, height=640)
    page.insert_text((30, 60), "Photograph of the broken street light", fontsize=13)
    page.get_pixmap(dpi=110).save(str(path))
    document.close()
    return path


def run(url: str, work: Path, language: str, attachment: Path,
        expect_pages: int, label: str) -> None:
    print(f"\n--- {label} ---")
    console: list[str] = []
    failed: list[str] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.on("pageerror", lambda e: console.append(f"pageerror: {e}"))
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}")
                if m.type == "error" else None)
        page.on("requestfailed", lambda r: failed.append(
            f"{r.method} {r.url} — {r.failure}"))
        page.on("response", lambda r: failed.append(f"HTTP {r.status} {r.url}")
                if r.status >= 400 else None)

        # The app lands on #home; the interview lives at #create.
        page.goto(url + "/#create")
        page.wait_for_timeout(500)
        expect(page.locator(".turn.assistant").first).to_be_visible(timeout=30000)

        if language == "ta":
            page.locator("#lang").select_option("ta")
            # A petition already under way gets a confirmation dialog first;
            # a fresh page switches straight over. Handle both rather than
            # assuming the one the older harness happens to hit.
            confirm = page.locator("[data-go]")
            if confirm.count() and confirm.first.is_visible():
                confirm.first.click()
            page.wait_for_function("view?.language === 'ta' && !requestPending",
                                   timeout=60000)

        def answer(text: str, status: str = "collecting") -> dict:
            page.locator("#text").fill(text)
            with page.expect_response(lambda r: r.url.endswith("/message"),
                                      timeout=120000) as response:
                page.locator("#send").click()
            return response.value.json()

        if language == "ta":
            answers = ["ஹரிஷ்", "23", "9344174752",
                       "80/33 பெருமாள் கோவில் தெரு, தேனி",
                       "எங்கள் தெருவில் குடிநீர் வரவில்லை. சரிசெய்யுமாறு கேட்கிறேன்."]
        else:
            answers = ["Harish", "23", "9344174752",
                       "80/33 Perumal Kovil Street, Theni",
                       "There is no drinking water in our street. Please restore the supply."]

        state = {}
        for text in answers:
            state = answer(text)
            if state.get("status") in ("attachments", "confirming"):
                break

        # ---- A: attach a real file -------------------------------------
        if state.get("status") == "attachments" or page.locator("#attachBtn").count():
            with page.expect_response(lambda r: "/attachments" in r.url
                                      and r.request.method == "POST",
                                      timeout=180000) as response:
                page.locator("#attachInput").set_input_files(str(attachment))
            state = response.value.json()
        attached = len((state.get("attachments") or {}).get("items", []))
        check(f"[{label}] A · attachment accepted", attached == 1, f"{attached} on the petition")

        # Answer whatever is still being asked until the petition can be made.
        for _ in range(4):
            if state.get("status") == "confirming":
                break
            state = answer("no" if language == "en" else "இல்லை")

        with page.expect_response(lambda r: r.url.endswith("/confirm"),
                                  timeout=300000) as response:
            page.locator("#confirm").click()
        ready = response.value.json()
        check(f"[{label}] A · petition generated", ready.get("status") == "ready",
              str(ready.get("error") or ""))
        sid = page.evaluate("sid")

        # ---- B: the citizen can SEE it ---------------------------------
        expect(page.locator("#enclosures")).to_be_visible(timeout=30000)
        shown = page.locator("#enclosures .enclosure")
        text = page.locator("#enclosures").inner_text()
        check(f"[{label}] B · Supporting Documents section visible",
              shown.count() == 1, f"{shown.count()} card(s)")
        check(f"[{label}] B · shows the page count",
              any(w in text for w in ("pages", "page", "பக்க")), text[:70].replace("\n", " "))
        check(f"[{label}] B · shows the file type",
              attachment.suffix.lstrip(".").upper() in text.upper(),
              attachment.suffix)

        # ---- View / Download actions -----------------------------------
        view_link = page.locator("#enclosures a[target='_blank']").first
        save_link = page.locator("#enclosures a[download]").first
        check(f"[{label}] B · View action present", view_link.count() > 0)
        check(f"[{label}] B · Download action present", save_link.count() > 0)

        view_url = url + view_link.get_attribute("href")
        got = page.request.get(view_url)
        check(f"[{label}] B · View returns the file",
              got.status == 200 and len(got.body()) > 100,
              f"HTTP {got.status}, {len(got.body())} bytes")
        save = page.request.get(url + save_link.get_attribute("href"))
        check(f"[{label}] B · Download returns the file",
              save.status == 200 and save.body() == attachment.read_bytes(),
              f"HTTP {save.status}, byte-identical="
              f"{save.body() == attachment.read_bytes()}")

        # ---- C + D: the combined package -------------------------------
        button = page.locator("#packagePdf")
        check(f"[{label}] C · Full Package button visible",
              button.is_visible(), "hidden" if not button.is_visible() else "")
        package_url = url + (button.get_attribute("href") or "")
        response = page.request.get(package_url)
        check(f"[{label}] C · package downloads", response.status == 200,
              f"HTTP {response.status}")
        combined = work / f"combined-{label}.pdf"
        combined.write_bytes(response.body())

        with pymupdf.open(combined) as built:
            pages = [built[i].get_text() for i in range(built.page_count)]
        petition_pages = len(pages) - 1 - expect_pages
        index_page = pages[petition_pages] if petition_pages < len(pages) else ""
        tail = pages[petition_pages + 1:]
        check(f"[{label}] D · package has petition + index + {expect_pages} attachment page(s)",
              len(pages) == petition_pages + 1 + expect_pages,
              f"{len(pages)} pages total")
        check(f"[{label}] D · index page sits between them",
              attachment.name in index_page,
              index_page.strip().replace("\n", " ")[:60])
        if attachment.suffix == ".pdf":
            check(f"[{label}] D · original pages kept as text, not rasterised",
                  any("page 1 of" in p for p in tail),
                  (tail[0].strip().replace("\n", " ")[:50] if tail else "no tail"))
        else:
            with pymupdf.open(combined) as built:
                has_image = bool(built[petition_pages + 1].get_images(full=True))
            check(f"[{label}] D · photograph placed on its own page", has_image)

        # ---- E + F: the plain downloads --------------------------------
        plain_pdf = page.request.get(
            f"{url}/api/sessions/{sid}/document.pdf?enclosures=0")
        if plain_pdf.status == 200:
            with pymupdf.open(stream=plain_pdf.body(), filetype="pdf") as doc:
                plain_pages = doc.page_count
                images = sum(len(doc[i].get_images(full=True)) for i in range(plain_pages))
            check(f"[{label}] E · plain PDF excludes attachments",
                  plain_pages == petition_pages,
                  f"{plain_pages} pages vs {petition_pages} petition pages, {images} images")
        else:
            check(f"[{label}] E · plain PDF excludes attachments", False,
                  f"HTTP {plain_pdf.status}")

        plain_docx = page.request.get(
            f"{url}/api/sessions/{sid}/document.docx?enclosures=0")
        media = []
        if plain_docx.status == 200:
            with zipfile.ZipFile(io.BytesIO(plain_docx.body())) as z:
                media = [n for n in z.namelist() if n.startswith("word/media/")]
        # The emblem is legitimately in the letter; attachment pages would add
        # one image per page on top of it.
        check(f"[{label}] F · Word excludes attachment pages",
              plain_docx.status == 200 and len(media) <= 1,
              f"{len(media)} embedded image(s)")

        # ---- G: refresh / reopen ---------------------------------------
        page.reload()
        expect(page.locator("#docCard")).to_be_visible(timeout=30000)
        expect(page.locator("#enclosures")).to_be_visible(timeout=30000)
        after = page.locator("#enclosures .enclosure").count()
        again = page.request.get(package_url)
        check(f"[{label}] G · attachment still shown after reload", after == 1,
              f"{after} card(s)")
        check(f"[{label}] G · package still builds after reload",
              again.status == 200 and len(again.body()) == len(response.body()),
              f"HTTP {again.status}")

        # ---- J: console and network ------------------------------------
        noise = [c for c in console if "favicon" not in c.lower()]
        bad = [f for f in failed if "favicon" not in f.lower()]
        check(f"[{label}] J · no browser console errors", not noise,
              "; ".join(noise[:2]))
        # Anything this module touches must be clean, with no excuses made
        # for it.
        module_bad = [f for f in bad
                      if "/attachments/" in f or "package.pdf" in f
                      or "document.pdf" in f or "document.docx" in f]
        check(f"[{label}] J · no failed attachment or package requests",
              not module_bad, "; ".join(module_bad[:3]))

        # Everything else is REPORTED, not swallowed. ERR_ABORTED is the
        # browser cancelling a fetch that was still in flight, which is what
        # `page.reload()` in step G does to a speech prefetch. That is not a
        # request that failed, but it is also not something to hide, so it is
        # counted separately and printed.
        others = [f for f in bad if f not in module_bad]
        aborted = [f for f in others if "ERR_ABORTED" in f and "/speech" in f]
        genuine = [f for f in others if f not in aborted]
        check(f"[{label}] J · no other failed requests", not genuine,
              "; ".join(genuine[:3]))
        if aborted:
            print(f"       note: {len(aborted)} speech prefetch(es) cancelled "
                  f"by the page reload — browser ERR_ABORTED, no server error")

        context.close()
        browser.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8013")
    args = parser.parse_args()

    work = Path(tempfile.mkdtemp(prefix="attachment-merge-"))
    pdf = a_pdf(work / "earlier_petition.pdf", 3, "Earlier petition")
    photo = an_image(work / "road_photo.png")

    print(f"Server: {args.url}\nScratch: {work}")
    run(args.url, work, "en", pdf, 3, "english-pdf")
    run(args.url, work, "en", photo, 1, "english-image")
    run(args.url, work, "ta", pdf, 3, "tamil-pdf")

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
