"""Small, explicit edits to the current petition, independent of drafting.

The current text is always the input. Unsupported or ambiguous instructions
become a question, never a silently regenerated template.
"""

from __future__ import annotations

import re
from typing import Any

_SUBJECT = re.compile(r"^(?:Subject|Sub|பொருள்)\s*:", re.I)
_RECIPIENT = re.compile(r"^(?:To|பெறுநர்)\s*[,：:]?\s*$", re.I)
_CLOSING = re.compile(r"^(?:Thank you|நன்றி|Yours faithfully|இப்படிக்கு)", re.I)
_ACK = re.compile(r"^(?:ok(?:ay)?|yes|no|thanks?|thank you|good|sure|சரி|ஆம்|நன்றி)[.! ]*$", re.I)


def question(target: str, language: str = "en") -> str:
    english = {
        "subject": "What should the new subject say?",
        "recipient": "Which recipient and office should this petition be addressed to?",
        "add": "What exact sentence would you like to add?",
        "remove": "Please paste the paragraph or sentence you want removed.",
        "replace": "Please say: replace \"current text\" with \"new text\".",
        "previous": "Please give the previous acknowledgement number or submission date and the sentence to include.",
        "attachments": "Use Add attachment to upload evidence. To change the enclosure wording, tell me the exact text.",
        "instruction": "Tell me the subject, recipient, or exact text to add, replace or remove. You can also ask for a shorter or more formal petition.",
    }
    tamil = {
        "subject": "புதிய பொருள் வரி என்னவாக இருக்க வேண்டும்?",
        "recipient": "மனுவை எந்த அதிகாரி மற்றும் அலுவலகத்திற்கு அனுப்ப வேண்டும்?",
        "add": "எந்த வாக்கியத்தைச் சேர்க்க வேண்டும்? அதை முழுமையாகச் சொல்லவும்.",
        "remove": "நீக்க வேண்டிய பத்தி அல்லது வாக்கியத்தை இங்கே உள்ளிடவும்.",
        "replace": "மாற்ற வேண்டிய தற்போதைய உரையையும் புதிய உரையையும் குறிப்பிடவும்.",
        "previous": "முந்தைய ஒப்புகை எண் அல்லது சமர்ப்பித்த தேதியையும் சேர்க்க வேண்டிய வாக்கியத்தையும் கூறவும்.",
        "attachments": "ஆதாரத்தைப் பதிவேற்ற இணைப்பு பொத்தானைப் பயன்படுத்தவும். இணைப்பு விவர உரையை மாற்ற புதிய உரையைக் கூறவும்.",
        "instruction": "பொருள், பெறுநர் அல்லது சேர்க்க, மாற்ற, நீக்க வேண்டிய உரையைக் கூறவும். மனுவைச் சுருக்கவும் கேட்கலாம்.",
    }
    return (tamil if language == "ta" else english).get(target, english["instruction"])


# --------------------------------------------------------------------------- #
# Tamil
#
# Written as STEMS, not whole words. `பொருள்` ends in a pulli, and the accusative a
# citizen actually says — `பொருளை` — REPLACES that pulli. So the dictionary
# form is not a substring of the spoken one, and every Tamil edit instruction
# fell through to "tell me what to change", by voice and by typing alike: a
# Tamil petition could not be edited at all once it existed.
#
# The stem is a prefix of every case ending, which is how Tamil works, and why
# `\b` is no help — a Tamil word boundary is not what `\w` thinks it is.
#
# The other half is word order. Tamil puts the value BEFORE the verb, marked by
# `என்று`: "change the subject to X" is "பொருளை X என்று மாற்று". The English
# patterns look for a connector after the keyword, which in Tamil is never
# there.
# --------------------------------------------------------------------------- #

_TA_SUBJECT = "பொருள"       # subject, without its pulli
_TA_RECIPIENT = "பெறுநர"    # recipient
_TA_AS = "என்று"            # "as" — closes the value
_TA_CHANGE = "மாற்ற"        # change
_TA_ADD = "சேர்"           # add
_TA_REMOVE = "நீக்"        # remove
_TA_OBJECT = r"(?:ஐ|அதை)?"   # the accusative particle, when written

# A bare "a line" / "a sentence" / "a paragraph" names no content. That is a
# question to put back to the citizen, not a value to insert.
_TA_EMPTY_VALUE = re.compile(r"^(?:ஒரு\s+)?(?:வரி|வாக்கிய|பத்தி)\S*\s*$")


