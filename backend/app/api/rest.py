"""REST endpoints.

The whole conversation is available over REST as well as over the WebSocket,
because a citizen at a service centre may be typing on a shared terminal with no
microphone, and an officer reviewing a petition later needs to read the record
without a live connection.

Every endpoint that advances the conversation goes through the same graph
invocation. There is no second code path for text, which is what keeps typed and
spoken sessions identical.
"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from ..config import get_settings
from ..domain import attachment_relevance, prior_petition, revisions
from ..domain import attachments as attachment_rules
from ..domain.fields import MAX_FREE_TEXT
from ..domain.letter import verbatim_lines
from ..domain.templates import missing_fields, the_template
from ..graph.state import LetterState, new_state
from ..logging_setup import preview, session_context
from ..services import (
    asr,
    attachment_store,
    credential_check,
    document_intelligence,
    extraction,
    llm,
    package,
    system_one,
    tts,
)
from ..services.officer_store import require_citizen_session
from ..services.render import pdf_status
from ..services.speech_text import readable_sections, redact_for_speech, speech_for
from ..services.translate import language_of, translate_lines
from .views import session_view

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api", dependencies=[Depends(require_citizen_session)])


# --------------------------------------------------------------------------- #
# Request bodies
# --------------------------------------------------------------------------- #


class StartRequest(BaseModel):
    language: str = Field(default="en", pattern="^(en|ta)$")
    # An opening statement is optional: the citizen may just say "hello" and be
    # asked the first question, or may open with their name already in it.
    text: str = Field(default="", max_length=MAX_FREE_TEXT)


class MessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_FREE_TEXT)
    expected_version: int | None = Field(default=None, ge=0)

    @field_validator("text")
    @classmethod
    def nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Please enter a message.")
        return value


class ReviseRequest(BaseModel):
    """A change to how the petition READS, asked for after it exists.

    Not a change to the record: the particulars were confirmed before anything
    was drafted, and a citizen correcting one of those names the field and goes
    through the ordinary correction flow instead.
    """
    instruction: str = Field(min_length=4, max_length=600)
    expected_version: int | None = Field(default=None, ge=0)


# The fields a citizen may correct on the confirmation screen. Narrow on
# purpose: these are the ones a petition may later cite, and nothing else read
# out of an attachment is ever used.
_CONFIRMABLE = frozenset({
    "reference_number", "petition_number", "submitted_on", "department",
    "authority", "subject", "status",
})


class AttachmentConfirmRequest(BaseModel):
    """What the citizen says about the values read from their attachment."""

    confirmed: bool = True
    # Corrections, keyed by field name. A blank value clears that field.
    values: dict[str, str] = Field(default_factory=dict)


class FieldEditRequest(BaseModel):
    """An out-of-band correction from a text UI, rather than by speaking.

    It goes through the same validators; the only thing it skips is the
    understanding step, because the citizen has already said which field.
    """
    name: str = Field(min_length=1, max_length=60)
    value: str = Field(min_length=1, max_length=MAX_FREE_TEXT)

    @field_validator("name")
    @classmethod
    def known_field(cls, value: str) -> str:
        name = value.strip()
        if the_template().field(name) is None:
            raise ValueError("That field is not part of this petition.")
        return name

    @field_validator("value")
    @classmethod
    def nonblank_value(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Please enter a value for this detail.")
        return value


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _workflow(request: Request):
    workflow = getattr(request.app.state, "workflow", None)
    if workflow is None:  # pragma: no cover - only if startup failed
        raise HTTPException(503, "The service is still starting.")
    return workflow


async def _require_state(request: Request, session_id: str):
    state = await _workflow(request).snapshot(session_id)
    _require_existing(state)
    return state


def _require_existing(state: LetterState | None) -> bool:
    if not state:
        raise HTTPException(404, "That session was not found. It may have expired.")
    return True


def _require_editable(state: LetterState | None) -> bool:
    _require_existing(state)
    if state.get("status") == "cancelled":
        raise HTTPException(409, "This petition was cancelled. Restart it before making changes.")
    return True


def _version_guard(expected: int | None = None, *, ready: bool = False, text: str | None = None):
    def guard(state: LetterState | None) -> bool:
        _require_existing(state)
        if ready and state.get("status") != "ready":
            raise HTTPException(409, "There is no petition to edit yet. Finish and confirm it first.")
        document = state.get("document") or {}
        actual = int(state.get("document_version") or document.get("version") or (1 if document.get("docx") else 0))
        if expected is not None and expected != actual:
            raise HTTPException(409, "This petition changed while you were editing. Review the latest version before saving.")
        return text is None or text != state.get("letter_text")
    return guard


def _require_confirmable(state: LetterState | None) -> bool:
    _require_editable(state)
    if (missing_fields(the_template(), state.get("fields") or {})
            or state.get("field_errors") or state.get("awaiting_correction")):
        raise HTTPException(409, "Some details are still missing or need a correction.")
    if state.get("status") == "ready":
        return False
    if state.get("status") not in ("confirming", "failed"):
        raise HTTPException(409, "Please review all details before confirming the petition.")
    return True


# --------------------------------------------------------------------------- #
# Reference data
# --------------------------------------------------------------------------- #


@router.get("/health")
async def health() -> dict:
    """What is actually working, including whether citizen text leaves the box."""
    settings = get_settings()
    language_status = await llm.available(settings)
    pdf = pdf_status(settings)
    return {
        "ok": True,
        # The commit this container was built from, so "is my change live?"
        # is a question with an answer. Not a secret: it is the same sha the
        # repository shows publicly.
        "build": settings.build_sha or "unknown",
        "language_model": {
            "available": language_status["available"],
            "provider": language_status.get("provider"),
            "egress": language_status.get("egress"),
            "detail": language_status.get("detail"),
            "note": language_status.get("note"),
        },
        "dictation": asr.status(settings),
        "spoken_replies": tts.status(settings),
        # Keys that are present and switched off. `ok: true` is the normal
        # state. When it is false the operator holds credentials that were
        # read correctly and cannot be used — which otherwise presents as
        # "the keys do not work", with nothing anywhere to contradict it.
        "credentials": credential_check.summary(settings),
        # How a terminal should behave. Sent to every client because the
        # page has to know BEFORE it claims anything about printing: a
        # browser cannot tell whether the dialog will appear, so the
        # deployment says so and the page reports only what it can stand
        # behind.
        "kiosk": {
            "enabled": settings.kiosk_enabled,
            "print_mode": settings.kiosk_print_mode,
            "auto_print": settings.kiosk_auto_print,
            "print_package": settings.kiosk_print_package,
            "idle_timeout_seconds": settings.kiosk_idle_timeout_seconds,
            "reset_after_finish": settings.kiosk_reset_after_finish,
        },
        # What can be done with a file a citizen encloses. `ocr.available` is
        # false on a machine with no engine, and that is a supported state:
        # photographs are attached and reported unreadable rather than guessed.
        "attachments": {
            # Two readers, reported separately because they fail separately.
            # `reader` is the document engine that handles scans, photographs,
            # spreadsheets and the legacy Office formats; `ocr` is the older
            # standalone engine the built-in readers fall back to. Either can
            # be absent, and the service works with neither.
            "reader": document_intelligence.status(),
            "ocr": extraction.ocr_status(),
            "max_files": attachment_rules.MAX_ATTACHMENTS,
            "max_bytes": attachment_rules.MAX_BYTES,
            "accepts": sorted(attachment_rules.ALLOWED_SUFFIXES),
        },
        "documents": {
            "docx": True,
            # Two questions, deliberately separate. `pdf` says whether this
            # machine can produce one at all; `pdf_production_ready` says
            # whether the engine doing it is one a department server may be
            # commissioned on. Word answers yes to the first and no to the
            # second, and collapsing them is how that gets lost between a
            # demonstration and a deployment.
            "pdf": pdf["available"],
            "pdf_engine": pdf["engine"],
            "pdf_production_ready": pdf["production_ready"],
            "note": pdf["note"],
        },
        # Stated plainly: nothing about validation, letter assembly or
        # verification depends on a language model being reachable.
        "degraded_mode": (
            "Without a language model the assistant still collects every detail, "
            "validates it, and produces the petition using the standard wording."
        ),
    }


# --------------------------------------------------------------------------- #
# Conversation
# --------------------------------------------------------------------------- #


@router.post("/sessions", status_code=201)
async def start_session(body: StartRequest, request: Request, response: Response) -> dict:
    session_id = str(uuid.uuid4())
    workflow = _workflow(request)

    with session_context(session_id):
        seed = new_state(session_id, body.language)  # type: ignore[arg-type]
        seed["template_id"] = the_template().id

        # Seed and ask in one invocation, so recovery cannot observe an
        # intermediate record with no missing fields and no first question.
        seed["utterance"] = body.text if body.text.strip() else ""
        state = await workflow.invoke(session_id, seed)

        from ..services.officer_store import remember_citizen
        remember_citizen(request, response, session_id)

        log.info("session.started", extra={"language": state.get("language"),
                                           "opening": bool(body.text.strip())})
        return session_view(state)


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request) -> dict:
    """Session recovery. A citizen who lost signal resumes from here."""
    with session_context(session_id):
        return session_view(await _require_state(request, session_id))


@router.get("/sessions/{session_id}/progress")
async def session_progress(session_id: str, request: Request) -> dict:
    """Is this session composing a petition right now?

    Deliberately lock-free, and deliberately one word.

    A turn is a single request that returns only once it has finished, so the
    page cannot learn from it that composition has begun — and the full session
    endpoint is no help, because it waits on the same session lock the running
    turn is holding. Asking that "are you still working?" can only be answered
    after the work has stopped.

    So this reads the checkpoint directly. Nothing here decides that work is
    under way: the confirm step records `generating` before it routes to
    composition, and this reports that status and nothing else. No document, no
    fields, no transcript — there is no reason for a progress check to carry a
    citizen's details.
    """
    state = await _workflow(request).peek(session_id)
    _require_existing(state)
    return {"status": state.get("status") or "collecting"}


@router.post("/sessions/{session_id}/message")
async def send_message(session_id: str, body: MessageRequest, request: Request) -> dict:
    with session_context(session_id):
        log.info("turn.received", extra={"chars": len(body.text),
                                         "preview": preview(body.text)})
        state = await _workflow(request).invoke(
            session_id, {"utterance": body.text}, guard=_version_guard(body.expected_version),
        )
        return session_view(state)


@router.post("/sessions/{session_id}/field")
async def edit_field(session_id: str, body: FieldEditRequest, request: Request) -> dict:
    """Correct one field directly, from a form rather than a sentence.

    Implemented as a normal turn carrying an explicit correction, so the value
    passes the same validators and the change lands in the same audit trail as a
    spoken "actually, my age is 31".
    """
    with session_context(session_id):
        state = await _workflow(request).invoke(
            session_id,
            {
                "utterance": f"{body.name}: {body.value}",
                "intent": "correct",
                "understood_by": "form",
                "_extracted": {},
                "_corrections": {body.name: body.value},
                "_correction_target": None,
                "_edited_text": None,
                "question": None,
                "ambiguous": False,
                # The understanding step is skipped, so the turn starts at validate.
                "_skip_understand": True,
            },
            guard=_require_editable,
        )
        return session_view(state)


@router.post("/sessions/{session_id}/confirm")
async def confirm_session(session_id: str, request: Request) -> dict:
    """Explicit confirmation from a button rather than from speech."""
    with session_context(session_id):
        result = await _workflow(request).invoke(
            session_id,
            {"utterance": "yes", "intent": "confirm", "understood_by": "form",
             "_extracted": {}, "_corrections": {}, "_correction_target": None, "_edited_text": None,
             "_skip_understand": True},
            guard=_require_confirmable,
        )
        return session_view(result)


# --------------------------------------------------------------------------- #
# Attachments
#
# The citizen's own evidence, for THIS petition. It is stored in the session's
# own directory and is never written to the government knowledge corpus: an
# Aadhaar card or a previous petition naming a person is not reference material,
# and making it retrievable by the next citizen's grievance would be the worst
# thing this service could do with it.
# --------------------------------------------------------------------------- #


def _attachment_turn(session_id: str, request: Request, **patch):
    """Push an attachment change through the graph as an ordinary turn.

    Everything the citizen does goes through one invocation, which is what keeps
    the WebSocket and the REST views identical, and what makes an upload a thing
    the transcript records rather than a side effect nobody can see.
    """
    return _workflow(request).invoke(
        session_id,
        {"utterance": "", "understood_by": "form", "_extracted": {},
         "_corrections": {}, "_correction_target": None, "_revision": None,
         "_edited_text": None, "_skip_understand": True, **patch},
    )


@router.post("/sessions/{session_id}/attachments", status_code=201)
async def add_attachment(
    session_id: str,
    request: Request,
    # B008 is suppressed on all three: FastAPI reads these markers OUT of the
    # default to build the multipart signature, so moving the call into the body
    # is not a refactor, it breaks the endpoint.
    file: UploadFile = File(...),                # noqa: B008
    kind: str = Form(default=""),                # noqa: B008
    note: str = Form(default=""),                # noqa: B008
) -> dict:
    """Accept one file, read what can be read from it, and say what was found.

    Reading is not applying. Whatever is extracted is held on the attachment
    and shown to the citizen; nothing reaches the petition until they confirm
    it. That is the whole of rule 7 - current citizen information outranks
    anything an old document says - and it is enforced here by simply not
    writing to `fields`.
    """
    with session_context(session_id):
        state = await _require_state(request, session_id)
        if state.get("status") in ("cancelled",):
            raise HTTPException(409, "This petition was cancelled.")

        current = attachment_rules.AttachmentSet.from_state(state.get("attachments"))
        content = await file.read()
        try:
            stored = attachment_store.save(
                session_id=session_id,
                filename=file.filename or "attachment",
                content=content,
                content_type=file.content_type or "",
                existing=current,
            )
        except attachment_store.AttachmentRejected as exc:
            raise HTTPException(400, str(exc)) from exc

        attachment = stored.attachment
        if note.strip():
            attachment.note = note.strip()[:120]

        # Read it. A file that cannot be read is still attached - the citizen
        # brought it for a reason - it simply carries no extracted fields.
        # Through the router, and awaited. Reading is now genuinely heavy —
        # OCR on a scanned page is most of a second — and this endpoint is
        # async, so doing it inline would stop every other session in the
        # service, including the WebSocket carrying somebody's voice.
        read = await document_intelligence.read(stored.path)
        prior = prior_petition.analyse(
            read.text, readable=read.readable, reason=read.reason,
            low_confidence=read.low_confidence, segments=read.segments)

        chosen = kind.strip().lower()
        if chosen in attachment_rules.KIND_LABELS:
            attachment.kind = chosen            # the citizen said what it is
        elif prior.kind in attachment_rules.KIND_LABELS and prior.kind != "other":
            attachment.kind = prior.kind        # otherwise what it looks like
        elif Path(attachment.stored_name).suffix.lower() in (
                ".jpg", ".jpeg", ".png", ".webp", ".heic"):
            # A photograph the classifier could make nothing of is still a
            # photograph. "Supporting document" on the enclosure line for a
            # picture of a broken street light is needlessly vague.
            attachment.kind = "photo"

        # An Aadhaar card is never held as extracted text. The number on it is
        # already a validated field on the record, and a second copy sitting in
        # the session state is a second place it can leak from.
        if attachment.kind == "aadhaar":
            attachment.extracted = None
            attachment.confirmed = True
        elif prior.has_anything:
            attachment.extracted = prior.as_dict()
        elif not read.readable:
            attachment.extracted = prior.as_dict()   # carries `readable: false`
        elif read.method == "ocr":
            # OCR that recognised text but no citable field. It is still shown
            # rather than silently accepted: an engine that produced words this
            # service could not parse is exactly the case where a citizen should
            # be looking at the result, not trusting it.
            attachment.extracted = prior.as_dict()
        else:
            attachment.confirmed = True          # nothing to confirm

        # Belt and braces on the rule that matters: an OCR read is NEVER
        # auto-confirmed. Everything it produced is a guess about pixels, and a
        # guess about pixels may not become a claim on a government form until
        # the person who took the photograph has agreed it says that.
        if read.method == "ocr" and attachment.kind != "aadhaar":
            attachment.confirmed = False

        # How much this document bears on what the citizen has told us. Kept
        # on the attachment so a reopened petition shows the same judgement,
        # and so it survives without being recomputed against a grievance
        # that has since been edited.
        fields = state.get("fields") or {}
        judgement = attachment_relevance.assess(
            kind=attachment.kind, text=read.text,
            grievance=str(fields.get("grievance") or ""),
            readable=read.readable, language=state.get("language", "en"))
        attachment.relevance = judgement.as_dict()

        # WHOSE document this is. Advisory metadata, stored beside the
        # relevance judgement and carrying exactly as much authority: none
        # over the citizen's own fields. Its one effect is to withhold — a
        # third party's petition may not become the source of the sentence
        # "I had previously submitted ... under acknowledgement number N".
        #
        # The name compared here is the one the CITIZEN gave, never the one
        # read off the page. That direction is the whole point.
        attachment.relationship = system_one.describe_attachment(
            kind=attachment.kind, text=read.text,
            grievance=str(fields.get("grievance") or ""),
            citizen_name=str(fields.get("applicant_name") or ""),
            document_name=(prior.petitioner_name.value
                           if prior.petitioner_name else ""),
            readable=read.readable, language=state.get("language", "en"),
            relevance_level=judgement.level)

        current.items.append(attachment)
        log.info("attachment.added",
                 extra={"kind": attachment.kind, "readable": read.readable,
                        "method": read.method, "extracted": prior.has_anything,
                        "relevance": judgement.level,
                        # The class only. Neither name goes to the log: one is
                        # the citizen's, the other is a third party's, and
                        # neither belongs in an operational record.
                        "relationship": attachment.relationship.get("value"),
                        "needs_review": attachment.relationship.get("requires_review"),
                        "tables": len(read.tables)})
        result = await _attachment_turn(
            session_id, request,
            intent="attach_added",
            attachments=current.as_state())
        return session_view(result)


@router.get("/sessions/{session_id}/attachments/{attachment_id}/file")
async def attachment_file(session_id: str, attachment_id: str,
                          request: Request, download: bool = False) -> FileResponse:
    """The citizen's own attachment, so the page can show it.

    WHY THIS EXISTS. The petition preview drew the letter and nothing else,
    so a citizen who attached a document saw only the line "Enclosures: 1.
    Copy of earlier petition" and had no way to tell whether the file itself
    had gone anywhere. It had — the generated document carries the pages —
    but the only way to find that out was to download and open it. Somebody
    at a counter should be able to see their own paperwork on the screen in
    front of them.

    SCOPED LIKE EVERY OTHER SESSION ROUTE. `_require_state` resolves the
    session the same way the rest of this file does, so this serves one
    citizen their own file and nothing else. The response is sandboxed and
    not cached, because an attachment may carry an Aadhaar card.
    """
    with session_context(session_id):
        state = await _require_state(request, session_id)
        enclosed = attachment_rules.AttachmentSet.from_state(state.get("attachments"))
        attachment = enclosed.get(attachment_id)
        if attachment is None:
            raise HTTPException(404, "That attachment is not on this petition.")
        path = attachment_store.path_of(session_id, attachment)
        if path is None or not path.is_file():
            raise HTTPException(410, "This attachment is no longer available.")
        # `?download=1` is the citizen asking for the file rather than a look
        # at it. Anything this browser cannot display is sent as a download
        # whichever they asked for, because an inline .docx is a blank tab.
        inline = (not download) and attachment.content_type in (
            "application/pdf", "image/png", "image/jpeg", "image/webp")
        return FileResponse(
            path, media_type=attachment.content_type or "application/octet-stream",
            filename=attachment.filename,
            content_disposition_type="inline" if inline else "attachment",
            headers={"Cache-Control": "no-store",
                     "Content-Security-Policy": "sandbox; default-src 'none'"})


@router.delete("/sessions/{session_id}/attachments/{attachment_id}")
async def remove_attachment(session_id: str, attachment_id: str,
                            request: Request) -> dict:
    with session_context(session_id):
        state = await _require_state(request, session_id)
        current = attachment_rules.AttachmentSet.from_state(state.get("attachments"))
        attachment = current.get(attachment_id)
        if attachment is None:
            raise HTTPException(404, "That attachment is not on this petition.")
        attachment_store.delete(session_id, attachment)
        current.remove(attachment_id)
        result = await _attachment_turn(
            session_id, request, intent="attach_removed",
            attachments=current.as_state())
        return session_view(result)


@router.post("/sessions/{session_id}/attachments/{attachment_id}/confirm")
async def confirm_attachment(session_id: str, attachment_id: str,
                             body: AttachmentConfirmRequest,
                             request: Request) -> dict:
    """The citizen has read what was extracted and says whether it is right.

    Corrections are taken as given: a citizen reading their own acknowledgement
    slip is a better source than a regular expression reading a photograph of
    it. A refusal drops the extracted values entirely - the file stays attached,
    it simply stops being evidence of anything.
    """
    with session_context(session_id):
        state = await _require_state(request, session_id)
        current = attachment_rules.AttachmentSet.from_state(state.get("attachments"))
        attachment = current.get(attachment_id)
        if attachment is None:
            raise HTTPException(404, "That attachment is not on this petition.")

        if not body.confirmed:
            attachment.extracted = None
            attachment.confirmed = False
        else:
            extracted = dict(attachment.extracted or {})
            for name, value in (body.values or {}).items():
                if name not in _CONFIRMABLE:
                    continue
                text = str(value or "").strip()
                if text:
                    extracted[name] = {"value": text[:180], "evidence": "",
                                       "confidence": 1.0, "source": "citizen"}
                else:
                    extracted[name] = None
            attachment.extracted = extracted
            attachment.confirmed = True

        log.info("attachment.confirmed",
                 extra={"attachment_id": attachment_id, "confirmed": body.confirmed})
        result = await _attachment_turn(
            session_id, request, intent="attach_confirmed",
            attachments=current.as_state())
        return session_view(result)


@router.post("/sessions/{session_id}/attachments/done")
async def finish_attachments(session_id: str, request: Request) -> dict:
    """"Continue with These Details" - the only thing that advances the step."""
    with session_context(session_id):
        result = await _workflow(request).invoke(
            session_id,
            {"utterance": "", "intent": "skip_attach", "understood_by": "form",
             "_extracted": {}, "_corrections": {}, "_correction_target": None,
             "_revision": None, "_edited_text": None, "_skip_understand": True},
            guard=_require_editable,
        )
        return session_view(result)


class EditRequest(BaseModel):
    """The petition, as the citizen typed it themselves."""

    text: str = Field(min_length=40, max_length=40000)
    expected_version: int | None = Field(default=None, ge=0)

    @field_validator("text")
    @classmethod
    def nonblank_document(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A petition cannot be empty.")
        return value


@router.post("/sessions/{session_id}/document/text")
async def edit_document(session_id: str, body: EditRequest,
                        request: Request) -> dict:
    """Replace the petition text with what the citizen edited by hand.

    Used EXACTLY as given. No model, no re-composition, no tidying — a manual
    editor that improves what it was handed is not a manual editor, and a
    citizen who corrected one word and got a differently-worded document back
    would be right to stop trusting it.

    The document is remade and verified as always. What differs is the verdict:
    a detail the citizen removed themselves is reported as a warning and the
    petition is still handed over, because refusing to give someone their own
    edited letter is the wrong answer to "you changed something".
    """
    with session_context(session_id):
        log.info("session.manual_edit", extra={"chars": len(body.text)})
        result = await _workflow(request).invoke(
            session_id,
            {"utterance": "", "intent": "edit_text", "understood_by": "form",
             "_extracted": {}, "_corrections": {}, "_correction_target": None,
             "_revision": None, "_emblem": None, "_skip_understand": True,
             "_edited_text": body.text},
            guard=_version_guard(body.expected_version, ready=True, text=body.text),
        )
        return session_view(result)


# Named in English for the history, which an officer reads as often as a
# citizen does. The menu names each language in its own script.
_LANGUAGE_NAMES = {"en": "English", "ta": "Tamil", "hi": "Hindi"}


class TranslateRequest(BaseModel):
    """Which language the citizen wants to read their petition in."""

    language: str = Field(pattern="^(en|ta|hi)$")
    expected_version: int | None = Field(default=None, ge=0)


@router.post("/sessions/{session_id}/translate")
async def translate_document(session_id: str, body: TranslateRequest,
                             request: Request) -> dict:
    """Produce the finished petition in another language.

    What is translated is the letter the service wrote. What is NOT translated
    is the citizen's own text — their name, their address and their grievance
    come through exactly as they were entered, in whatever language they chose
    to write them. That is not a nicety: a petition whose complaint has been
    reworded is a different petition, and a translator has already been seen to
    turn Coimbatore into the name of a locality in Chennai. A document naming
    the wrong town does not get acted on.

    The translated text then takes the same path a hand edit takes — remade,
    versioned and verified — so the downloads carry it and the previous
    language is still in the version history.
    """
    with session_context(session_id):
        state = await _require_state(request, session_id)
        _require_existing(state)
        text = str(state.get("letter_text") or "")
        if state.get("status") != "ready" or not text.strip():
            raise HTTPException(409, "There is no finished petition to translate yet.")

        target = body.language
        keep = verbatim_lines(state.get("fields") or {})
        lines = text.split("\n")
        source = language_of(lines, keep)
        log.info("session.translate", extra={"source": source, "target": target})
        if source == target:
            # Nothing to do, and nothing pretended: no new version, no
            # re-render, and the same document handed straight back.
            return session_view(state)

        try:
            result = await translate_lines(lines, target, keep=keep, source=source)
        except Exception as exc:  # noqa: BLE001
            log.warning("translate.request_failed", extra={"error": str(exc)[:200]})
            raise HTTPException(
                503, "The translation service is unavailable. "
                     "Your petition has not been changed.") from None

        translated = "\n".join(result.lines)
        if translated.strip() == text.strip():
            raise HTTPException(
                503, "The petition could not be translated. It has not been changed.")

        # The same route a hand edit takes: used exactly as given, then
        # rendered, versioned and verified like any other change.
        outcome = await _workflow(request).invoke(
            session_id,
            {"utterance": "", "intent": "edit_text", "understood_by": "form",
             "_extracted": {}, "_corrections": {}, "_correction_target": None,
             "_revision": None, "_emblem": None, "_skip_understand": True,
             "_edited_text": translated,
             "_edit_label": {"source": "Translation",
                             "summary": f"Translated into {_LANGUAGE_NAMES[target]}"}},
            guard=_version_guard(body.expected_version, ready=True, text=translated),
        )
        return session_view(outcome)


@router.post("/sessions/{session_id}/revise")
async def revise_session(session_id: str, body: ReviseRequest, request: Request) -> dict:
    """Use the same editing interpretation as chat and voice."""
    with session_context(session_id):
        result = await _workflow(request).invoke(
            session_id, {"utterance": body.instruction},
            guard=_version_guard(body.expected_version, ready=True),
        )
        return session_view(result)


@router.get("/sessions/{session_id}/versions")
async def document_versions(session_id: str, request: Request) -> dict:
    """Saved content snapshots; filesystem paths never cross the API boundary."""
    state = await _require_state(request, session_id)
    versions = revisions.history(state)
    return {
        "session_id": session_id,
        "reference": state.get("petition_reference") or (state.get("document") or {}).get("reference"),
        "current_version": int(state.get("document_version") or (versions[-1]["version"] if versions else 0)),
        "versions": [{key: item.get(key) for key in
                      ("version", "updated_at", "source", "summary", "letter_text", "verification")}
                     for item in versions],
    }


@router.post("/sessions/{session_id}/restart")
async def restart_session(session_id: str, request: Request) -> dict:
    with session_context(session_id):
        state = await _workflow(request).invoke(
            session_id,
            {"utterance": "", "intent": "restart", "understood_by": "form",
             "_extracted": {}, "_corrections": {}, "_correction_target": None, "_edited_text": None,
             "_skip_understand": True},
            guard=_require_existing,
        )
        log.info("session.restarted")
        return session_view(state)


@router.post("/sessions/{session_id}/cancel")
async def cancel_session(session_id: str, request: Request) -> dict:
    with session_context(session_id):
        state = await _workflow(request).invoke(
            session_id,
            {"utterance": "", "intent": "cancel", "understood_by": "form",
             "_extracted": {}, "_corrections": {}, "_correction_target": None, "_edited_text": None,
             "_skip_understand": True},
            guard=_require_existing,
        )
        log.info("session.cancelled")
        return session_view(state)


# --------------------------------------------------------------------------- #
# Documents
# --------------------------------------------------------------------------- #


async def _letter_only(state: LetterState, kind: str) -> Path:
    """The petition re-rendered without the attachments appended to it.

    Built on demand rather than alongside the main document: most citizens
    download one form or the other, and producing both every time would add a
    second LibreOffice conversion to every generation for a file that is
    usually never fetched.

    Cached under the version-stamped name of the document it came from, so a
    petition edited after generation produces a new one rather than serving
    the previous version's letter.
    """
    import asyncio

    from ..domain import emblem
    from ..services import render as render_service

    settings = get_settings()
    document = state.get("document") or {}
    docx_path = Path(str(document.get("docx") or ""))

    target = settings.document_dir / f"{docx_path.stem}-letter-only.docx"
    if not target.is_file():
        await asyncio.to_thread(
            render_service.render_docx,
            state.get("letter_text") or "", target,
            reference=str(document.get("reference") or ""),
            title=the_template().label_for("en"), settings=settings,
            placement=emblem.placement_for(state.get("emblem"), settings),
            enclosures=None,
        )
    if kind == "docx":
        return target

    pdf_path, error = await render_service.render_pdf(target, settings)
    if pdf_path is None:
        # The package PDF exists; this variant could not be made. Saying so is
        # better than quietly handing back the one WITH the attachments, which
        # is not what was asked for.
        raise HTTPException(
            503, "The letter-only PDF could not be produced on this service. "
                 "The full petition PDF is available.")
    log.info("document.letter_only", extra={"kind": kind, "error": error or ""})
    return pdf_path


@router.get("/sessions/{session_id}/document/package.pdf")
async def document_package(session_id: str, request: Request) -> FileResponse:
    """The petition, an index, and then the citizen's originals.

    WHY THIS IS NOT THE ORDINARY PDF. The DOCX carries its attachments as
    pictures — that is all a Word file can hold of another document — and it
    stops at twelve pages per attachment. The PDF is converted from that
    DOCX, so it inherits both limits.

    This is assembled the other way round: the pages of an attached PDF are
    COPIED ACROSS, so their text layer survives and a hundred-page annexure
    arrives as a hundred pages. It is what an office receives and files; the
    DOCX remains the thing a citizen edits.

    Built on request rather than at generation time. Most petitions are
    never packaged, the inputs cannot change once the petition is ready, and
    copying a hundred pages is not work to do speculatively on every
    generation.
    """
    with session_context(session_id):
        built, result, document = await _package_for(request, session_id)
        reference = str(document.get("reference") or session_id).replace("/", "-")
        return FileResponse(
            built, media_type="application/pdf",
            filename=f"{reference}-package.pdf",
            headers={"Cache-Control": "no-store",
                     "X-Petition-Version": str(document.get("version") or 1),
                     "X-Package-Pages": str(result.total_pages),
                     "X-Package-Complete": "1" if result.complete else "0"})


async def _package_for(request: Request, session_id: str):
    """Build the combined package, or hand back the one already built.

    Shared by the download and by the page renderer that draws the preview,
    because those are two views of ONE document and rebuilding it per page
    request would copy a hundred attached pages a hundred times over.

    Keyed on the document version, so a petition edited after generation
    rebuilds rather than serving the previous version's package.
    """
    state = await _require_state(request, session_id)
    document = state.get("document") or {}
    if state.get("status") != "ready" or not document.get("docx"):
        raise HTTPException(409, "The petition has not been generated yet.")

    version = str(document.get("version") or 1)
    cached = _PACKAGE_CACHE.get(session_id)
    if cached and cached[0] == version and cached[1].is_file():
        return cached[1], cached[2], document

    built, result = await _build_package(state, session_id, document)
    _PACKAGE_CACHE[session_id] = (version, built, result)
    return built, result, document


async def _build_package(state: LetterState, session_id: str, document: dict):
    """The assembly itself. Kept apart from the caching so each reads."""

    language = state.get("language", "en")
    enclosed = attachment_rules.AttachmentSet.from_state(state.get("attachments"))

    # THE LETTER ALONE IS THE BASE, not the ordinary PDF. That one already
    # carries the attachments rasterised into it, so packaging it would
    # deliver every attachment twice — once as pictures inside the letter
    # and again as the originals behind the index. Measured on a real
    # petition: a 2-page letter with one 2-page enclosure came out as
    # 7 pages instead of 5.
    #
    # THE ORDINARY PDF IS NOT REQUIRED TO EXIST. It used to be, and that
    # was wrong: the letter-only PDF is rendered here from `letter_text`
    # anyway, so gating on a file this endpoint does not use meant the
    # package was refused whenever the main PDF conversion was slow,
    # queued or unavailable — which is exactly when a citizen is standing
    # at a counter pressing the button again.
    try:
        letter = await _letter_only(state, "pdf")
    except Exception as exc:  # noqa: BLE001
        log.warning("document.package_letter_failed",
                    extra={"error": str(exc)[:200]})
        raise HTTPException(
            503, "The petition could not be converted to PDF on this "
                 "server, so the combined package cannot be built. The "
                 "petition and the attachments are still available "
                 "separately.") from exc
    if not letter.is_file():
        raise HTTPException(410, "The generated file is no longer on disk.")
    items = []
    for index, attachment in enumerate(enclosed.items, start=1):
        try:
            source = attachment_store.path_of(session_id, attachment)
        except Exception:  # noqa: BLE001
            source = None
        if source is None:
            continue
        items.append(package.Item(
            label=f"{index}. {attachment.label(language)}",
            path=Path(source), filename=attachment.filename))

    # Beside the petition it belongs to, so it is cleaned up with it.
    destination = letter.with_name(f"{letter.stem}-package.pdf")
    words = _PACKAGE_WORDS.get(language, _PACKAGE_WORDS["en"])
    result = await package.build(
        letter, items, destination,
        index_title=words["index"], held_separately=words["separate"])

    log.info("document.package", extra={
        "attachments": len(result.items),
        "included": sum(1 for i in result.items if i.included),
        "pages": result.total_pages,
        "complete": result.complete,
    })
    return destination, result


# One built package per session, keyed by document version. The preview asks
# for pages one at a time, and rebuilding a hundred-page package on each of
# those requests would copy the citizen's attachments a hundred times over.
_PACKAGE_CACHE: dict[str, tuple[str, Path, object]] = {}

# What a preview page is rendered at. 110 DPI is legible for a scanned Tamil
# letter on a laptop without producing a megabyte per page; the citizen who
# needs to read the small print opens the original, which is one click away.
_PREVIEW_DPI = 110
_PREVIEW_MAX_DPI = 200


@router.get("/sessions/{session_id}/document/package/pages")
async def package_pages(session_id: str, request: Request) -> dict:
    """What the combined package contains, page by page.

    The preview draws one continuous document — petition, index, then the
    citizen's originals — and it needs to know how many pages there are and
    where each attachment begins BEFORE it draws anything, so it can put up
    the right number of placeholders and load only what is on screen.

    Sending the pages themselves here instead would mean a hundred images in
    one response for a hundred-page annexure. It sends a list of numbers.
    """
    import pymupdf

    with session_context(session_id):
        built, result, document = await _package_for(request, session_id)
        language = "ta" if (await _require_state(request, session_id)
                            ).get("language") == "ta" else "en"
        # Counted from the FILE, not from the arithmetic. `Result.total_pages`
        # adds an index page whether or not one was drawn, which is right
        # whenever something is attached and one short of the truth when
        # nothing is — and a preview that asks for a page which is not there
        # is a broken image in front of a citizen.
        with pymupdf.open(built) as document_:
            total = int(document_.page_count)

        pages: list[dict] = []
        petition_pages = int(getattr(result, "petition_pages", 0) or 0)
        for number in range(1, petition_pages + 1):
            pages.append({"page": number, "section": "petition"})
        placed = [item for item in result.items if item.included]
        if placed:
            pages.append({"page": petition_pages + 1, "section": "index"})
        # Each attachment's own run of pages, so the preview can draw a
        # boundary at the top of the first one rather than guessing.
        cursor = petition_pages + (1 if placed else 0)
        for order, item in enumerate(placed, start=1):
            for offset in range(int(item.pages or 0)):
                cursor += 1
                pages.append({
                    "page": cursor,
                    "section": "attachment",
                    "attachment": order,
                    "label": item.label,
                    "filename": item.filename,
                    "first": offset == 0,
                    "of": int(item.pages or 0),
                })

        missing = [{"label": i.label, "filename": i.filename,
                    "reason": i.reason} for i in result.items if not i.included]
        return {
            "total": total,
            "petition_pages": petition_pages,
            "complete": bool(result.complete),
            "language": language,
            "pages": pages,
            # Named rather than silently dropped: "do not pretend it was
            # merged if it was not".
            "not_included": missing,
            "page_url": (f"/api/sessions/{session_id}"
                         f"/document/package/page/{{n}}.png"),
            "version": str(document.get("version") or 1),
        }


@router.get("/sessions/{session_id}/document/package/page/{number}.png")
async def package_page(session_id: str, number: int, request: Request,
                       dpi: int = _PREVIEW_DPI) -> Response:
    """One page of the combined package, drawn as an image.

    WHY AN IMAGE AND NOT THE PDF. Handing the browser's PDF plugin an
    embedded document was measured doing two things badly: it re-issued its
    own requests (aborted fetches in the browser log), and it gives no way to
    load a hundred-page annexure a page at a time. Rendering here means the
    preview is a list of ordinary images that the page can lazy-load, and
    what the citizen sees is the actual page — the scan, the handwriting, the
    photograph — not a transcription of it.

    Cached on disk beside the package, because scrolling back up a long
    document must not re-render what was already drawn.
    """
    import asyncio

    import pymupdf

    with session_context(session_id):
        built, result, document = await _package_for(request, session_id)
        with pymupdf.open(built) as document_:
            total = int(document_.page_count)
        if number < 1 or number > total:
            raise HTTPException(404, "That page is not in this package.")
        # Clamped rather than trusted: a query string must not be able to ask
        # this server to render a 2000 DPI bitmap of a hundred-page document.
        resolution = max(60, min(int(dpi or _PREVIEW_DPI), _PREVIEW_MAX_DPI))

        cache = built.with_name(f"{built.stem}-p{number}-{resolution}.png")
        if not cache.is_file():
            def draw() -> None:
                with pymupdf.open(built) as document_:
                    document_[number - 1].get_pixmap(dpi=resolution).save(str(cache))

            try:
                await asyncio.to_thread(draw)
            except Exception as exc:  # noqa: BLE001
                log.warning("document.package_page_failed",
                            extra={"page": number, "error": str(exc)[:160]})
                raise HTTPException(
                    500, "That page could not be drawn.") from exc

        return FileResponse(
            cache, media_type="image/png",
            headers={"Cache-Control": "no-store",
                     "X-Package-Page": str(number),
                     "X-Package-Pages": str(total)})


# The two phrases the index page needs. Not in the template: they describe
# this service's own packaging, not the letter an office prescribes.
_PACKAGE_WORDS = {
    "en": {"index": "SUPPORTING DOCUMENTS",
           "separate": "held separately with this petition"},
    "ta": {"index": "\u0b87\u0ba3\u0bc8\u0b95\u0bcd\u0b95\u0baa\u0bcd\u0baa\u0b9f\u0bcd\u0b9f \u0b86\u0bb5\u0ba3\u0b99\u0bcd\u0b95\u0bb3\u0bcd",
           "separate": "\u0ba4\u0ba9\u0bbf\u0baf\u0bbe\u0b95 \u0b87\u0ba3\u0bc8\u0b95\u0bcd\u0b95\u0baa\u0bcd\u0baa\u0b9f\u0bcd\u0b9f\u0ba4\u0bc1"},
}


async def _document(request: Request, session_id: str, kind: str, *,
                    with_enclosures: bool = True) -> FileResponse:
    state = await _require_state(request, session_id)
    verification = state.get("verification") or {}
    # `hand_edited` passes the gate the same way `ok` does. The check failed
    # because the CITIZEN changed their own letter; they have been told which
    # detail went missing, and the file is theirs to download.
    verified = bool(verification.get("ok") or verification.get("hand_edited") or verification.get("user_edited"))
    if (state.get("status") != "ready" or not state.get("confirmed")
            or state.get("field_errors") or not verified):
        raise HTTPException(409, "The petition has not been generated yet.")
    document = state.get("document") or {}
    path_text = document.get(kind)
    if not path_text:
        raise HTTPException(
            404,
            "No PDF was produced for this petition. The DOCX is available."
            if kind == "pdf" else "No document was produced.",
        )
    path = Path(path_text)
    if not path.is_file():
        raise HTTPException(410, "The generated file is no longer on disk.")

    # With no attachments the two forms are the same file, so nothing is
    # re-rendered for a distinction that does not exist.
    enclosed = attachment_rules.AttachmentSet.from_state(state.get("attachments"))
    letter_only = not with_enclosures and bool(enclosed.items)
    if letter_only:
        path = await _letter_only(state, kind)

    reference = str(document.get("reference") or session_id).replace("/", "-")
    if letter_only:
        reference = f"{reference}-letter"
    media = (
        "application/pdf" if kind == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return FileResponse(path, media_type=media, filename=f"{reference}.{kind}",
                        headers={"Cache-Control": "no-store", "X-Petition-Version": str(document.get("version") or 1)})


@router.get("/sessions/{session_id}/document.pdf")
async def document_pdf(session_id: str, request: Request,
                       enclosures: bool = True) -> FileResponse:
    """The petition. `?enclosures=0` for the letter without the files after it.

    Two things a citizen legitimately wants at different moments: the whole
    package to hand in at the office, and the letter on its own to read, to
    e-mail, or to print when the attachments are already in the envelope as
    paper. Default is the package, because that is what gets submitted.
    """
    with session_context(session_id):
        return await _document(request, session_id, "pdf",
                               with_enclosures=enclosures)


@router.get("/sessions/{session_id}/document.docx")
async def document_docx(session_id: str, request: Request,
                        enclosures: bool = True) -> FileResponse:
    with session_context(session_id):
        return await _document(request, session_id, "docx",
                               with_enclosures=enclosures)


# --------------------------------------------------------------------------- #
# Spoken replies
# --------------------------------------------------------------------------- #


@router.get("/sessions/{session_id}/speech")
async def speech(
    session_id: str,
    request: Request,
    turn: int | None = None,
    section: int | None = None,
):
    """Audio for something the citizen has asked to hear again.

    Three things, and nothing else:

        no parameter   the assistant's current reply, as before
        turn=N         assistant turn N, said again on request
        section=N      one section of the finished petition

    READING IS PRESENTATION. Nothing here touches the record, the document
    or the workflow, and none of it can be reached for a turn the citizen
    spoke: `turn` addresses the ASSISTANT's side of the transcript only. A
    citizen's own answer read back aloud at a counter is heard by the queue
    behind them, and they did not ask for that by pressing a speaker icon
    beside a question.
    """
    from fastapi.responses import Response

    if turn is not None and section is not None:
        raise HTTPException(400, "Ask for a turn or a section, not both.")

    with session_context(session_id):
        state = await _require_state(request, session_id)
        language = state.get("language", "en")
        headers = {}

        if turn is not None:
            # `turns` on the record; `session_view` is what renames it to
            # `transcript` for the page. Reading the view's name off the raw
            # state found nothing, and every speaker icon returned 404.
            spoken = [entry for entry in (state.get("turns") or [])
                      if entry.get("who") == "assistant"]
            if not 0 <= turn < len(spoken):
                raise HTTPException(404, "That question is not in this conversation.")
            spoken_text = redact_for_speech(spoken[turn].get("text") or "")
        elif section is not None:
            # Sectioned rather than read in one go: a petition runs past
            # what a speech service will take in a single request, and a
            # citizen who has heard enough can stop between sections instead
            # of waiting out the whole document.
            sections = readable_sections(state.get("letter_text") or "")
            if not sections:
                raise HTTPException(404, "There is no document to read yet.")
            headers["X-Speech-Sections"] = str(len(sections))
            if not 0 <= section < len(sections):
                raise HTTPException(404, "That section is past the end of the petition.")
            # `readable_sections` has already taken the identifiers out —
            # the document on the screen carries them, the room does not
            # need to hear them. Redacting again here would say that rule
            # lives in two places when it lives in one, and
            # `test_voice.py::TestTheDocumentIsReadWhole` is what holds it.
            spoken_text = sections[section]
        else:
            spoken_text = speech_for(
                display_text=state.get("reply", ""), view=session_view(state),
                template=the_template(), language=language,
                allow_spoken_identifiers=get_settings().voice_spoken_identifiers,
            )

        if not spoken_text.strip():
            raise HTTPException(404, "There is nothing to read there.")
        audio = await tts.speak(spoken_text, language)
        if audio is None:
            raise HTTPException(503, "Spoken replies are not configured on this service.")
        return Response(content=audio, media_type="audio/wav", headers=headers)
