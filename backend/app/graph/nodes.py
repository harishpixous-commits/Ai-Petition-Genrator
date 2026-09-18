"""The eight nodes.

Exactly one of them — `understand` — may call a language model, and it skips
even that whenever the answer can be read deterministically. The other seven are
code: validation, arithmetic over a field list, sentence selection from a written
table, template assembly, a conditional translator, a DOCX writer, and a check
that reads the finished file back off disk.

Node contract: each returns a PARTIAL state dict, which LangGraph merges.

Two rules hold everywhere in this file and are worth stating once:

  * NO RECORDED VALUE IS EVER SENT TO A MODEL. Not as context, not for drafting.
    The model is told which fields are answered, never what the answers are, and
    identifier-typed fields are excluded from every prompt at source.
  * THE CITIZEN'S GRIEVANCE IS NEVER CHANGED ON THE RECORD. It is stored exactly
    as given, shown back to them exactly as given, and is what every later turn
    reasons from.

    What reaches the PETITION is the representation the model writes from it:
    the same matter, stated faithfully in official language. A citizen speaks in
    the grammar of speech, often briefly, sometimes in a different language from
    the letter, and printing that between two formal paragraphs read as a
    mistake rather than as evidence. The model may correct grammar, order the
    facts and formalise them; it may not soften, strengthen, widen or narrow the
    complaint, and it may not add one that was not raised.

    With no model reachable there is nothing to state the complaint with, and a
    petition that names no problem is not a petition — so the citizen's own
    words are placed, exactly as they always were.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..domain import attachments, emblem, phrasing, prior_petition, revisions
from ..domain.fields import (
    clean_text,
    display_value,
    is_sensitive,
    read_boolean,
    validate_field,
)
from ..domain.letter import (
    VERBATIM_FIELDS,
    Composition,
    build_letter_text,
    reference_number,
    verbatim_lines,
    verification_targets,
)
from ..domain.letter import (
    label as letter_label,
)
from ..domain.templates import (
    LetterTemplate,
    match_field,
    missing_fields,
    next_field,
    the_template,
    validate_extracted,
)
from ..domain.understanding import (
    SYSTEM_PROMPT,
    Understanding,
    from_provider_payload,
    understanding_schema,
)
from ..logging_setup import timed
from ..services import render as render_service
from ..services.llm import chat_json, enhance
from ..services.translate import translate_lines
from .state import LetterState, turn

log = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


# Cleared on every turn. `understand` writes them and `validate` reads them; a
# value left over from the previous turn would be recorded a second time.
BLANK_TURN: dict[str, Any] = {"_extracted": {}, "_corrections": {},
                              "_correction_target": None, "_revision": None,
                              "_emblem": None, "_edited_text": None, "_document_edit": None,
                              "_edit_label": None}


# --------------------------------------------------------------------------- #
# Deterministic readers, used before any model is considered
# --------------------------------------------------------------------------- #

# Shorter than this is an acknowledgement, not an instruction about wording.
# "ok", "thanks", "good" must not each rewrite a finished petition.
_MIN_REVISION_CHARS = 8

_RESTART = re.compile(
    r"\b(start over|start again|restart|begin again|from the beginning)\b"
    r"|மீண்டும்\s*தொடங்கு|புதிதாக\s*தொடங்கு|மீண்டும்\s*ஆரம்பி",
    re.I,
)
_CANCEL = re.compile(
    r"\b(cancel|forget it|never mind|abandon|quit|exit|stop this)\b"
    r"|ரத்து\s*செய்|நிறுத்திவிடு|வேண்டவே\s*வேண்டாம்",
    re.I,
)
# A correction is the one case where the fast path must NOT accept an utterance
# as the answer to the pending question: the citizen is talking about a
# different field, and recording it here would put the value in the wrong place.
_CORRECTION = re.compile(
    r"\b(actually|sorry|i meant|i said|instead|change|correct(?:ion)?|mistake|wrong|"
    r"not\s+\d|should be|make it)\b"
    r"|உண்மையில்|தவறு|மாற்று|சரிசெய்|நான்\s*சொன்னது",
    re.I,
)
# A citizen's question is not a failed answer. Detecting one deterministically
# is what lets the first-failure rule below stay strict without silencing
# someone who asked something the form cannot answer by itself.
_QUESTION = re.compile(
    r"[?？]\s*$"
    r"|^(what|why|how|when|where|who|which|can|could|should|do|does|is|are)\b"
    r"|என்ன|ஏன்|எப்படி|எப்போது|எங்கே|யார்|எதை",
    re.I,
)
_TAMIL = re.compile(r"[஀-௿]")

# What a citizen says when a recorded value is WRONG, as opposed to what they
# say when supplying a new one. Matched against the whole captured tail, so
# "the address is wrong" is caught while "my address is Wrongton Street" is not.
_COMPLAINT = re.compile(
    r"(?:wrong|incorrect|not\s+(?:right|correct)|mistaken|a\s+mistake|bad|"
    r"wrong\s+one|different|changed)[.!]*"
    r"|தவறு|தவறாக|சரியில்லை|வேறு",
    re.I)


def _detect_language(text: str) -> str:
    return "ta" if _TAMIL.search(str(text or "")) else "en"


# --------------------------------------------------------------------------- #
# 1. understand — the only agentic step
# --------------------------------------------------------------------------- #


async def understand(state: LetterState) -> dict[str, Any]:
    """What did the citizen just say?

    Tiers, cheapest first, because a voice turn that resolves in tier one costs
    no network round trip at all — and in a conversation that is mostly
    "answer the question that was asked", tier one is the common case.

      1a. Control words: cancel, start over.
      1b. At the read-back: a named field to correct, or a plain yes/no.
      1c. A clean answer to the question that was actually asked.
      2.  One structured-output model call.
      3.  No model reachable: hand the raw utterance to the pending field, so
          the validator says precisely what was wrong with it.
    """
    # A form endpoint has already said which field is being set, so there is
    # nothing to infer. Cleared here so the next spoken turn is read normally.
    if state.get("_skip_understand"):
        return {"_skip_understand": False, "updated_at": _now()}

    # `text` is cleaned for DETECTION only — matching control words, spotting a
    # correction. What gets EXTRACTED is the raw utterance, because each
    # validator does its own normalisation and only the validator knows what is
    # safe to strip for its own field. Cleaning once here, for everything, is
    # what silently deleted the full stop from the end of a citizen's grievance.
    raw = state.get("utterance", "")
    text = clean_text(raw)
    if not text:
        return {**BLANK_TURN, "intent": "unclear", "understood_by": "none", "updated_at": _now()}

    language = state.get("language") or "en"
    # Follow the citizen's script on the opening turn only. Switching mid-form
    # because one Tamil place name appeared in an English sentence would be
    # worse than staying put.
    if not state.get("turns"):
        language = _detect_language(text)

    base: dict[str, Any] = {
        **BLANK_TURN,
        "language": language,
        "updated_at": _now(),
        "question": None,
        "ambiguous": False,
    }

    # ---- tier 1a: control words ----------------------------------------- #
    if _CANCEL.search(text):
        return {**base, "intent": "cancel", "understood_by": "deterministic"}
    if _RESTART.search(text):
        return {**base, "intent": "restart", "understood_by": "deterministic"}

    if state.get("status") == "cancelled":
        return {**base, "intent": "unclear", "understood_by": "deterministic"}

    template = the_template()
    awaiting = state.get("awaiting")
    spec = template.field(awaiting) if awaiting else None

    # ---- tier 1a-ii: where the emblem goes, once a petition exists ------ #
    #
    # Ahead of the yes/no reading, and that order is load-bearing: "right" is
    # one of the words that means YES, so "move the logo to the right" was read
    # as a confirmation and did nothing at all. Everything else about the
    # emblem worked, which is what made it look like a one-off.
    #
    # Layout has exactly one correct outcome per instruction, so it is read
    # from a table of words rather than by a model, and it never reaches the
    # drafting call — moving the emblem must not risk the wording coming back
    # different.
    if state.get("status") == "ready":
        placement = emblem.read_instruction(
            text, emblem.placement_for(state.get("emblem"), get_settings()))
        if placement is not None:
            return {**base, "intent": "emblem", "understood_by": "deterministic",
                    "_emblem": placement.as_dict()}

        # Editing is a continuation of the saved document, not another intake.
        # Factual fields still pass through the original validators. A wording
        # request mentioning "grievance" must not erase that recorded field.
        named = match_field(template, text, language)
        wording = re.search(r"\b(formal|shorter|shorten|firmer|polite|wording)\b|சுருக்க|முறையான", text, re.I)
        if named and not wording and not state.get("pending_edit"):
            field_spec = template.field(named)
            aliases = [named.replace("_", " "), field_spec.label_for("en"),
                       field_spec.label_for(language), *field_spec.aliases.get(language, ())]
            if named == "applicant_name":
                aliases.extend(["name", "my name"])
            aliases.extend({"aadhaar": ["aadhaar", "aadhar"], "mobile": ["mobile", "phone"],
                            "age": ["age"], "address": ["address"], "grievance": ["grievance", "complaint"]}.get(named, []))
            alternatives = "|".join(re.escape(alias) for alias in sorted(set(aliases), key=len, reverse=True))
            supplied = re.search(r"(?:" + alternatives + r")\s*(?:number\s*)?(?:to|is|should be|:|as)\s+(.+)", raw, re.I)
            # "my address is wrong" is a COMPLAINT about the recorded value, not
            # a new one. Without this the connector "is" swallowed it and the
            # address became the literal word "wrong" — and "my name is wrong"
            # set the petitioner's name to "wrong", which the name validator
            # happily accepts. A citizen reporting an error must never have the
            # report itself written into the record.
            if supplied and _COMPLAINT.fullmatch(supplied[1].strip()):
                supplied = None
            if supplied:
                return {**base, "intent": "correct", "understood_by": "fast-path",
                        "_corrections": {named: supplied[1].strip()}}
            return {**base, "intent": "correct", "understood_by": "fast-path",
                    "_correction_target": named}
        plan = revisions.interpret(raw, state.get("pending_edit"))
        if plan is None:
            return {**base, "intent": "unclear", "understood_by": "deterministic"}
        if plan.get("question"):
            return {**base, "intent": "edit_question", "understood_by": "deterministic",
                    "_document_edit": plan}
        return {**base, "intent": "revise", "understood_by": "deterministic",
                "_revision": raw.strip(), "_document_edit": plan}

    # ---- tier 1a-iii: answering the attachment offer -------------------- #
    #
    # Ahead of the yes/no reading for the same reason the emblem is: this
    # question is an either/or, and "I have the receipt" is an answer to it that
    # `read_boolean` sees nothing in at all.
    if state.get("status") == "attachments":
        # The RAW utterance, not the cleaned one. `clean_text` strips a leading
        # "yes"/"ok"/"சரி" as politeness — correct when the rest is an answer
        # to a field question, wrong here, where "yes" IS the answer. "Yes, I
        # want to add attachments" arrived as "i want to add attachments" and
        # lost the only word that decided it.
        choice = attachments.read_choice(raw) or attachments.read_choice(text)
        if choice == "continue":
            return {**base, "intent": "skip_attach", "understood_by": "deterministic"}
        if choice == "add":
            return {**base, "intent": "attach", "understood_by": "deterministic"}
        # Neither. The question stands rather than being answered by a guess.

    # ---- tier 1b: at the read-back, or being asked which field is wrong -- #
    at_readback = state.get("status") in ("confirming", "ready")
    if at_readback or state.get("awaiting_correction"):
        # A named field wins over a bare yes/no, so "no, the address is wrong"
        # is one turn rather than two. A plain "no" names nothing and falls
        # through to the boolean below.
        named = match_field(template, text, language)
        if named:
            return {**base, "intent": "correct", "understood_by": "fast-path",
                    "_correction_target": named}
        if at_readback:
            decision = read_boolean(text)
            if decision is True:
                return {**base, "intent": "confirm", "understood_by": "fast-path"}
            if decision is False:
                return {**base, "intent": "reject", "understood_by": "fast-path"}

    # A finished petition can still be asked to say something differently.
    #
    # The facts are settled by this point — they were confirmed before anything
    # was generated — so what is left to change is the WORDING, and a citizen
    # who has just read their petition is exactly the person who knows what is
    # wrong with it. A named field is handled above and goes through the
    # ordinary correction flow; anything else here is an instruction about how
    # the letter reads.
    #
    # Deliberately deterministic: nothing is interpreted, the sentence is
    # carried to `compose` as the citizen wrote it. What the model may do with
    # it is bounded by the same rules as the first draft — it may not introduce
    # a fact, a number or a date, and it may not touch the grievance.
    if state.get("status") == "ready":
        instruction = text.strip()

        if len(instruction) >= _MIN_REVISION_CHARS and not read_boolean(instruction):
            return {**base, "intent": "revise", "understood_by": "deterministic",
                    "_revision": instruction}
        # Too short, or a bare yes/no, to be an instruction about wording.
        return {**base, "intent": "unclear", "understood_by": "deterministic"}

    # ---- tier 1c: a clean answer to the pending question ----------------- #
    if spec is not None and not _CORRECTION.search(text):
        if validate_field(spec.type, raw).ok:
            return {**base, "intent": "provide", "understood_by": "fast-path",
                    "_extracted": {spec.name: raw}}

        # The answer did not validate. Whether that is worth a model call
        # depends on what it looks like:
        #
        #   * an IDENTIFIER goes straight to the validator, always. There is
        #     nothing to interpret — it is twelve digits or it is not — and
        #     sending it would put the citizen's attempted number on the wire to
        #     learn what code has already established.
        #   * a QUESTION goes to the model. It is not a failed answer, and it is
        #     the one thing on this path with no pre-written reply.
        #   * a FIRST failure at any other field goes to the validator. A round
        #     trip buys nothing; the validator knows exactly what was wrong and
        #     says so. Only a REPEAT failure suggests the citizen is trying to
        #     say something other than the answer to this question.
        failures = (state.get("attempts") or {}).get(spec.name, 0)
        asking = bool(_QUESTION.search(text))
        if is_sensitive(spec.type) or (failures == 0 and not asking):
            return {**base, "intent": "provide", "understood_by": "deterministic",
                    "_extracted": {spec.name: raw}}

    # ---- tier 2: one model call ------------------------------------------ #
    settings = get_settings()

    async def call() -> Understanding:
        payload = await chat_json(
            system=f"{SYSTEM_PROMPT}\n\n{_understanding_context(state, template, awaiting)}",
            user=text,
            schema=understanding_schema(list(template.field_names)),
            max_tokens=700,
            timeout_ms=settings.understand_timeout_ms,
            budget_ms=settings.understand_budget_ms,
        )
        return from_provider_payload(payload)

    with timed(log, "node.understand", awaiting=awaiting, chars=len(text)) as carry:
        understanding: Understanding | None = await enhance(call, None)
        carry["tier"] = "model" if understanding else "fallback"

    # ---- tier 3: no model reachable -------------------------------------- #
    if understanding is None:
        if spec is not None:
            # Hand the raw utterance to the pending field anyway. The validator
            # rejects it and says exactly what was wrong, which is far more use
            # than "I did not understand" — and without this, a deployment with
            # no model answers every bad Aadhaar number with the same sentence.
            return {**base, "intent": "provide", "understood_by": "deterministic",
                    "_extracted": {spec.name: raw}}
        return {**base, "intent": "unclear", "understood_by": "none"}

    return {
        **base,
        "intent": understanding.intent,
        "understood_by": "model",
        "ambiguous": understanding.ambiguous,
        "question": understanding.question,
        "_extracted": understanding.fields,
        "_corrections": understanding.corrections,
    }


def _understanding_context(state: LetterState, template: LetterTemplate, awaiting: str | None) -> str:
    """The minimum the model needs: which fields exist, and what was just asked.

    NO RECORDED VALUE APPEARS HERE. The model needs to know that a field is
    already answered — so it can tell a correction from a first answer — and it
    does not need to know what the answer was. An earlier version wrote
    "[already recorded: <value>]" into this prompt, which put a validated
    Aadhaar number on the wire to an external provider.

    Small in every other way too: a model given the whole transcript starts
    re-answering earlier questions, where a model given the field list and the
    pending question reads one sentence and reports what is in it.
    """
    held = state.get("fields") or {}
    lines = [f"Form: {template.label_for('en')}", "Fields on this form:"]
    for spec in template.fields:
        status = " [already answered]" if spec.name in held else ""
        lines.append(f"  - {spec.name} ({spec.type}): {spec.label_for('en')}{status}")
    if awaiting:
        lines.append(f"\nThe question just asked was for the field: {awaiting}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 2. validate — code decides, always
# --------------------------------------------------------------------------- #


async def validate(state: LetterState) -> dict[str, Any]:
    """Apply the understanding to the record, judging every value in code.

    A raw string never reaches `fields`. It is validated first, and a value that
    fails is not stored at all — it becomes a `field_error` that `ask` turns
    into a specific sentence about what was wrong with it.
    """
    intent = state.get("intent", "provide")
    language = state.get("language", "en")
    template = the_template()
    now = _now()

    turns = (
        [turn("citizen", state.get("utterance", ""), intent=intent)]
        if state.get("utterance")
        else []
    )

    # A cancelled session does not quietly resume because the citizen said
    # something else afterwards. Only an explicit restart reopens it.
    if state.get("status") == "cancelled" and intent != "restart":
        return {"status": "cancelled", "awaiting": None, "updated_at": now, "turns": turns}

    if intent == "cancel":
        reply = phrasing.phrase("cancelled", language)
        return {"status": "cancelled", "reply": reply, "awaiting": None,
                "awaiting_correction": False,
                "confirmed": False, "composition": None, "letter_text": None,
                "document": None, "verification": None, "warnings": [], "error": None,
                "turns": turns + [turn("assistant", reply)], "updated_at": now}

    if intent == "restart":
        reply = phrasing.phrase("restarted", language)
        return {
            "fields": {}, "field_sources": {}, "attempts": {},
            # Recomputed, not hard-coded to []: an empty `missing` on an empty
            # record routes straight to the read-back and confirms nothing.
            "missing": missing_fields(template, {}),
            "field_errors": {}, "awaiting": None, "awaiting_correction": False,
            "confirmed": False, "status": "collecting", "composition": None,
            "letter_text": None, "document": None, "verification": None,
            "warnings": [], "corrections": [], "error": None, "reply": reply,
            "revisions": [], "document_versions": [], "document_version": 0,
            "petition_reference": None, "pending_edit": None, "document_edited": False,
            "manually_edited": False, "_revision_base": None, "_revision_fields": {},
            "_version_source": None, "_version_summary": None,
            "turns": turns + [turn("assistant", reply)], "updated_at": now,
        }

    if intent == "emblem" and state.get("_emblem"):
        # Nothing about the WORDING changes, so the drafting call is not made
        # again: `letter_text` is kept and `compose` passes it through. Only
        # the document is rebuilt, which is the only place the emblem appears.
        placement = emblem.Placement.from_state(state["_emblem"])
        reply = emblem.describe(placement, language)
        return {
            **revisions.begin(state, "AI", "Emblem placement updated"),
            "status": "generating",
            "confirmed": True,
            "emblem": placement.as_dict(),
            "document": None, "verification": None, "error": None,
            "awaiting": None, "awaiting_correction": False,
            "reply": reply,
            "turns": turns + [turn("assistant", reply)],
            "updated_at": now,
        }

    if intent == "edit_text" and state.get("_edited_text"):
        # The citizen typed the petition themselves. Straight to generating:
        # there is nothing to confirm, because what they wrote IS the
        # confirmation. `letter_text` is deliberately NOT cleared here — it is
        # replaced wholesale by `compose`, which passes the edit through
        # untouched.
        # Used verbatim either way; only the name in the history differs.
        label = state.get("_edit_label") or {}
        return {
            **revisions.begin(state, label.get("source") or "Manual",
                              label.get("summary") or "Manual edit"),
            "status": "generating",
            "confirmed": True,
            "manually_edited": True,
            "document_edited": True, "pending_edit": None,
            "document": None, "verification": None, "warnings": [], "error": None,
            "awaiting": None, "awaiting_correction": False,
            "updated_at": now,
            "turns": turns,
        }

    if intent == "edit_question":
        target = (state.get("_document_edit") or {}).get("question", "instruction")
        reply = revisions.question(target, language)
        return {"status": "ready", "pending_edit": {"target": target, "question": reply},
                "reply": reply, "updated_at": now,
                "turns": turns + [turn("assistant", reply)]}

    if intent == "revise" and state.get("_revision"):
        # Straight back to generating. The facts were confirmed before the
        # first draft and none of them is being changed, so asking the citizen
        # to confirm an identical read-back would be ceremony rather than a
        # check. What they asked for is recorded on the session.
        note = str(state["_revision"]).strip()
        plan = state.get("_document_edit") or revisions.interpret(note, state.get("pending_edit")) or {}
        try:
            if plan.get("question"):
                raise ValueError(plan["question"])
            edited, summary, _ = revisions.apply(
                state.get("letter_text") or "", plan, language=language,
                fields=state.get("fields") or {}, composition=state.get("composition"),
            )
        except ValueError as exc:
            target = str(exc)
            reply = revisions.question(target, language)
            return {"status": "ready", "pending_edit": {"target": target, "question": reply},
                    "reply": reply, "updated_at": now,
                    "turns": turns + [turn("assistant", reply)]}
        if edited == state.get("letter_text"):
            reply = "மனுவில் இந்த மாற்றம் ஏற்கனவே உள்ளது." if language == "ta" else "The petition already contains this change."
            return {"status": "ready", "reply": reply, "pending_edit": None,
                    "turns": turns + [turn("assistant", reply)], "updated_at": now}
        reply = phrasing.phrase("revising", language)
        return {
            **revisions.begin(state, "AI", summary),
            "_edited_text": edited, "document_edited": True, "pending_edit": None,
            "status": "generating",
            "confirmed": True,
            "revisions": [*(state.get("revisions") or []), note],
            "composition": state.get("composition"), "letter_text": None, "document": None,
            "verification": None, "warnings": [], "error": None,
            "awaiting": None, "awaiting_correction": False,
            "reply": reply,
            "turns": turns + [turn("assistant", reply)],
            "updated_at": now,
        }

    # Retrying a spoken confirmation after reconnecting does not regenerate
    # the document or send the same grievance to a model a second time.
    if state.get("status") == "ready" and intent in ("confirm", "unclear", "question") \
            and not state.get("_extracted") and not state.get("_corrections") \
            and not state.get("_correction_target"):
        return {"status": "ready", "updated_at": now, "turns": turns}

    fields = dict(state.get("fields") or {})
    sources = dict(state.get("field_sources") or {})
    attempts = dict(state.get("attempts") or {})
    corrections_log = list(state.get("corrections") or [])
    awaiting = state.get("awaiting")
    awaiting_correction = bool(state.get("awaiting_correction"))
    understood_by = state.get("understood_by", "model")

    # ---- the citizen named a field to change ----------------------------- #
    #
    # Only that field is cleared. Everything else stands, so rejecting the
    # read-back never costs the citizen the rest of the interview. The field
    # then shows as missing, `ask` asks it, the answer is validated the same way
    # as the first time, and the read-back comes round again.
    target = state.get("_correction_target")
    if target and template.field(target):
        previous = fields.pop(target, None)
        sources.pop(target, None)
        attempts.pop(target, None)
        if previous is not None:
            # Opened now and completed when the replacement arrives, so the
            # trail reads "45 -> 31" rather than "45 -> None". An entry left
            # open means the citizen asked to change a value and never gave a
            # new one, which is itself worth seeing.
            corrections_log.append({"field": target, "from": previous, "to": None,
                                    "at": now, "source": "citizen-request"})
        return {
            **(revisions.begin(state, "AI", "Citizen details corrected")
               if state.get("letter_text") else {}),
            "fields": fields, "field_sources": sources, "attempts": attempts,
            "corrections": corrections_log,
            "missing": missing_fields(template, fields),
            "field_errors": {}, "awaiting": target, "awaiting_correction": False,
            "confirmed": False, "status": "collecting",
            "composition": None, "letter_text": None, "document": None,
            "verification": None, "warnings": [], "error": None,
            "updated_at": now, "turns": turns,
        }

    # ---- new values and corrections -------------------------------------- #
    raw_new = dict(state.get("_extracted") or {})
    raw_corrections = dict(state.get("_corrections") or {})
    accepted, rejected = validate_extracted(template, {**raw_new, **raw_corrections})

    for name, value in accepted.items():
        previous = fields.get(name)
        is_correction = name in raw_corrections or (previous is not None and previous != value)

        # Close an entry opened when the citizen asked to change this field.
        open_entry = next(
            (e for e in reversed(corrections_log) if e["field"] == name and e["to"] is None),
            None,
        )
        if open_entry is not None:
            open_entry["to"] = value
            open_entry["at"] = now
        elif is_correction and previous is not None:
            # "Actually my age is 31" overwrites in one turn, with no clear step
            # before it. An officer reading the file is entitled to see that a
            # value moved, either way it happened.
            corrections_log.append({"field": name, "from": previous, "to": value,
                                    "at": now, "source": understood_by})
        fields[name] = value
        sources[name] = "correction" if is_correction else understood_by
        attempts.pop(name, None)

    # An invalid attempted correction remains unresolved when an unrelated
    # detail is edited. Otherwise confirmation could print the older value
    # after the citizen has already said it is wrong.
    field_errors: dict[str, dict[str, Any]] = dict(state.get("field_errors") or {})
    for name in accepted:
        field_errors.pop(name, None)
    for name, result in rejected.items():
        spec = template.field(name)
        attempts[name] = attempts.get(name, 0) + 1
        field_errors[name] = {
            "code": result.code,
            "message": phrasing.error_text(result.code or "", language, result.detail),
            "attempts": attempts[name],
            "label": spec.label_for(language) if spec else name,
        }

    # An utterance that produced nothing usable, while a question was pending,
    # counts as a failed attempt at THAT field. Without this, a citizen whose
    # accent defeats the recogniser is asked the identical sentence for ever and
    # the rephrase never triggers.
    if not accepted and not rejected and awaiting and state.get("utterance") \
            and intent in ("provide", "unclear"):
        spec = template.field(awaiting)
        attempts[awaiting] = attempts.get(awaiting, 0) + 1
        field_errors[awaiting] = {
            "code": "not_understood",
            "message": phrasing.phrase("not_understood", language),
            "attempts": attempts[awaiting],
            "label": spec.label_for(language) if spec else awaiting,
        }

    # ---- the attachment offer -------------------------------------------- #
    #
    # "Continue" is the only thing that advances past it. "Add" leaves the
    # session exactly where it is, waiting for a file to arrive through the
    # upload endpoint, because a citizen who says "yes, I have the receipt" has
    # not yet given us the receipt.
    if intent == "skip_attach":
        return {
            "attachments_done": True,
            "status": "collecting",
            "updated_at": now,
            "turns": turns,
        }
    if intent == "attach":
        return {
            "attachments_done": False,
            "status": "attachments",
            "reply": phrasing.phrase("attach_waiting", language),
            "updated_at": now,
            "turns": turns + [turn("assistant",
                                   phrasing.phrase("attach_waiting", language))],
        }

    # The knowledge layer, started the moment the grievance is on the record and
    # then left alone. Started, not awaited: a voice turn is latency-critical
    # and this is advisory, so it runs beside the conversation and its result is
    # collected at composition time — by which point it is almost always done.
    if "grievance" in accepted:
        _start_knowledge(fields)

    still_missing = missing_fields(template, fields)

    # ---- confirmation ---------------------------------------------------- #
    confirmed = bool(state.get("confirmed"))
    status = state.get("status", "collecting")
    changed = bool(accepted or rejected)

    if changed:
        confirmed, status, awaiting_correction = False, "collecting", False

    if intent == "confirm" and not still_missing and not field_errors \
            and not awaiting_correction and not changed:
        confirmed, status, awaiting_correction = True, "generating", False
    elif intent == "reject":
        # The citizen says the read-back is wrong but has not said which detail.
        # `ask` now asks that, rather than reading the identical list back.
        confirmed, status, awaiting_correction = False, "collecting", True
    elif still_missing or field_errors:
        confirmed, status, awaiting_correction = False, "collecting", False

    return {
        "fields": fields,
        "field_sources": sources,
        "attempts": attempts,
        "corrections": corrections_log,
        "missing": still_missing,
        "field_errors": field_errors,
        "confirmed": confirmed,
        "status": status,
        "awaiting_correction": awaiting_correction,
        "updated_at": now,
        "turns": turns,
        # A corrected GRIEVANCE re-opens the attachment question: what is worth
        # enclosing depends on what the complaint is about. A corrected phone
        # number does not, and re-asking there would be noise.
        **({"attachments_done": False, "attachments_offered": False}
           if "grievance" in accepted else {}),
        **({"composition": None, "letter_text": None, "document": None,
            "verification": None, "warnings": [], "error": None}
           if changed or intent == "reject" else {}),
        **(revisions.begin(state, "AI", "Citizen details corrected")
           if (changed or intent == "reject") and state.get("letter_text") else {}),
        **({"error": None} if status == "generating" else {}),
    }


# Strong references to the background analyses in flight. Without this the
# event loop holds only a weak reference to a bare task and may collect it
# mid-run; the set is tiny and each entry removes itself when it finishes.
_knowledge_tasks: set = set()


def _start_knowledge(fields: dict[str, Any]) -> None:
    """Kick off the knowledge analysis for this grievance, once, off to the side.

    Every failure mode here ends the same way: nothing happens and the petition
    is produced exactly as it would have been. That is the capability contract
    in `extensions/registry.py`, and this is the one place it could be broken
    by accident — so nothing in this function is allowed to raise.
    """
    grievance = str(fields.get("grievance") or "")
    if len(grievance.split()) < 4:
        return
    try:
        from ..knowledge.capability import service

        knowledge = service()
        if not knowledge.enabled:
            return
        task = asyncio.ensure_future(
            knowledge.analyse(grievance, subject=str(fields.get("subject") or "")))
        _knowledge_tasks.add(task)
        task.add_done_callback(_knowledge_tasks.discard)
    except Exception as exc:  # noqa: BLE001
        log.info("knowledge.not_started", extra={"reason": str(exc)[:160]})


# --------------------------------------------------------------------------- #
# 3. ask — a written sentence, chosen in code
# --------------------------------------------------------------------------- #


async def ask(state: LetterState) -> dict[str, Any]:
    """Say the next thing. Almost always a sentence that was written in advance.

    A model is consulted in exactly two situations, both genuinely
    conversational rather than clerical:

      * the citizen asked a QUESTION, which by definition has no pre-written
        answer; and
      * the same field has now failed THREE times, where saying the identical
        sentence a fourth time is not a strategy.

    Everything else — the first ask, the second ask, every validation error, the
    request to name which detail is wrong — comes from `phrasing.py` at no
    latency cost and no network round trip.
    """
    language = state.get("language", "en")
    template = the_template()
    now = _now()

    # The citizen rejected the read-back without naming a field.
    if state.get("awaiting_correction"):
        labels = ", ".join(spec.label_for(language) for spec in template.fields)
        text = phrasing.phrase("which_field", language).format(fields=labels)
        return {"reply": text, "awaiting": None, "awaiting_correction": True,
                "status": "collecting", "turns": [turn("assistant", text)], "updated_at": now}

    errors = state.get("field_errors") or {}
    target = next((name for name in template.field_names if name in errors), None)
    if target is None:
        spec = next_field(template, state.get("fields") or {})
        target = spec.name if spec else None
    else:
        spec = template.field(target)

    if target is None:
        # Nothing outstanding and no correction pending. The router only sends
        # us here when something needs saying, so this is a safety net.
        text = phrasing.phrase("confirm_unclear", language)
        return {"reply": text, "awaiting": None, "status": "collecting",
                "turns": [turn("assistant", text)], "updated_at": now}

    error = errors.get(target)
    attempts = (state.get("attempts") or {}).get(target, 0)
    question = spec.prompt_for(language)
    text = error["message"] if error else question
    used_model = False

    if state.get("intent") == "question" and state.get("question"):
        answer = await _answer_question(state, template, language)
        if answer:
            text = f"{answer}\n\n{question}"
            used_model = True
        else:
            text = f"{phrasing.phrase('not_understood', language)} {question}"
    elif attempts >= 3:
        fresh = await _rephrase(spec, language, error)
        if fresh:
            text = fresh
            used_model = True

    return {
        "reply": text,
        "awaiting": target,
        "awaiting_correction": False,
        "status": "collecting",
        "turns": [turn("assistant", text, field=target, model_assisted=used_model or None)],
        "updated_at": now,
    }


async def _rephrase(spec, language: str, error: dict | None) -> str | None:
    """A different way of asking for the same thing, after three failures.

    Nothing citizen-supplied goes into this prompt — only the field's own
    description and the machine code for why the last answer was rejected.
    """
    settings = get_settings()

    async def call() -> str | None:
        payload = await chat_json(
            system=(
                "A citizen has failed three times to give a usable answer to one question "
                "on a government form. Rewrite the question in simpler, more concrete words "
                "in the requested language. Give one short example of an acceptable answer. "
                "Do not ask for anything other than the field named. Do not add requirements."
            ),
            user=(
                f"Language: {'Tamil' if language == 'ta' else 'English'}\n"
                f"Field: {spec.label_for('en')} (type: {spec.type})\n"
                f"Question as currently worded: {spec.prompt_for(language)}\n"
                f"Why the last answer was rejected: {(error or {}).get('code') or 'not understood'}"
            ),
            schema={"type": "object",
                    "properties": {"question": {"type": "string", "maxLength": 300}},
                    "required": ["question"]},
            max_tokens=300,
            timeout_ms=settings.understand_timeout_ms,
            budget_ms=settings.understand_budget_ms,
            mask=False,  # nothing citizen-supplied is in this payload
        )
        return str(payload.get("question") or "").strip() or None

    return await enhance(call, None)


async def _answer_question(state: LetterState, template: LetterTemplate, language: str) -> str | None:
    """Answer a citizen's question about the form, and nothing else.

    Tightly fenced on purpose. A free model was measured confidently directing a
    state government pensioner to EPFO; a model answering "what documents do I
    need" from its own memory will do the same here. It is given the form's own
    text and told to say it does not know otherwise.
    """
    settings = get_settings()
    enclosures = "\n".join(f"- {e}" for e in template.enclosures_for(language)) or "(none listed)"

    async def call() -> str | None:
        payload = await chat_json(
            system=(
                "You answer a citizen's question about the government form they are filling in. "
                "Answer ONLY from the form description given to you. If the answer is not in it, "
                "say plainly that you do not know and that they should ask the issuing office. "
                "Never state eligibility, legal position, fees, or processing times. "
                "Two sentences at most. Answer in the requested language."
            ),
            user=(
                f"Language: {'Tamil' if language == 'ta' else 'English'}\n"
                f"Form: {template.label_for(language)}\n"
                f"Office: {template.text_for('addressee', language)}, "
                f"{template.text_for('department', language)}\n"
                f"Documents listed on this form:\n{enclosures}\n"
                f"Details this form collects: "
                f"{', '.join(f.label_for(language) for f in template.fields)}\n\n"
                f"Question: {state.get('question')}"
            ),
            schema={"type": "object",
                    "properties": {"answer": {"type": "string", "maxLength": 500}},
                    "required": ["answer"]},
            max_tokens=400,
            timeout_ms=settings.understand_timeout_ms,
            budget_ms=settings.understand_budget_ms,
        )
        return str(payload.get("answer") or "").strip() or None

    return await enhance(call, None)


# --------------------------------------------------------------------------- #
# 3b. attach - "is anything enclosed?", asked once
# --------------------------------------------------------------------------- #


async def attach(state: LetterState) -> dict[str, Any]:
    """Ask whether the citizen wants to enclose anything, once.

    This sits between the last detail and the read-back for a reason that is
    about the office rather than the software: a citizen who is back a second
    time is usually holding the acknowledgement slip from the first, and that
    slip carries the reference number that lets a receiving officer find the
    earlier file. Nobody had ever asked them for it.

    The question is asked ONCE. `attachments_offered` is what stops it being
    re-asked every turn - the same discipline that stops the knowledge layer
    re-running on every message.

    No model is involved, here or in reading the answer. "Would you like to
    attach anything" has two outcomes and a table of words decides between
    them; an answer that decides neither leaves the question standing rather
    than guessing, because guessing "no" throws away the slip in their hand.
    """
    language = state.get("language", "en")

    # A file may already have arrived through the upload endpoint, in which case
    # the citizen has answered by acting and the question is moot.
    already = bool(state.get("attachments"))
    reply = (attachments.MORE_OR_CONTINUE if already else attachments.OFFER)[language]

    return {
        "status": "attachments",
        "attachments_offered": True,
        "reply": reply,
        "awaiting": None,
        "updated_at": _now(),
        "turns": [turn("assistant", reply)],
    }


# --------------------------------------------------------------------------- #
# 4. confirm — read back what will be printed
# --------------------------------------------------------------------------- #


async def confirm(state: LetterState) -> dict[str, Any]:
    """Read the record back before anything is generated.

    Entirely deterministic, and it reads back the DISPLAY form of each value —
    Aadhaar grouped in fours, the date as dd-mm-yyyy — because that is what the
    citizen will see on the finished document. Confirming a value in one format
    and printing it in another is not a confirmation.
    """
    language = state.get("language", "en")
    template = the_template()
    fields = state.get("fields") or {}

    lines = [phrasing.phrase("confirm_intro", language), ""]
    for spec in template.fields:
        if spec.name in fields:
            lines.append(
                f"{spec.label_for(language)}: {display_value(spec.type, fields[spec.name], language)}"
            )
    lines += ["", phrasing.phrase("confirm_ask", language)]
    text = "\n".join(lines)

    return {
        "reply": text,
        "status": "confirming",
        "awaiting": None,
        "awaiting_correction": False,
        "turns": [turn("assistant", text, kind="confirmation")],
        "updated_at": _now(),
    }


# --------------------------------------------------------------------------- #
# 5. compose — the only place a model writes prose
# --------------------------------------------------------------------------- #


async def compose(state: LetterState) -> dict[str, Any]:
    """Assemble the petition. ONE model call, for the formal wording only.

    The model writes four things: a subject line tailored to this grievance, an
    opening paragraph, the representation, and the closing request. The
    particulars — name, age, address, identifiers — are placed by
    `build_letter_text`, deterministically, and the model never writes one.

    The representation is where the complaint is STATED. It is the only place
    the document describes the matter, so if the model does not say it, the
    petition does not contain it. It is told to state the complaint faithfully
    and to add nothing: no number, date, office, official, statute or scheme it
    was not given, and no widening or narrowing of what was said. Identifier
    fields are excluded from the prompt at source and masked again at the
    provider boundary, so an Aadhaar number is not in what the model sees even
    if the citizen typed one inside their complaint.

    When no model is reachable the standard wording is used and the petition is
    produced anyway. A slightly flat letter is a working letter.
    """
    # A layout change re-renders; it does not re-draft. The words are already
    # settled, and sending them to a model again would cost a round trip and
    # risk coming back different for a request that was only about where the
    # emblem sits.
    if state.get("intent") == "emblem" and state.get("letter_text"):
        return {"status": "generating", "updated_at": _now()}

    # The citizen edited the petition by hand. It is used EXACTLY as typed: no
    # model call, no re-composition, no tidying. A manual editor that improves
    # what it was given is not a manual editor, and a citizen who fixed one
    # word and got a differently-worded document back would rightly stop
    # trusting the thing.
    edited = str(state.get("_edited_text") or "")
    if edited.strip():
        log.info("compose.manual_edit", extra={"chars": len(edited)})
        return {
            "letter_text": edited,
            "manually_edited": bool(state.get("manually_edited")) or state.get("intent") == "edit_text",
            "status": "generating",
            "error": None,
            "updated_at": _now(),
        }

    language = state.get("language", "en")
    template = the_template()
    fields = state.get("fields") or {}
    settings = get_settings()

    # A factual correction updates the last saved text in place. Rebuilding
    # from the template here would discard earlier manual and chat edits.
    if state.get("_revision_base") and state.get("document_versions"):
        current = str(state["_revision_base"])
        previous = state.get("_revision_fields") or {}
        for spec in template.fields:
            if spec.name not in fields or fields.get(spec.name) == previous.get(spec.name):
                continue
            old = display_value(spec.type, previous.get(spec.name), language)
            new = display_value(spec.type, fields[spec.name], language)
            expression = r"(?<!\w)" + r"\s+".join(re.escape(p) for p in old.split()) + r"(?!\w)"
            if old and re.search(expression, current):
                # `new` bound as a default: the lambda is called inside this
                # iteration today, but a closure over a loop variable is one
                # refactor away from replacing every field with the last
                # one. The lambda itself is there so a backslash in a
                # citizen's value is not read as a regex escape.
                current = re.sub(expression, lambda _, value=new: value, current)
            else:
                line = f"    {spec.label_for(language)}: {new}"
                heading = re.search(r"(?m)^(?:To|பெறுநர்)\s*,?\s*$", current)
                if heading:
                    current = current[:heading.start()] + line + "\n\n" + current[heading.start():]
                else:
                    current += "\n" + line
        return {"letter_text": current, "status": "generating", "error": None,
                "updated_at": _now()}

    particulars = "\n".join(
        f"- {spec.label_for('en')}: {display_value(spec.type, fields[spec.name], 'en')}"
        for spec in template.fields
        if spec.name in fields
        and spec.name not in VERBATIM_FIELDS
        and not is_sensitive(spec.type)
    )
    grievance = "\n".join(
        str(fields.get(name) or "").strip() for name in VERBATIM_FIELDS if fields.get(name)
    )

    # What the citizen asked for after reading the draft, in their own words.
    #
    # They are the person who has just read the petition, so this is worth
    # honouring — but it is an instruction about WORDING and is bounded by
    # every rule the first draft was bounded by. It cannot introduce a fact, a
    # number or a date (the grounding check drops any field that does), it
    # cannot reach the grievance, which is placed verbatim by code, and it
    # cannot reach the identifiers, which are excluded from this prompt at
    # source. The worst it can do is produce wording that gets rejected and
    # falls back to the standard text.
    revisions = [r for r in (state.get("revisions") or []) if str(r).strip()]
    revision_brief = ""
    if revisions:
        asked = "\n".join(f"- {str(r).strip()[:400]}" for r in revisions[-4:])
        revision_brief = (
            "\n\nThe citizen has read this petition and asked for these changes to "
            "how it is WRITTEN. Apply them, in order, to the four fields you are "
            "producing. They may change emphasis, tone, length or what the subject "
            "line names. They may NOT add a fact, a number, a date or a document "
            "that you were not given, and they may NOT alter the complaint, which "
            "is reproduced separately in the citizen's own words. If a request "
            "cannot be honoured within those limits, write the field as you "
            "otherwise would:\n" + asked
        )

    async def call() -> Composition | None:
        payload = await chat_json(
            system=(
                "You are drafting the formal wording of a petition to an Indian government "
                "office, on behalf of the citizen whose complaint you are shown. Write in "
                "the register used in official correspondence to a District Collector: "
                "courteous, plain, and specific to THIS complaint. A petition that could "
                "have been written about any complaint is of no use to the citizen or to "
                "the officer who has to act on it.\n\n"
                "Produce exactly four things.\n\n"
                "1. `subject` - one line, under 120 characters, naming what the petition "
                "is about. Concrete and particular, not a generic heading. It is printed "
                "after the word 'Subject:' and, in Tamil, is followed by the word "
                "'தொடர்பாக.' - so write a noun phrase that reads naturally before that "
                "word, and do NOT add the word yourself. Put no names, numbers or "
                "addresses in it.\n\n"
                "2. `introduction` - 3 to 5 sentences in the first person, opening the "
                "letter. Greet the officer, say that you reside at the address given "
                "above, and introduce the specific matter you are writing about. Name the "
                "kind of problem and where it is, so that a clerk sorting post knows which "
                "department this belongs to. The paragraph that follows states the "
                "matter in full, so open it; do not finish it here.\n\n"
                "3. `background` - 5 to 8 sentences in the first person: the "
                "representation. This is the body of the petition and the ONLY place the "
                "matter is stated, so it carries the whole account. Set out, in ordinary "
                "official language:\n"
                "   - WHAT THE PROBLEM IS. State it plainly and completely, in the "
                "petitioner's meaning but in the language of a formal petition. The "
                "citizen described it in their own way - possibly briefly, possibly in "
                "another language, possibly in the grammar of speech rather than "
                "writing. Say the same thing properly: not more than it, not less;\n"
                "   - what the continuing effect of it is on the petitioner and on "
                "others in the locality, reasoning ONLY from what the complaint actually "
                "says;\n"
                "   - why it needs the officer's attention rather than being left where "
                "it is;\n"
                "   - what would put it right, in practical terms.\n"
                "   If the complaint says a street light has not worked for months, you "
                "state that the street light at the petitioner's locality has remained "
                "non-functional for several months, and you may then write about "
                "darkness, risk to people walking at night, and the need for the line to "
                "be inspected and repaired - because all of that follows from what was "
                "said. You may NOT write that anyone was injured, that a number of "
                "families are affected, or that any official promised anything, because "
                "none of that was said.\n\n"
                "4. `request` - 3 to 4 sentences in the first person: the closing prayer, "
                "which follows the representation. Ask the officer to arrange an "
                "inspection, to direct the department concerned to take the specific "
                "action this complaint calls for, and to inform the petitioner of the "
                "action taken. Keep it courteous and definite. Do NOT end it with a "
                "greeting or with thanks: the letter closes with its own thanks and "
                "sign-off immediately below your paragraph, and a second one reads as "
                "though the letter ended twice.\n\n"
                "HARD RULES.\n"
                "The complaint is NOT printed anywhere else in the document. If you do "
                "not state it, the petition does not contain it, and the officer reading "
                "the letter will not learn what is being complained about.\n"
                "State it FAITHFULLY. You may correct grammar, order the facts, and put "
                "them into official language. You may NOT soften it, strengthen it, "
                "widen it, narrow it, or add a grievance that was not raised. A petition "
                "in which the complaint has become a different complaint is a different "
                "petition, and the citizen signs it believing it is their own.\n"
                "You must NOT introduce any NUMBER that is not already in the material "
                "you were given - no dates, durations, counts, amounts, section numbers "
                "or file numbers. Write about duration in words only if the complaint "
                "itself gave one.\n"
                "You must NOT invent a fact, an office, an official, a statute, a scheme "
                "or a document that you were not given.\n"
                "You must NOT state eligibility, entitlement, legal position, fees, or a "
                "timescale that any office has promised.\n"
                "Write all four fields in the requested language and in no other."
            ),
            user=(
                f"Language for all four fields: "
                f"{'Tamil' if language == 'ta' else 'English'}\n"
                f"Petition type: {template.label_for('en')}\n"
                f"Addressed to: {template.text_for('addressee', 'en')}, "
                f"{template.text_for('department', 'en')}\n"
                f"Standard subject for this form: {template.text_for('subject', 'en')}\n"
                f"Purpose of this form: {template.narrative_brief}\n\n"
                f"Petitioner's particulars, for context only - do not repeat these:\n"
                f"{particulars}\n\n"
                f"The complaint, in the citizen's own words. This is the ONLY "
                f"description of the matter the document will carry: state it in the "
                f"representation, faithfully and in full, in official language. Add "
                f"nothing to it:\n{grievance[:3000]}"
                + revision_brief
            ),
            schema={
                "type": "object",
                "properties": {
                    "subject": {"type": "string", "maxLength": 200},
                    "introduction": {"type": "string", "maxLength": 1400},
                    "background": {"type": "string", "maxLength": 2200},
                    "request": {"type": "string", "maxLength": 1200},
                },
                "required": ["subject", "introduction", "background", "request"],
            },
            max_tokens=2400,
            timeout_ms=settings.compose_timeout_ms,
            budget_ms=settings.compose_budget_ms,
        )
        return _read_composition(payload, language, grounding=f"{grievance} {particulars}")

    with timed(log, "node.compose", language=language) as carry:
        composition = await enhance(call, None)
        carry["wording"] = "model" if composition else "standard"

    analysis = await _collect_knowledge(fields)

    enclosed = attachments.AttachmentSet.from_state(state.get("attachments"))
    letter_text = build_letter_text(
        template=template,
        fields=fields,
        language=language,
        composition=composition,
        session_id=state.get("session_id", ""),
        attachments=enclosed,
        prior_reference=_prior_reference(enclosed, language),
    )

    return {
        "composition": (
            {
                "subject": composition.subject,
                "introduction": composition.introduction,
                "background": composition.background,
                "request": composition.request,
            }
            if composition
            else None
        ),
        "letter_text": letter_text,
        # For the officer's panel only. It is NOT passed to `build_letter_text`
        # and no part of it appears in the petition: the document a citizen
        # signs says what the citizen said, and a retrieval result — however
        # well cited — is not something they said.
        **({"analysis": analysis} if analysis is not None else {}),
        "status": "generating",
        # This attempt supersedes whatever the last one failed at. Without
        # this, a retry after an interrupted generation reached `ready` still
        # carrying "Document preparation was interrupted", and the page put a
        # failure banner over a petition that had just been produced.
        "error": None,
        "updated_at": _now(),
    }




def _enclosure_files(state: LetterState, language: str) -> list:
    """The citizen's attachments, as files on disk, in the order they appear on
    the enclosure list.

    A missing file is skipped rather than failing the render: the petition is
    the deliverable, and an enclosure that cannot be found is still correctly
    listed — the citizen is carrying it.
    """
    from ..services import attachment_store
    from ..services.enclosures import Enclosure

    enclosed = attachments.AttachmentSet.from_state(state.get("attachments"))
    session_id = str(state.get("session_id") or "")
    out = []
    for index, attachment in enumerate(enclosed.items, start=1):
        try:
            path = attachment_store.path_of(session_id, attachment)
        except Exception as exc:  # noqa: BLE001
            log.info("enclosure.unreadable", extra={"error": str(exc)[:120]})
            continue
        if path is None:
            log.info("enclosure.missing_file",
                     extra={"attachment_id": attachment.attachment_id})
            continue
        out.append(Enclosure(label=f"{index}. {attachment.label(language)}",
                             path=path, filename=attachment.filename))
    return out


def _prior_reference(enclosed: Any, language: str) -> str:
    """The sentence about an earlier petition, if one is actually evidenced.

    Three conditions, all required, and every one of them is the citizen's
    decision rather than the software's:

      1. a document was attached,
      2. something was read out of it,
      3. the citizen looked at what was read and confirmed it.

    Fail any one and the petition says nothing about an earlier submission. A
    petition that claims a prior reference number which does not resolve is
    worse than one that claims nothing: it sends a receiving officer to look
    for a file that was never opened.
    """
    for attachment in getattr(enclosed, "items", []):
        if attachment.kind not in ("previous_petition", "acknowledgement", "response"):
            continue
        if not attachment.confirmed or not attachment.extracted:
            continue
        prior = prior_petition.PriorPetition.from_dict(attachment.extracted)
        if prior is None:
            continue
        sentence = prior_petition.reference_sentence(prior, language)
        if sentence:
            return sentence
    return ""


async def _collect_knowledge(fields: dict[str, Any]) -> dict[str, Any] | None:
    """Pick up the analysis started back in `validate`.

    Almost always already finished — it began several turns ago — so this is a
    cache read. When it is not finished, or was never started, or fails, this
    returns None and composition carries on: the analysis is advisory and the
    citizen is waiting on a document.
    """
    try:
        from ..knowledge.capability import service

        knowledge = service()
        if not knowledge.enabled:
            return None
        analysis = await knowledge.analyse(
            str(fields.get("grievance") or ""),
            subject=str(fields.get("subject") or ""))
        return analysis.model_dump() if analysis is not None else None
    except Exception as exc:  # noqa: BLE001
        log.info("knowledge.unavailable", extra={"reason": str(exc)[:160]})
        return None


_DIGITS = re.compile(r"\d+")


def _numbers_are_grounded(text: str, grounding: str) -> bool:
    """True when every number in `text` also appears in the source material.

    The single most dangerous thing a model can do on a government form is
    invent a figure: a date the citizen never gave, a duration, a count of
    affected families, a section number. Prose is checkable by a reader;
    "for the past 18 months" is not, because it looks exactly like something
    the citizen said.

    So the elaboration may reason freely in words and may not introduce a digit
    of its own. A field that does is dropped, and the letter falls back for that
    slot. Deliberately strict: a false rejection costs a flatter paragraph, and
    a false acceptance puts a fabricated figure on a petition.
    """
    allowed = set(_DIGITS.findall(grounding))
    return all(number in allowed for number in _DIGITS.findall(text))


def _read_composition(payload: dict, language: str, grounding: str = "") -> Composition | None:
    """Accept what the model returned, one field at a time.

    A field that is empty, over-long, in the wrong script, or carrying a number
    that was never given is dropped, and the standard wording fills that slot.
    Partial acceptance is deliberate: a model that wrote a good subject and a
    poor representation should not cost the letter its subject.
    """

    def take(key: str, limit: int) -> str | None:
        value = str(payload.get(key) or "").strip()
        if key == "subject":
            # Some models return "Sub: ..." or "பொருள்: ...". The letter adds the
            # label itself, so a prefix here prints it twice.
            value = re.sub(r"^\s*(sub(ject)?|பொருள்)\s*[:\-]\s*", "", value, flags=re.I).strip()
        if not value or len(value) > limit:
            return None
        # A Tamil petition with an English paragraph in it is worse than the
        # standard Tamil wording, and the reverse is equally true.
        if language == "ta" and not _TAMIL.search(value):
            return None
        if language == "en" and _TAMIL.search(value):
            return None
        if grounding and not _numbers_are_grounded(value, grounding):
            log.warning("compose.ungrounded_number", extra={"field": key})
            return None
        return value

    composition = Composition(
        subject=take("subject", 220),
        introduction=take("introduction", 1600),
        background=take("background", 2400),
        request=take("request", 1400),
    )
    return None if composition.empty else composition


# --------------------------------------------------------------------------- #
# 6. translate — reached only when the router says it is needed
# --------------------------------------------------------------------------- #


async def translate(state: LetterState) -> dict[str, Any]:
    """Bring the assembled petition into the citizen's language.

    A failure here does not fail the petition. The untranslated text is kept,
    the reason is attached as a warning, and the citizen gets a document rather
    than nothing at all.
    """
    language = state.get("language", "en")
    text = state.get("letter_text") or ""
    warnings = list(state.get("warnings") or [])

    with timed(log, "node.translate", language=language) as carry:
        try:
            result = await translate_lines(
                text.split("\n"), language,
                keep=verbatim_lines(state.get("fields") or {}),
            )
            carry["engine"] = result.engine
            carry["lines"] = result.translated_count
        except Exception as exc:  # noqa: BLE001
            log.warning("translate.failed", extra={"error": str(exc)[:200]})
            warnings.append(phrasing.phrase("translation_unavailable", language))
            return {"warnings": warnings, "updated_at": _now()}

    return {
        "letter_text": "\n".join(result.lines),
        "warnings": warnings + result.warnings,
        "updated_at": _now(),
    }


# --------------------------------------------------------------------------- #
# 7. render — DOCX always, PDF through the configured engine
# --------------------------------------------------------------------------- #


async def render(state: LetterState) -> dict[str, Any]:
    settings = get_settings()
    session_id = state.get("session_id") or str(uuid.uuid4())
    text = state.get("letter_text") or ""
    language = state.get("language", "en")
    template = the_template()
    warnings = list(state.get("warnings") or [])

    if not text.strip():
        return {"status": "failed", "error": "Nothing to render.",
                "reply": phrasing.phrase("render_failed", language), "updated_at": _now()}

    reference = state.get("petition_reference") or reference_number(session_id)
    version = int(state.get("document_version") or 0) + 1
    docx_path = settings.document_dir / f"{session_id}-{template.id}-v{version}.docx"

    with timed(log, "node.render") as carry:
        try:
            # Off the event loop. Writing the document is synchronous work,
            # and with attachments it also rasterises up to twelve pages per
            # file through PyMuPDF. Held on the loop, that freezes every other
            # session in the service — including the WebSocket carrying
            # somebody's voice, which drops rather than waits.
            await asyncio.to_thread(
                render_service.render_docx,
                text, docx_path, reference=reference,
                title=template.label_for("en"), settings=settings,
                placement=emblem.placement_for(state.get("emblem"), settings),
                enclosures=_enclosure_files(state, language),
                enclosure_heading=letter_label("enclosure_page", language),
                enclosure_note=letter_label("enclosure_note", language),
            )
        except Exception as exc:  # noqa: BLE001
            log.exception("render.docx.failed")
            return {"status": "failed", "error": f"DOCX rendering failed: {exc}"[:300],
                    "reply": phrasing.phrase("render_failed", language), "updated_at": _now()}

        pdf_path, pdf_error = await render_service.render_pdf(docx_path, settings)
        carry["pdf"] = bool(pdf_path)

    if pdf_error:
        # The DOCX is a complete, usable document. A missing PDF converter
        # degrades the result; it does not fail the petition.
        warnings.append(phrasing.phrase("pdf_unavailable", language))
        log.warning("render.pdf.unavailable", extra={"detail": pdf_error})

    return {
        "document": {
            "reference": reference,
            "version": version,
            "docx": str(docx_path),
            "pdf": str(pdf_path) if pdf_path else None,
            "generated_at": _now(),
        },
        "warnings": warnings,
        "updated_at": _now(),
    }


# --------------------------------------------------------------------------- #
# 8. verify — read the finished file back and check it
# --------------------------------------------------------------------------- #


def _normalise(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


async def verify(state: LetterState) -> dict[str, Any]:
    """Assert that every required value is actually present in the file produced.

    The last deterministic gate, and it reads the DOCX back off disk rather than
    trusting the string that was passed to the renderer. A template bug, a
    translation that dropped a line, and a renderer that silently skipped a
    paragraph all look identical from the inside, and are all caught here.

    A failed verification does NOT delete the document — it withholds it and
    keeps the reason, so an operator can look at the file that failed.
    """
    language = state.get("language", "en")
    document = state.get("document") or {}
    template = the_template()
    fields = state.get("fields") or {}

    if state.get("status") == "failed" or not document.get("docx"):
        return {"status": "failed", "updated_at": _now()}

    # A hand-edited petition is checked the same way but judged differently.
    #
    # Verification exists to catch the SYSTEM corrupting a document — a template
    # bug, a dropped paragraph, a translation that lost a line. A citizen
    # deleting their own middle name from their own petition is not that. So
    # the check still runs and still reports exactly what is missing, but it
    # warns instead of withholding the document: refusing to hand someone their
    # own edited letter is the wrong answer to "you changed something".
    hand_edited = bool(state.get("manually_edited"))

    docx_path = Path(document["docx"])
    # The complaint is a verification target only when it was PLACED, which is
    # when no account was written from it. Asking the document to contain a
    # string it is not meant to contain fails a letter that is correct.
    stored = state.get("composition") or {}
    targets = verification_targets(
        template, fields, language,
        Composition(**{key: stored.get(key) for key in
                       ("subject", "introduction", "background", "request")})
        if stored else None)

    try:
        produced = _normalise(render_service.extract_docx_text(docx_path))
    except Exception as exc:  # noqa: BLE001
        log.exception("verify.read.failed")
        return {"status": "failed",
                "error": f"The generated document could not be read back: {exc}"[:300],
                "reply": phrasing.phrase("verify_failed", language),
                "verification": {"ok": False, "reason": "unreadable"}, "updated_at": _now()}

    missing_values = [
        name for name, expected in targets.items()
        if expected and re.search(
            r"(?<!\w)" + re.escape(_normalise(expected)) + r"(?!\w)", produced
        ) is None
    ]
    size = docx_path.stat().st_size if docx_path.exists() else 0
    reference = str(document.get("reference") or "")
    reference_ok = bool(reference and reference in produced)
    # Intentional edits may differ from intake fields. They must still be
    # rendered faithfully: a missing user-added line is a system failure.
    content_ok = all(
        _normalise(line).rstrip(":") in produced
        for line in str(state.get("letter_text") or "").splitlines() if line.strip()
    )
    verification = {
        "ok": not missing_values and size > 0 and reference_ok and content_ok,
        "checked": len(targets),
        "missing_values": missing_values,
        "reference_ok": reference_ok,
        "content_ok": content_ok,
        "bytes": size,
        "at": _now(),
    }

    if (not verification["ok"] and (hand_edited or state.get("document_edited"))
            and size > 0 and reference_ok and content_ok):
        # The citizen changed it themselves. Say exactly what is no longer in
        # the document and hand it over anyway — it is their petition, and an
        # officer reading it can see from the record that the wording is theirs.
        log.warning("verify.hand_edited_missing",
                    extra={"missing": missing_values, "reference_ok": reference_ok})
        verification["hand_edited"] = hand_edited
        verification["user_edited"] = True
        labels = [template.field(name).label_for(language)
                  if template.field(name) else name for name in missing_values]
        warnings = list(state.get("warnings") or [])
        warnings.append(phrasing.phrase("edited_missing", language).format(
            fields=", ".join(labels) or "—"))
        return {**revisions.committed(state, verification, _now()),
                "status": "ready", "verification": verification,
                "warnings": warnings, "error": None,
                "reply": phrasing.phrase("edited_saved", language),
                "updated_at": _now()}

    if not verification["ok"]:
        # Field NAMES only. The values that failed to appear are the citizen's
        # identifiers, and a log is not the place for them.
        log.error("verify.failed", extra={"missing": missing_values, "bytes": size,
                                          "reference_ok": reference_ok})
        return {"status": "failed", "verification": verification,
                "error": "Required values are missing from the generated document.",
                "reply": phrasing.phrase("verify_failed", language), "updated_at": _now()}

    # An emblem change says what happened to the emblem. "Your letter is
    # ready" is true but tells the citizen nothing about the thing they just
    # asked for, and leaves them opening the PDF to find out whether it worked.
    if state.get("intent") == "emblem":
        reply = emblem.describe(
            emblem.placement_for(state.get("emblem"), get_settings()), language)
    elif state.get("_edited_text"):
        reply = ("மனு புதுப்பிக்கப்பட்டு சரிபார்க்கப்பட்டது." if language == "ta" else
                 f"Petition updated. {state.get('_version_summary') or 'Changes saved'}. Verification passed.")
    else:
        reply = phrasing.phrase("generated", language)
    return {
        **revisions.committed(state, verification, _now()),
        "status": "ready",
        "verification": verification,
        "error": None,
        "reply": reply,
        "awaiting": None,
        "turns": [turn("assistant", reply, kind="document", reference=document.get("reference"))],
        "updated_at": _now(),
    }
