"""The conversation state, and the shape of one turn.

One citizen utterance is ONE graph invocation. The graph runs to an `END` after
`ask` or `confirm` rather than blocking on an interrupt, and the checkpointer
persists the state against `session_id` in between. That choice is what makes a
voice session survivable: a dropped WebSocket loses nothing, the citizen
reconnects, and the next utterance resumes from the last checkpoint.

Everything in here must be JSON-serialisable, because the checkpointer writes it
to SQLite. That is why values are plain dicts and lists rather than the dataclass
types they came from.
"""

from __future__ import annotations

from datetime import UTC
from typing import Annotated, Any, Literal, TypedDict

Language = Literal["en", "ta"]

Status = Literal[
    "collecting",   # still gathering details
    "attachments",  # every detail is in; asked whether anything is enclosed
    "confirming",   # read-back sent, waiting for yes
    "generating",   # compose/render running
    "ready",        # document produced and verified
    "cancelled",    # citizen abandoned the request
    "failed",       # generation or verification failed; details are kept
]


def merge_turns(left: list[dict] | None, right: list[dict] | None) -> list[dict]:
    """Append-only transcript. Trimmed, because a long session must not grow the
    checkpoint without bound — the last 60 turns are far more than any node reads."""
    combined = (left or []) + (right or [])
    return combined[-60:]


class LetterState(TypedDict, total=False):
    # -- identity ---------------------------------------------------------- #
    session_id: str
    language: Language
    created_at: str
    updated_at: str

    # The single installed form. Kept on the record so a stored session says
    # which form it was filled against, not to select between forms.
    template_id: str | None

    # -- what has been accepted -------------------------------------------- #
    # Validated values only. A raw string never reaches this dict.
    fields: dict[str, Any]
    # How each value arrived: "fast-path", "model", "correction", "opening".
    # Kept because an officer reviewing a letter is entitled to know which
    # details were typed by the citizen and which were inferred from speech.
    field_sources: dict[str, str]
    # Consecutive failures per field, used to decide when a fresh phrasing is
    # worth a model call.
    attempts: dict[str, int]

    # -- what is still needed ---------------------------------------------- #
    missing: list[str]
    field_errors: dict[str, dict[str, Any]]
    awaiting: str | None
    # True between "no, that read-back is wrong" and the citizen naming which
    # detail is wrong. Without it, "no" could only repeat the same list.
    awaiting_correction: bool

    # -- this turn --------------------------------------------------------- #
    utterance: str
    intent: str
    ambiguous: bool
    understood_by: str          # "fast-path" | "model" | "deterministic" | "none"
    question: str | None

    # -- progress ---------------------------------------------------------- #
    status: Status
    confirmed: bool
    reply: str

    # -- output ------------------------------------------------------------ #
    # What the model wrote: the tailored subject, the opening and the closing
    # request. None when no model was reachable, in which case the letter
    # carries the standard wording instead.
    composition: dict[str, str] | None
    # What the citizen asked to have said differently, in their own words,
    # after reading the petition. Kept on the session rather than used once and
    # discarded, so a second revision builds on the first instead of undoing
    # it, and so an officer can see what was asked for.
    revisions: list[str]
    document_version: int
    document_versions: list[dict[str, Any]]
    petition_reference: str | None
    pending_edit: dict[str, Any] | None
    document_edited: bool
    # When the citizen pressed Submit, as an ISO timestamp, or None. The
    # petition stays editable afterwards by design — this records that they
    # said they were finished, it does not freeze the record.
    submitted_at: str | None
    _document_edit: dict[str, Any] | None
    _revision_base: str | None
    _revision_fields: dict[str, Any]
    _version_source: str | None
    _version_summary: str | None
    # Where the emblem is printed: {"align": ..., "pages": ...}. Kept on the
    # session so a citizen who moved it and then asked for the wording to
    # change does not get it moved back.
    emblem: dict[str, str] | None
    # -- what the citizen enclosed ----------------------------------------- #
    # Files this citizen supplied for THIS petition. They live in the session's
    # own directory and never enter the government knowledge corpus: an Aadhaar
    # card or a previous petition naming a person is not reference material and
    # must not be retrievable by the next citizen's grievance.
    attachments: list[dict[str, Any]]
    # The offer is made once, after the grievance is on the record. Asking it
    # again every turn would be the same bug as re-running the knowledge layer
    # on every message.
    attachments_offered: bool
    # The citizen has said "continue". Until then the petition is not composed,
    # because they may still be holding the slip that makes it actionable.
    attachments_done: bool

    letter_text: str | None
    # The citizen edited the text of the petition by hand. Recorded on the
    # session because an officer reading it is entitled to know that the wording
    # is the citizen's own rather than the form's — and because verification
    # behaves differently afterwards. Once set it stays set: a later edit does
    # not un-edit the document.
    manually_edited: bool
    # What the knowledge layer found for this grievance, with its citations.
    # Advisory and for the officer's panel only — nothing here is printed on
    # the petition. None when the layer is off or the corpus has nothing to say.
    analysis: dict[str, Any] | None
    document: dict[str, Any] | None
    verification: dict[str, Any] | None
    warnings: list[str]
    error: str | None

    # -- transient, one turn only ------------------------------------------ #
    # Written by `understand`, read by `validate`, and REWRITTEN EVERY TURN.
    # They live on the state because LangGraph only passes declared keys between
    # nodes; the leading underscore marks them as not part of the session record,
    # and `understand` always sets all three so a stale value from the previous
    # turn can never be read as though it were current.
    _extracted: dict[str, str]
    _corrections: dict[str, str]
    # The field the citizen just named as wrong, e.g. from "the address is wrong".
    _correction_target: str | None
    # A wording instruction for a petition that already exists: "make the
    # subject mention drinking water". Transient like the two above.
    _revision: str | None
    # A layout instruction about the emblem, read deterministically.
    _emblem: dict[str, str] | None
    # The whole petition, as the citizen edited it by hand. Transient: it is
    # applied to `letter_text` and cleared. Nothing rewrites it on the way
    # through — that is the entire point of the manual editor.
    _edited_text: str | None
    # How to label this edit in the version history. A translation takes
    # the same path a hand edit takes, and without this the history tells
    # the citizen they typed a Hindi petition themselves.
    _edit_label: dict[str, str] | None
    # Set by the REST form endpoints, which have already been told which field
    # the citizen is editing. The turn then starts at `validate`, because there
    # is nothing left to understand.
    _skip_understand: bool

    # -- history ----------------------------------------------------------- #
    turns: Annotated[list[dict], merge_turns]
    # Replace, not append: a restart must be able to clear the audit trail it
    # is restarting from. Nodes append to the existing list explicitly.
    corrections: list[dict]


