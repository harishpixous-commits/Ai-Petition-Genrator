"""The grievance taxonomy file, and the checks that stop a bad edit shipping.

WHO THIS PROTECTS. The point of moving the vocabulary into
`app/taxonomy/grievance.yaml` is that a departmental officer can correct a word
without being able to read Python. That only works if a mistake in the file is
caught and explained, rather than silently changing how every petition in one
language is classified.

Each check below exists because the mistake it catches is SILENT. A Malayalam
word filed under `te` does not fail — it simply never matches anything, and the
only symptom is that Malayalam accuracy quietly falls. A blank entry does not
fail either: `""` is a substring of every string, so one blank line makes its
category match every grievance ever submitted.

So the file is validated at import and the service refuses to start on a bad
one. That is deliberate: an administrator who has just edited the file is
looking at the log.
"""

from __future__ import annotations

import pytest
import yaml

from app.domain.languages import SUPPORTED
from app.domain.taxonomy import (
    TAXONOMY_PATH,
    TaxonomyError,
    _load,
    taxonomy,
)


@pytest.fixture
def raw() -> dict:
    return yaml.safe_load(TAXONOMY_PATH.read_text(encoding="utf-8"))


def write(tmp_path, data: dict):
    path = tmp_path / "grievance.yaml"
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


class TestTheRealFileIsSound:
    def test_it_loads(self):
        assert taxonomy().categories

    def test_every_language_the_service_offers_has_words(self):
        """THE REGRESSION THAT STARTED ALL OF THIS. The service offered five
        languages while the classifier had words for two, and every grievance
        in the other three came back UNKNOWN — always, not often."""
        loaded = taxonomy()
        for language in SUPPORTED:
            if language == "en":
                continue
            covered = [name for name, c in loaded.categories.items()
                       if c.by_language.get(language)]
            assert len(covered) >= 8, (
                f"{language} has words in only {len(covered)} categories: "
                f"a citizen writing in it would get UNKNOWN for the rest")

    def test_every_category_can_be_answered_in_english_too(self):
        for name, category in taxonomy().categories.items():
            assert category.by_language.get("en"), name

    def test_each_category_has_a_label_in_every_language(self):
        """The officer portal shows the label. A missing one falls back to
        English, which is right as a fallback and wrong as a normal state."""
        for name, category in taxonomy().categories.items():
            for language in SUPPORTED:
                assert category.labels.get(language), f"{name}.{language}"

    def test_routing_is_marked_as_needing_evidence(self):
        """The file carries a candidate department per category. It is a
        CANDIDATE — the department on a petition comes from a retrieved
        document with a citation, never from this file."""
        for name, category in taxonomy().categories.items():
            assert category.routing.get("requires_evidence") is True, name


class TestABadEditIsCaughtAndExplained:
    def test_a_blank_term_is_refused(self, raw, tmp_path):
        """`""` is a substring of every string. One blank line would make its
        category match every grievance ever submitted."""
        raw["categories"]["WATER"]["terms"]["en"].append("   ")
        with pytest.raises(TaxonomyError, match="blank"):
            _load(write(tmp_path, raw))

    def test_a_word_in_the_wrong_script_is_refused(self, raw, tmp_path):
        """The silent one. A Malayalam word filed under `te` is matched
        against Telugu text and never fires; nothing fails, Telugu accuracy
        just quietly drops."""
        raw["categories"]["WATER"]["terms"]["te"].append("വെള്ളം")
        with pytest.raises(TaxonomyError, match="not written in the te script"):
            _load(write(tmp_path, raw))

    def test_a_term_claimed_by_two_categories_is_refused(self, raw, tmp_path):
        """A word that means two things is evidence for neither, and silently
        tips every tie between them."""
        raw["categories"]["ROAD"]["terms"]["en"].append("pension")
        with pytest.raises(TaxonomyError, match="listed under both"):
            _load(write(tmp_path, raw))

    def test_a_romanised_duplicate_of_an_english_word_is_refused(self, raw, tmp_path):
        """THIS ONE COST A REAL REGRESSION. Romanised terms are matched as
        substrings of folded, space-stripped text, so "ration" under `roman`
        is found inside "corporation" — and "the corporation has not lifted
        the rubbish" stopped being a sanitation complaint.

        The English list already matches it, with a word boundary.
        """
        raw["categories"]["WELFARE"]["terms"]["roman"] = ["ration"]
        with pytest.raises(TaxonomyError, match="spelled exactly like the English"):
            _load(write(tmp_path, raw))

    def test_an_unknown_language_key_is_refused(self, raw, tmp_path):
        """A typo like `tm:` instead of `ta:` would otherwise be accepted and
        the words simply never used."""
        raw["categories"]["WATER"]["terms"]["tm"] = ["something"]
        with pytest.raises(TaxonomyError, match="unknown term group"):
            _load(write(tmp_path, raw))

    def test_a_category_with_no_terms_at_all_is_refused(self, raw, tmp_path):
        raw["categories"]["WATER"]["terms"] = {}
        with pytest.raises(TaxonomyError):
            _load(write(tmp_path, raw))

    def test_a_missing_file_says_so(self, tmp_path):
        with pytest.raises(TaxonomyError, match="missing"):
            _load(tmp_path / "not-there.yaml")

    def test_the_message_names_the_category_and_the_language(self, raw, tmp_path):
        """An administrator who gets this error has to be able to find the
        line. "invalid taxonomy" would not be enough."""
        raw["categories"]["SANITATION"]["terms"]["hi"].append("தமிழ்")
        with pytest.raises(TaxonomyError) as caught:
            _load(write(tmp_path, raw))
        assert "SANITATION" in str(caught.value)
        assert "hi" in str(caught.value)


class TestTheTablesHandedToTheClassifier:
    def test_romanised_forms_reach_the_word_table_too(self):
        """They are matched by both rules and de-duplicated, which is what the
        live tables did before the move to a file."""
        loaded = taxonomy()
        words = loaded.words()
        for name, category in loaded.categories.items():
            for term in category.roman:
                assert term in words[name], f"{name}: {term}"

    def test_no_table_has_duplicates(self):
        for name, terms in taxonomy().words().items():
            assert len(terms) == len(set(terms)), name

    def test_the_classifier_reads_the_same_tables(self):
        """If these ever diverge, the file stops being the thing that governs
        the behaviour and becomes documentation of it."""
        from app.services import system_one

        assert system_one._CATEGORY_WORDS == taxonomy().words()
        assert system_one._WEAK_WORDS == taxonomy().weak
        assert system_one._COORDINATION == taxonomy().coordination

    def test_the_category_vocabulary_matches_the_application(self):
        from app.services.system_one import CATEGORIES

        assert set(taxonomy().names) | {"OTHER", "UNKNOWN"} == set(CATEGORIES)
