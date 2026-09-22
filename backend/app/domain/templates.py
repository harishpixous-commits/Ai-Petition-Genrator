"""Letter templates: the schema, the loader, and the missing-field calculation.

A template is DATA, not code. Adding a letter type means dropping a YAML file
into `app/letter_templates/` — no Python change, no redeploy of logic, and no
prompt edit. That constraint is inherited from the Node service's Service Master
and it is what lets a department add its own form without an engineer.

Nothing in this module calls a model. Which fields a template requires, and
which of them are still missing, is arithmetic over a list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from dataclasses import field as dc_field
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml

from .fields import FieldResult, validate_field

Language = Literal["en", "ta"]

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "letter_templates"


# --------------------------------------------------------------------------- #
# Schema
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class TemplateField:
    name: str
    type: str
    required: bool
    label: dict[str, str]
    prompt: dict[str, str]
    # An optional field a citizen has declined is recorded as skipped rather than
    # asked again; `skippable` says whether declining is allowed at all.
    skippable: bool = True
    # Words a citizen may use to name this field when correcting it, per
    # language. Data, so that local usage can be added without a code change.
    aliases: dict[str, tuple[str, ...]] = dc_field(default_factory=dict)
    # What to call this field in a SPOKEN sentence, when the form's own label
    # does not sit well in one. A form column reads "Name of petitioner";
    # said aloud that becomes "your name of petitioner". Optional, and falls
    # back to the label, so only the fields that need it carry one.
    speech_label: dict[str, str] = dc_field(default_factory=dict)

    def label_for(self, language: Language) -> str:
        return self.label.get(language) or self.label.get("en") or self.name

    def speech_label_for(self, language: Language) -> str:
        return (self.speech_label.get(language) or self.speech_label.get("en")
                or self.label_for(language))

    def prompt_for(self, language: Language) -> str:
        return self.prompt.get(language) or self.prompt.get("en") or self.label_for(language)


@dataclass(frozen=True)
class LetterTemplate:
    id: str
    label: dict[str, str]
    authoring_language: Language
    department: dict[str, str]
    addressee: dict[str, str]
    subject: dict[str, str]
    fields: tuple[TemplateField, ...]
    enclosures: dict[str, tuple[str, ...]]
    narrative_brief: str
    closing: dict[str, str] = dc_field(default_factory=dict)

    # -- lookups ----------------------------------------------------------- #

    def field(self, name: str) -> TemplateField | None:
        return next((f for f in self.fields if f.name == name), None)

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields)

    @property
    def required_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields if f.required)

    def label_for(self, language: Language) -> str:
        return self.label.get(language) or self.label["en"]

    def text_for(self, key: str, language: Language) -> str:
        source = getattr(self, key, {}) or {}
        return source.get(language) or source.get("en") or ""

    def enclosures_for(self, language: Language) -> tuple[str, ...]:
        return self.enclosures.get(language) or self.enclosures.get("en") or ()


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #


def _as_lang_map(value: Any, fallback: str = "") -> dict[str, str]:
    """Accept either a plain string or an {en:, ta:} map in the YAML."""
    if value is None:
        return {"en": fallback} if fallback else {}
    if isinstance(value, str):
        return {"en": value}
    return {str(k): str(v) for k, v in value.items()}


def _load_one(path: Path) -> LetterTemplate:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    fields: list[TemplateField] = []
    for entry in raw.get("fields") or []:
        name = entry["name"]
        ftype = entry["type"]
        # A template naming a field type with no validator is a configuration
        # error that would otherwise surface as an accepted-but-unchecked value.
        # Fail at load, where an administrator sees it, not mid-conversation.
        validate_field(ftype, "")  # raises KeyError for an unknown type
        fields.append(
            TemplateField(
                name=name,
                type=ftype,
                required=bool(entry.get("required", True)),
                label=_as_lang_map(entry.get("label"), name.replace("_", " ").title()),
                prompt=_as_lang_map(entry.get("prompt")),
                # Empty unless the template supplies one, so `speech_label_for`
                # falls back to the label for every field that does not.
                speech_label=(_as_lang_map(entry["speech_label"])
                              if entry.get("speech_label") else {}),
                skippable=bool(entry.get("skippable", not entry.get("required", True))),
                aliases={
                    str(lang): tuple(str(a).lower() for a in words)
                    for lang, words in (entry.get("aliases") or {}).items()
                },
            )
        )

    enclosures_raw = raw.get("enclosures") or {}
    if isinstance(enclosures_raw, list):
        enclosures_raw = {"en": enclosures_raw}
    enclosures = {str(k): tuple(str(x) for x in v) for k, v in enclosures_raw.items()}

    return LetterTemplate(
        id=raw["id"],
        label=_as_lang_map(raw.get("label"), raw["id"]),
        authoring_language=raw.get("authoring_language", "en"),
        department=_as_lang_map(raw.get("department")),
        addressee=_as_lang_map(raw.get("addressee")),
        subject=_as_lang_map(raw.get("subject")),
        closing=_as_lang_map(raw.get("closing")),
        fields=tuple(fields),
        enclosures=enclosures,
        narrative_brief=str(raw.get("narrative_brief") or ""),
    )


@lru_cache(maxsize=1)
def load_templates() -> tuple[LetterTemplate, ...]:
    """Every template on disk, sorted by id. Cached; call `reload()` after edits."""
    if not TEMPLATE_DIR.exists():
        return ()
    return tuple(_load_one(p) for p in sorted(TEMPLATE_DIR.glob("*.yaml")))


def the_template() -> LetterTemplate:
    """The one installed form.

    There is a single petition form, so nothing selects between forms and the
    citizen is never asked which document they want. This raises rather than
    returning None: a service with no form loaded cannot do anything at all, and
    failing here points straight at the missing YAML instead of surfacing as a
    conversation that goes nowhere.
    """
    templates = load_templates()
    if not templates:
        raise RuntimeError(
            f"No petition template found in {TEMPLATE_DIR}. The service cannot run without one."
        )
    return templates[0]


def match_field(
    template: LetterTemplate, text: str, language: Language = "en"
) -> str | None:
    """Which field is the citizen naming? Deterministic, no model.

    This is what makes "no — the address is wrong" work at the read-back with
    nothing reachable over the network. Longest alias first, so that "aadhaar
    number" is preferred over a bare "number" if a template ever declares both.

    Returns None when nothing matches, which is a real answer: the assistant
    then lists the fields rather than guessing which one the citizen meant.
    """
    haystack = str(text or "").lower()
    candidates: list[tuple[int, str]] = []
    for spec in template.fields:
        words = set(spec.aliases.get(language, ())) | set(spec.aliases.get("en", ()))
        words.add(spec.name.replace("_", " ").lower())
        words.add(spec.label_for(language).lower())
        for word in words:
            word = word.strip().lower()
            if word and _alias_pattern(word).search(haystack):
                candidates.append((len(word), spec.name))
    if not candidates:
        return None
    return max(candidates)[1]


@lru_cache(maxsize=256)
def _alias_pattern(word: str) -> re.Pattern[str]:
    """Where an alias may appear inside what the citizen said.

    A plain substring test is wrong, and was wrong in a way that reached a
    citizen: "age" occurs inside "shortage", "village", "storage", "message"
    and "sewage", so "there is a water shortage in my village" was read as
    naming the AGE field. At the read-back that wiped an age the citizen had
    already given, and the assistant then asked for it again.

    Latin aliases are matched as whole words. Tamil aliases are anchored at the
    start only, because Tamil inflects by suffixing — a rule that requires a
    boundary at the end would stop matching the moment a case ending is added,
    which is most of the time anyone says it in a sentence.
    """
    latin = all(ord(ch) < 128 for ch in word)
    tail = r"(?!\w)" if latin else ""
    return re.compile(r"(?<!\w)" + re.escape(word) + tail)


# --------------------------------------------------------------------------- #
# Missing-field calculation — pure arithmetic, never a model call
# --------------------------------------------------------------------------- #


def missing_fields(template: LetterTemplate, collected: dict[str, Any]) -> list[str]:
    """Required fields with no accepted value yet, in template order.

    The whole of the "agentic loop" that decides what to ask next. Arithmetic
    over a list; no model has an opinion about it.
    """
    return [f.name for f in template.fields if f.required and f.name not in collected]


def next_field(template: LetterTemplate, collected: dict[str, Any]) -> TemplateField | None:
    """The single field to ask for next, in template order."""
    pending = missing_fields(template, collected)
    return template.field(pending[0]) if pending else None


def validate_extracted(
    template: LetterTemplate,
    extracted: dict[str, str],
) -> tuple[dict[str, Any], dict[str, FieldResult]]:
    """Run every extracted raw value through its field's validator.

    Returns (accepted, rejected). A value for a field the template does not
    declare is dropped silently: a model inventing `father_name` on a form that
    never asked for it must not be able to widen the record.
    """
    accepted: dict[str, Any] = {}
    rejected: dict[str, FieldResult] = {}
    for name, raw in (extracted or {}).items():
        spec = template.field(name)
        if spec is None:
            continue
        if raw is None or not str(raw).strip():
            continue
        result = validate_field(spec.type, str(raw))
        if result.ok:
            accepted[name] = result.value
        else:
            rejected[name] = result
    return accepted, rejected
