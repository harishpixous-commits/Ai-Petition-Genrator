"""The SRS-aligned view of a petition's status, derived from the internal state.

TWO VOCABULARIES, deliberately kept separate.

The SRS §3.3 names ten lifecycle states — Draft, Capturing, Transcribing,
Needs clarification, Ready for review, Approved by citizen, Exported,
Submitted/Received, Failed and Interrupted — which is the vocabulary an
officer, a reviewer or a policy document is written in. The internal state
machine uses a seven-value vocabulary from `graph/state.py` — collecting,
attachments, confirming, generating, ready, cancelled, failed — which is
the one every node, test and petition record is written against.

Renaming the internal set to match the SRS would ripple through ~90 call
sites, each of which is a correct call today. Keeping two vocabularies out
of sync is how the officer screen comes to say one thing and the audit log
another. The compromise, which is what this module exists for, is: ONE
truth in the state (the internal word), and one derived function that says
what that corresponds to in the SRS wording, including the two that are not
status values at all (`Exported`, `Submitted/Received`) but are derived
from "the petition has a document" and "the submission timestamp is set".

This never changes behaviour — it only produces a label. The internal
status remains the single source of truth; this is the formatter.
"""

from __future__ import annotations

from typing import Any

#: Internal status -> SRS label for the pure-status cases.
_SRS = {
    "collecting":  "Draft",
    "attachments": "Capturing",
    "confirming":  "Needs clarification",
    "generating":  "Transcribing",
    "ready":       "Ready for review",
    "cancelled":   "Interrupted",
    "failed":      "Failed",
}


def srs_label(state: dict[str, Any] | None) -> dict[str, Any]:
    """A view of the status every caller can share.

    Returned shape:

      {
        "internal":  "ready",
        "srs":       "Ready for review" | "Exported" | "Submitted" | …,
        "exported":  bool,          # a DOCX/PDF has been produced
        "submitted": bool,          # the citizen pressed Submit — NOT a real
                                    # government filing
      }

    `exported` and `submitted` are reported separately from `srs` because
    some callers want the single string to render in a badge and others
    want each state independently. "Submitted" here means a locally
    recorded "I'm finished" — AC-17 is the real official submission and
    requires an authoritative integration this product does not have.
    """
    state = state or {}
    internal = state.get("status")
    document = state.get("document") or {}
    exported = bool(document.get("docx"))
    submitted = bool(state.get("submitted_at"))

    if submitted and internal == "ready":
        label = "Submitted (local record only — not an official filing)"
    elif exported and internal == "ready":
        label = "Exported"
    else:
        label = _SRS.get(internal or "", internal or "unknown")

    return {
        "internal": internal,
        "srs": label,
        "exported": exported,
        "submitted": submitted,
    }
