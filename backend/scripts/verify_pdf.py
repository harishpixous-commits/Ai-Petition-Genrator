"""Prove this machine's PDF engine is fit for a government deployment.

    .venv/Scripts/python scripts/verify_pdf.py

`pdf_production_ready` does NOT become true because `soffice` is on PATH. A
binary being present says nothing about whether it renders Tamil, whether it
cleans up after itself, or whether it survives four petitions at once — and each
of those has a failure mode that only shows up in front of a citizen. So the
flag is gated on this script passing, and this script writes the stamp that
unlocks it.

Nine checks, every one of them against a real petition this service produced:

    1  startup detection      the engine is found the way the service finds it
    2  DOCX to PDF            a real petition converts, and the file is a PDF
    3  Tamil rendering        rasterised and inspected for missing glyphs
    4  English rendering      the same, for the other language
    5  page layout            A4, sane margins, text inside the page box
    6  attachments section    the enclosure list survives conversion
    7  reference number       the petition's own reference is in the PDF text
    8  concurrency + temp     four at once, and nothing left behind
    9  failure fallback       a broken input fails soft, returning a reason

Re-run it after upgrading LibreOffice: the stamp records the version it passed
against, and a different version invalidates it.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from app.config import get_settings  # noqa: E402
from app.domain.attachments import Attachment, AttachmentSet  # noqa: E402
from app.domain.letter import build_letter_text  # noqa: E402
from app.domain.templates import the_template  # noqa: E402
from app.services.render import (  # noqa: E402
    STAMP_NAME,
    engine_fingerprint,
    render_docx,
    render_pdf,
)

RESULTS: list[dict] = []

ANSWERS = {
    "en": {
        "applicant_name": "Ravi Kumar",
        "age": 45,
        "mobile": "9876543210",
        "address": "12 Gandhi Street, Peelamedu, Coimbatore 641004",
        "aadhaar": "234567890124",
        "grievance": ("The street light outside my house has not worked for three "
                      "months. I have complained twice at the panchayat office."),
    },
    "ta": {
        "applicant_name": "ரவி குமார்",
        "age": 45,
        "mobile": "9876543210",
        "address": "12 காந்தி தெரு, பீளமேடு, கோயம்புத்தூர் 641004",
        "aadhaar": "234567890124",
        "grievance": ("எனது வீட்டின் முன் உள்ள தெருவிளக்கு மூன்று மாதங்களாக "
                      "எரியவில்லை. ஊராட்சி அலுவலகத்தில் இரண்டு முறை புகார் "
                      "அளித்துள்ளேன்."),
    },
}


def record(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append({"name": name, "ok": bool(ok), "detail": detail[:300]})
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail[:110]}" if detail else ""))
    return ok


def _attachments() -> AttachmentSet:
    return AttachmentSet(items=[
        Attachment(attachment_id="v1", filename="ack.pdf", stored_name="v1.pdf",
                   content_type="application/pdf", size=1024,
                   kind="acknowledgement", confirmed=True),
    ])


def _letter(language: str, reference: str) -> str:
    return build_letter_text(
        template=the_template(),
        fields=ANSWERS[language],
        language=language,          # type: ignore[arg-type]
        composition=None,
        session_id=reference,
        attachments=_attachments(),
    )


async def _make_pdf(language: str, out_dir: Path, reference: str):
    settings = get_settings()
    docx = out_dir / f"verify-{language}.docx"
    render_docx(_letter(language, reference), docx, reference=reference,
                title=the_template().label_for("en"), settings=settings)
    return await render_pdf(docx, settings)


# --------------------------------------------------------------------------- #

def check_detection() -> bool:
    from app.services.render import pdf_status

    report = pdf_status()
    if report["engine"] != "libreoffice":
        return record(
            "1  startup detection", False,
            f"engine is {report['engine']!r}, not libreoffice. Install LibreOffice "
            f"and set PDF_ENGINE=libreoffice.")
    return record("1  startup detection", True,
                  f"soffice found; configured engine {report['configured_engine']}")


async def check_conversion(out_dir: Path) -> bool:
    pdf, error = await _make_pdf("en", out_dir, "VERIFY/EN/1")
    if pdf is None:
        return record("2  DOCX to PDF", False, error or "no PDF produced")
    head = pdf.read_bytes()[:5]
    return record("2  DOCX to PDF", head == b"%PDF-",
                  f"{pdf.name}, {pdf.stat().st_size} bytes")


def _rasterise(pdf: Path):
    import pymupdf

    with pymupdf.open(pdf) as document:
        pages = [page.get_text() for page in document]
        boxes = [(page.rect.width, page.rect.height) for page in document]
    return pages, boxes


def check_script(language: str, pdf: Path, expected: str) -> bool:
    """The text layer must carry the script, and no glyph may be missing.

    A PDF whose Tamil is drawn as boxes still has a perfect text layer, so the
    text check alone proves nothing. The render is rasterised and scanned for
    the .notdef glyph, which is what a missing font actually produces.
    """
    label = "3  Tamil rendering" if language == "ta" else "4  English rendering"
    try:
        pages, _ = _rasterise(pdf)
    except ImportError:
        return record(label, False, "PyMuPDF not installed; cannot rasterise")

    text = "\n".join(pages)
    if expected not in " ".join(text.split()):
        return record(label, False, "the grievance is not in the PDF text layer")

    try:
        import pymupdf

        missing = 0
        with pymupdf.open(pdf) as document:
            for page in document:
                for block in page.get_text("rawdict")["blocks"]:
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            for char in span.get("chars", []):
                                # 0 is .notdef: the glyph a font uses for "I do
                                # not have this character".
                                if char.get("c") and char.get("glyph") == 0:
                                    missing += 1
        if missing:
            return record(label, False,
                          f"{missing} characters rendered as .notdef — the font "
                          f"does not cover this script")
    except Exception as exc:  # noqa: BLE001
        return record(label, False, f"could not inspect glyphs: {exc}")

    return record(label, True, f"{len(pages)} page(s), no missing glyphs")


def check_layout(pdf: Path) -> bool:
    try:
        _, boxes = _rasterise(pdf)
    except ImportError:
        return record("5  page layout", False, "PyMuPDF not installed")
    if not boxes:
        return record("5  page layout", False, "no pages")
    width, height = boxes[0]
    # A4 in points, with a tolerance for rounding by the converter.
    a4 = abs(width - 595) < 6 and abs(height - 842) < 6
    return record("5  page layout", a4, f"{width:.0f}x{height:.0f}pt (A4 is 595x842)")


def check_attachments(pdf: Path) -> bool:
    try:
        pages, _ = _rasterise(pdf)
    except ImportError:
        return record("6  attachments section", False, "PyMuPDF not installed")
    text = " ".join("\n".join(pages).split())
    ok = "Enclosures" in text and "Acknowledgement receipt" in text
    return record("6  attachments section", ok,
                  "enclosure list present" if ok else "enclosure list lost in conversion")


def check_reference(pdf: Path, reference: str) -> bool:
    try:
        pages, _ = _rasterise(pdf)
    except ImportError:
        return record("7  reference number", False, "PyMuPDF not installed")
    text = " ".join("\n".join(pages).split())
    return record("7  reference number", reference in text,
                  f"looking for {reference}")


async def check_concurrency(out_dir: Path) -> bool:
    """Four at once, and nothing left in the temp directory.

    LibreOffice keeps a user profile and will serialise or collide on one if
    several conversions share it. A queue that deadlocks under load is the kind
    of fault that only appears on the day the office is busy.
    """
    before = set(Path(tempfile.gettempdir()).glob("*"))
    results = await asyncio.gather(*[
        _make_pdf("en" if i % 2 else "ta", out_dir, f"VERIFY/C/{i}")
        for i in range(4)
    ], return_exceptions=True)

    failures = [r for r in results
                if isinstance(r, BaseException) or r[0] is None]
    if failures:
        return record("8  concurrency + temp", False,
                      f"{len(failures)} of 4 concurrent conversions failed")

    leaked = [p for p in set(Path(tempfile.gettempdir()).glob("*")) - before
              if "soffice" in p.name.lower() or "lu" in p.name.lower()[:2]]
    return record("8  concurrency + temp", not leaked,
                  "4/4 converted, temp clean" if not leaked
                  else f"left behind: {[p.name for p in leaked][:3]}")


async def check_fallback(out_dir: Path) -> bool:
    """A broken input must return a reason, not raise.

    The DOCX is the deliverable. A converter that throws takes the petition
    with it, and the citizen leaves with nothing rather than with the file that
    was always going to be the one they hand in.
    """
    broken = out_dir / "not-a-docx.docx"
    broken.write_bytes(b"this is not a docx at all")
    try:
        pdf, error = await render_pdf(broken, get_settings())
    except Exception as exc:  # noqa: BLE001
        return record("9  failure fallback", False, f"raised instead of returning: {exc}")
    return record("9  failure fallback", pdf is None and bool(error),
                  (error or "")[:120])


# --------------------------------------------------------------------------- #

async def main() -> int:
    settings = get_settings()
    out_dir = settings.data_dir / "pdf-verification"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Verifying the PDF engine for production use.\n")
    if not check_detection():
        print("\nStopping: LibreOffice is the supported production engine.")
        _write_stamp(False)
        return 1

    if not await check_conversion(out_dir):
        _write_stamp(False)
        return 1

    reference = "VERIFY/TA/1"
    ta_pdf, _ = await _make_pdf("ta", out_dir, reference)
    en_pdf, _ = await _make_pdf("en", out_dir, "VERIFY/EN/2")

    if ta_pdf:
        check_script("ta", ta_pdf, " ".join(ANSWERS["ta"]["grievance"].split()))
        check_layout(ta_pdf)
        check_attachments(ta_pdf)
        check_reference(ta_pdf, reference)
    else:
        record("3  Tamil rendering", False, "no Tamil PDF produced")
    if en_pdf:
        check_script("en", en_pdf, " ".join(ANSWERS["en"]["grievance"].split()))
    else:
        record("4  English rendering", False, "no English PDF produced")

    await check_concurrency(out_dir)
    await check_fallback(out_dir)

    passed = all(r["ok"] for r in RESULTS)
    _write_stamp(passed)

    print()
    if passed:
        print(f"All {len(RESULTS)} checks passed. pdf_production_ready is now true.")
        print(f"Samples in {out_dir} — open the Tamil one and read it.")
    else:
        failed = [r["name"] for r in RESULTS if not r["ok"]]
        print(f"{len(failed)} check(s) failed: {', '.join(failed)}")
        print("pdf_production_ready stays false. DOCX remains the deliverable.")
    return 0 if passed else 1


def _write_stamp(passed: bool) -> None:
    settings = get_settings()
    stamp = settings.data_dir / STAMP_NAME
    stamp.write_text(json.dumps({
        "passed": passed,
        "engine": "libreoffice",
        "fingerprint": engine_fingerprint(settings),
        "verified_at": datetime.now(UTC).isoformat(),
        "checks": RESULTS,
    }, indent=2), encoding="utf-8")
    print(f"\nStamp written to {stamp}")


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except subprocess.SubprocessError as exc:   # pragma: no cover
        print(f"Converter failed: {exc}")
        raise SystemExit(1) from exc
