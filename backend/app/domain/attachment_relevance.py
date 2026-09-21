"""Whether an attached document has anything to do with this complaint.

A citizen at a service centre hands over whatever is in the folder. Some of it
bears on the grievance — the earlier petition about the same street light, the
slip acknowledging it. Some of it is a ration card they brought because
somebody once told them to bring a ration card.

WHAT THIS CHANGES, AND WHAT IT DOES NOT. It changes what the citizen is shown:
a document judged unrelated is presented as "kept as supporting evidence"
rather than as a source of facts to confirm, so they are not asked to check a
reference number that belongs to a different matter. It does NOT gate
anything. An unrelated attachment stays attached, stays listed on the
petition, and stays downloadable, because the citizen brought it on purpose
and this service does not know their case better than they do.

Deterministic, and no model. The judgement is word overlap between the
document and the grievance the citizen has just written, plus the document's
own kind — both things the service already has. A model asked "is this
relevant?" would answer confidently on a blurred photograph, and the cost of
that confidence is a citizen being told their evidence does not matter.

The scoring is deliberately shy: anything it cannot place comes back
`unknown`, which the page treats exactly as it treats a document it could not
read. Being unsure is a normal outcome here, not a failure.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# Kinds that, by their nature, bear on a grievance: they are the paper trail
# of this or an earlier complaint.
_CASE_DOCUMENTS = frozenset({
    "previous_petition", "acknowledgement", "response", "notice",
})

# Kinds that support a petition without being about its subject. A residence
# proof is relevant to the PETITION and says nothing about the street light,
# so it is never mined for facts about the complaint.
_SUPPORTING = frozenset({"address_proof", "aadhaar", "photo"})

# Words too common to mean anything when they match. Short tokens are dropped
# by length; these are the ones long enough to survive that and still carry
# no signal. Tamil is handled by length alone — its function words are short,
# and a list transliterated by someone who does not read the script would do
# more harm than good.
_NOISE = frozenset({
    "the", "and", "for", "that", "this", "with", "from", "have", "has", "been",
    "not", "are", "was", "were", "will", "would", "please", "kindly", "sir",
    "madam", "respected", "petition", "grievance", "request", "regarding",
    "subject", "date", "dated", "number", "your", "our", "their", "there",
    "which", "about", "into", "over", "under", "after", "before", "since",
})

MIN_TOKEN = 4          # shorter than this carries no signal in either script
STRONG = 0.18          # share of grievance words the document also uses
WEAK = 0.06

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


@dataclass
class Relevance:
    """How much this document appears to bear on the current grievance."""

    level: str          # high | partial | unrelated | unknown
    reason: str         # one line, shown to the citizen
    overlap: float = 0.0

    @property
    def mine_for_facts(self) -> bool:
        """Whether values read from it are worth putting to the citizen.

        False does not mean discard. It means the card offers the file as
        evidence rather than asking them to confirm figures out of it.
        """
        return self.level in ("high", "partial", "unknown")

    def as_dict(self) -> dict[str, Any]:
        return {"level": self.level, "reason": self.reason,
                "overlap": round(self.overlap, 3)}


def _words(text: str) -> set[str]:
    return {w.casefold() for w in _WORD.findall(str(text or ""))
            if len(w) >= MIN_TOKEN and w.casefold() not in _NOISE}


def _overlap(document: str, grievance: str) -> float:
    """Share of the grievance's distinctive words the document also uses.

    Measured against the GRIEVANCE, not against the document. A fifty-page
    order that happens to contain the six words of the complaint is relevant;
    dividing by the document's own vocabulary would score it near zero purely
    for being long.
    """
    wanted = _words(grievance)
    if not wanted:
        return 0.0
    return len(wanted & _words(document)) / len(wanted)


def assess(*, kind: str, text: str, grievance: str, readable: bool = True,
           language: str = "en") -> Relevance:
    """Judge one attachment against the complaint the citizen has described."""
    tamil = language == "ta"

    def say(en: str, ta: str) -> str:
        return ta if tamil else en

    if not readable or not str(text or "").strip():
        return Relevance("unknown", say(
            "This could not be read, so it is kept as supporting evidence.",
            "இதைப் படிக்க முடியவில்லை; ஆதார ஆவணமாக வைக்கப்படுகிறது."))

    if not str(grievance or "").strip():
        return Relevance("unknown", say(
            "Your complaint has not been described yet.",
            "உங்கள் குறை இன்னும் விவரிக்கப்படவில்லை."))

    if kind in _SUPPORTING:
        return Relevance("partial", say(
            "Kept as supporting evidence for this petition.",
            "இந்த மனுவுக்கான ஆதார ஆவணமாக வைக்கப்படுகிறது."))

    share = _overlap(text, grievance)
    case_document = kind in _CASE_DOCUMENTS

    if share >= STRONG and case_document:
        return Relevance("high", say(
            "This appears to be about the same matter as your complaint.",
            "இது உங்கள் குறையுடன் தொடர்புடையதாகத் தெரிகிறது."), share)
    if share >= STRONG or (case_document and share >= WEAK):
        return Relevance("partial", say(
            "This may be about the same matter. Please check what was found.",
            "இது தொடர்புடையதாக இருக்கலாம். கண்டறியப்பட்டதைச் சரிபார்க்கவும்."), share)
    if case_document:
        return Relevance("partial", say(
            "An official document, but it does not mention your complaint.",
            "அலுவல் ஆவணம்; ஆனால் உங்கள் குறையைக் குறிப்பிடவில்லை."), share)
    return Relevance("unrelated", say(
        "This does not appear to relate to your complaint. It stays attached.",
        "இது உங்கள் குறையுடன் தொடர்பில்லை எனத் தெரிகிறது. இணைப்பாக இருக்கும்."), share)
