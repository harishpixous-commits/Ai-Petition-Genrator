"""The headers that stand between injected markup and a citizen's browser.

WHY THESE ARE TESTED BY BEHAVIOUR rather than by reading the middleware. A
Content Security Policy is a string, and a string with a typo in it is still a
string: `script-src 'self'` misspelled is silently ignored by the browser and
the page keeps working perfectly, with no protection at all. Nothing fails.

So each clause that is load-bearing is asserted by name here, and the two that
would quietly undo the whole policy — `'unsafe-inline'` and `'unsafe-eval'` in
`script-src` — are asserted ABSENT.

WHAT MAKES THE STRICT POLICY POSSIBLE, and what would break it: the pages
carry no inline <script>, no on*= handlers and no external hosts. The last
test holds that, because the policy and the markup have to stay in agreement
and the markup is what will drift.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

STATIC = Path(__file__).resolve().parent.parent / "app" / "static"
PAGES = ("index.html", "officer.html", "operator.html")


@pytest.fixture
def client():
    from app.main import create_app

    with TestClient(create_app()) as test_client:
        yield test_client


def policy(response) -> dict[str, str]:
    """The CSP parsed into directive -> value."""
    header = response.headers.get("Content-Security-Policy", "")
    out = {}
    for part in header.split(";"):
        part = part.strip()
        if not part:
            continue
        name, _, value = part.partition(" ")
        out[name] = value.strip()
    return out


class TestThePolicyIsPresentAndStrict:
    def test_every_page_carries_a_policy(self, client):
        for path in ("/", "/officer/login"):
            response = client.get(path)
            assert response.headers.get("Content-Security-Policy"), path

    def test_scripts_may_only_come_from_this_application(self, client):
        """THE CLAUSE THAT MATTERS. Rendering is almost entirely innerHTML
        against a hand-rolled escaper, so markup that got through would
        otherwise execute."""
        directives = policy(client.get("/"))
        assert directives["script-src"] == "'self'", directives.get("script-src")

    def test_no_unsafe_escape_hatch_in_script_src(self, client):
        """Either of these turns the policy off for scripts while leaving it
        looking like a policy."""
        script_src = policy(client.get("/"))["script-src"]
        assert "'unsafe-inline'" not in script_src
        assert "'unsafe-eval'" not in script_src
        assert "*" not in script_src

    @pytest.mark.parametrize("directive,expected", [
        ("default-src", "'self'"),
        ("object-src", "'none'"),
        ("base-uri", "'self'"),
        ("form-action", "'self'"),
        ("frame-ancestors", "'none'"),
        ("connect-src", "'self'"),
        ("font-src", "'self'"),
    ])
    def test_the_other_directives_are_locked_down(self, client, directive, expected):
        assert policy(client.get("/"))[directive] == expected

    def test_what_the_page_genuinely_needs_is_allowed(self, client):
        """A policy that breaks the application gets removed by whoever is on
        call, so the concessions matter as much as the restrictions.

        The spoken read-back builds an Audio element from a Blob URL, and
        previews inline small images as data URIs.
        """
        directives = policy(client.get("/"))
        assert "blob:" in directives["media-src"]
        assert "data:" in directives["img-src"]

    def test_styles_are_self_hosted_and_inline_markup_is_absent(self, client):
        """Every page and the print view remain under the strict same-origin
        stylesheet policy."""
        directives = policy(client.get("/"))
        assert directives["style-src"] == "'self'"
        assert "'unsafe-inline'" not in directives["script-src"]
        for page in PAGES:
            html = (STATIC / page).read_text(encoding="utf-8")
            assert not re.search(r"<script\b(?![^>]*\bsrc\s*=)", html, re.I), page
            assert not re.search(r"\sstyle\s*=", html, re.I), page
            assert not re.search(r"<style\b", html, re.I), page


class TestTheOtherHeaders:
    def test_the_microphone_is_the_only_capability_asked_for(self, client):
        permissions = client.get("/").headers.get("Permissions-Policy", "")
        assert "microphone=(self)" in permissions
        assert "camera=()" in permissions
        assert "geolocation=()" in permissions

    def test_sniffing_and_referrers_are_still_handled(self, client):
        headers = client.get("/").headers
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["Referrer-Policy"] == "no-referrer"

    def test_framing_is_refused(self, client):
        assert client.get("/").headers.get("X-Frame-Options") == "DENY"


class TestTheStricterPolicyOnUntrustedPreviewsSurvives:
    """Two endpoints render a document a citizen supplied and send their own
    `sandbox; default-src 'none'`. The blanket policy must not replace it with
    something more permissive."""

    def test_the_blanket_policy_does_not_overwrite_a_stricter_one(self):
        from app.main import create_app

        app = create_app()
        # Asserted on the mechanism rather than by reaching the endpoint,
        # which needs a session and an uploaded file: the middleware uses
        # setdefault, so a handler that already set the header keeps it.
        source = Path(__file__).resolve().parent.parent / "app" / "main.py"
        body = source.read_text(encoding="utf-8")
        assert 'setdefault("Content-Security-Policy"' in body, (
            "the middleware must not overwrite a handler's stricter policy")
        assert app is not None


class TestTheMarkupStaysCompatibleWithThePolicy:
    """The policy and the pages have to agree, and it is the pages that drift.

    A developer adding one `onclick=` or one inline <script> would not see a
    failure in the browser they were testing in until the feature silently
    stopped working under the policy.
    """

    @pytest.mark.parametrize("page", PAGES)
    def test_no_inline_script_blocks(self, page):
        html = (STATIC / page).read_text(encoding="utf-8")
        inline = [b for b in re.findall(
            r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S) if b.strip()]
        assert not inline, (
            f"{page} has an inline <script>; it will not run under "
            f"script-src 'self'. Move it to a file in app/static/.")

    @pytest.mark.parametrize("page", PAGES)
    def test_no_inline_event_handlers(self, page):
        html = (STATIC / page).read_text(encoding="utf-8")
        handlers = re.findall(r"\son[a-z]+\s*=", html)
        assert not handlers, (
            f"{page} has inline handler(s) {handlers[:3]}; they will not fire "
            f"under script-src 'self'. Attach them with addEventListener.")

    @pytest.mark.parametrize("page", PAGES)
    def test_no_resource_is_loaded_from_another_host(self, page):
        """`default-src 'self'` blocks a third-party script, stylesheet, font
        or image, and a government service should not be making a citizen's
        browser talk to a third party anyway.

        A PLAIN LINK IS NOT A RESOURCE LOAD and is deliberately not flagged.
        CSP governs what the page FETCHES, not where it can send somebody who
        clicks: `<a href="https://...">` in the footer is unaffected by any
        directive here. An earlier version of this test flagged it, which
        would have had somebody removing a working link to satisfy a rule that
        was never about links.
        """
        html = (STATIC / page).read_text(encoding="utf-8")
        loads = re.findall(r'\ssrc="(https?://[^"]+)"', html)
        loads += re.findall(r'<link\b[^>]*\bhref="(https?://[^"]+)"', html)
        assert not loads, f"{page} loads resources from {loads}"
