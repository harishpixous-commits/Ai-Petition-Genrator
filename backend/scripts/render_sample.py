"""Render a sample petition and rasterise it, so the output can be LOOKED AT.

Tamil correctness cannot be established by asserting that a PDF file exists.
Vowel signs reorder around the consonant they attach to, and a converter without
OpenType shaping produces a file of the right size, with the right text layer,
that is unreadable on the page. The only check that catches that is a human
looking at an image of the page.

Run this on any machine you are about to deploy to, with the converter that
machine will actually use:

    python scripts/render_sample.py                 # both languages, default engine
    PDF_ENGINE=libreoffice python scripts/render_sample.py
    python scripts/render_sample.py --lang ta --out /tmp/check

PNG rasterisation needs PyMuPDF (`pip install -r requirements-dev.txt`). Without
it the DOCX and PDF are still written and the script says so.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.domain.letter import build_letter_text  # noqa: E402
from app.domain.templates import the_template  # noqa: E402
from app.services.render import pdf_available, render_docx, render_pdf  # noqa: E402

# Deliberately awkward content: a multi-paragraph grievance with digits and
# punctuation, a long address, and an identifier that must stay grouped.
SAMPLES = {
    "en": {
        "applicant_name": "Ravi Kumar",
        "age": 45,
        "address": "12 Gandhi Street, Peelamedu, Coimbatore - 641004",
        "aadhaar": "234567890124",
        "grievance": (
            "The street light outside my house has not worked since 12/03/2026.\n"
            "During the rains the road floods and is impassable.\n\n"
            "I complained twice at the panchayat office and paid Rs. 1,500 for a "
            "connection, but no receipt was issued."
        ),
    },
    "ta": {
        "applicant_name": "ரவி குமார்",
        "age": 45,
        "address": "12 காந்தி தெரு, பீளமேடு, கோயம்புத்தூர் - 641004",
        "aadhaar": "234567890124",
        "grievance": (
            "எனது வீட்டின் முன் உள்ள தெருவிளக்கு மூன்று மாதங்களாக எரியவில்லை.\n"
            "மழைக்காலத்தில் சாலையில் நீர் தேங்கி நிற்கிறது.\n\n"
            "நான் இரண்டு முறை ஊராட்சி அலுவலகத்தில் புகார் அளித்தேன். இதுவரை நடவடிக்கை இல்லை."
        ),
    },
}


async def render(language: str, out_dir: Path) -> None:
    settings = get_settings()
    text = build_letter_text(
        template=the_template(),
        fields=SAMPLES[language],
        language=language,
        composition=None,
        session_id=f"sample-0000-0000-0000-{language}00000001",
    )
    docx = render_docx(text, out_dir / f"sample-{language}.docx",
                       reference=f"AP/2026/SAMPLE-{language.upper()}", settings=settings)
    print(f"  DOCX  {docx}  ({docx.stat().st_size:,} bytes)")

    pdf, error = await render_pdf(docx, settings)
    if not pdf:
        print(f"  PDF   not produced: {error}")
        return
    print(f"  PDF   {pdf}  ({pdf.stat().st_size:,} bytes)")

    try:
        import pymupdf
    except ImportError:
        print("  PNG   skipped: pip install -r requirements-dev.txt to rasterise")
        return

    document = pymupdf.open(pdf)
    for number in range(document.page_count):
        image = out_dir / f"sample-{language}-p{number + 1}.png"
        document[number].get_pixmap(dpi=140).save(str(image))
        print(f"  PNG   {image}")
    print("  --> open the PNGs and read them. Check that Tamil vowel signs sit")
    print("      on the correct consonant and that nothing renders as a box.")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lang", choices=["en", "ta", "both"], default="both")
    parser.add_argument("--out", type=Path, default=Path("var/samples"))
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    ok, note = pdf_available()
    print(f"PDF engine: {get_settings().pdf_engine}  ({'available' if ok else 'unavailable'})")
    print(f"            {note}\n")

    for language in (["en", "ta"] if args.lang == "both" else [args.lang]):
        print(f"{language}:")
        await render(language, args.out)
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
