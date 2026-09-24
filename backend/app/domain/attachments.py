"""What a citizen attaches to their petition, and what may be said about it.

One rule governs this whole module, and it is the reason it exists rather than
the attachments being a list of filenames somewhere:

**The petition may only claim an attachment that was actually supplied.**

Before this, the document printed a fixed enclosure list off the template —
"Copy of Aadhaar card", "Copies of any earlier petition" — on every petition
ever produced, whether or not anything was enclosed. A receiving officer reading
that list has been told three documents are in the envelope. If they are not,
the citizen is the one who looks as though they withheld them.

So the template's list becomes what it always should have been: a SUGGESTION,
shown when the citizen is asked whether they want to attach anything. What is
printed on the petition comes only from files that exist on disk in this
session's own directory.

The second rule is separation. Attachments are the citizen's own evidence and
belong to one session. They never enter the government knowledge corpus — there
is no code path from here to `app/knowledge`, and `store.py` has no writer but
ingestion.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Language = Literal["en", "ta"]

# What a file is, as far as a petition is concerned. `other` is not a failure —
# most things a citizen attaches are photographs of a broken thing, and a
# petition should list them plainly rather than pretend to classify them.
AttachmentKind = Literal[
    "aadhaar",
    "address_proof",
    "previous_petition",
    "acknowledgement",
    "notice",
    "response",
    "photo",
    "other",
]

# How each kind is named on the petition, in both languages. On the document
# itself, not in the code that builds it, so a department can change the wording
# of an enclosure line without touching Python.
KIND_LABELS: dict[str, dict[str, str]] = {
    "aadhaar": {"en": "Copy of Aadhaar card", "ta": "ஆதார் அட்டை நகல்"},
    "address_proof": {"en": "Copy of proof of residence", "ta": "வசிப்பிடச் சான்று நகல்"},
    "previous_petition": {"en": "Copy of earlier petition", "ta": "முந்தைய மனு நகல்"},
    "acknowledgement": {"en": "Acknowledgement receipt", "ta": "ஒப்புகைச் சீட்டு"},
    "notice": {"en": "Copy of notice received", "ta": "பெறப்பட்ட அறிவிப்பு நகல்"},
    "response": {"en": "Copy of reply received", "ta": "பெறப்பட்ட பதில் நகல்"},
    "photo": {"en": "Photograph", "ta": "புகைப்படம்"},
    "other": {"en": "Supporting document", "ta": "துணை ஆவணம்"},
}

# The question itself, asked once, after the grievance is on the record.
OFFER: dict[str, str] = {
    "en": ("Would you like to add supporting attachments to this petition, "
           "or continue with these details?"),
    "ta": ("இந்த மனுவுடன் ஏதேனும் இணைப்புகளைச் சேர்க்க விரும்புகிறீர்களா? "
           "அல்லது தற்போது வழங்கியுள்ள விவரங்களுடன் மனுவைத் தயாரிக்கலாமா?"),
}

# Asked instead of OFFER once at least one file is already attached: the
# citizen has answered the first question by acting, and being asked it again
# reads as though the upload did not register.
MORE_OR_CONTINUE: dict[str, str] = {
    "en": ("That is attached. Would you like to add another, or continue with "
           "these details?"),
    "ta": ("அது இணைக்கப்பட்டது. மேலும் ஏதேனும் சேர்க்க வேண்டுமா, அல்லது இந்த "
           "விவரங்களுடன் தொடரலாமா?"),
}

ADD_LABEL: dict[str, str] = {"en": "Add Attachments", "ta": "இணைப்புகளைச் சேர்"}
CONTINUE_LABEL: dict[str, str] = {
    "en": "Continue with These Details", "ta": "இந்த விவரங்களுடன் தொடரவும்"}

# Said above the suggestion list so nobody reads it as a requirement. A document
# is only called for when a retrieved OFFICIAL source says so — see
# `required_from_analysis` below.
SUGGESTION_NOTE: dict[str, str] = {
    "en": ("These are suggestions only. Nothing here is required unless an "
           "official document says so."),
    "ta": ("இவை பரிந்துரைகள் மட்டுமே. அதிகாரப்பூர்வ ஆவணம் கோரினால் தவிர "
           "எதுவும் கட்டாயமில்லை."),
}

MAX_ATTACHMENTS = 10
MAX_BYTES = 10 * 1024 * 1024

# Deliberately narrow. Everything here is either a document this service can
# read or an image a citizen photographed; nothing here executes.
ALLOWED_TYPES: dict[str, str] = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
    # The pre-2007 binary formats. Accepted and carried, never opened: a
    # citizen holding a .doc from an office should not be turned away, and
    # nothing in this service parses them, so there is no parser to attack.
    # `extraction` reports them as unreadable and asks the citizen to type
    # what they say, rather than attaching an empty-looking document.
    "application/msword": ".doc",
    "application/vnd.ms-powerpoint": ".ppt",
    # Spreadsheets. A ward's complaint register or a bill schedule arrives as
    # one of these more often than as anything else.
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/vnd.ms-excel": ".xls",
    "text/csv": ".csv",
    "text/html": ".html",
    "text/plain": ".txt",
}
ALLOWED_SUFFIXES = frozenset({".pdf", ".jpg", ".jpeg", ".png", ".webp", ".heic",
                              ".docx", ".pptx", ".doc", ".ppt",
                              ".xlsx", ".xls", ".csv", ".html", ".txt"})

# Formats carried as plain text: no binary signature to check, so the content
# is inspected for NUL bytes instead. HTML is here because an .html file IS
# text — it is never executed by this service, only read for its words.
TEXT_SUFFIXES = frozenset({".txt", ".csv", ".html"})

# Formats whose bytes cannot be told apart from each other, so the declared
# extension decides between them once the signature has proved the family.
# .doc and .ppt are both OLE compound files; separating them needs a parser
# for a format this service deliberately does not parse.
INDISTINGUISHABLE: tuple[frozenset[str], ...] = (
    frozenset({".doc", ".ppt", ".xls"}),
)


@dataclass
class Attachment:
    """One file the citizen supplied. It exists on disk or it is not here."""

    attachment_id: str
    filename: str            # sanitised; what the citizen called it
    stored_name: str         # what it is called on disk, inside the session dir
    content_type: str
    size: int
    kind: AttachmentKind = "other"
    uploaded_at: str = ""
    # A citizen-supplied or classifier-suggested description, shown on the
    # petition after the kind label when it adds something.
    note: str = ""
    # What was read out of it, if anything could be. NEVER applied to the
    # petition record on its own — see `prior_petition.py` and the confirm step.
    extracted: dict[str, Any] | None = None
    # True once the citizen has seen what was extracted and said it is right.
    # Until then nothing from `extracted` may appear in the petition.
    confirmed: bool = False
    # How much this document appears to bear on the current grievance, as
    # `attachment_relevance` judged it at upload. Advisory: it changes how the
    # file is PRESENTED, never whether it is kept or listed.
    relevance: dict[str, Any] | None = None
    # WHOSE document this appears to be, as System-1 classified it at upload:
    # their own earlier petition, somebody else's, a reply from an office, a
    # receipt. Advisory in the same sense as `relevance` — it cannot keep a
    # file out and it cannot alter a single citizen field.
    #
    # It has exactly one power, and it is a power to WITHHOLD: a document
    # classified as a third party's may not become the source of the sentence
    # "I had previously submitted a petition ... under acknowledgement number
    # N". See `_prior_reference` in `graph/nodes.py`. Sethubala's reference
    # number in Harish's first person is a false claim on a government form.
    relationship: dict[str, Any] | None = None

    def label(self, language: Language = "en") -> str:
        base = KIND_LABELS.get(self.kind, KIND_LABELS["other"]).get(
            language, KIND_LABELS["other"]["en"])
        return f"{base} – {self.note}" if self.note else base

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: Any) -> Attachment | None:
        if not isinstance(value, dict) or not value.get("attachment_id"):
            return None
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in value.items() if k in known})


@dataclass
class AttachmentSet:
    """Every attachment on this session, in the order they were added."""

    items: list[Attachment] = field(default_factory=list)

    @classmethod
    def from_state(cls, value: Any) -> AttachmentSet:
        if not isinstance(value, list):
            return cls()
        return cls(items=[a for a in (Attachment.from_dict(v) for v in value) if a])

    def as_state(self) -> list[dict[str, Any]]:
        return [a.as_dict() for a in self.items]

    def __len__(self) -> int:
        return len(self.items)

    def __bool__(self) -> bool:
        return bool(self.items)

    def get(self, attachment_id: str) -> Attachment | None:
        return next((a for a in self.items if a.attachment_id == attachment_id), None)

    def remove(self, attachment_id: str) -> bool:
        before = len(self.items)
        self.items = [a for a in self.items if a.attachment_id != attachment_id]
        return len(self.items) != before

    def confirmed_of(self, kind: AttachmentKind) -> list[Attachment]:
        return [a for a in self.items if a.kind == kind and a.confirmed]

    def lines(self, language: Language = "en") -> list[str]:
        """The enclosure lines for the petition. One per supplied file.

        Nothing is inferred and nothing is padded out to look complete: if the
        citizen attached one photograph, the petition says one photograph.
        """
        return [a.label(language) for a in self.items]


# Answering the offer in words, for a citizen who is speaking rather than
# clicking. The question is an either/or, so a bare "yes" is genuinely
# ambiguous — it is resolved by the wording that follows it, and by `None`
# otherwise, which makes the assistant ask again rather than guess.
_WANTS_TO_ATTACH = re.compile(
    # Stems with `\w*`, not a list of forms. Spelling the forms out missed
    # "attachmentS" — the exact word the question itself uses — so a citizen
    # answering "yes I want to add attachments" matched nothing at all here,
    # fell through to the model, and was asked the same question again. It read
    # as the send button being broken.
    r"\b(attach\w*|upload\w*|enclos\w*|document\w*|cop(?:y|ies)|"
    r"photo\w*|aadhaar|receipt\w*|slip\w*|proof|certificate\w*|"
    r"petition\s+copy|i\s+have)\b"
    r"|இணைப்|இணைக்க|சேர்க்க|ஆவணம்|ஆவணங்கள|நகல்|புகைப்படம்|ஆதார்|ரசீது|"
    r"சான்று|என்னிடம்\s*உள்ளது",
    re.I)

_WANTS_TO_CONTINUE = re.compile(
    r"\b(continue|proceed|carry on|go ahead|no need|nothing|none|no more|"
    r"that'?s all|thats all|skip|without|generate|finish|done)\b"
    r"|தொடர|தொடரவும்|போதும்|வேண்டாம்|இல்லை|ஏதுமில்லை|முடிக்க|தயாரி",
    re.I)


_NO_DOCUMENTS = re.compile(
    r"\b(?:no|not|don'?t|do\s+not|doesn'?t|haven'?t|have\s+not|without|nothing)\b"
    r"[^.!?]{0,24}?\b(?:attach\w*|document\w*|cop(?:y|ies)|photo\w*|proof|"
    r"receipt|slip|enclosure\w*|paper\w*)\b",
    re.I)


def read_choice(text: str) -> Literal["add", "continue"] | None:
    """"add" | "continue" | None — read from words, with no model.

    `None` is the important one. This is an either/or question and a citizen who
    said something neither branch recognises has not chosen; guessing "continue"
    there would silently discard the acknowledgement slip in their hand.
    """
    said = str(text or "").strip()
    if not said:
        return None

    # "no documents", "I don't have any attachments" — a negation standing in
    # front of the very word that means "add". Checked first, because otherwise
    # naming the thing you do NOT have reads as asking for it.
    if _NO_DOCUMENTS.search(said):
        return "continue"

    wants = bool(_WANTS_TO_ATTACH.search(said))
    done = bool(_WANTS_TO_CONTINUE.search(said))

    if wants and done:
        return "continue"
    if wants:
        return "add"
    if done:
        return "continue"

    # A bare yes/no, which only means anything against this specific question:
    # "yes" to "would you like to add attachments" is "add".
    from .fields import read_boolean

    decided = read_boolean(said)
    if decided is True:
        return "add"
    if decided is False:
        return "continue"
    return None


def sanitise_filename(name: str) -> str:
    """A filename safe to write inside the session directory.

    Path separators, traversal, control characters and reserved Windows device
    names all removed. The result is never empty and never escapes the
    directory it is joined to.
    """
    raw = unicodedata.normalize("NFC", str(name or "")).strip()
    raw = raw.replace("\\", "/").split("/")[-1]
    raw = "".join(ch for ch in raw if ord(ch) >= 32 and ch not in '<>:"|?*')
    raw = raw.strip(". ")
    # CON, PRN, AUX, NUL, COM1-9, LPT1-9 — reserved by Windows whatever the
    # extension, and creating one is a write that goes somewhere unexpected.
    stem = raw.split(".")[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(COM|LPT)[1-9]", stem):
        raw = f"file_{raw}"
    return raw[:120] or "attachment"


def kind_label(kind: str, language: Language = "en") -> str:
    return KIND_LABELS.get(kind, KIND_LABELS["other"]).get(
        language, KIND_LABELS["other"]["en"])


def suggestions(template: Any, language: Language = "en") -> list[str]:
    """What a citizen is shown when asked whether they want to attach anything.

    Read from the template's own list, which is where a department edits it.
    These are suggestions and are labelled as such; they are NOT printed on the
    petition, because the petition may only list what was actually supplied.
    """
    try:
        return list(template.enclosures_for(language))
    except Exception:      # noqa: BLE001 - a template without the block is fine
        return []


def required_from_analysis(analysis: Any, language: Language = "en") -> list[dict[str, str]]:
    """Documents an OFFICIAL retrieved source actually says are required.

    This is the only route by which a suggestion becomes a requirement. It reads
    the knowledge layer's `required_documents` findings and keeps only those
    whose citations are official or departmental — an unofficial summary saying
    a document is mandatory is not a reason to tell a citizen it is.
    """
    if not isinstance(analysis, dict):
        return []
    out: list[dict[str, str]] = []
    for finding in analysis.get("required_documents") or []:
        if not isinstance(finding, dict):
            continue
        value = str(finding.get("value") or "").strip()
        sources = [s for s in (finding.get("sources") or []) if isinstance(s, dict)]
        official = [s for s in sources
                    if s.get("authority") in ("official", "departmental")]
        if not value or not official:
            continue
        cite = official[0]
        where = " · ".join(
            str(x) for x in (cite.get("document_title"), cite.get("section")) if x)
        out.append({"value": value, "source": where,
                    "url": str(cite.get("source_url") or "")})
    return out
