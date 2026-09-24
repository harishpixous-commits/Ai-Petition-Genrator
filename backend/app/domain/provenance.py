"""Where every value came from, kept apart by construction.

WHY THIS EXISTS. A petition went out under a name belonging to nobody. The
citizen had typed "Harish". An attached PDF belonged to "சேதுபாலா". OCR read
that as "சேபாலா" — a syllable short of the name actually on the page — and the
misreading was offered as a one-click replacement for a name that had been
typed correctly. Three different values for one field, and at the point they
met, nothing said which was which.

THE RULE, in priority order:

    1. the citizen's confirmed data
    2. the citizen's corrections
    3. confirmed attachment evidence
    4. verified government RAG
    5. never a guess

A flat dictionary cannot express that order. Once "Harish" and "சேபாலா" are
both just strings under the key `applicant_name`, the last writer wins and the
question of which one had the better claim is gone. So they are never put in
the same dictionary: `context()` returns them in separate compartments and
the composer is handed that, not a merge.

WHAT THIS MODULE DOES NOT DO. It does not decide. It labels, separates, and
refuses to combine. Deciding is `attachment_conflicts` (which reports a
disagreement and, for a name, does not offer the swap) and the citizen.
"""

from __future__ import annotations

from typing import Any

# The only sources a value on a petition may have. A value with no source is
# a guess, and a guess does not go on a government form.
CITIZEN = "citizen"
ATTACHMENT = "attachment"
RAG = "verified_rag"

# Fields an attachment may NEVER supply on its own authority, however
# confidently it was read. These are the citizen's identity and their
# complaint; a document is evidence about them, never a source for them.
#
# BOTH NAMING CONVENTIONS ARE LISTED, and the omission was caught by a test.
# The petition calls the field `applicant_name`; `prior_petition` calls what
# it reads off a page `petitioner_name`. A set holding only the first looks
# complete and protects nothing, because the value arriving from a document
# never carries that name.
NEVER_FROM_ATTACHMENT = frozenset({
    # as the petition names them
    "applicant_name", "age", "mobile", "address", "aadhaar", "grievance",
    # as `prior_petition` names what it read
    "petitioner_name",
})


def citizen_fact(key: str, value: Any, *, confirmed: bool = True) -> dict[str, Any]:
    """A value the citizen gave. The highest authority there is."""
    return {"key": key, "value": value, "source_type": CITIZEN,
            "confirmed": bool(confirmed)}


def attachment_fact(key: str, extracted: Any, attachment: Any) -> dict[str, Any]:
    """A value read out of a document, with enough to check it by.

    `evidence` and `page` are not decoration: the citizen is shown them beside
    the value and asked whether it is right, which is only a meaningful
    question if they can see where it came from.
    """
    return {
        "key": key,
        "value": getattr(extracted, "value", None),
        "source_type": ATTACHMENT,
        "attachment_id": getattr(attachment, "attachment_id", ""),
        "filename": getattr(attachment, "filename", ""),
        "page": getattr(extracted, "page", 0),
        "unit": getattr(extracted, "unit", ""),
        "evidence": getattr(extracted, "evidence", ""),
        "confidence": round(float(getattr(extracted, "confidence", 0.0)), 2),
        # Whose document this came out of, as System-1 classified it. An
        # officer reading a value needs to know it was read off somebody
        # else's paperwork.
        "relationship": (getattr(attachment, "relationship", None) or {}).get("value"),
        # Never true for anything in NEVER_FROM_ATTACHMENT.
        "may_fill_petition_field": key not in NEVER_FROM_ATTACHMENT,
    }


def context(fields: dict[str, Any], enclosed: Any = None,
            knowledge: Any = None) -> dict[str, Any]:
    """The compartments composition is allowed to see.

    Deliberately NOT a merge. Each compartment is a separate key, so a
    composer cannot read an attachment value where it meant to read the
    citizen's without naming the compartment it took it from.
    """
    from .prior_petition import PriorPetition

    citizen = {key: citizen_fact(key, value)
               for key, value in (fields or {}).items() if value not in (None, "")}

    evidence: list[dict[str, Any]] = []
    for attachment in getattr(enclosed, "items", []):
        # UNCONFIRMED EVIDENCE IS NOT EVIDENCE. Until the citizen has looked
        # at what was read and said it is right, it is a regular expression's
        # opinion about a photograph.
        if not getattr(attachment, "confirmed", False):
            continue
        prior = PriorPetition.from_dict(getattr(attachment, "extracted", None))
        if prior is None:
            continue
        for key in ("petitioner_name", "reference_number", "submitted_on",
                    "address", "subject", "department", "authority"):
            found = getattr(prior, key, None)
            if found and str(getattr(found, "value", "")).strip():
                evidence.append(attachment_fact(key, found, attachment))

    return {
        "current_citizen_facts": citizen,
        "confirmed_attachment_evidence": evidence,
        "verified_rag_context": knowledge or {},
    }


def petitioner_fields(context_: dict[str, Any]) -> dict[str, Any]:
    """The petitioner block, built from the citizen compartment ALONE.

    This function is the answer to "how do we know an attachment value cannot
    reach the petitioner block" — it cannot read the other compartments. It
    takes the whole context and looks in exactly one of them.
    """
    return {key: fact["value"]
            for key, fact in (context_.get("current_citizen_facts") or {}).items()}
