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

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from ..config import get_settings
from ..domain import attachments as attachment_rules
from ..domain import prior_petition, revisions
from ..domain.fields import MAX_FREE_TEXT
from ..domain.letter import verbatim_lines
from ..domain.templates import missing_fields, the_template
from ..graph.state import LetterState, new_state
from ..logging_setup import preview, session_context
from ..services import asr, attachment_store, extraction, llm, tts
from ..services.render import pdf_status
from ..services.speech_text import speech_for
from ..services.translate import language_of, translate_lines
from .views import session_view

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api")


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
        "language_model": {
            "available": language_status["available"],
            "provider": language_status.get("provider"),
            "egress": language_status.get("egress"),
            "detail": language_status.get("detail"),
            "note": language_status.get("note"),
        },
        "dictation": asr.status(settings),
        "spoken_replies": tts.status(settings),
        # What can be done with a file a citizen encloses. `ocr.available` is
        # false on a machine with no engine, and that is a supported state:
        # photographs are attached and reported unreadable rather than guessed.
        "attachments": {
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
async def start_session(body: StartRequest, request: Request) -> dict:
    session_id = str(uuid.uuid4())
    workflow = _workflow(request)

    with session_context(session_id):
        seed = new_state(session_id, body.language)  # type: ignore[arg-type]
        seed["template_id"] = the_template().id

        # Seed and ask in one invocation, so recovery cannot observe an
        # intermediate record with no missing fields and no first question.
        seed["utterance"] = body.text if body.text.strip() else ""
        state = await workflow.invoke(session_id, seed)

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
        read = extraction.extract(stored.path)
        prior = prior_petition.analyse(
            read.text, readable=read.readable, reason=read.reason,
            low_confidence=read.low_confidence)

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

        current.items.append(attachment)
        log.info("attachment.added",
                 extra={"kind": attachment.kind, "readable": read.readable,
                        "method": read.method, "extracted": prior.has_anything})
        result = await _attachment_turn(
            session_id, request,
            intent="attach_added",
            attachments=current.as_state())
        return session_view(result)


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


async def _document(request: Request, session_id: str, kind: str) -> FileResponse:
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

    reference = str(document.get("reference") or session_id).replace("/", "-")
    media = (
        "application/pdf" if kind == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return FileResponse(path, media_type=media, filename=f"{reference}.{kind}",
                        headers={"Cache-Control": "no-store", "X-Petition-Version": str(document.get("version") or 1)})


@router.get("/sessions/{session_id}/document.pdf")
async def document_pdf(session_id: str, request: Request) -> FileResponse:
    with session_context(session_id):
        return await _document(request, session_id, "pdf")


@router.get("/sessions/{session_id}/document.docx")
async def document_docx(session_id: str, request: Request) -> FileResponse:
    with session_context(session_id):
        return await _document(request, session_id, "docx")


# --------------------------------------------------------------------------- #
# Spoken replies
# --------------------------------------------------------------------------- #


@router.get("/sessions/{session_id}/speech")
async def speech(session_id: str, request: Request):
    """Audio for the assistant's current reply, when TTS is configured."""
    from fastapi.responses import Response

    with session_context(session_id):
        state = await _require_state(request, session_id)
        language = state.get("language", "en")
        spoken_text = speech_for(
            display_text=state.get("reply", ""), view=session_view(state),
            template=the_template(), language=language,
            allow_spoken_identifiers=get_settings().voice_spoken_identifiers,
        )
        audio = await tts.speak(spoken_text, language)
        if audio is None:
            raise HTTPException(503, "Spoken replies are not configured on this service.")
        return Response(content=audio, media_type="audio/wav")
