"""OCR, as a capability that may or may not be installed.

The petition workflow does not change when an engine appears. That is the whole
point of this module existing separately from `extraction.py`: the pipeline is

    attachment
      → is there extractable text?
          yes → deterministic extraction
          no  → is an OCR engine available?
                  yes → OCR, at reduced confidence
                  no  → say so, and ask the citizen to type it

and only the fourth line changes when Tesseract is installed. Nothing above it
moves, and nothing below it is skipped: **an OCR result re-enters the same
extraction → confidence → evidence → confirmation pipeline as a text layer
does**, and is never written into a petition field on its own.

Registering an engine is one call. A department running this behind a
government OCR service adds a class with three methods and calls `register`;
`extraction.py` does not learn its name and the conversation does not learn it
exists.

No engine is installed on this machine. `status()` says so, `/api/health` and
the operator screen report it, and photographs come back unreadable rather than
imagined.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Protocol, runtime_checkable

log = logging.getLogger(__name__)

# OCR output never gets the confidence of a real text layer, whatever the engine
# reports about itself. It is good enough to show a citizen for correction and
# never good enough to use without them confirming it — and `LOW_CONFIDENCE` in
# `extraction.py` sits above this deliberately, so every OCR result is flagged.
OCR_CONFIDENCE = 0.45


@runtime_checkable
class OcrEngine(Protocol):
    """Anything that can turn pixels into text.

    `available()` is checked at call time rather than at import: an engine can
    be installed while the service is running, and a deployment should not need
    a restart to start using it.
    """

    name: str

    def available(self) -> bool:
        """Is this engine usable right now?"""
        ...

    def image(self, path: Path) -> str:
        """Text from a photograph. Raises if it cannot."""
        ...

    def pdf(self, path: Path) -> str:
        """Text from a scanned PDF, page by page. Raises if it cannot."""
        ...


class TesseractEngine:
    """The one engine shipped with this service, and it is not bundled.

    Needs the `tesseract` binary on PATH and the `pytesseract` package. For
    Tamil it also needs the Tamil traineddata, which is a separate package on
    most distributions (`tesseract-ocr-tam`) — without it Tamil pages come back
    as noise, which is why `languages()` is reported on the operator screen
    rather than assumed.
    """

    name = "tesseract"

    def available(self) -> bool:
        if not shutil.which("tesseract"):
            return False
        try:
            import pytesseract  # noqa: F401
        except ImportError:
            return False
        return True

    def languages(self) -> list[str]:
        try:
            import pytesseract

            return sorted(pytesseract.get_languages(config=""))
        except Exception:  # noqa: BLE001
            return []

    def _language_argument(self) -> str:
        """Ask for Tamil and English together when both are installed.

        A Tamil petition photographed by a citizen usually has English in it too
        — the reference number, the date, the department's name in the
        letterhead — so requesting one script alone reads the other as noise.
        """
        installed = set(self.languages())
        wanted = [code for code in ("tam", "eng") if code in installed]
        return "+".join(wanted) if wanted else "eng"

    def image(self, path: Path) -> str:
        import pytesseract
        from PIL import Image

        with Image.open(path) as handle:
            return pytesseract.image_to_string(handle, lang=self._language_argument())

    def pdf(self, path: Path) -> str:
        import pymupdf

        pages = []
        with pymupdf.open(path) as document:
            for page in document:
                pages.append(page.get_textpage_ocr(
                    flags=0, language=self._language_argument(), full=True
                ).extractText())
        # Form feed between pages, not a bare newline. A newline is
        # indistinguishable from the line breaks inside a page, so the page a
        # value came from was unrecoverable and a scanned acknowledgement
        # could not be cited as "page 2" the way a text one can. Form feed is
        # whitespace to everything downstream that does not care.
        return "\n\f\n".join(pages)


# The registry. A list rather than one slot so a deployment can install a
# preferred engine ahead of the default without removing it.
_ENGINES: list[OcrEngine] = [TesseractEngine()]


def register(engine: OcrEngine, *, first: bool = True) -> None:
    """Add an engine. Called by a deployment, never by the petition flow."""
    if first:
        _ENGINES.insert(0, engine)
    else:
        _ENGINES.append(engine)
    log.info("ocr.engine_registered", extra={"engine": getattr(engine, "name", "?")})


def active() -> OcrEngine | None:
    """The first engine that is actually usable, or None."""
    for engine in _ENGINES:
        try:
            if engine.available():
                return engine
        except Exception as exc:  # noqa: BLE001 - a broken engine is an absent one
            log.info("ocr.engine_check_failed",
                     extra={"engine": getattr(engine, "name", "?"),
                            "error": str(exc)[:120]})
    return None


def status() -> dict[str, object]:
    """What this machine can do about scanned documents, stated plainly.

    Not cached: an engine installed while the service runs should be picked up,
    and this is called once per health check rather than per request.
    """
    engine = active()
    if engine is None:
        return {
            "available": False,
            "engine": None,
            "languages": [],
            "registered": [getattr(e, "name", "?") for e in _ENGINES],
            "note": (
                "No OCR engine is installed, so photographs and scanned PDFs "
                "cannot be read. The citizen is asked to type those details "
                "instead — nothing is guessed from the image. Install "
                "Tesseract (with tesseract-ocr-tam for Tamil) and the "
                "`pytesseract` package to enable it."
            ),
        }

    languages = list(getattr(engine, "languages", lambda: [])())
    missing = [code for code in ("tam", "eng") if code not in languages]
    note = f"Scanned images and photographed documents are read with {engine.name}."
    if missing and languages:
        note += (f" Language data is missing for {', '.join(missing)}; pages in "
                 f"that script will not be read correctly.")
    note += (" Anything it reads is shown to the citizen with the words it came "
             "from and must be confirmed before the petition can cite it.")
    return {
        "available": True,
        "engine": engine.name,
        "languages": languages,
        "registered": [getattr(e, "name", "?") for e in _ENGINES],
        "note": note,
    }


def read_image(path: Path) -> str | None:
    """Text from a photograph, or None when no engine could read it."""
    engine = active()
    if engine is None:
        return None
    try:
        return engine.image(Path(path))
    except Exception as exc:  # noqa: BLE001
        log.info("ocr.image_failed",
                 extra={"engine": engine.name, "error": str(exc)[:160]})
        return None


def read_pdf(path: Path) -> str | None:
    """Text from a scanned PDF, or None when no engine could read it."""
    engine = active()
    if engine is None:
        return None
    try:
        return engine.pdf(Path(path))
    except Exception as exc:  # noqa: BLE001
        log.info("ocr.pdf_failed",
                 extra={"engine": engine.name, "error": str(exc)[:160]})
        return None
