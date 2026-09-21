"""Identifier masking, applied at the boundary where text leaves this machine.

Ported from the Node service's `mask.mjs`, where it sits between the application
and every external model provider. It has its own module for the same reason
there: everything depends on it, and giving it no dependencies of its own is
what keeps the import graph acyclic.

This is a reduction of exposure, not anonymisation. A masked petition can still
be re-identified from its content by anyone who already knows the case. It exists
so that an accidental provider-side log of a request body does not contain a
readable Aadhaar number — not so that citizen text can be treated as harmless.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Aadhaar, however it was grouped when it was written down.
    (re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}\b"), "[IDENTIFIER REDACTED]"),
    (re.compile(r"(?:\+91[ -]?)?\b[6-9]\d{9}\b"), "[PHONE REDACTED]"),
    (re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"), "[EMAIL REDACTED]"),
    (re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"), "[PAN REDACTED]"),
    (re.compile(r"\b[A-Z]{3}[0-9]{7}\b"), "[VOTER ID REDACTED]"),
    # Bank accounts and anything else long and numeric. Runs last so that the
    # more specific patterns above have already claimed what is theirs.
    (re.compile(r"\b\d{9,18}\b"), "[ACCOUNT REDACTED]"),
)


# Masking for the SCREEN, which is a different job from the redaction above.
#
# Text leaving the machine is redacted outright: the provider has no business
# knowing an Aadhaar number exists. Text shown back to the citizen is a
# different matter — they need to recognise WHICH card the document was read
# from, and "[IDENTIFIER REDACTED]" tells them nothing. The last four digits
# are what every Indian bank, telco and utility shows for exactly this reason.
#
# Deliberately only these two patterns. The catch-all `\d{9,18}` above would
# swallow a government reference number like 2026/PG/44710012, and mangling
# the one value the petition most needs to quote would be a worse failure
# than the one this prevents.
# Both patterns allow the internal grouping the numbers are actually written
# with. The mobile one matters most: this service PRINTS "+91 93441 74752" on
# every petition it produces, so a pattern requiring ten consecutive digits
# fails on the service's own output — which is precisely the document a
# returning citizen attaches.
# The national number is CAPTURED, and the country code is matched but left
# outside the group. Counting digits across the whole match instead made
# "+91 93441 74752" twelve digits, which failed the ten-digit check and left
# a mobile number in the clear — while a bare "9344174752" was masked.
#
# Mobiles are tried before Aadhaar so that "+919344174752" is recognised as
# the phone it is rather than as twelve anonymous digits.
_DISPLAY: tuple[tuple[re.Pattern[str], int], ...] = (
    (re.compile(r"(?:\+91[ -]?)?\b([6-9]\d{4}[ -]?\d{5})\b"), 10),
    (re.compile(r"(?:\+91[ -]?)?\b([6-9]\d{9})\b"), 10),
    (re.compile(r"\b(\d{4}[ -]?\d{4}[ -]?\d{4})\b"), 12),
)


def _keep_last_four(match: re.Match[str], digits: int) -> str:
    raw = re.sub(r"\D", "", match.group(1))
    if len(raw) != digits:
        return match.group(0)
    hidden = "XXXX XXXX " if digits == 12 else "XXXXXX"
    return f"{hidden}{raw[-4:]}"


def mask_for_display(text: str) -> str:
    """Hide identifiers but leave the last four digits readable.

    Applied to anything read OUT of an attachment before it is stored on the
    session or shown on a confirmation card. A previous petition carries the
    petitioner's Aadhaar and mobile in its own header, and the evidence
    snippet shown beside an extracted value is a line of that document — so
    without this, confirming a reference number could put a full Aadhaar on
    screen and into the checkpoint.
    """
    out = str(text or "")
    for pattern, digits in _DISPLAY:
        out = pattern.sub(lambda m, d=digits: _keep_last_four(m, d), out)
    return out


def mask_pii(text: str, names: Iterable[str] = ()) -> str:
    """Redact identifiers, and any supplied names, from `text`."""
    out = str(text or "")
    for pattern, replacement in _PATTERNS:
        out = pattern.sub(replacement, out)
    for name in names:
        candidate = str(name or "").strip()
        if len(candidate) > 2:
            out = out.replace(candidate, "[PERSON]")
    return out
