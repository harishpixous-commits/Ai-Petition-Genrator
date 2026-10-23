"""The India Code TN importer gates on the registry and refuses live hits
to discovery-only sources.

PHASE 2 RULE 10 asked for `discovery-only source blocking`. The registry's
own tests cover the structural rule; this file holds the CLI's enforcement
of it so a future author cannot bypass the gate by hard-coding a URL into
the ingester.

Offline. The one subprocess the CLI runs is `_source()` which reads the
registry — the actual network paths are not exercised here.
"""

from __future__ import annotations

import importlib

import pytest


@pytest.fixture
def cli():
    """The ingest CLI. Reloaded here so patching the registry module works."""
    importlib.import_module("app.knowledge.source_registry").registry.cache_clear()
    yield importlib.import_module("scripts.ingest_india_code_tn")
    importlib.import_module("app.knowledge.source_registry").registry.cache_clear()


class TestTheRegistryGate:
    def test_the_india_code_tn_source_is_citable(self, cli):
        """A quick sanity check: without this, the gate would refuse the
        intended path too and no amount of fixing the CLI would help."""
        source = cli._source()
        assert source.id == "indiacode-tn"
        assert source.tier == "tier_2_repository"
        assert source.access == "polite"

    def test_a_discovery_only_source_cannot_be_targeted(self, cli, monkeypatch):
        """If the ingester were ever repointed at Wikipedia, `_source()`
        must refuse. The registry's `is_citable` + the CLI's SystemExit
        is the second half of the structural rule."""
        monkeypatch.setattr(cli, "SOURCE_ID", "wikipedia-tn-laws")
        with pytest.raises(SystemExit, match="non-citable"):
            cli._source()

    def test_an_unknown_source_id_refuses(self, cli, monkeypatch):
        monkeypatch.setattr(cli, "SOURCE_ID", "not-a-real-source")
        with pytest.raises(SystemExit, match="not in the registry"):
            cli._source()
