"""Translation — and, more often, the decision not to translate.

`needs_translation` is the important function in this module. Most letters never
need it: a citizen who spoke Tamil against a template authored in Tamil already
has a Tamil letter, and calling a translator on it would spend a round trip to
produce the text that already exists. The graph asks this question before it
routes to the translate node at all.

The safety machinery below is ported from the Node service's `translation.mjs`
and every piece of it exists because it went wrong in testing:

1.  NUMBER COMPARISON. NLLB renders Indian-style thousands groups with spaces,
    so "12,00,000" comes back as "12 00 000". Comparing raw digit runs then
    reported a changed number where none had changed.
2.  PER-LINE DEGRADATION. One suspect line used to reject the whole job. A
    letter with one line left in the source language and a visible warning is
    more useful, and more honest, than no letter at all.
3.  PINNED TERMS. The model rendered "Coimbatore" as கோயம்பேடூர் — Koyambedu, a
    locality in Chennai — and turned "petitions were disposed" into
    "மனுக்கள் நிராகரிக்கப்பட்டன", petitions were REJECTED. Both are caught
    instantly by a Tamil-speaking reader, so the terms that matter are pinned.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field

import httpx

from ..config import Settings, get_settings

log = logging.getLogger(__name__)

TAMIL = re.compile("[" + chr(0x0B80) + "-" + chr(0x0BFF) + "]")
DEVANAGARI = re.compile("[" + chr(0x0900) + "-" + chr(0x097F) + "]")
LATIN_WORD = re.compile(r"[A-Za-z]{3}")

# The languages a petition can be produced in, and what the translator
# calls them. Adding one here is the whole change: every code below is
# looked up, never derived from "whichever one it is not".
SARVAM_CODE = {"en": "en-IN", "ta": "ta-IN", "hi": "hi-IN"}
SCRIPTS = {"ta": TAMIL, "hi": DEVANAGARI, "en": LATIN_WORD}
LANGUAGES = tuple(SARVAM_CODE)


def script_of(text: str) -> str:
    """Which language's script this text is written in.

    Order matters: an Indic script is decisive, because a Tamil or Hindi line
    routinely carries a Latin word — a place name, an initial, a reference
    number — while a genuinely English line carries neither.
    """
    value = str(text or "")
    if TAMIL.search(value):
        return "ta"
    if DEVANAGARI.search(value):
        return "hi"
    return "en"


def has_letters(text: str) -> bool:
    """Is there anything here that could be translated at all?

    A reference number, a date or a row of digits has no language, and treating
    one as untranslated text is what used to send finished letters back to the
    translator.
    """
    value = str(text or "")
    return bool(TAMIL.search(value) or DEVANAGARI.search(value)
                or LATIN_WORD.search(value))


def language_of(lines: list[str], keep: frozenset[str] | set[str] = frozenset()) -> str:
    """What language a document is currently written in.

    Decided by counting, not by the first line that matches, and with the
    citizen's own verbatim text left out of the count. A petition written in
    English routinely contains a grievance in Tamil — that is the document
    working correctly, and it must not be read as a Tamil petition.
    """
    tally: dict[str, int] = {}
    for line in lines:
        stripped = str(line or "").strip()
        if not stripped or line in keep or stripped in keep or not has_letters(stripped):
            continue
        script = script_of(stripped)
        tally[script] = tally.get(script, 0) + len(stripped)
    if not tally:
        return "en"
    return max(tally, key=lambda key: tally[key])


def needs_translation(
    lines: list[str], target: str, keep: frozenset[str] | set[str] = frozenset()
) -> bool:
    """True only if some line carries content that is not already in `target`.

    This is the guard that keeps the translate node off the critical path for
    the common case. A line with no letters at all — a reference number, a date,
    a row of digits — never needs translating and never counts.

    `keep` holds lines that are reproduced verbatim by rule: the citizen's own
    account of the grievance. They are not evidence that the letter is in the
    wrong language, because they are in whatever language the citizen chose and
    are staying that way. Counting them sent correct letters to a translator.
    """
    for line in lines:
        stripped = str(line or "").strip()
        if not stripped:
            continue
        if line in keep or stripped in keep:
            continue
        if not has_letters(stripped):
            continue
        if script_of(stripped) != target:
            return True
    return False


# --------------------------------------------------------------------------- #
# Number preservation
# --------------------------------------------------------------------------- #

_GROUP_SEP = re.compile(r"(?<=\d)[\s ,](?=\d)")


def _normalise_digits(text: str) -> str:
    """Digit-group separators are presentation, not value."""
    return _GROUP_SEP.sub("", str(text or ""))


def _numbers(text: str) -> str:
    return "|".join(sorted(re.findall(r"\d+(?:\.\d+)*", _normalise_digits(text))))


def numbers_preserved(source: str, translated: str) -> bool:
    """Every figure in the source must survive into the translation, unchanged."""
    return _numbers(source) == _numbers(translated)


# --------------------------------------------------------------------------- #
# Pinned terms
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class PinnedTerm:
    source: re.Pattern[str]
    wrong: re.Pattern[str]
    correct: str


PINNED: tuple[PinnedTerm, ...] = (
    # Place names. Koyambedu is a different city entirely.
    PinnedTerm(re.compile(r"\bCoimbatore\b", re.I), re.compile(r"கோயம்பேடூ\S*|கோயம்பேட்டை"), "கோயம்புத்தூர்"),
    PinnedTerm(re.compile(r"\bTamil ?Nadu\b", re.I), re.compile(r"தமிழ் நாடு"), "தமிழ்நாடு"),
    # Meaning inversions. "Disposed" in Indian administrative English means
    # completed or settled — never rejected.
    PinnedTerm(re.compile(r"\bdispos(?:e|ed|al|ing)\b", re.I), re.compile(r"நிராகரிக்கப்பட்ட\S*"), "தீர்வு காணப்பட்டன"),
    PinnedTerm(re.compile(r"\bpending\b", re.I), re.compile(r"நிராகரிக்கப்பட்ட\S*"), "நிலுவையில் உள்ளன"),
    # A certificate that says "rejected" where the citizen asked for "issued"
    # is worse than an untranslated line.
    PinnedTerm(re.compile(r"\bissued?\b", re.I), re.compile(r"நிராகரிக்கப்பட்ட\S*"), "வழங்கப்பட்டது"),
)


def apply_pinned(source: str, translated: str, target: str) -> str:
    """Repair known-bad output, using the source line to decide what was meant."""
    if target != "ta" or not translated:
        return translated
    out = translated
    for term in PINNED:
        if term.source.search(source) and term.wrong.search(out):
            out = term.wrong.sub(term.correct, out)
    return out


# --------------------------------------------------------------------------- #
# Result
# --------------------------------------------------------------------------- #


@dataclass
class TranslationResult:
    lines: list[str]
    warnings: list[str] = field(default_factory=list)
    engine: str = "none"
    translated_count: int = 0

    @property
    def degraded(self) -> bool:
        return bool(self.warnings)


# --------------------------------------------------------------------------- #
# Sarvam (Mayura) — Indic-first, preferred when configured
# --------------------------------------------------------------------------- #


async def _translate_via_sarvam(
    lines: list[str], target: str, s: Settings, warnings: list[str],
    source: str = "en",
) -> list[str] | None:
    keys = s.sarvam_key_list
    if not keys:
        return None

    # Both ends are named. This used to read "whichever of the two it is not",
    # which had no answer once there were three.
    source_code = SARVAM_CODE.get(source, "en-IN")
    target_code = SARVAM_CODE.get(target, "en-IN")
    out = list(lines)
    todo = [
        (i, text)
        for i, text in enumerate(lines)
        if text.strip() and has_letters(text)
        and script_of(text) != target
    ]
    if not todo:
        return out

    # A key that is out of quota should not cost every remaining line a failure,
    # so the working key is remembered for the rest of the batch.
    active = 0
    lock = asyncio.Lock()

    async def one(client: httpx.AsyncClient, index: int, text: str) -> None:
        nonlocal active
        body = {
            "input": text[:1000],
            "source_language_code": source_code,
            "target_language_code": target_code,
            "speaker_gender": "Male",
            "mode": "formal",
            "model": "mayura:v1",
            "enable_preprocessing": True,
        }
        translated, last_status = "", 0
        for offset in range(len(keys)):
            key = keys[(active + offset) % len(keys)]
            try:
                response = await client.post(
                    "https://api.sarvam.ai/translate",
                    headers={"api-subscription-key": key, "Content-Type": "application/json"},
                    json=body,
                    timeout=30.0,
                )
            except httpx.HTTPError:
                break
            if response.status_code < 400:
                translated = (response.json() or {}).get("translated_text", "")
                async with lock:
                    active = (active + offset) % len(keys)
                break
            last_status = response.status_code
            # Only a credential or quota problem is worth another key.
            if response.status_code not in (401, 402, 403, 429):
                break

        if not translated.strip():
            warnings.append(
                f"Line {index + 1} is shown in the original language: "
                f"the translator returned nothing{f' (HTTP {last_status})' if last_status else ''}."
            )
            return
        translated = apply_pinned(text, translated, target)
        if not numbers_preserved(text, translated):
            warnings.append(
                f"Line {index + 1} is shown in the original language: the translation altered a figure."
            )
            return
        out[index] = translated

    # Modest concurrency: fast enough for a live session, gentle on the quota.
    semaphore = asyncio.Semaphore(4)

    async def guarded(client: httpx.AsyncClient, index: int, text: str) -> None:
        async with semaphore:
            await one(client, index, text)

    async with httpx.AsyncClient() as client:
        await asyncio.gather(*(guarded(client, i, t) for i, t in todo))

    # Nothing translated at all means the provider is effectively down; let the
    # caller fall through to the local worker rather than ship the source text.
    if not any(out[i] != text for i, text in todo):
        return None
    return out


# --------------------------------------------------------------------------- #
# Local NLLB worker — the on-premise option
# --------------------------------------------------------------------------- #


async def _translate_via_worker(
    lines: list[str], target: str, s: Settings, warnings: list[str]
) -> list[str] | None:
    """Drive the Node NLLB worker as a subprocess, one JSON batch per line.

    The worker is reused as-is from the existing runtime assets rather than
    reimplemented: it already holds a warmed ONNX session, and re-hosting the
    model in this process would double the memory for no gain.
    """
    from pathlib import Path

    worker = Path(s.nllb_worker) if s.nllb_worker else None
    if not worker or not worker.exists():
        return None

    todo = [
        (i, text)
        for i, text in enumerate(lines)
        if text.strip() and has_letters(text)
        and script_of(text) != target
    ]
    if not todo:
        return list(lines)

    batches = [todo[i : i + 8] for i in range(0, len(todo), 8)]
    env = {"NLLB_MODEL_DIR": s.nllb_model_dir} if s.nllb_model_dir else None

    import json as _json
    import os

    process = await asyncio.create_subprocess_exec(
        "node", str(worker),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, **(env or {})},
    )

    request = "".join(
        _json.dumps({"id": bid, "source": "en" if target == "ta" else "ta",
                     "target": target, "texts": [t for _, t in batch]}) + "\n"
        for bid, batch in enumerate(batches)
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(request.encode("utf-8")), timeout=300
        )
    except TimeoutError:
        process.kill()
        warnings.append("The local translation worker did not finish in time.")
        return None

    if process.returncode not in (0, None) and not stdout:
        log.warning("nllb.worker.failed", extra={"stderr": stderr.decode("utf-8", "replace")[-500:]})
        return None

    out = list(lines)
    translated_any = False
    for raw in stdout.decode("utf-8", "replace").splitlines():
        if not raw.strip():
            continue
        try:
            message = _json.loads(raw)
        except ValueError:
            continue
        if not message.get("ok"):
            continue
        batch = batches[message["id"]]
        results = message.get("translations") or []
        if len(results) != len(batch):
            warnings.append("An incomplete translation batch was discarded.")
            continue
        for (index, source_text), candidate in zip(batch, results, strict=True):
            fixed = apply_pinned(source_text, candidate or "", target)
            if not fixed.strip():
                warnings.append(f"Line {index + 1} came back empty and is shown in the original language.")
                continue
            if not numbers_preserved(source_text, fixed):
                warnings.append(f"Line {index + 1} is shown in the original language: the translation altered a figure.")
                continue
            out[index] = fixed
            translated_any = True

    return out if translated_any else None


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #


async def translate_lines(
    lines: list[str],
    target: str,
    settings: Settings | None = None,
    keep: frozenset[str] | set[str] = frozenset(),
    source: str | None = None,
) -> TranslationResult:
    """Translate an ordered line list, returning a list of the SAME length.

    Lines that could not be safely translated come back unchanged, with the
    reason in `warnings`, so the caller can map the result straight back onto
    the letter and still tell the citizen what was left alone.
    """
    s = settings or get_settings()
    warnings: list[str] = []

    if not needs_translation(lines, target, keep):
        return TranslationResult(lines=list(lines), engine="skipped")

    # Read off the document when the caller does not say. The composition path
    # knows (it authors in English); a citizen asking for a different language
    # after the fact does not, and the document itself is the evidence.
    origin = source or language_of(lines, keep)
    out = await _translate_via_sarvam(lines, target, s, warnings, source=origin)
    engine = "sarvam"
    if out is None:
        warnings.clear()
        out = await _translate_via_worker(lines, target, s, warnings)
        engine = "nllb"
    if out is None:
        raise RuntimeError("No translation engine is available.")

    # A whole document that came back without a single character of the target
    # script means the model did not do the job at all — that is worth refusing
    # rather than handing over a letter that claims to be translated.
    expected = SCRIPTS.get(target)
    if expected is not None:
        translatable = sum(1 for line in lines
                           if has_letters(line) and script_of(line) != target)
        produced = sum(1 for line in out if expected.search(line))
        if translatable > 2 and produced == 0:
            raise RuntimeError(f"Translation to {target!r} produced none of its script.")

    # Whatever the engine did with the verbatim lines, they go back exactly as
    # they were. Restoring here rather than withholding them from the request
    # keeps the line count identical, which is what makes the result mappable
    # back onto the letter — and means no engine can quietly reword the
    # citizen's complaint, however it was called.
    if keep:
        out = [
            original if (original in keep or original.strip() in keep) else translated
            for original, translated in zip(lines, out, strict=True)
        ]

    translated_count = sum(1 for a, b in zip(lines, out, strict=True) if a != b)
    return TranslationResult(lines=out, warnings=warnings, engine=engine,
                             translated_count=translated_count)
