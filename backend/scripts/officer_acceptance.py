"""Isolated browser acceptance: real auth, records, documents and reviews."""

import asyncio
import os
import secrets
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

import httpx
from playwright.sync_api import expect, sync_playwright

root = Path(__file__).resolve().parents[1]
os.environ.update(
    DATA_DIR=tempfile.mkdtemp(prefix="officer-acceptance-"),
    LLM_PROVIDER="off",
    ALLOW_EXTERNAL_AI="false",
    PDF_ENGINE="off",
    STREAM_ASR_PROVIDER="off",
    TTS_PROVIDER="off",
    KNOWLEDGE_ENABLED="false",
)
sys.path.insert(0, str(root))
from app.config import get_settings
from app.graph.state import new_state
from app.graph.workflow import workflow_lifespan
from app.services.officer_store import provision
from app.services.render import render_docx
from app.services import attachment_store

password = secrets.token_urlsafe(24)
provision("ui-reviewer", "Acceptance Officer", password)
sid = str(uuid.uuid4())
tamil_sid = str(uuid.uuid4())
settings = get_settings()


async def seed():
    async with workflow_lifespan(settings) as workflow:
        for identity, language, name, subject, body in [
            (
                sid,
                "en",
                "Sample Citizen",
                "Repair street lights",
                "The street light is broken. Please repair it.",
            ),
            (
                tamil_sid,
                "ta",
                "மீனா ராஜன்",
                "குடிநீர் விநியோகம்",
                "குடிநீர் விநியோகம் சீராக இல்லை. சீரமைக்க வேண்டுகிறேன்.",
            ),
        ]:
            letter = f"From\n{name}\nTest Street\n\nTo\nThe concerned officer\n\nDate: 23 September 2026\nPlace: Test town\n\nSubject: {subject}\n\n{body}\n\nThank you,\n{name}"
            docx = settings.document_dir / (identity + ".docx")
            docx.parent.mkdir(parents=True, exist_ok=True)
            render_docx(letter, docx, reference="TEST-" + language, settings=settings)
            attachment = attachment_store.save(
                session_id=identity,
                filename="receipt.txt",
                content=b"Acknowledgement: ACK-TEST-42\nReceived for review.",
                content_type="text/plain",
            ).attachment
            attachment.kind = "acknowledgement"
            attachment.confirmed = True
            attachment.extracted = {
                "reference_number": {"value": "ACK-TEST-42"},
                "submitted_on": {"value": "2026-09-23"},
            }
            state = {
                **new_state(identity, language),
                "fields": {"applicant_name": name, "address": "Test Street", "grievance": body},
                "status": "ready",
                "confirmed": True,
                "letter_text": letter,
                "document": {"reference": "TEST-" + language, "docx": str(docx)},
                "verification": {"ok": True},
                "attachments": [attachment.as_dict()],
            }
            await workflow._compiled.aupdate_state(
                workflow.config(identity), state, as_node="verify"
            )


asyncio.run(seed())
url = "http://127.0.0.1:8022"
log = Path(os.environ["DATA_DIR"]) / "server.log"
with log.open("w") as stream:
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8022"],
        cwd=root,
        env=os.environ,
        stdout=stream,
        stderr=stream,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    try:
        for _ in range(100):
            try:
                if httpx.get(url + "/api/health").status_code == 200:
                    break
            except httpx.ConnectError:
                pass
            time.sleep(0.1)
        out = root.parent / "artifacts" / "officer"
        out.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.goto(url)
            page.locator(".officer-login-link").click()
            expect(page).to_have_url(url + "/officer/login")
            page.screenshot(path=str(out / "live-login.png"), full_page=True)
            page.locator("#username").fill("ui-reviewer")
            page.locator("#password").fill("wrong")
            page.locator("[type=submit]").click()
            expect(page.locator("#loginError")).to_contain_text("Invalid")
            page.locator("#password").fill(password)
            page.locator("[type=submit]").click()
            expect(page.locator("tbody tr")).to_have_count(2)
            page.locator("#language").select_option(label="Tamil")
            expect(page.locator("tbody tr")).to_have_count(1)
            page.locator("#clear").click()
            page.locator("#search").fill("TEST-en")
            expect(page.locator("tbody tr")).to_have_count(1)
            page.get_by_role("link", name="View TEST-en").click()
            expect(page.locator(".letter-text")).to_contain_text("Please repair it.")
            with page.expect_download() as dl:
                page.get_by_role("link", name="Download Word").click()
            assert dl.value.suggested_filename.endswith(".docx")
            page.locator("#note").fill("Internal test review")
            page.locator("#reviewStatus").select_option("Under Review")
            page.get_by_role("button", name="Save review").click()
            expect(page.locator("#savedNotes")).to_contain_text("Internal test review")
            page.reload()
            expect(page.locator("#savedNotes")).to_contain_text("Internal test review")
            page.screenshot(path=str(out / "live-review.png"), full_page=True)
            page.goto(url + "/officer/petitions/" + tamil_sid)
            expect(page.locator(".letter-text")).to_contain_text("குடிநீர்")
            for width in [1440, 768, 390]:
                page.set_viewport_size({"width": width, "height": 950})
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
                page.screenshot(path=str(out / f"live-tamil-{width}.png"), full_page=True)
            page.goto(url + "/officer/dashboard")
            page.locator("#acksTab").click()
            expect(page.locator("tbody tr")).to_have_count(2)
            page.get_by_role("link", name="View ACK-TEST-42").first.click()
            expect(page.locator(".paper")).to_contain_text("ACK-TEST-42")
            assert page.request.get(url + "/api/petitions").json()["items"] == []
            page.locator("#logout").click()
            expect(page).to_have_url(url + "/officer/login")
            page.goto(url + "/officer/dashboard")
            expect(page).to_have_url(url + "/officer/login")
            assert page.request.get(url + "/api/officer/petitions").status == 401
            for width in [1440, 768, 390]:
                page.set_viewport_size({"width": width, "height": 950})
                page.goto(url)
                expect(page.locator(".officer-login-link")).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth<=innerWidth"), (
                    "home",
                    width,
                )
                page.screenshot(path=str(out / f"home-{width}.png"), full_page=True)
            assert not errors, errors
            browser.close()
        print(
            "PASS: home entry, invalid/valid login, real lists, filters, review persistence, Word download, attachment receipt, Tamil, responsive layout, logout and route/API protection"
        )
    finally:
        process.terminate()
        process.wait(timeout=15)
