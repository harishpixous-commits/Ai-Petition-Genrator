"""Every word on the page exists in both languages.

THE BUG THIS EXISTS FOR. The landing page was redesigned and the
translation table was not. The header and the navigation switched to Tamil
because those ids are painted explicitly; the hero, both action cards and
all three steps stayed in English, because nothing connected them to the
table at all. A citizen who picked தமிழ் got a Tamil menu bar on an English
page, and nothing anywhere failed.

Two failure modes, and the tests below are split to match:

    an element on the page with no string behind it      -> stays English
    a string in the table with no element in front of it -> silently dead

The second is how the first happened: the table still held the copy from
the previous design, so it looked populated while pointing at nothing.
"""

from __future__ import annotations

import pathlib
import re

import pytest

STATIC = pathlib.Path("app/static")

# Key and its double-quoted value, matched anywhere on a line rather than at
# the start of one, because several keys share a line in this table. The
# value permits escaped characters so an apostrophe written \\" does not end
# it early.
_ENTRY = re.compile(r'\b([A-Za-z0-9_]+):\s*"((?:[^"\\]|\\.)*)"')


def page() -> str:
    return (STATIC / "index.html").read_text(encoding="utf-8")


def navigation() -> str:
    return (STATIC / "navigation.js").read_text(encoding="utf-8")


def wired_keys() -> list[str]:
    return sorted(set(re.findall(r'data-i18n="([A-Za-z0-9_]+)"', page())))


def table(language: str) -> dict[str, str]:
    """The `en` or `ta` block of NAV, as a plain dict.

    Parsed rather than executed: this is a test, and running the page's
    JavaScript to read a lookup table would need a browser to prove
    something that is true of the text.
    """
    js = navigation()
    start = js.index(f"  {language}: {{")
    end = js.index("  ta: {") if language == "en" else len(js)
    return dict(_ENTRY.findall(js[start:end]))


def test_the_page_has_translatable_text_at_all():
    """A guard on the guard. If the attribute is renamed, every test below
    passes vacuously by finding nothing to check."""
    assert len(wired_keys()) >= 25, wired_keys()


def test_both_tables_parsed():
    """Likewise: an empty table would make the checks below trivially true."""
    assert len(table("en")) >= 40
    assert len(table("ta")) >= 40


@pytest.mark.parametrize("language", ["en", "ta"])
def test_every_element_on_the_page_has_a_string(language):
    missing = [key for key in wired_keys() if key not in table(language)]
    assert not missing, f"{language}: no string for {missing}"


def test_nothing_is_left_in_english_by_accident():
    """A Tamil entry identical to the English one is almost always a key
    that was copied and never translated."""
    english, tamil = table("en"), table("ta")
    same = [key for key in wired_keys()
            if key in english and key in tamil
            and english[key].strip() == tamil[key].strip()]
    assert not same, f"still English in the Tamil table: {same}"


def test_the_hero_line_break_survives_translation():
    """The title is two lines by design. Held as one string it would be set
    with `textContent`, which eats the `<br>` and gives Tamil a single long
    line where English has two."""
    markup = page()

    assert 'data-i18n="homeTitleLineOne"' in markup
    assert 'data-i18n="homeTitleLineTwo"' in markup
    assert re.search(r'homeTitleLineOne"[^<]*</span><br>', markup), (
        "the two lines are no longer separated by a break")


def test_the_table_does_not_carry_copy_the_page_stopped_using():
    """Dead entries are how the original bug hid: the table looked
    populated while pointing at a design that no longer existed.

    Only the home keys are checked, because the rest of the table is read
    by name from navigation.js rather than through the attribute.
    """
    wired = set(wired_keys())
    js = navigation()
    dead = [key for key in table("en")
            if key.startswith("home")
            and key not in wired
            # Still legitimate if navigation.js reads it by name.
            and f"n.{key}" not in js and f"N().{key}" not in js]
    assert not dead, f"nothing on the page uses: {dead}"


@pytest.mark.parametrize("key,expected", [
    ("homeTitleLineOne", "உங்கள் குறைகள்."),
    ("homeCreateTitle", "மனு உருவாக்கு"),
    ("homePetitionsTitle", "அனைத்து மனுக்கள்"),
    ("homeGuideEyebrow", "மூன்று எளிய படிகள்"),
])
def test_the_tamil_actually_says_what_it_should(key, expected):
    """Spot checks, so a future edit that empties a string or pastes the
    wrong one is caught rather than merely being different from English."""
    assert table("ta")[key] == expected


# ---------------------------------------------------------------------------
# The two microphones
# ---------------------------------------------------------------------------

def app_js() -> str:
    return (STATIC / "app.js").read_text(encoding="utf-8")










# ---------------------------------------------------------------------------
# The labels painted by id rather than by data-i18n
# ---------------------------------------------------------------------------
#
# The filter panel on the petitions list was built with plain ids and never
# joined to either mechanism, so "Sort by", "Created from", "Department",
# "Category", "Status" and "Language" stayed English on a Tamil page — beside
# their own dropdowns, whose contents were already translated.

