"""The public shape of a session.

One function, used by both the REST endpoints and the WebSocket, so that a
citizen who switches from typing to speaking mid-conversation sees exactly the
same record either way.

Internal machinery does not cross this boundary: no file paths, no provider
names, no transient extraction keys. What comes out is what a screen needs to
render and what an officer needs to read.
"""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from ..domain import attachments as attachment_rules
from ..domain import emblem, phrasing, prior_petition, revisions
from ..domain.fields import MAX_FREE_TEXT, display_value
from ..domain.letter import verbatim_lines
from ..domain.phrasing import DISCLAIMER
from ..domain.templates import the_template
from ..graph.state import LetterState
from ..knowledge.schema import UNVERIFIED, UNVERIFIED_TA
from ..services import extraction
from ..services import translate as translate_service

# The knowledge layer's findings, in the order an officer reads them: which
# office, under what law, then what happens next. Labels live here rather than
# in the page so both languages come from one place.
_ANALYSIS_SECTIONS: tuple[tuple[str, str, str], ...] = (
    ("department", "Department", "துறை"),
    ("petition_category", "Category", "வகை"),
    ("responsible_authority", "Responsible authority", "பொறுப்பு அதிகாரி"),
    ("applicable_acts", "Applicable Acts", "பொருந்தும் சட்டங்கள்"),
    ("applicable_rules", "Applicable Rules", "பொருந்தும் விதிகள்"),
    ("government_orders", "Government Orders", "அரசாணைகள்"),
    ("processing_hierarchy", "Processing hierarchy", "நடைமுறை படிநிலை"),
    ("required_documents", "Documents required", "தேவையான ஆவணங்கள்"),
    ("processing_steps", "Processing steps", "நடைமுறைப் படிகள்"),
    ("transfer_process", "Transfer process", "மாற்ற நடைமுறை"),
    ("closure_process", "Closure process", "முடிவு நடைமுறை"),
)


def analysis_view(analysis: dict[str, Any] | None, language: str) -> dict[str, Any] | None:
    """Flatten the analysis into sections and one numbered source list.

    Citations become indices into a single deduplicated list, so the panel can
    print [1][3] beside a finding and list each document once underneath —
    which is how a government note cites, and it keeps the page from having to
    know the eleven field names.
    """
    if not analysis:
        return None

    sources: list[dict[str, Any]] = []
    index_of: dict[tuple, int] = {}

    def cite(source: dict[str, Any]) -> int:
        key = (source.get("document_id") or source.get("document_title"),
               source.get("section"), source.get("page_number"))
        if key not in index_of:
            index_of[key] = len(sources) + 1
            sources.append({**source, "index": len(sources) + 1})
        return index_of[key]

    sections = []
    for name, english, tamil in _ANALYSIS_SECTIONS:
        raw = analysis.get(name)
        findings = raw if isinstance(raw, list) else ([raw] if raw else [])
        items = []
        for finding in findings:
            if not isinstance(finding, dict) or not finding.get("value"):
                continue
            items.append({
                "value": finding["value"],
                "cites": [cite(s) for s in (finding.get("sources") or [])],
            })
        if items:
            sections.append({
                "key": name,
                "label": tamil if language == "ta" else english,
                "items": items,
            })

    unverified = not sections
    return {
        "available": True,
        "unverified": unverified,
        "message": (UNVERIFIED_TA if language == "ta" else UNVERIFIED) if unverified else "",
        "sections": sections,
        "sources": sources,
        "retrieved_chunks": int(analysis.get("retrieved_chunks") or 0),
        "includes_external": bool(analysis.get("includes_external")),
        # Conflicts that could NOT be resolved. Shown as warnings, because an
        # answer assembled from two versions of a rule is worse than no answer,
        # and the officer is the one who can settle which applies.
        "warnings": [str(w) for w in (analysis.get("warnings") or [])],
        # Every conflict, resolved ones included, so an officer can see that
        # the corpus held two answers and which one was used.
        "conflicts": [
            {
                "resolution": c.get("resolution"),
                "message": c.get("message"),
                "newer": (c.get("newer") or {}).get("document_title"),
                "older": (c.get("older") or {}).get("document_title"),
            }
            for c in (analysis.get("conflicts") or []) if isinstance(c, dict)
        ],
        # Said plainly on the panel. An officer has to be able to tell a
        # retrieval result from something the citizen stated, and from
        # settled legal advice, which this is not.
        "note": (
            "தானியங்கி ஆவணத் தேடல். மனுவின் பகுதி அல்ல; அலுவலகச் சரிபார்ப்பு தேவை."
            if language == "ta" else
            "Automated document search. Not part of the petition; requires "
            "verification by the office."
        ),
    }



