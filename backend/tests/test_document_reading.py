"""The finished petition is readable at its own length.

THE BUG THIS EXISTS FOR. The workspace is a fixed-height grid, which is
right for a conversation — the newest message is at the bottom and nothing
above it needs to be on screen. Applied to a two-page letter on a laptop it
left roughly 274px for the paper: about eleven lines of forty, behind a
nested scrollbar, inside a page that was already scrolling. A citizen
checking their own address had to scroll a small box inside a big one to
find it.

WHAT IS AND IS NOT CHECKED HERE. These are assertions about CSS text, which
cannot prove a layout renders — only a browser does that. What they can do
is stop the rules quietly going back: a later edit that restores
`overflow-y:auto` on the paper, or drops the sticky columns and leaves
`align-items:start`, puts the letter back in the hole or stretches the chat
panel to the height of a two-page document. Both are silent in every other
test in this suite.
"""

from __future__ import annotations

import pathlib
import re

CSS = pathlib.Path("app/static/app.css")


def stylesheet() -> str:
    return CSS.read_text(encoding="utf-8")


def without_comments() -> str:
    return re.sub(r"/\*.*?\*/", "", stylesheet(), flags=re.S)


def reading_block() -> str:
    """The wide-layout rules for a finished petition."""
    css = without_comments()
    start = css.index("@media(min-width:1181px)")
    depth, end = 0, start
    for i in range(start, len(css)):
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    return css[start:end]


def test_the_rules_exist_at_all():
    """A guard on the guard: if the block is renamed, everything below
    passes by finding nothing."""
    block = reading_block()
    assert "main.workspace.done" in block
    assert len(block) > 200


def test_the_paper_is_not_a_scrolling_box():
    """The whole point. A document shown through a window of its own is a
    document read a dozen lines at a time."""
    block = reading_block()

    assert "overflow:visible" in block
    assert re.search(r"\.paper-wrap\{[^}]*overflow-y:auto", block) is None


def test_the_grid_stops_forcing_one_screen():
    block = reading_block()

    assert "height:auto" in block
    assert "align-items:start" in block


def test_the_other_columns_do_not_stretch_to_the_letter():
    """`align-items:start` without this leaves the conversation and the
    details panel at their content height beside a two-page document, with
    a screen of empty page under each."""
    block = reading_block()

    assert "position:sticky" in block
    assert block.count("height:calc(100dvh") >= 1


def test_the_sticky_columns_clear_the_header():
    """The header is `position:sticky; top:0`. A column stuck to the top of
    the viewport sits behind it."""
    block = reading_block()

    assert "top:calc(var(--header-h)" in block


def test_none_of_it_applies_while_a_change_is_being_drafted():
    """Both classes are present while a revision is drafted against an
    existing petition, and the document is hidden behind the animation
    then. Sizing the grid to a document nobody can see makes the page jump
    as the animation ends."""
    block = reading_block()
    targets = re.findall(r"main\.workspace\.done(?:[^ ,{]*)", block)

    assert targets, block
    for target in targets:
        assert target.startswith("main.workspace.done:not(.generating)"), target


def test_the_narrow_layout_is_left_alone():
    """Below 1180px the columns stack and each already has the full width.
    The stacked rules keep their own max-height, and they must keep the
    scrolling paper that goes with it."""
    css = without_comments()
    narrow = css[css.index("@media(max-width:1180px)"):]

    assert "max-height:calc(100dvh - 160px)" in narrow


def test_the_base_rule_still_scrolls_for_the_conversation():
    """Unchanged for every state that is not a finished petition: the
    drafting panel and the mid-conversation document still live inside the
    fixed-height grid."""
    css = without_comments()
    base = re.search(r"\.paper-wrap\{([^}]*)\}", css).group(1)

    assert "overflow-y:auto" in base
    assert "flex:1" in base


def test_the_stylesheet_is_still_balanced():
    """A media block left open takes every rule after it with it."""
    css = without_comments()

    assert css.count("{") == css.count("}")