_ID_MAP = re.compile(r"Object\.entries\(\{ navHome:.*?\}\)\)", re.S)


def id_map() -> dict[str, str]:
    """The `{ elementId: n.key }` table inside navigationLabels()."""
    block = _ID_MAP.search(navigation())
    assert block, "the id paint table has been renamed"
    return dict(re.findall(r"(\w+):\s*n\.(\w+)", block.group(0)))


@pytest.mark.parametrize("element_id", [
    "petitionSortLabel", "filterDateFromLabel", "filterDateToLabel",
    "filterDepartmentLabel", "filterCategoryLabel", "filterStatusLabel",
    "filterLanguageLabel", "petitionFilterHint", "versionTitle",
])
def test_every_filter_label_is_painted(element_id):
    assert element_id in id_map(), element_id


def test_the_ids_it_paints_are_really_on_the_page():
    """The other half of the same bug: a table entry pointing at nothing."""
    markup = page()
    for element_id in id_map():
        assert f'id="{element_id}"' in markup, element_id


@pytest.mark.parametrize("language", ["en", "ta"])
def test_each_painted_label_has_a_string_behind_it(language):
    words = table(language)
    for element_id, key in id_map().items():
        assert words.get(key, "").strip(), f"{element_id} -> {key} ({language})"


def test_the_status_filter_translates_its_own_options():
    """The sort dropdown had this loop; the status one did not, so Draft,
    Ready, Preparing, Needs attention and Cancelled sat in English inside a
    Tamil list."""
    js = navigation()
    fn = js[js.index("function navigationLabels"):]
    fn = fn[:fn.index("\nfunction ")]

    assert 'filterStatus' in fn
    for value in ("draft", "ready", "generating", "failed", "cancelled"):
        assert f"{value}: n." in fn, value


# ---------------------------------------------------------------------------
# One name for the list, everywhere it is named
# ---------------------------------------------------------------------------
#
# A kiosk and a shared counter machine both show every petition made on them,
# so "My petitions" named something the citizen in front of it does not own.
# The nav said one thing, the page heading another, and the home card a third.

ALL_PETITIONS = {"en": "All petitions", "ta": "\u0b85\u0ba9\u0bc8\u0ba4\u0bcd\u0ba4\u0bc1 \u0bae\u0ba9\u0bc1\u0b95\u0bcd\u0b95\u0bb3\u0bcd"}


@pytest.mark.parametrize("language", ["en", "ta"])
def test_the_nav_the_heading_and_the_home_card_agree(language):
    words = table(language)
    expected = ALL_PETITIONS[language]

    assert words["petitions"].lower() == expected.lower()
    assert words["petitionsTitle"] == expected
    assert words["homePetitionsTitle"] == expected


@pytest.mark.parametrize("language", ["en", "ta"])
def test_nothing_still_calls_them_the_citizens_own(language):
    """Checked across the whole table, not in the three places that were
    reported: the loading line, the error line and the empty state each said
    "your petitions" too."""
    stale = "my petitions" if language == "en" else "\u0b8e\u0ba9\u0ba4\u0bc1 \u0bae\u0ba9\u0bc1"
    for key, value in table(language).items():
        assert stale not in value.lower(), f"{key}: {value}"


def test_the_markup_defaults_say_it_too():
    """These are what a citizen reads for the moment before the table is
    applied, and all that is left if the script fails."""
    markup = page()

    assert "My Petitions" not in markup
    assert "My petitions" not in markup
    assert "your petitions" not in markup
    assert "your saved petitions" not in markup


def test_dictation_ui_is_bilingual_and_has_one_microphone():
    """Every word the dictation controls can say, in both languages.

    The Tamil here was lost to an encoding once already — the assertions
    read "????? ???????? ON", which no source file will ever contain, so
    the check passed nothing and failed loudly. Written as escapes now,
    which survive any editor.
    """
    source = app_js()

    # The two things the microphone beside the box can say.
    assert "Start voice typing" in source
    assert "குரல் தட்டச்சைத் தொடங்கு" in source
    # ...and while it is running.
    assert "Listening..." in source
    assert "கேட்கிறேன்..." in source
    # The header button now toggles SPOKEN RESPONSES, not a listening
    # session. Two microphones that both started recording was the
    # confusion this replaced.
    assert "Voice Responses ON" in source
    assert "குரல் பதில்கள் ON" in source

    # One socket, and it is the dictation one. The continuous listening
    # socket is gone, and a page that still opened it would be running the
    # behaviour this replaced alongside the replacement.
    assert "/ws/dictation/" in source
    assert "/ws/voice/" not in source


def test_the_citizen_is_told_what_to_do_when_voice_will_not_start():
    """Both failures name the way forward, because there always is one:
    the text box was never taken away."""
    source = app_js()

    for message in ("Microphone access is required for voice typing. "
                    "You can continue typing.",
                    "Voice typing is temporarily unavailable. "
                    "Please type your answer."):
        assert message in source, message
