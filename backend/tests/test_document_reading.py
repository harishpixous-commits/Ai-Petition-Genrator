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

import pytest

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


# ---------------------------------------------------------------------------
# What actually comes out of the printer
# ---------------------------------------------------------------------------

def print_block() -> str:
    css = without_comments()
    start = css.index("@media print")
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


class TestOnlyThePetitionIsPrinted:
    """A citizen printed their petition and got the browser's date and URL
    across the top, the page title beside them, and the developer's logo at
    the foot of the letter. None of that belongs on a document handed across
    a counter."""

    def test_there_is_one_set_of_print_rules(self):
        """There were two, and the second re-showed children the first had
        hidden — which is how the footer survived."""
        assert without_comments().count("@media print") == 1

    def test_the_browser_draws_no_header_or_footer(self):
        """The date, the page title, the URL and "1/2" are the browser's, and
        it draws them inside the page margin. A page with no margin has
        nowhere to draw them."""
        block = print_block()

        assert "@page" in block
        assert re.search(r"@page\{[^}]*margin:0", block.replace(" ", "")), block

    def test_the_margins_move_onto_the_paper(self):
        """`@page{margin:0}` would otherwise print a petition with its text
        against the edge of the sheet."""
        block = print_block()
        paper = re.search(r"\.paper\{([^}]*)\}", block)

        assert paper, block
        assert "mm" in paper.group(1), paper.group(1)

    def test_it_is_a4(self):
        assert "size:A4" in print_block().replace(" ", "")

    def test_nothing_is_shown_unless_it_leads_to_the_letter(self):
        """Written as a chain, not a list of things to hide. The list rotted:
        every panel added since — the voice bar, the answer card, the kiosk
        screens, the site footer with its logo — was a thing somebody had to
        remember to add, and the footer was the one nobody did."""
        block = print_block().replace(" ", "").replace("\n", "")

        assert "body>*" in block, "the top level is not hidden by default"
        assert "#docCard>*" in block
        assert "body>#mainContent" in block, "and the path back is not re-opened"

    def test_the_developers_logo_is_not_on_the_document(self):
        """The specific thing reported. It is excluded by the chain rather
        than by name, so the next thing added to the page is excluded too."""
        block = print_block().replace(" ", "").replace("\n", "")

        # Not named anywhere — and that is the point.
        assert "site-footer" not in block
        # But its parent level is hidden, so it cannot print.
        assert "body>*" in block

    @pytest.mark.parametrize("panel", [
        ".voicebar", ".answer-check", ".dictation", ".kiosk-done",
        ".kiosk-welcome", ".doc-toolbar", ".stepper",
    ])
    def test_no_interface_panel_can_reach_the_page(self, panel):
        """None of these are named in the print rules. All of them sit below
        a level the chain hides, which is why naming them is unnecessary."""
        assert panel not in print_block()
