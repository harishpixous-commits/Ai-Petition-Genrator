"""The agentic loop — which contains no model call at all.

This is the whole of it. Deciding what to do next is arithmetic over the state
the validators produced: are there errors, is anything missing, has the citizen
confirmed. A model is not better at this than an `if`, and an `if` is testable,
identical on every run, and free.

Keeping this deterministic is also what makes the rest of the system auditable.
For any state you can say exactly which node runs next and why, which matters
when the output is a document a citizen submits to a government office.
"""

from __future__ import annotations

from typing import Literal

from langgraph.graph import END

from ..domain.letter import verbatim_lines
from ..services.translate import needs_translation
from .state import LetterState

AfterValidate = Literal["ask", "attach", "confirm", "compose", "__end__"]
AfterCompose = Literal["translate", "render"]


def route_after_validate(state: LetterState) -> AfterValidate:
    """ask | attach | confirm | compose | end.

    Order matters and is deliberate:
      1. A terminated session stops, whatever else is true.
      2. Errors outrank missing fields — a value the citizen just gave and that
         was rejected is the most recent thing that happened, and asking about
         something else first loses them.
      3. Nothing may be composed until the citizen has confirmed the read-back.
         This is the invariant the whole confirmation step exists for.
    """
    if state.get("status") in ("cancelled", "ready", "failed"):
        return END

    if state.get("field_errors"):
        return "ask"

    if state.get("missing"):
        return "ask"

    # A question, or an utterance nothing could be made of, is answered without
    # advancing the form — the citizen has not given a value, so there is
    # nothing to confirm and nothing to compose.
    if state.get("intent") in ("question", "unclear"):
        # Except at the attachment step. There the citizen is being asked one
        # specific either/or, and the useful answer to something unrecognised is
        # that question again — not a generic "I did not understand" that also
        # drops the session out of the step and takes the upload panel with it.
        if (state.get("intent") == "unclear"
                and not state.get("attachments_done")
                and not state.get("missing")):
            return "attach"
        return "ask"

    # The citizen has just said the read-back is wrong. Reading the identical
    # list back to them a second time is not a response to that, so the next
    # thing said is a request for the correction.
    if state.get("intent") == "reject":
        return "ask"

    # The citizen has just ANSWERED the attachment offer with "yes, I have
    # something". `validate` has already replied to that — asking them to add
    # the file — and running the `attach` node again would overwrite that reply
    # with the original question. Which is exactly what it did: a citizen who
    # typed "yes i want to add attachments" got the same question back, and it
    # read as the send button being broken.
    if state.get("intent") == "attach":
        return END

    # Every detail is in and nothing is wrong with any of it. Before the
    # read-back, ask once whether anything is enclosed — a citizen who is
    # holding the acknowledgement slip from their last petition has the one
    # thing that makes this one traceable, and nobody has asked them for it.
    if not state.get("attachments_done"):
        return "attach"

    if not state.get("confirmed"):
        return "confirm"

    return "compose"


def route_after_compose(state: LetterState) -> AfterCompose:
    """Translate only when translation is genuinely required.

    The check is on the assembled letter, not on the session language: a citizen
    who answered in Tamil against a Tamil template already has a Tamil letter,
    and a round trip to a translator would produce the text that already exists.
    """
    if state.get("status") == "failed":
        return "render"

    # A hand-edited petition is never translated. The citizen typed exactly
    # what they want the document to say, and "exactly" has to survive the rest
    # of the pipeline — a Tamil sentence added by hand came back as "The
    # additional tax", which is a translator doing its job to text that was
    # never meant for it.
    if state.get("_edited_text") or state.get("_revision_base"):
        return "render"

    language = state.get("language", "en")
    lines = (state.get("letter_text") or "").split("\n")
    # The citizen's own words are not evidence of the letter's language.
    keep = verbatim_lines(state.get("fields") or {})

    # One question, asked of the text that actually exists rather than of the
    # session's language setting. A template authored in the citizen's language,
    # filled with values they gave in that language, needs nothing further — and
    # that is the common case, so it is the one that must be free.
    return "translate" if needs_translation(lines, language, keep) else "render"
