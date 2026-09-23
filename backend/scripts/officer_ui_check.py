from pathlib import Path

from playwright.sync_api import expect, sync_playwright

out = Path("artifacts/officer")
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    for name, path in [
        ("login", "login"),
        ("dashboard", "dashboard"),
        ("review", "petitions/sample-1"),
        ("tamil", "petitions/sample-2"),
        ("acknowledgement", "acknowledgements/sample-ack"),
    ]:
        page.goto("http://127.0.0.1:8020/officer/" + path + "?preview=1")
        page.wait_for_timeout(350)
        page.screenshot(path=str(out / (name + ".png")), full_page=True)
        assert page.locator("h2").count() > 0
    for width in [768, 390]:
        page.set_viewport_size({"width": width, "height": 900})
        for name, path in [
            ("login", "login"),
            ("dashboard", "dashboard"),
            ("review", "petitions/sample-1"),
        ]:
            page.goto("http://127.0.0.1:8020/officer/" + path + "?preview=1")
            page.wait_for_timeout(200)
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), (width, name)
            page.screenshot(path=str(out / (name + "-" + str(width) + ".png")), full_page=True)
    page.goto("http://127.0.0.1:8020/officer/dashboard?preview=1")
    page.locator("#search").fill("Ravi")
    expect(page.locator("tbody tr")).to_have_count(1)
    page.locator("#clear").click()
    expect(page.locator("tbody tr")).to_have_count(6)
    page.locator("#acksTab").click()
    expect(page.locator("tbody")).to_contain_text("ACK-2026")
    page.screenshot(path=str(out / "acknowledgements-tab.png"), full_page=True)
    assert not errors, errors
    b.close()
print(
    "UI preview passed: screens, Tamil, search, clear filters, acknowledgements, 768/390px overflow checks"
)
