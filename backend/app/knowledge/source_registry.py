"""The source directory — what the service LOOKS AT, not what it cites.

TWO FILES, deliberately kept separate:

  `corpus/tamil_nadu.yaml`
      documents that have been read, approved and ingested — i.e. the
      corpus the officer sees citations from. Nothing here can be a
      citation until a curator has walked it through this file.

  `corpus/source_registry.yaml`
      the catalogue of URLs the discovery script may touch to find new
      Acts, Rules, Government Orders, Gazette notifications, circulars
      and court orders. Loaded by this module. Compiled from the operator
      brief dated 14 October 2026.

THE RULE THAT MATTERS, from SRS §8.2 and §D of the operator brief:

  * tier_1 (Gazette or signed PDF)             strongest evidence
  * tier_2 (current repository: India Code)    reference text
  * tier_3 (issuing department website)        procedure, forms, contacts
  * tier_4 (official court portal)             judgments, case status
  * tier_5 (grievance portal)                  routing only, never a cite
  * tier_6 (Wikipedia, blogs, commercial)      DISCOVERY ONLY — never cite

The officer UI reads `priority` to rank side-by-side findings. The discovery
script reads `access` to decide whether to touch a URL at all. The ingestion
pipeline refuses `discovery_only` sources outright, so a Wikipedia-sourced
PDF cannot slip into the corpus by mistake.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REGISTRY_PATH = (Path(__file__).resolve().parent.parent.parent
                 / "corpus" / "source_registry.yaml")

#: Valid tier ids. If the registry YAML names anything else, the parser
#: refuses to load — a misclassified source would otherwise be allowed
#: through downstream.
VALID_TIERS = frozenset({
    "tier_1_gazette",
    "tier_2_repository",
    "tier_3_department",
    "tier_4_court",
    "tier_5_grievance",
    "tier_6_discovery",
})

#: What a URL yields in practice. `discovery` is the sentinel for tier_6.
VALID_KINDS = frozenset({"document", "index", "hub", "search", "directory",
                         "discovery"})

#: How the fetch script may touch the URL. `discovery_only` locks a source
#: out of the ingestion pipeline entirely.
VALID_ACCESS = frozenset({"polite", "manual", "discovery_only"})


class RegistryError(ValueError):
    """The source registry file is malformed."""


@dataclass(frozen=True)
class Tier:
    id: str
    priority: int
    name: str
    description: str


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    url: str
    tier: str
    kind: str
    access: str
    departments: tuple[str, ...]
    captures: tuple[str, ...]
    notes: str = ""

    @property
    def is_citable(self) -> bool:
        """Can a document fetched from here be cited to a citizen?

        No for `tier_6_discovery` or `access = discovery_only`. The brief
        is explicit: Wikipedia and commercial databases may suggest search
        terms and nothing more.
        """
        return self.tier != "tier_6_discovery" and self.access != "discovery_only"


@dataclass(frozen=True)
class Registry:
    version: int
    compiled_on: str
    tiers: dict[str, Tier]
    sources: tuple[Source, ...]

    def source(self, source_id: str) -> Source | None:
        return next((s for s in self.sources if s.id == source_id), None)

    def by_tier(self, tier_id: str) -> tuple[Source, ...]:
        return tuple(s for s in self.sources if s.tier == tier_id)

    def by_access(self, access: str) -> tuple[Source, ...]:
        return tuple(s for s in self.sources if s.access == access)

    def citable_sources(self) -> tuple[Source, ...]:
        return tuple(s for s in self.sources if s.is_citable)


def _load(path: Path) -> Registry:
    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    tiers = {}
    for index, item in enumerate(raw.get("tiers") or ()):
        tier_id = str(item.get("id") or "")
        if tier_id not in VALID_TIERS:
            raise RegistryError(
                f"tiers[{index}]: id {tier_id!r} not in VALID_TIERS")
        tiers[tier_id] = Tier(
            id=tier_id,
            priority=int(item.get("priority") or 0),
            name=str(item.get("name") or ""),
            description=str(item.get("description") or "").strip(),
        )
    missing = VALID_TIERS - set(tiers)
    if missing:
        raise RegistryError(f"tiers missing from the file: {sorted(missing)}")

    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    sources: list[Source] = []
    for index, item in enumerate(raw.get("sources") or ()):
        where = f"sources[{index}]"
        source_id = str(item.get("id") or "")
        if not source_id:
            raise RegistryError(f"{where}: missing id")
        if source_id in seen_ids:
            raise RegistryError(f"{where}: duplicate id {source_id!r}")
        seen_ids.add(source_id)

        url = str(item.get("url") or "")
        if not url.startswith(("http://", "https://")):
            raise RegistryError(
                f"{where} ({source_id}): url must start with http(s), got {url!r}")
        if url in seen_urls:
            raise RegistryError(f"{where} ({source_id}): duplicate url {url!r}")
        seen_urls.add(url)

        tier = str(item.get("tier") or "")
        if tier not in VALID_TIERS:
            raise RegistryError(
                f"{where} ({source_id}): tier {tier!r} not in VALID_TIERS")

        kind = str(item.get("kind") or "")
        if kind not in VALID_KINDS:
            raise RegistryError(
                f"{where} ({source_id}): kind {kind!r} not in VALID_KINDS")

        access = str(item.get("access") or "")
        if access not in VALID_ACCESS:
            raise RegistryError(
                f"{where} ({source_id}): access {access!r} not in VALID_ACCESS")

        # Tier 6 and `discovery_only` must match. A tier_6 row with
        # access=polite would let the discovery script fetch content from
        # a Wikipedia URL and later let an operator ingest it — which the
        # brief forbids.
        if tier == "tier_6_discovery" and access != "discovery_only":
            raise RegistryError(
                f"{where} ({source_id}): tier_6_discovery MUST declare "
                "access: discovery_only")
        if access == "discovery_only" and tier != "tier_6_discovery":
            raise RegistryError(
                f"{where} ({source_id}): access: discovery_only requires "
                "tier_6_discovery")

        departments = tuple(str(d).strip() for d in (item.get("departments") or ()))
        captures = tuple(str(c).strip() for c in (item.get("captures") or ()))

        sources.append(Source(
            id=source_id,
            name=str(item.get("name") or source_id),
            url=url,
            tier=tier,
            kind=kind,
            access=access,
            departments=departments,
            captures=captures,
            notes=str(item.get("notes") or "").strip(),
        ))

    if not sources:
        raise RegistryError("the registry file has no sources — refusing to load")

    return Registry(
        version=int(raw.get("version") or 1),
        compiled_on=str(raw.get("compiled_on") or ""),
        tiers=tiers,
        sources=tuple(sources),
    )


@lru_cache(maxsize=1)
def registry() -> Registry:
    """The parsed registry, cached for the life of the process."""
    return _load(REGISTRY_PATH)


def rank_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Order findings by source priority — stronger evidence first.

    A finding is {source_url, ...}. The source priority is looked up by
    URL in the registry; findings pointing at an unknown URL fall to the
    end. Ties keep the original order (stable sort).

    The officer page uses this to render Gazette-cited findings above
    repository-cited ones, which SRS §8.5 asks for when a conflict exists.
    """
    url_to_tier = {s.url: s.tier for s in registry().sources}
    tier_priority = {t.id: t.priority for t in registry().tiers.values()}
    highest = max(tier_priority.values()) + 1

    def key(finding: dict[str, Any]) -> int:
        tier = url_to_tier.get(str(finding.get("source_url") or ""))
        return tier_priority.get(tier or "", highest)

    return sorted(findings, key=key)
