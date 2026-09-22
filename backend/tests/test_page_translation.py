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
    ("homePetitionsTitle", "எனது மனுக்கள்"),
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


def test_the_two_microphones_do_different_things():
    """The one in the header runs the hands-free conversation; the one
    beside the text box dictates into it. They were the same handler, and a
    citizen who wanted to say one sentence instead of typing it got the
    whole form read aloud."""
    js = app_js()

    assert re.search(r'\$\("mic"\)\.onclick\s*=\s*toggleVoice', js)
    assert re.search(r'\$\("micInline"\)\.onclick\s*=\s*toggleDictation', js)


def test_dictation_asks_the_server_for_dictation():
    js = app_js()

    assert 'startVoice("dictation")' in js
    assert "mode: voice.mode" in js


def test_a_dictated_transcript_goes_to_the_box_not_to_a_turn():
    js = app_js()
    handler = js[js.index('case "stt.final":'):]
    handler = handler[:handler.index('case "state":')]

    assert 'voice.mode === "dictation"' in handler
    assert "writeIntoTheBox" in handler
    # And it stops there: the conversation path must not also run.
    assert handler.index("writeIntoTheBox") < handler.index("VOICE.PROCESSING")


def test_dictation_appends_rather_than_replacing():
    """A second press adds a sentence to what is already there. Replacing
    would wipe a half-typed answer the moment somebody reached for the
    microphone to finish it."""
    js = app_js()
    fn = js[js.index("function writeIntoTheBox"):]
    fn = fn[:fn.index("\n}") + 2]

    assert "existing ?" in fn
    assert "box.maxLength" in fn, "the box has a hard cap and setting .value walks past it"