def _tamil(text: str) -> dict[str, Any] | None:
    """A Tamil instruction, or None when this is not one."""
    value = r"(.+?)\s*" + _TA_AS + r"\S*\s*"

    match = re.search(_TA_SUBJECT + r"\S*\s+" + value + _TA_CHANGE, text)
    if match:
        return {"action": "subject", "value": match[1].strip().strip('"“”')}

    match = re.search(_TA_RECIPIENT + r"\S*\s+" + value + _TA_CHANGE, text)
    if match:
        return {"action": "recipient", "value": match[1].strip().strip('"“”')}

    match = re.search(value + _TA_ADD, text)
    if match and not _TA_EMPTY_VALUE.match(match[1].strip()):
        return {"action": "add", "value": match[1].strip().strip('"“”')}

    match = re.search(r"(.+?)\s*" + _TA_OBJECT + r"\s*" + _TA_REMOVE, text)
    if match and not _TA_EMPTY_VALUE.match(match[1].strip()):
        return {"action": "remove", "value": match[1].strip().strip('"“”')}

    # Named the thing but not the change: ask which, rather than guess at it.
    if re.search(_TA_SUBJECT, text):
        return {"question": "subject"}
    if re.search(_TA_RECIPIENT, text):
        return {"question": "recipient"}
    if re.search(_TA_ADD, text):
        return {"question": "add"}
    if re.search(_TA_REMOVE, text):
        return {"question": "remove"}
    return None


def interpret(instruction: str, pending: dict | None = None) -> dict[str, Any] | None:
    text = str(instruction or "").strip()
    if not text or _ACK.fullmatch(text):
        return None
    if pending and pending.get("target") in {"subject", "recipient", "add", "remove", "previous"}:
        # A fresh command supersedes a pending question; a plain reply fills it.
        if not re.match(r"^(?:change|set|add|remove|delete|replace|make|shorten|update)\b", text, re.I):
            target = pending["target"]
            return {"action": "add" if target == "previous" else target, "value": text}

    # Tamil first: its own grammar, and none of the English patterns
    # below can match it anyway.
    tamil = _tamil(text)
    if tamil is not None:
        return tamil

    match = re.search(r"\b(?:subject|பொருள்)\b\s*(?:line\s*)?(?:to|as|:|say|mention|be)\s+(.+)", text, re.I)
    if match:
        return {"action": "subject", "value": match[1].strip().strip('"“”')}
    if re.search(r"\bsubject\b|பொருள்", text, re.I):
        return {"question": "subject"}
    match = re.search(r"\b(?:recipient|addressee|receiving office)\b\s*(?:to|as|:|be)\s+(.+)", text, re.I)
    if match:
        return {"action": "recipient", "value": match[1].strip().strip('"“”')}
    if re.search(r"\b(?:recipient|addressee)\b|பெறுநர்", text, re.I):
        return {"question": "recipient"}
    match = re.match(r'(?:please\s+)?replace\s+["“](.+?)["”]\s+with\s+["“](.+?)["”][.!]?$', text, re.I | re.S)
    if match:
        return {"action": "replace", "value": match[2], "old": match[1]}
    if re.match(r"(?:please\s+)?replace\b", text, re.I):
        return {"question": "replace"}
    match = re.match(r"(?:please\s+)?(?:remove|delete)\s+(.+)", text, re.I | re.S)
    if match:
        value = re.sub(r"^(?:the\s+)?(?:paragraph|sentence|line)\s+(?:that\s+)?(?:says|saying|containing)\s+", "", match[1], flags=re.I)
        if re.fullmatch(r"(?:this|that|the|a|one)?\s*(?:paragraph|sentence|line)[.!]?", value, re.I):
            return {"question": "remove"}
        return {"action": "remove", "value": value.strip('"“”')}
    match = re.match(r"(?:please\s+)?(?:add|include|mention|append)\s+(.+)", text, re.I | re.S)
    if match:
        value = re.sub(r"^(?:that|a sentence saying|the sentence|a note that)\s+", "", match[1], flags=re.I)
        if re.fullmatch(r"(?:one\s+more|another|a|the)?\s*(?:sentence|paragraph|line)[.!]?", value, re.I):
            return {"question": "add"}
        if re.fullmatch(r"(?:the\s+)?previous\s+(?:acknowledg\w*|complaint|petition|submission)(?:\s+(?:number|date|reference))?[.!]?", value, re.I):
            return {"question": "previous"}
        return {"action": "add", "value": value.strip('"“”')}
    if re.search(r"\b(?:shorter|shorten|concise|brief)\b|சுருக்க", text, re.I):
        return {"action": "shorten"}
    if re.search(r"\b(?:formal|firmer|polite|professional)\b|முறையான", text, re.I):
        return {"action": "formal", "target": "grievance" if re.search(r"grievance|complaint|குறை", text, re.I) else "closing"}
    if re.search(r"\battach(?:ment)?s?\b|இணைப்பு", text, re.I):
        return {"question": "attachments"}
    return {"question": "instruction"}


def _body_end(lines: list[str]) -> int:
    return next((i for i, line in enumerate(lines) if _CLOSING.match(line.strip())), len(lines))