def new_state(session_id: str, language: Language = "en") -> LetterState:
    from datetime import datetime

    now = datetime.now(UTC).isoformat()
    return LetterState(
        session_id=session_id,
        language=language,
        created_at=now,
        updated_at=now,
        template_id=None,
        fields={},
        field_sources={},
        attempts={},
        missing=[],
        field_errors={},
        awaiting=None,
        utterance="",
        intent="provide",
        revisions=[],
        document_version=0,
        document_versions=[],
        petition_reference=None,
        pending_edit=None,
        document_edited=False,
        submitted_at=None,
        _document_edit=None,
        _revision_base=None,
        _revision_fields={},
        _version_source=None,
        _version_summary=None,
        emblem=None,
        _revision=None,
        ambiguous=False,
        understood_by="none",
        question=None,
        status="collecting",
        confirmed=False,
        reply="",
        composition=None,
        attachments=[],
        attachments_offered=False,
        attachments_done=False,
        letter_text=None,
        manually_edited=False,
        analysis=None,
        document=None,
        verification=None,
        warnings=[],
        error=None,
        turns=[],
        corrections=[],
        awaiting_correction=False,
        _extracted={},
        _corrections={},
        _correction_target=None,
        _skip_understand=False,
    )


def turn(who: Literal["citizen", "assistant"], text: str, **extra: Any) -> dict:
    from datetime import datetime

    return {
        "who": who,
        "text": text,
        "at": datetime.now(UTC).isoformat(),
        **{k: v for k, v in extra.items() if v is not None},
    }