def attachments_view(state: LetterState, language: str,
                     analysis: dict | None) -> dict[str, Any]:
    """The attachment step, as the page needs to draw it.

    `suggested` and `required` are deliberately two different lists. The
    template's list is what a citizen is prompted to consider; `required` holds
    only documents an OFFICIAL retrieved source actually says are mandatory, and
    it is usually empty. Presenting a suggestion as a requirement tells a
    citizen at a service centre to go home and fetch something nobody asked for.
    """
    template = the_template()
    enclosed = attachment_rules.AttachmentSet.from_state(state.get("attachments"))

    items = []
    for attachment in enclosed.items:
        extracted = attachment.extracted or {}
        prior = prior_petition.PriorPetition.from_dict(extracted) if extracted else None
        fields = []
        if prior is not None:
            for name in ("reference_number", "petition_number", "submitted_on",
                         "department", "authority", "subject", "status"):
                value = getattr(prior, name, None)
                if value:
                    fields.append({
                        "name": name,
                        "value": value.value,
                        "evidence": value.evidence,
                        "confidence": round(value.confidence, 2),
                    })
        items.append({
            "attachment_id": attachment.attachment_id,
            "filename": attachment.filename,
            "kind": attachment.kind,
            "label": attachment.label(language),
            "size": attachment.size,
            "confirmed": attachment.confirmed,
            # True while the citizen still has to look at what was read. The
            # page shows a confirmation card, and nothing here reaches the
            # petition until they answer it.
            "needs_confirmation": bool(extracted) and not attachment.confirmed,
            "readable": bool(prior.readable) if prior else True,
            # Phrased in the session language. `prior.reason` is written for the
            # log and is English; showing it verbatim put an English sentence in
            # the middle of a Tamil petition workflow.
            "reason": (phrasing.phrase("attachment_unreadable", language)
                       if prior and not prior.readable else ""),
            # The English detail, for an operator reading a support ticket.
            "reason_detail": prior.reason if prior else "",
            "low_confidence": bool(prior.low_confidence) if prior else False,
            "fields": fields,
        })

    return {
        "status": state.get("status"),
        "offered": bool(state.get("attachments_offered")),
        "done": bool(state.get("attachments_done")),
        # The citizen has just said yes and has not sent a file yet. The page
        # opens the picker on this rather than leaving them to hunt for the
        # button after answering a question with "yes".
        "awaiting_file": state.get("intent") == "attach",
        "question": (attachment_rules.MORE_OR_CONTINUE if enclosed
                     else attachment_rules.OFFER)[language],
        "add_label": attachment_rules.ADD_LABEL[language],
        "continue_label": attachment_rules.CONTINUE_LABEL[language],
        "suggested": attachment_rules.suggestions(template, language),
        "suggestion_note": attachment_rules.SUGGESTION_NOTE[language],
        "required": attachment_rules.required_from_analysis(analysis, language),
        "items": items,
        "max": attachment_rules.MAX_ATTACHMENTS,
        "max_bytes": attachment_rules.MAX_BYTES,
        "accepts": sorted(attachment_rules.ALLOWED_SUFFIXES),
        # Said plainly on the panel. Nothing photographed can be read here.
        "ocr": extraction.ocr_status(),
    }



def petition_title(state: LetterState, language: str) -> str:
    """What to call this petition in a list, in the session's own language.

    Best available, in order:

      1. the subject the model wrote for it — tailored to the grievance and
         already the line an officer reads first;
      2. the citizen's own opening words, trimmed to a phrase;
      3. the form's name, for a petition that has not reached a grievance yet.

    Computed here rather than in the page so both languages come from one
    place and a stored name cannot drift from the document it belongs to.
    """
    template = the_template()
    import re

    current_subject = re.search(r"(?mi)^(?:Subject|Sub|பொருள்)\s*:\s*(.+)$", state.get("letter_text") or "")
    if current_subject:
        return _shorten(current_subject[1].strip())
    composition = state.get("composition") or {}
    subject = str(composition.get("subject") or "").strip()
    if subject:
        return _shorten(subject)

    grievance = str((state.get("fields") or {}).get("grievance") or "").strip()
    if grievance:
        return _shorten(grievance)

    return template.label_for(language)


def _shorten(text: str, limit: int = 58) -> str:
    """One line, ending at a word, short enough for a narrow list."""
    flat = " ".join(str(text or "").split())
    if len(flat) <= limit:
        return flat
    # Prefer a sentence boundary when there is one inside the budget: a title
    # that ends mid-clause reads worse than a shorter one that does not.
    for stop in (". ", "। ", "? ", "! "):
        head = flat[:limit].rsplit(stop, 1)
        if len(head) > 1 and len(head[0]) > 20:
            return head[0]
    return flat[:limit].rsplit(" ", 1)[0] + "…"