def apply(text: str, plan: dict[str, Any], *, language: str, fields: dict,
          composition: dict | None = None) -> tuple[str, str, dict[str, str]]:
    """Return new text, summary and intentional field wording overrides.

    ValueError means the requested target was not found unambiguously.
    """
    action, value = plan.get("action"), str(plan.get("value") or "").strip()
    lines = text.split("\n")
    overrides: dict[str, str] = {}
    if action == "subject":
        index = next((i for i, line in enumerate(lines) if _SUBJECT.match(line.strip())), None)
        if index is None or not value:
            raise ValueError("subject")
        prefix = lines[index].split(":", 1)[0]
        lines[index] = f"{prefix}: {value}"
        summary = "Subject updated"
    elif action == "recipient":
        start = next((i for i, line in enumerate(lines) if _RECIPIENT.match(line.strip())), None)
        if start is None or not value:
            raise ValueError("recipient")
        end = start + 1
        while end < len(lines) and lines[end].strip():
            end += 1
        lines[start + 1:end] = [f"    {part.strip()}" for part in value.splitlines() if part.strip()]
        summary = "Recipient updated"
    elif action == "add":
        if not value:
            raise ValueError("add")
        value = value[0].upper() + value[1:]
        if value[-1] not in ".!?。":
            value += "."
        end = _body_end(lines)
        lines[end:end] = [f"   {value}", ""]
        summary = "Requested sentence added"
    elif action in {"remove", "replace"}:
        old = str(plan.get("old") or value)
        if not old or text.count(old) != 1:
            raise ValueError("remove" if action == "remove" else "replace")
        text = text.replace(old, "" if action == "remove" else value, 1)
        return text, "Text removed" if action == "remove" else "Text replaced", overrides
    elif action == "formal":
        if plan.get("target") == "grievance":
            original = str(fields.get("grievance") or "")
            if not original or original not in text:
                raise ValueError("replace")
            if language == "ta":
                revised = "பின்வரும் குறையைத் தங்கள் கவனத்திற்கு மரியாதையுடன் சமர்ப்பிக்கிறேன்: " + original
            else:
                revised = "I respectfully bring the following matter to your attention: " + original
            # Preserve the account verbatim while improving its formal framing.
            text = text.replace(original, revised, 1)
            return text, "Grievance wording made more formal", overrides
        end = _body_end(lines)
        closing = ("எனது மனுவைப் பரிசீலித்து உரிய நடவடிக்கை எடுக்குமாறு பணிவுடன் கேட்டுக்கொள்கிறேன்."
                   if language == "ta" else
                   "I respectfully request that this petition be considered and appropriate action be taken to address the matter described above.")
        old = str((composition or {}).get("request") or "")
        if old and old in text:
            return text.replace(old, closing, 1), "Closing request revised", overrides
        lines[end:end] = [f"   {closing}", ""]
        summary = "Closing request revised"
    elif action == "shorten":
        # Remove standard generated elaboration, preserving citizen text and
        # every manual addition. Never choose an arbitrary factual paragraph.
        removable = [str((composition or {}).get(key) or "") for key in ("background", "introduction")]
        from .letter import fallback_composition
        from .templates import the_template

        fallback = fallback_composition(the_template(), fields, language)
        removable.append(fallback.introduction or "")
        revised = text
        for paragraph in removable:
            if paragraph and paragraph in revised:
                revised = revised.replace(paragraph, "", 1)
        revised = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", revised)
        if revised == text:
            raise ValueError("remove")
        return revised, "Petition shortened; citizen details and additions preserved", overrides
    else:
        raise ValueError("instruction")
    return "\n".join(lines), summary, overrides


def history(state: dict) -> list[dict]:
    versions = list(state.get("document_versions") or [])
    if not versions and state.get("letter_text") and (state.get("document") or {}).get("docx"):
        document = dict(state["document"])
        versions.append({
            "version": int(document.get("version") or 1),
            "updated_at": document.get("generated_at") or state.get("updated_at"),
            "source": "Manual" if state.get("manually_edited") else "AI",
            "summary": "Saved petition", "letter_text": state["letter_text"],
            "document": document, "verification": dict(state.get("verification") or {}),
        })
    return versions


def begin(state: dict, source: str, summary: str) -> dict:
    versions = history(state)
    return {
        "document_versions": versions,
        "document_version": int(state.get("document_version") or (versions[-1]["version"] if versions else 0)),
        "petition_reference": state.get("petition_reference") or (state.get("document") or {}).get("reference"),
        "_version_source": source, "_version_summary": summary,
        "_revision_base": state.get("letter_text") or state.get("_revision_base"),
        "_revision_fields": state.get("_revision_fields") or dict(state.get("fields") or {}),
    }


def committed(state: dict, verification: dict, at: str) -> dict:
    document = dict(state.get("document") or {})
    version = int(document.get("version") or 1)
    source = state.get("_version_source") or "AI"
    summary = state.get("_version_summary") or "Initial generation"
    snapshot = {"version": version, "updated_at": at, "source": source,
                "summary": summary, "letter_text": state.get("letter_text"),
                "document": document, "verification": verification}
    versions = [*list(state.get("document_versions") or []), snapshot]
    return {"document_versions": versions, "document_version": version,
            "petition_reference": document.get("reference"), "pending_edit": None,
            "_version_source": None, "_version_summary": None,
            "_revision_base": None, "_revision_fields": {}, "_document_edit": None}
