"""The source registry is a security boundary, not a reference table.

WHY THESE TESTS. The brief dated 14 October 2026 draws one bright line
through everything else: Wikipedia and commercial legal databases may be
used to find search terms, but never cited as legal authority. The
registry parser enforces that line with a type-level rule — tier_6 and
`discovery_only` must coincide — and these tests pin that rule in place so
a future author cannot quietly open the gate by misclassifying a row.

The tests also hold the shape of the file:

  * every tier id is one of the six the parser accepts
  * every source has a tier, a kind, an access policy and an http(s) url
  * duplicate ids and duplicate urls are refused
  * tier_6 and access=discovery_only are coupled both ways
  * the Wikipedia entry is specifically identified as discovery-only

Offline. The YAML is read, nothing is fetched.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from app.knowledge import source_registry as sr


class TestTheRealFileLoads:
    def test_the_registry_loads_cleanly(self):
        reg = sr.registry()
        assert reg.sources, "the registry must have at least one source"
        assert reg.tiers.keys() == sr.VALID_TIERS

    def test_every_source_has_a_tier_the_parser_accepts(self):
        reg = sr.registry()
        for source in reg.sources:
            assert source.tier in sr.VALID_TIERS, source
            assert source.kind in sr.VALID_KINDS, source
            assert source.access in sr.VALID_ACCESS, source
            assert source.url.startswith(("http://", "https://")), source

    def test_ids_are_unique(self):
        reg = sr.registry()
        assert len({s.id for s in reg.sources}) == len(reg.sources)

    def test_urls_are_unique(self):
        reg = sr.registry()
        assert len({s.url for s in reg.sources}) == len(reg.sources)


class TestTheDiscoveryOnlyLine:
    def test_the_wikipedia_entry_is_discovery_only(self):
        """The brief is explicit: Wikipedia may be used for search terms,
        never as controlling authority. The registry must carry that rule."""
        wiki = sr.registry().source("wikipedia-tn-laws")
        assert wiki is not None, "the Wikipedia discovery entry is missing"
        assert wiki.tier == "tier_6_discovery"
        assert wiki.access == "discovery_only"
        assert not wiki.is_citable

    def test_nothing_in_tier_6_is_citable(self):
        for source in sr.registry().by_tier("tier_6_discovery"):
            assert not source.is_citable

    def test_nothing_marked_discovery_only_is_citable(self):
        for source in sr.registry().by_access("discovery_only"):
            assert not source.is_citable

    def test_every_tier_except_discovery_IS_citable(self):
        """A real-source misclassified as discovery_only is as bad as the
        opposite error — a Gazette URL that cannot be cited is useless."""
        for tier_id in sr.VALID_TIERS - {"tier_6_discovery"}:
            for source in sr.registry().by_tier(tier_id):
                assert source.is_citable, (tier_id, source)


class TestTheParserRefusesMisclassifiedRows:
    def _write(self, tmp_path, body: dict) -> Path:
        path = tmp_path / "registry.yaml"
        path.write_text(yaml.safe_dump(body), encoding="utf-8")
        return path

    def _base_tiers(self) -> list[dict]:
        return [
            {"id": tier, "priority": priority, "name": tier, "description": "x"}
            for priority, tier in enumerate(sorted(sr.VALID_TIERS), start=1)
        ]

    def test_a_tier_6_row_without_discovery_only_is_refused(self, tmp_path):
        """This is the whole point of the two-field pair. A tier_6 row with
        access=polite would let the discovery script fetch it and let an
        operator later approve the result into the corpus."""
        body = {
            "version": 1, "compiled_on": "test",
            "tiers": self._base_tiers(),
            "sources": [{
                "id": "wiki-mistake",
                "name": "x", "url": "https://en.wikipedia.org/wiki/X",
                "tier": "tier_6_discovery", "kind": "discovery",
                "access": "polite",   # the mistake
                "departments": ["all"], "captures": [],
            }],
        }
        with pytest.raises(sr.RegistryError, match="discovery_only"):
            sr._load(self._write(tmp_path, body))

    def test_a_discovery_only_row_not_in_tier_6_is_refused(self, tmp_path):
        """The reverse: an India Code URL marked discovery_only would make
        the real repository unciteable. The two fields must agree."""
        body = {
            "version": 1, "compiled_on": "test",
            "tiers": self._base_tiers(),
            "sources": [{
                "id": "india-code-mistake",
                "name": "x", "url": "https://indiacode.gov.in/",
                "tier": "tier_2_repository", "kind": "hub",
                "access": "discovery_only",  # the mistake
                "departments": ["all"], "captures": [],
            }],
        }
        with pytest.raises(sr.RegistryError, match="tier_6_discovery"):
            sr._load(self._write(tmp_path, body))

    def test_a_duplicate_id_is_refused(self, tmp_path):
        body = {
            "version": 1, "compiled_on": "test",
            "tiers": self._base_tiers(),
            "sources": [
                {"id": "a", "name": "x", "url": "https://a.example/",
                 "tier": "tier_1_gazette", "kind": "hub", "access": "polite",
                 "departments": [], "captures": []},
                {"id": "a", "name": "y", "url": "https://b.example/",
                 "tier": "tier_1_gazette", "kind": "hub", "access": "polite",
                 "departments": [], "captures": []},
            ],
        }
        with pytest.raises(sr.RegistryError, match="duplicate id"):
            sr._load(self._write(tmp_path, body))

    def test_a_non_http_url_is_refused(self, tmp_path):
        body = {
            "version": 1, "compiled_on": "test",
            "tiers": self._base_tiers(),
            "sources": [{
                "id": "ftp", "name": "x", "url": "ftp://example.com/",
                "tier": "tier_1_gazette", "kind": "hub", "access": "polite",
                "departments": [], "captures": [],
            }],
        }
        with pytest.raises(sr.RegistryError, match="http"):
            sr._load(self._write(tmp_path, body))

    def test_a_missing_tier_in_the_header_is_refused(self, tmp_path):
        body = {
            "version": 1, "compiled_on": "test",
            "tiers": [{"id": "tier_1_gazette", "priority": 1, "name": "x",
                       "description": "x"}],  # only one tier
            "sources": [{"id": "a", "name": "x", "url": "https://a.example/",
                         "tier": "tier_1_gazette", "kind": "hub",
                         "access": "polite", "departments": [], "captures": []}],
        }
        with pytest.raises(sr.RegistryError, match="tiers missing"):
            sr._load(self._write(tmp_path, body))


class TestFindingsRankedByTier:
    def test_a_gazette_finding_outranks_a_repository_one(self):
        """Officer rendering uses this to put stronger evidence first when
        two sources both cover the same point — SRS §8.5."""
        gazette_url = sr.registry().by_tier("tier_1_gazette")[0].url
        repository_url = sr.registry().by_tier("tier_2_repository")[0].url
        findings = [
            {"name": "weak",   "source_url": repository_url},
            {"name": "strong", "source_url": gazette_url},
        ]
        ordered = sr.rank_findings(findings)
        assert ordered[0]["name"] == "strong"
        assert ordered[1]["name"] == "weak"

    def test_an_unknown_url_falls_to_the_end(self):
        gazette_url = sr.registry().by_tier("tier_1_gazette")[0].url
        findings = [
            {"name": "mystery", "source_url": "https://nowhere.example/"},
            {"name": "gazette", "source_url": gazette_url},
        ]
        ordered = sr.rank_findings(findings)
        assert ordered[0]["name"] == "gazette"
        assert ordered[1]["name"] == "mystery"

    def test_the_sort_is_stable_within_a_tier(self):
        """Two findings with the same source priority keep input order, so
        the officer sees them in retrieval order rather than scrambled."""
        gazette_url = sr.registry().by_tier("tier_1_gazette")[0].url
        findings = [
            {"name": f"g{i}", "source_url": gazette_url} for i in range(5)
        ]
        ordered = sr.rank_findings(findings)
        assert [f["name"] for f in ordered] == [f"g{i}" for i in range(5)]