def session_view(state: LetterState) -> dict[str, Any]:
    language = state.get("language", "en")
    template = the_template()
    fields = state.get("fields") or {}
    errors = state.get("field_errors") or {}

    collected: list[dict[str, Any]] = []
    outstanding: list[dict[str, Any]] = []
    for spec in template.fields:
        entry = {
            "name": spec.name,
            "label": spec.label_for(language),
            "type": spec.type,
            "required": spec.required,
            "prompt": spec.prompt_for(language),
            # These are text-entry limits, not identifier digit counts: spoken
            # number words remain valid inputs to the same validators.
            "max_length": {"person_name": 80, "address": 400}.get(spec.type, MAX_FREE_TEXT),
            "error": errors.get(spec.name, {}).get("message"),
        }
        if spec.name in fields:
            collected.append({
                **entry,
                "value": fields[spec.name],
                "display": display_value(spec.type, fields[spec.name], language),
                "source": (state.get("field_sources") or {}).get(spec.name),
            })
        else:
            outstanding.append(entry)

    document = state.get("document") or {}
    verification = state.get("verification") or {}
    # A hand-edited petition whose verification now complains is still handed
    # over. The complaint is about a detail the CITIZEN removed from their own
    # letter, it is shown to them as a warning, and withholding the document
    # would be answering "you changed something" by confiscating it.
    verified = bool(verification.get("ok") or verification.get("hand_edited") or verification.get("user_edited"))
    ready = (
        state.get("status") == "ready" and bool(document.get("docx"))
        and bool(state.get("confirmed")) and not errors and verified
    )

    versions = revisions.history(state)
    version = int(state.get("document_version") or (versions[-1]["version"] if versions else 0))
    return {
        "session_id": state.get("session_id"),
        "language": language,
        "started_at": state.get("created_at"),
        "updated_at": state.get("updated_at"),
        "status": state.get("status", "collecting"),
        "version": version,
        "updated_by": versions[-1].get("source") if versions else None,
        "editing": {"active": ready, "pending": state.get("pending_edit")},
        "versions": [{key: entry.get(key) for key in ("version", "updated_at", "source", "summary")}
                     for entry in versions],
        "form": {
            "id": template.id,
            "label": template.label_for(language),
            "office": template.text_for("addressee", language),
            "department": template.text_for("department", language),
        },
        # A short name for this petition, for the list in the sidebar. Derived
        # from the petition itself — the drafted subject line where there is
        # one, the citizen's opening words otherwise.
        "title": petition_title(state, language),
        "reply": state.get("reply", ""),
        "awaiting": state.get("awaiting"),
        "awaiting_correction": bool(state.get("awaiting_correction")),
        "collected": collected,
        "outstanding": outstanding,
        "missing": state.get("missing") or [],
        "field_errors": errors,
        "progress": {"answered": len(collected), "total": len(template.fields)},
        "confirmed": bool(state.get("confirmed")),
        "corrections": state.get("corrections") or [],
        # Wording changes the citizen asked for after reading the petition.
        # Shown beside the corrections so an officer can see what was asked of
        # the draft as well as what was changed in the record.
        "revisions": state.get("revisions") or [],
        # Where the emblem is printed. Exposed so the page can show it and so
        # an operator can see what a citizen asked for without opening the
        # document.
        "emblem": emblem.placement_for(state.get("emblem"), get_settings()).as_dict(),
        "warnings": state.get("warnings") or [],
        "error": state.get("error"),
        # The petition text is returned so a citizen can read it before
        # downloading. File paths are NOT: downloads go through the document
        # endpoints, which check the session, rather than by handing out a path.
        "letter_text": state.get("letter_text") if ready else None,
        # What language the DOCUMENT is in, which is not always the language of
        # the conversation: a citizen can ask for the finished petition in
        # another one. Computed with the same rule the translator uses, so the
        # page never has to work it out from the text a second time and reach a
        # different answer.
        "document_language": (
            translate_service.language_of(
                str(state.get("letter_text") or "").splitlines(),
                verbatim_lines(state.get("fields") or {}),
            ) if ready and state.get("letter_text") else language
        ),
        # What the model wrote, if anything. Null means the petition carries
        # the standard wording, which is worth being able to see.
        "composition": state.get("composition") if ready else None,
        "document": (
            {
                "reference": document.get("reference"),
                "version": version,
                "docx_url": f"/api/sessions/{state.get('session_id')}/document.docx",
                "pdf_url": (
                    f"/api/sessions/{state.get('session_id')}/document.pdf"
                    if document.get("pdf") else None
                ),
                "generated_at": document.get("generated_at"),
            }
            if ready else None
        ),
        # Advisory findings from the government knowledge base. Shown in its
        # own panel, clearly attributed, and never printed on the petition.
        "analysis": analysis_view(state.get("analysis"), language),
        # The citizen's own evidence for this petition. Kept entirely separate
        # from the government corpus: these files live in the session's
        # directory and are never indexed, embedded or retrievable.
        "attachments": attachments_view(state, language, state.get("analysis")),
        "verification": state.get("verification"),
        "transcript": state.get("turns") or [],
        "disclaimer": DISCLAIMER[language],
    }
