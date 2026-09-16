"""The one agentic step: what did the citizen just say, and what does it mean?

This is the ONLY place in the conversational loop where a language model has any
say, and even here its output is a typed object that the deterministic code then
judges. It extracts; `fields.py` decides.

It is a single structured-output call rather than a tool-calling loop on purpose.
A tool loop runs an unpredictable number of round trips, and in a voice
conversation the variance is the problem: the citizen hears a different amount of
silence every turn and starts talking over the assistant. One call in, one object
out, fixed cost.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Intent = Literal[
    "provide",   # answering the question that was asked
    "correct",   # amending something already recorded
    "confirm",   # yes, generate the letter
    "reject",    # no, something is wrong
    "skip",      # decline an optional field
    "question",  # asking the assistant something
    "restart",   # start over
    "cancel",    # abandon the request
    "unclear",   # the model could not tell
]


class Understanding(BaseModel):
    """What one citizen utterance meant, as a typed object.

    Every string in `fields` and `corrections` is RAW — exactly what the citizen
    said for that field, not a cleaned or reformatted version. The model is told
    not to normalise, because normalisation is a decision and decisions here
    belong to the validators, which are testable and identical on every run.
    """

    intent: Intent = "provide"

    fields: dict[str, str] = Field(
        default_factory=dict,
        description="New values, keyed by template field name. Raw, exactly as said.",
    )

    corrections: dict[str, str] = Field(
        default_factory=dict,
        description="Amendments to values already recorded, keyed by template field name.",
    )

    question: str | None = Field(
        default=None,
        description="The citizen's question, when intent is 'question'.",
    )

    # Not a confidence score on the answer — a flag for "I am guessing which
    # field this belongs to". The router uses it to prefer re-asking over
    # recording something the citizen did not mean to say.
    ambiguous: bool = False

    @field_validator("fields", "corrections", mode="before")
    @classmethod
    def _drop_empties(cls, value: object) -> dict[str, str]:
        if not isinstance(value, dict):
            return {}
        return {
            str(k): str(v).strip()
            for k, v in value.items()
            if v is not None and str(v).strip() and str(v).strip().lower() not in {"null", "none", "n/a", "-"}
        }


# --------------------------------------------------------------------------- #
# The JSON schema handed to the provider
# --------------------------------------------------------------------------- #


def understanding_schema(field_names: list[str]) -> dict:
    """A JSON schema pinned to THIS template's field names.

    Constraining `fields` to an enum of real field names is what stops a model
    inventing `father_name` on a form that never asked for one. `templates.py`
    drops unknown keys as a second line of defence, but preventing them costs
    nothing and keeps the model's output honest.
    """
    key_enum = {"type": "string", "enum": field_names} if field_names else {"type": "string"}
    return {
        "type": "object",
        "properties": {
            "intent": {"type": "string", "enum": list(Intent.__args__)},
            "fields": {
                "type": "array",
                "maxItems": 12,
                "items": {
                    "type": "object",
                    "properties": {"name": key_enum, "value": {"type": "string", "maxLength": 400}},
                    "required": ["name", "value"],
                },
            },
            "corrections": {
                "type": "array",
                "maxItems": 12,
                "items": {
                    "type": "object",
                    "properties": {"name": key_enum, "value": {"type": "string", "maxLength": 400}},
                    "required": ["name", "value"],
                },
            },
            "question": {"type": "string", "maxLength": 400},
            "ambiguous": {"type": "boolean"},
        },
        "required": ["intent"],
    }


def from_provider_payload(payload: dict) -> Understanding:
    """Build an `Understanding` from the array-of-pairs shape the schema asks for.

    Arrays rather than free-form objects because strict `json_schema` mode on
    several providers rejects an object with arbitrary keys outright — the same
    constraint that the Node service hit and documented.
    """
    def pairs(key: str) -> dict[str, str]:
        out: dict[str, str] = {}
        for item in payload.get(key) or []:
            if isinstance(item, dict) and item.get("name"):
                out[str(item["name"])] = str(item.get("value", ""))
        return out

    return Understanding(
        intent=payload.get("intent") or "provide",
        fields=pairs("fields"),
        corrections=pairs("corrections"),
        question=payload.get("question") or None,
        ambiguous=bool(payload.get("ambiguous", False)),
    )


SYSTEM_PROMPT = """You read one message from a citizen who is filling in an Indian government form by voice or text, and you report what it contained.

You do exactly one job: report what the citizen said. You do not decide whether a value is valid, you do not reformat it, and you do not fill in anything the citizen did not say.

Rules:
- Copy values EXACTLY as the citizen said them. Do not reformat numbers, dates, or names. "four one two three" stays "four one two three". Separate code checks and normalises every value.
- Use `fields` for answers to what was asked. Use `corrections` only when the citizen is changing something they already gave ("actually my age is 31", "no, that should be 641004").
- Only use field names from the list you are given. If something the citizen said has no matching field, leave it out.
- Set intent to `confirm` only for a clear agreement to proceed, `reject` for a clear disagreement, `skip` when they decline to answer, `restart` to start over, `cancel` to abandon, `question` when they are asking you something.
- If you cannot tell which field a value belongs to, set `ambiguous` to true and leave the value out rather than guessing.
- Never invent a name, number, date, amount, address or identifier. If it was not said, it is not there."""
