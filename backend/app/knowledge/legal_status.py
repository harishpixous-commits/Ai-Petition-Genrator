"""Whether a retrieved passage is current law, from declared amendments only.

THE QUESTION THIS ANSWERS. The corpus holds the Tamil Nadu Urban Local Bodies
Rules, 2023 as published, and eight instruments that have since changed them.
The base text of rule 290(1) still says a trade licence is "valid for a period
of three years". It has said ten years since 3 September 2026. A passage cited
from the base text is accurate to the document and wrong as law — and the
citation is exactly what makes a reader believe it.

So every passage this layer shows an officer carries its legal status:

    CURRENT     no declared amendment touches the provision it states
    HISTORICAL  the provision was substituted or amended; the text shown is
                not the law today, and the instrument that changed it is named
    INCOMPLETE  text has since been inserted (a proviso, a sub-rule); what is
                shown is not wrong, but it is no longer the whole provision
    UNKNOWN     the passage carries no heading this reader could parse, and the
                document it came from HAS declared amendments. Which provision
                the passage is cannot be read off the chunk, so neither CURRENT
                nor HISTORICAL is honest; the chunk's own text is the only guide
                a reader has and must be examined before it is relied on.

WHAT THIS REFUSES TO INFER, and why.

    Newer is not "supersedes". G.O. Ms. No. 164 of 2026 is the newest
    amendment and changes rules 289(1) and 290(1). Rule 289(5), changed by
    G.O. Ms. No. 104 of 2025, is untouched by it and remains as G.O. 104 left
    it. Status comes from relationships declared in
    `corpus/legal_relationships.yaml`, each with the Gazette text quoted,
    never from comparing dates.

    A mention is not the provision. "FORM 1 [See rules 289(3) and 290(2)]"
    cites rule 290 and is not rule 290. Only a passage whose own heading
    begins a provision is given that provision's status.

    An unverified commencement date is not presented as verified. Where the
    Gazette gives no commencement date, the status says the change is
    PRESUMED in force from publication.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REGISTRY_PATH = (Path(__file__).resolve().parent.parent.parent
                 / "corpus" / "legal_relationships.yaml")

RELATIONS = ("substitutes", "amends", "inserts")

#: "rule 290(1)" -> ("rule", "290", "(1)"); "Form 2" -> ("form", "2", "")
_PROVISION = re.compile(
    r"^\s*(rule|section|form)\s+(\d+(?:-[a-z])?)\s*((?:\([^)]*\))*)\s*$",
    re.IGNORECASE)

#: The provision a passage BEGINS, read from its own heading. Deliberately
#: anchored at the start: "FORM 1 [See rules 289 (3) and 290 (2)]" begins Form 1
#: and mentions rule 290; it must be read as Form 1 and nothing else.
_HEADING = re.compile(r"^\s*(?:(rule|section)\s+)?(\d+(?:-[A-Za-z])?)\s*[.\s—-]",
                      re.IGNORECASE)
_FORM_HEADING = re.compile(r"^\s*form\s+(\d+)\b", re.IGNORECASE)


class RegistryError(ValueError):
    """The relationships file is malformed."""


@dataclass(frozen=True)
class Provision:
    kind: str           # rule | section | form
    number: str         # "290", "300-a", "2"
    sub: str = ""       # "(1)", "" for the whole provision

    @property
    def base(self) -> str:
        return f"{self.kind} {self.number}"

    def __str__(self) -> str:
        return f"{self.kind} {self.number}{self.sub}"


def parse_provision(text: str) -> Provision:
    match = _PROVISION.match(str(text or ""))
    if not match:
        raise RegistryError(f"cannot read a provision from {text!r}")
    kind, number, sub = match.groups()
    return Provision(kind.lower(), number.lower(), (sub or "").replace(" ", ""))


@dataclass(frozen=True)
class Change:
    source: str
    relation: str
    target: str
    provision: Provision
    evidence: str
    issued: str | None
    effective_from: str | None
    citation: str

    @property
    def in_force_from(self) -> str | None:
        return self.effective_from or self.issued

    @property
    def commencement_presumed(self) -> bool:
        return self.effective_from is None


@dataclass
class Status:
    """The legal status of one passage."""

    state: str = "CURRENT"            # CURRENT | HISTORICAL | INCOMPLETE | UNKNOWN
    provision: str = ""
    changes: list[Change] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "provision": self.provision,
            "notes": list(self.notes),
            "changes": [
                {"by": c.citation, "source": c.source, "relation": c.relation,
                 "provision": str(c.provision), "issued": c.issued,
                 "in_force_from": c.in_force_from,
                 "commencement_presumed": c.commencement_presumed,
                 "evidence": c.evidence}
                for c in self.changes
            ],
        }


@dataclass
class Registry:
    instruments: dict[str, dict[str, Any]]
    changes: list[Change]
    current_sources: dict[str, dict[str, str]] = field(default_factory=dict)

    def affecting(self, target: str, provision: Provision,
                  as_of: str | None = None) -> list[Change]:
        """Every declared change to this provision, oldest first.

        A change to "rule 290(1)" affects a passage that begins rule 290. A
        change to rule 289 does NOT affect rule 290 — matching is on the whole
        base provision, never on a number appearing somewhere.
        """
        out = [c for c in self.changes
               if c.target == target and c.provision.base == provision.base
               and (as_of is None or (c.in_force_from or "") <= as_of)]
        return sorted(out, key=lambda c: c.in_force_from or "")

    def has_amendments(self, target: str) -> bool:
        """Any declared change at all touching this instrument.

        Used where the question is coarser than "which provision": a passage
        with no heading cannot be matched to a provision, but the fact that
        SOME provision of this instrument has changed is enough to refuse the
        default label of CURRENT. See `status_of`.
        """
        return any(c.target == target for c in self.changes)


def _load(path: Path) -> Registry:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    instruments = raw.get("instruments") or {}
    if not isinstance(instruments, dict):
        raise RegistryError("`instruments` must be a mapping")

    changes: list[Change] = []
    for index, item in enumerate(raw.get("relationships") or []):
        where = f"relationships[{index}]"
        relation = str(item.get("relation") or "")
        if relation not in RELATIONS:
            raise RegistryError(f"{where}: relation {relation!r} not in {RELATIONS}")
        source, target = str(item.get("source") or ""), str(item.get("target") or "")
        if source not in instruments:
            raise RegistryError(f"{where}: source {source!r} is not a declared instrument")
        if target not in instruments:
            raise RegistryError(f"{where}: target {target!r} is not a declared instrument")
        evidence = " ".join(str(item.get("evidence") or "").split())
        if len(evidence) < 20:
            # A relationship with no quoted evidence is an assertion. This file
            # exists so that every one of them can be checked against the
            # Gazette, and an empty quote cannot be.
            raise RegistryError(f"{where}: evidence must quote the source text")
        meta = instruments[source]
        changes.append(Change(
            source=source, relation=relation, target=target,
            provision=parse_provision(str(item.get("provision") or "")),
            evidence=evidence,
            issued=meta.get("issued"), effective_from=meta.get("effective_from"),
            citation=str(meta.get("citation") or source)))
    current_sources: dict[str, dict[str, str]] = {}
    for index, item in enumerate(raw.get("current_sources") or []):
        where = f"current_sources[{index}]"
        source_id = str(item.get("source") or "").strip()
        url = str(item.get("url") or "").strip()
        state = str(item.get("status") or "").strip().upper()
        verified = str(item.get("verified_on") or "").strip()
        scope = " ".join(str(item.get("scope") or "").split())
        if not source_id or not url.startswith(("https://", "http://")):
            raise RegistryError(f"{where}: source id and official URL are required")
        if state != "CURRENT":
            raise RegistryError(f"{where}: status must be CURRENT")
        if not verified or not scope:
            raise RegistryError(f"{where}: verified_on and scope are required")
        if source_id in current_sources:
            raise RegistryError(f"{where}: duplicate source {source_id!r}")
        current_sources[source_id] = {
            "status": state, "url": url, "verified_on": verified, "scope": scope,
        }
    return Registry(
        instruments=instruments, changes=changes, current_sources=current_sources
    )


@lru_cache(maxsize=1)
def registry() -> Registry:
    return _load(REGISTRY_PATH)


# --------------------------------------------------------------------------- #
# Reading a passage
# --------------------------------------------------------------------------- #

def provision_of(section: str | None, document_type: str) -> Provision | None:
    """The provision a passage BEGINS, from its own heading — or None.

    Acts number sections; Rules number rules. The noun is taken from the
    document type, because the heading usually gives only the number.
    """
    heading = str(section or "").strip()
    if not heading:
        return None
    form = _FORM_HEADING.match(heading)
    if form:
        return Provision("form", form.group(1))
    match = _HEADING.match(heading)
    if not match:
        return None
    noun = (match.group(1) or "").lower()
    if not noun:
        noun = "section" if document_type == "act" else "rule"
    return Provision(noun, match.group(2).lower())


def status_of(manifest_id: str, section: str | None, document_type: str,
              *, as_of: str | None = None) -> Status:
    """The legal status of a passage from `manifest_id` with this heading."""
    provision = provision_of(section, document_type)
    if provision is None:
        # No heading, so no provision match. If the document has NO declared
        # amendments at all, the passage can safely be marked CURRENT: nothing
        # we know about has changed it. If the document DOES have amendments,
        # the honest answer is UNKNOWN — the chunk MIGHT be the amended rule
        # 290, and labelling it CURRENT would mislead the officer.
        if registry().has_amendments(manifest_id):
            return Status(state="UNKNOWN", provision="",
                          notes=["no provision heading, and this instrument "
                                 "has declared amendments; the chunk's own "
                                 "text must be read before relying on it"])
        return Status(state="CURRENT", provision="",
                      notes=["no provision heading; status not determined by provision"])

    as_of = as_of or date.today().isoformat()
    changes = registry().affecting(manifest_id, provision, as_of=as_of)
    status = Status(provision=str(provision), changes=changes)
    if not changes:
        current_source = registry().current_sources.get(manifest_id)
        if current_source:
            return Status(
                state=current_source["status"], provision=str(provision),
                notes=[
                    f"Official departmental source checked {current_source['verified_on']}; "
                    f"scope: {current_source['scope']}. This is source currency, "
                    "not a general statutory service deadline."
                ],
            )
        return status

    if any(c.relation in ("substitutes", "amends") for c in changes):
        status.state = "HISTORICAL"
    else:
        status.state = "INCOMPLETE"

    for change in changes:
        when = change.in_force_from or "an unrecorded date"
        presumed = " (commencement presumed from publication)" \
            if change.commencement_presumed else ""
        verb = {"substitutes": "substituted", "amends": "amended",
                "inserts": "added to"}[change.relation]
        status.notes.append(
            f"{change.provision} was {verb} by {change.citation} "
            f"on {when}{presumed}.")
    return status


@lru_cache(maxsize=1)
def manifest_ids_by_url() -> dict[str, str]:
    """Official URL -> manifest id, so a stored document can find its entry."""
    manifest = Path(__file__).resolve().parent.parent.parent / "corpus" / "tamil_nadu.yaml"
    data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    out = {str(d.get("url")): str(d.get("id"))
           for d in (data.get("documents") or []) if d.get("url")}
    relationships = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    out.update({str(item.get("url")): str(item.get("source"))
                for item in (relationships.get("current_sources") or [])
                if item.get("url") and item.get("source")})
    return out


def status_for_chunk(source_url: str | None, section: str | None,
                     document_type: str, *, as_of: str | None = None) -> Status:
    """Status of a retrieved chunk, located by its document's official URL."""
    manifest_id = manifest_ids_by_url().get(str(source_url or ""))
    if not manifest_id:
        return Status(state="CURRENT",
                      notes=["document not in the manifest; legal status unknown"])
    return status_of(manifest_id, section, document_type, as_of=as_of)
