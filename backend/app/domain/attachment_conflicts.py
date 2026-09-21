"""When an attached document disagrees with what the citizen just told us.

A citizen who comes back about an unresolved complaint often attaches the
petition they filed two years ago. That petition carries the address they
lived at two years ago. Both are true; only one of them belongs on the letter
going out today.

The whole of this module is detection. Nothing here resolves anything, and
nothing here writes to the petition. It finds the disagreement, names both
sides, and says where the document's version was read from, so the citizen can
be ASKED. That ordering is the rule the brief and the rest of this service
already keep:

    1. what the citizen has confirmed this time      <- wins by default
    2. a correction the citizen makes when asked
    3. a fact from an attachment they have confirmed
    4. verified reference material
    5. nothing guessed, ever

Silently preferring the document would put an old address on a new petition and
send the reply to a house the petitioner has moved out of. Silently preferring
the current value would throw away the only evidence that the two differ, which
is itself worth their attention — a mismatched name may be a maiden name, or a
misspelling on a government record that needs correcting.

So: ask. Both values, both sources, and the citizen decides.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Which petition field each attachment value is the counterpart of, and how
# strictly to compare them. Only fields where a disagreement actually means
# something: a subject line that differs from last time is not a conflict, it
# is a different complaint.
#
# The two modes are not a refinement, they are a correctness matter.
# "extends" treats one value containing the other as agreement, which is right
# for an address — "72/11 Gandhipuram" and "72/11 Gandhipuram, Coimbatore
# 641012" are one place written at two lengths. Applying the same rule to a
# name says "Harish Kumar" and "Harish Kumaresan" are the same person, which
# is how a petition ends up filed under the wrong name.
COMPARED: tuple[tuple[str, str, str], ...] = (
    ("applicant_name", "petitioner_name", "exact"),
    ("address", "address", "extends"),
)

# Punctuation and case carry no meaning in an address. "80/33, Sidhapudur."
# and "80/33 Sidhapudur" are the same place, and asking a citizen to choose
# between them would be noise that teaches them to dismiss the question.
_NOISE = re.compile(r"[^\w\s]+", re.UNICODE)


def _normalise(value: Any) -> str:
    return " ".join(_NOISE.sub(" ", str(value or "")).casefold().split())


def _same(left: str, right: str, mode: str = "exact") -> bool:
    """Whether two values say the same thing, for the kind of thing they are.

    Both modes ignore case, punctuation and spacing, because none of those
    carry meaning here and asking a citizen to choose between "80/33,
    Sidhapudur." and "80/33 Sidhapudur" would be noise that teaches them to
    dismiss the question.

    `extends` additionally treats one value containing the other as
    agreement — an address with the postcode added is the same address. A
    short value is not allowed to swallow a long one, so "Coimbatore" inside a
    full address is still a disagreement.
    """
    a, b = _normalise(left), _normalise(right)
    if not a or not b:
        return True                      # nothing to disagree about
    if a == b:
        return True
    if mode != "extends":
        return False
    shorter, longer = sorted((a, b), key=len)
    return len(shorter) >= 8 and shorter in longer


@dataclass
class Conflict:
    """One disagreement, with both sides and where each came from."""

    field: str                # the petition field, e.g. "address"
    current: str              # what the citizen confirmed this time
    proposed: str             # what the document says
    attachment_id: str
    filename: str
    where: str = ""           # "page 2", "slide 4", or empty
    confidence: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "current": self.current,
            "proposed": self.proposed,
            "attachment_id": self.attachment_id,
            "filename": self.filename,
            "where": self.where,
            "confidence": round(self.confidence, 2),
        }


def find(fields: dict[str, Any], attachments: Any) -> list[Conflict]:
    """Every disagreement between the current details and the attachments.

    Only CONFIRMED attachments are considered. An extraction the citizen has
    not yet looked at is not yet a claim about anything, and raising a
    conflict against it would be asking them to arbitrate between their own
    address and a string this service has not even shown them.
    """
    from .prior_petition import PriorPetition

    found: list[Conflict] = []
    for attachment in getattr(attachments, "items", []) or []:
        if not getattr(attachment, "confirmed", False):
            continue
        prior = PriorPetition.from_dict(getattr(attachment, "extracted", None))
        if prior is None:
            continue
        for petition_field, prior_field, mode in COMPARED:
            current = fields.get(petition_field)
            value = getattr(prior, prior_field, None)
            if not current or value is None or not value.value.strip():
                continue
            if _same(current, value.value, mode):
                continue
            found.append(Conflict(
                field=petition_field,
                current=str(current),
                proposed=value.value.strip(),
                attachment_id=attachment.attachment_id,
                filename=attachment.filename,
                where=value.where(),
                confidence=value.confidence,
            ))
    return found
