"""Exercise real browser flows against an isolated running development server.

Run: python scripts/ui_acceptance.py --url http://127.0.0.1:8011
Use a temporary DATA_DIR and disabled external providers on the target server.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def run(url: str, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url)
        expect(page.locator(".turn.assistant")).to_have_count(1)
        page.evaluate("document.fonts.ready")
        page.screenshot(path=str(output / "01-start-desktop.png"), full_page=True)

        def answer(text: str, awaiting: str | None = None, status: str = "collecting") -> dict:
            page.locator("#text").fill(text)
            with page.expect_response(lambda r: r.url.endswith("/message")) as response:
                page.locator("#send").click()
            state = response.value.json()
            assert state["status"] == status, state.get("reply")
            if awaiting:
                assert state["awaiting"] == awaiting, state.get("reply")
            expect(page.locator("#text")).to_have_value("")
            return state

        answer("Ravi Kumar", "age")
        # Numeric validation must explain errors without advancing the interview.
        answer("999", "age")
        expect(page.locator(".field-err").first).to_be_visible()
        sid = page.evaluate("sid")
        page.reload()
        page.wait_for_function("view?.awaiting === 'age'")
        assert page.evaluate("sid") == sid
        expect(page.locator("#citizenFields")).to_contain_text("Ravi Kumar")

        # A failed request leaves the answer intact and requires recovery first.
        page.route("**/message", lambda route: route.abort())
        page.locator("#text").fill("45")
        page.locator("#send").click()
        expect(page.locator("#connectionBanner")).to_be_visible()
        expect(page.locator("#text")).to_have_value("45")
        expect(page.locator("#send")).to_be_disabled()
        page.unroute("**/message")
        page.locator("#retryConnection").click()
        expect(page.locator("#connectionBanner")).to_be_hidden()
        answer("45", "mobile")
        answer("9876543210", "address")
        answer("12 Gandhi Street, Peelamedu, Coimbatore", "aadhaar")
        answer("234567890124", "grievance")
        grievance = "The street light outside my house has not worked for three months. Please repair it."
        state = answer(grievance, status="confirming")
        assert state["progress"]["answered"] == 6
        expect(page.locator("#log")).not_to_contain_text("234567890124")
        page.screenshot(path=str(output / "02-review-desktop.png"), full_page=True)

        # Rejected edits remain visible and block confirmation until fixed.
        page.locator('[data-edit="age"]').click()
        page.locator('[data-editform="age"] [name="v"]').fill("999")
        with page.expect_response(lambda r: r.url.endswith("/field")) as response:
            page.locator('[data-editform="age"] button[type="submit"]').click()
        assert "age" in response.value.json()["field_errors"]
        expect(page.locator("#confirm")).to_be_hidden()
        page.locator('[data-editform="age"] [name="v"]').fill("46")
        with page.expect_response(lambda r: r.url.endswith("/field")):
            page.locator('[data-editform="age"] button[type="submit"]').click()
        expect(page.locator("#confirm")).to_be_visible()
        with page.expect_response(lambda r: r.url.endswith("/confirm"), timeout=120000) as response:
            page.locator("#confirm").click()
        ready = response.value.json()
        assert ready["status"] == "ready", ready.get("error")
        expect(page.locator("#docCard")).to_be_visible()
        expect(page.locator("#letter")).to_contain_text(grievance)
        assert page.request.get(url + ready["document"]["docx_url"]).body().startswith(b"PK")
        page.screenshot(path=str(output / "03-ready-desktop.png"), full_page=True)

        page.reload()
        expect(page.locator("#docCard")).to_be_visible()
        assert page.evaluate("sid") == sid
        page.locator('[data-edit="age"]').click()
        page.locator('[data-editform="age"] [name="v"]').fill("47")
        with page.expect_response(lambda r: r.url.endswith("/field")) as response:
            page.locator('[data-editform="age"] button[type="submit"]').click()
        assert response.value.json()["document"] is None
        expect(page.locator("#docCard")).to_be_hidden()
        assert page.request.get(url + ready["document"]["docx_url"]).status == 409

        # Language switching is explicit; keeping a petition retains its language.
        page.locator("#lang").select_option("ta")
        expect(page.locator('[role="dialog"]')).to_be_visible()
        page.keyboard.press("Escape")
        expect(page.locator("#lang")).to_have_value("en")
        page.locator("#lang").select_option("ta")
        page.locator("[data-go]").click()
        page.wait_for_function("view?.language === 'ta' && !requestPending")
        page.set_viewport_size({"width": 390, "height": 844})
        page.screenshot(path=str(output / "04-start-tamil-mobile.png"), full_page=True)
        answer("ரவி குமார்", "age")
        answer("45", "mobile")
        answer("9876543210", "address")
        answer("12 காந்தி தெரு, பீளமேடு, கோயம்புத்தூர்", "aadhaar")
        answer("234567890124", "grievance")
        answer("எனது வீட்டின் முன் உள்ள தெருவிளக்கு மூன்று மாதங்களாக எரியவில்லை.", status="confirming")
        page.locator("#detailsToggle").click()
        expect(page.locator("#detailsPanel")).to_be_visible()
        page.screenshot(path=str(output / "05-review-tamil-mobile.png"), full_page=True)
        with page.expect_response(lambda r: r.url.endswith("/confirm"), timeout=120000) as response:
            page.locator("#confirm").click()
        assert response.value.json()["status"] == "ready"
        expect(page.locator("#letter")).to_contain_text("தெருவிளக்கு")
        for width, height in [(390, 844), (768, 1024), (1440, 1000)]:
            page.set_viewport_size({"width": width, "height": height})
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), f"Overflow at {width}"
            page.screenshot(path=str(output / f"06-ready-tamil-{width}.png"), full_page=True)

        # Start-over truly resets transcript and inputs, and voice-off is actionable.
        page.locator("#new").click()
        page.wait_for_function("view?.progress.answered === 0 && !requestPending")
        expect(page.locator(".turn.assistant")).to_have_count(1)
        page.locator("#mic").click()
        expect(page.locator("#voiceError")).to_be_visible()
        page.locator("#voiceDismiss").click()
        expect(page.locator("#text")).to_be_enabled()
        assert not errors, errors
        browser.close()
    print("Browser acceptance passed: English/Tamil, recovery, failed sends, validation, corrections, downloads, responsive layout, voice unavailable.")
    print(f"Screenshots: {output.resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8011")
    parser.add_argument("--output", type=Path, default=Path("var/qa-upgrade"))
    args = parser.parse_args()
    run(args.url.rstrip("/"), args.output)
