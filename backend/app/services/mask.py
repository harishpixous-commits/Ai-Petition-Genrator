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
