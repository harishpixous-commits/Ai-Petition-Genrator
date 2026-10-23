"""Whether a retrieved passage is current law — from declared, quoted amendments.

THE CASE AT THE CENTRE, verified against the Gazette:

    rule 290(1) of the Tamil Nadu Urban Local Bodies Rules, 2023, as published:
        a trade licence is "valid for a period of three years"
    G.O. Ms. No. 35 of 17 March 2025:   that expression replaced
    G.O. Ms. No. 164 of 3 September 2026: sub-rule (1) SUBSTITUTED — ten years

The base text is still in the corpus and still retrievable. Cited without a
status, it is accurate to the document and wrong as law.

THE INVARIANT MOST LIKELY TO BE BROKEN by a well-meaning future change:
"the newest amendment supersedes the earlier ones". It does not. G.O. 164 is
the newest and touches rules 289(1) and 290(1) only. Rule 289(5) as G.O. 104
substituted it, and rules 255-268 as G.O. 480 amended them, are untouched.
Several tests below exist only to hold that line.

Offline: these read `corpus/legal_relationships.yaml` and synthetic headings.
The last class reads the real indexed corpus and skips if it is not built.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app.knowledge import legal_status as ls

RULES = "tn-ulb-rules-2023"


def status(section: str, *, as_of: str | None = None, document_type: str = "rule"):
    return ls.status_of(RULES, section, document_type, as_of=as_of)


class TestTheRegistryIsSound:
    def test_it_loads_and_every_change_quotes_its_source(self):
        registry = ls.registry()
        assert registry.changes
        for change in registry.changes:
            assert len(change.evidence) >= 20, change

    def test_an_unquoted_relationship_is_refused(self, tmp_path):
        """A relationship with no quoted evidence is an assertion; the file
        exists so that each one can be checked against the Gazette."""
        path = tmp_path / "rel.yaml"
        path.write_text(
            "instruments:\n  a: {citation: A, issued: '2025-01-01'}\n"
            "  b: {citation: B, issued: '2024-01-01'}\n"
            "relationships:\n  - {source: a, relation: amends, target: b, "
            "provision: 'rule 1', evidence: 'short'}\n", encoding="utf-8")
        with pytest.raises(ls.RegistryError, match="evidence"):
            ls._load(path)

    def test_an_undeclared_instrument_is_refused(self, tmp_path):
        path = tmp_path / "rel.yaml"
        path.write_text(
            "instruments:\n  a: {citation: A}\n"
            "relationships:\n  - {source: a, relation: amends, target: nowhere, "
            "provision: 'rule 1', evidence: 'a quotation long enough to count'}\n",
            encoding="utf-8")
        with pytest.raises(ls.RegistryError, match="not a declared instrument"):
            ls._load(path)

    def test_an_unknown_relation_is_refused(self, tmp_path):
        path = tmp_path / "rel.yaml"
        path.write_text(
            "instruments:\n  a: {citation: A}\n  b: {citation: B}\n"
            "relationships:\n  - {source: a, relation: obliterates, target: b, "
            "provision: 'rule 1', evidence: 'a quotation long enough to count'}\n",
            encoding="utf-8")
        with pytest.raises(ls.RegistryError, match="relation"):
            ls._load(path)


class TestTheTradeLicenceChain:
    def test_rule_290_today_is_historical(self):
        result = status("290 Validity and Renewal of Licences.")
        assert result.state == "HISTORICAL"
        sources = [c.source for c in result.changes]
        assert sources == ["tn-ulb-rules-amend-35-2025",
                           "tn-ulb-rules-amend-164-2026"], "oldest first"

    def test_the_status_names_the_instrument_and_the_date(self):
        notes = " ".join(status("290 Validity").notes)
        assert "G.O. Ms. No. 164" in notes
        assert "2026-09-03" in notes

    def test_an_unverified_commencement_date_is_labelled_presumed(self):
        """The Gazette gave no commencement date for these rule amendments.
        The service must say it is presuming, not imply it knows."""
        result = status("290 Validity")
        assert all(c.commencement_presumed for c in result.changes)
        assert "presumed" in " ".join(result.notes)


class TestStatusDependsOnTheDateAsked:
    def test_before_any_amendment_the_base_text_was_current(self):
        assert status("290 Validity", as_of="2024-12-31").state == "CURRENT"

    def test_between_the_two_amendments_only_the_first_applied(self):
        result = status("290 Validity", as_of="2025-12-31")
        assert result.state == "HISTORICAL"
        assert [c.source for c in result.changes] == ["tn-ulb-rules-amend-35-2025"]

    def test_after_the_second_both_are_on_the_record(self):
        result = status("290 Validity", as_of="2026-12-31")
        assert len(result.changes) == 2


class TestTheNewestAmendmentDoesNotSupersedeEverything:
    """The invariant most likely to be broken by a future 'simplification'."""

    def test_rule_289_5_is_as_go_104_left_it_not_go_164(self):
        result = status("289 Application for trade licence")
        by_subrule = {(c.source, str(c.provision)) for c in result.changes}
        assert ("tn-ulb-rules-amend-104-2025", "rule 289(5)") in by_subrule
        assert ("tn-ulb-rules-amend-164-2026", "rule 289(5)") not in by_subrule

    def test_property_tax_rules_are_touched_only_by_go_480(self):
        for rule in ("255", "258", "260", "265", "268"):
            result = status(f"{rule} Something about property tax")
            sources = {c.source for c in result.changes}
            assert sources == {"tn-ulb-rules-amend-480-2025"}, (rule, sources)

    def test_a_rule_with_no_declared_change_is_current(self):
        """Not 'current because nothing newer exists' — current because no
        declared relationship touches it. Rule 100 has none."""
        assert status("100 Something else entirely").state == "CURRENT"


class TestAMentionIsNotTheProvision:
    def test_a_form_that_cites_rule_290_is_not_rule_290(self):
        """'FORM 1 [See rules 289 (3) and 290 (2)]' cites rule 290. It is a
        form, and it must not be labelled as superseded rule text."""
        heading = "FORM 1 [See rules 289 (3) and 290 (2)] APPLICATION FOR ISSUE OF LICENCE"
        result = status(heading)
        assert result.state == "CURRENT"
        assert result.provision == "form 1"

    def test_an_unheaded_passage_from_an_amended_instrument_is_UNKNOWN(self):
        """status(X) uses tn-ulb-rules-2023, which HAS declared amendments.
        A chunk with no heading could be any provision — including rule 290(1),
        now historical. Marking it CURRENT would wrongly reassure a reader; the
        honest answer is UNKNOWN with a note telling them to read the text."""
        result = status("")
        assert result.state == "UNKNOWN"
        assert any("declared amendments" in note for note in result.notes)

    def test_an_unheaded_passage_from_an_unamended_instrument_is_CURRENT(self):
        """When the instrument has NO declared amendment at all, there is
        nothing the chunk could be a now-historical copy of — so the default
        CURRENT is safe. tn-swm-rules-2016-tamil has no amendments on file."""
        result = ls.status_of("tn-swm-rules-2016-tamil", None, "rule")
        assert result.state == "CURRENT"
        assert "not determined" in " ".join(result.notes)

    def test_an_insertion_makes_a_provision_incomplete_not_wrong(self):
        """Rule 192-A was INSERTED by G.O. 162. Nothing existing was replaced,
        so the passage beginning rule 192-A — had it existed — is not
        historical. A provision only touched by insertions is INCOMPLETE."""
        result = status("192-A Fixation of seniority")
        assert result.state == "INCOMPLETE"


class TestActsUseSections:
    def test_a_section_of_the_act_is_read_as_a_section(self):
        result = ls.status_of("tn-ulb-act-1998", "3 Constitution of local bodies",
                              "act")
        assert result.provision == "section 3"
        assert result.state == "HISTORICAL"

    def test_an_act_with_a_verified_commencement_is_not_presumed(self):
        """Act 30 of 2025 states its appointed day (26 June 2025, by G.O. 119).
        That date is verified and must not be labelled a presumption."""
        result = ls.status_of("tn-ulb-act-1998", "37 Something", "act")
        changes = [c for c in result.changes
                   if c.source == "tn-ulb-amendment-act-30-2025"]
        assert changes and not changes[0].commencement_presumed
        assert changes[0].in_force_from == "2025-06-26"


KNOWLEDGE = Path(__file__).resolve().parent.parent / "var" / "knowledge.sqlite"


@pytest.mark.skipif(not KNOWLEDGE.exists(),
                    reason="the real corpus is not built; run scripts/fetch_corpus.py ingest")
class TestTheRealIndexedText:
    """Against the actual Gazette-derived chunks, not a synthetic heading."""

    def _chunk(self, where: str):
        db = sqlite3.connect(f"file:{KNOWLEDGE}?mode=ro", uri=True)
        try:
            return db.execute(
                "SELECT c.section, d.source_url, d.document_type, c.text "
                "FROM chunks c JOIN documents d ON d.document_id = c.document_id "
                f"WHERE d.title LIKE '%Rules, 2023%' AND {where} LIMIT 1").fetchone()
        finally:
            db.close()

    def test_the_indexed_three_year_text_is_labelled_historical(self):
        row = self._chunk("c.section LIKE '290 Validity%'")
        if row is None:
            pytest.skip("rule 290 chunk not present in this corpus build")
        section, url, kind, text = row
        assert "three years" in text, "this is the superseded wording"
        result = ls.status_for_chunk(url, section, kind)
        assert result.state == "HISTORICAL"
        assert any("164" in note for note in result.notes)
