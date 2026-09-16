"""End-to-end acceptance run against a LIVE server over real HTTP.

Not a unit test. This starts nothing and mocks nothing: it talks to a running
service the same way a browser does, walks complete petitions in both languages,
and checks the files that come out.

    python scripts/acceptance.py --base http://127.0.0.1:8000

The provider recorder is the one piece that reaches inside the process, and it
has to: proving the Aadhaar never leaves the application means watching the
function that would put it on the wire. That check therefore runs in-process,
and says so in its output.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

AADHAAR = "234567890124"
AADHAAR_GROUPED = "2345 6789 0124"

ENGLISH = {
    "applicant_name": "Ravi Kumar",
    "age": "45",
    "mobile": "9876543210",
    "address": "12 Gandhi Street, Peelamedu, Coimbatore - 641004",
    "aadhaar": AADHAAR,
    "grievance": (
        "The street light outside my house has not worked since 12/03/2026.\n"
        "During the rains the road floods and is impassable.\n\n"
        "I complained twice at the panchayat office and paid Rs. 1,500 for a "
        'connection, but no receipt was issued. "Come tomorrow," they said.'
    ),
}

TAMIL = {
    "applicant_name": "ரவி குமார்",
    "age": "45",
    "mobile": "9876543210",
    "address": "12 காந்தி தெரு, பீளமேடு, கோயம்புத்தூர் - 641004",
    "aadhaar": AADHAAR,
    "grievance": (
        "எனது வீட்டின் முன் உள்ள தெருவிளக்கு மூன்று மாதங்களாக எரியவில்லை.\n"
        "மழைக்காலத்தில் சாலையில் நீர் தேங்கி நிற்கிறது.\n\n"
        "நான் இரண்டு முறை ஊராட்சி அலுவலகத்தில் புகார் அளித்தேன். இதுவரை நடவடிக்கை இல்லை."
    ),
}


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.rows.append((name, ok, detail))
        print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
        return ok

    @property
    def failed(self) -> list[str]:
        return [n for n, ok, _ in self.rows if not ok]


class Session:
    def __init__(self, client: httpx.AsyncClient, language: str) -> None:
        self.client = client
        self.language = language
        self.id: str | None = None
        self.view: dict = {}

    async def start(self) -> dict:
        r = await self.client.post("/api/sessions",
                                   json={"language": self.language, "text": ""})
        r.raise_for_status()
        self.view = r.json()
        self.id = self.view["session_id"]
        return self.view

    async def say(self, text: str) -> dict:
        r = await self.client.post(f"/api/sessions/{self.id}/message", json={"text": text})
        r.raise_for_status()
        self.view = r.json()
        return self.view

    async def post(self, action: str) -> dict:
        r = await self.client.post(f"/api/sessions/{self.id}/{action}")
        r.raise_for_status()
        self.view = r.json()
        return self.view

    def value(self, field: str):
        return next((f["value"] for f in self.view["collected"] if f["name"] == field), None)

    @property
    def status(self) -> str:
        return self.view["status"]


async def full_petition(client, report, language, answers, label) -> Session:
    print(f"\n{label}")
    s = Session(client, language)
    await s.start()
    report.check(f"{label}: first question is the name", s.view["awaiting"] == "applicant_name",
                 s.view["reply"][:60])

    for value in answers.values():
        await s.say(value)
    report.check(f"{label}: all five collected", s.view["status"] == "confirming",
                 f"status={s.status}")
    report.check(f"{label}: nothing generated before confirmation",
                 s.view["document"] is None and s.view["letter_text"] is None)
    report.check(f"{label}: read-back shows the printed Aadhaar",
                 AADHAAR_GROUPED in s.view["reply"])

    await s.post("confirm")
    report.check(f"{label}: petition generated", s.status == "ready", s.view.get("error") or "")
    report.check(f"{label}: verification passed",
                 bool(s.view["verification"] and s.view["verification"]["ok"]),
                 f"{(s.view.get('verification') or {}).get('checked')} values checked")
    report.check(f"{label}: grievance stored exactly as entered",
                 s.value("grievance") == answers["grievance"])
    return s


async def download(client, report, session: Session, out_dir: Path, label: str) -> dict:
    doc = session.view["document"] or {}
    files: dict[str, Path] = {}
    for kind, url in (("docx", doc.get("docx_url")), ("pdf", doc.get("pdf_url"))):
        if not url:
            report.check(f"{label}: {kind.upper()} available", False, "no URL in the session")
            continue
        r = await client.get(url)
        ok = r.status_code == 200 and len(r.content) > 5000
        path = out_dir / f"{label.lower().replace(' ', '-')}.{kind}"
        if ok:
            path.write_bytes(r.content)
            files[kind] = path
        report.check(f"{label}: {kind.upper()} downloads",
                     ok, f"HTTP {r.status_code}, {len(r.content):,} bytes -> {path.name}")
    return files


def check_document_text(report, docx: Path, answers: dict, label: str) -> None:
    from app.services.render import extract_docx_text

    produced = " ".join(extract_docx_text(docx).split())
    grievance = " ".join(answers["grievance"].split())
    report.check(f"{label}: grievance verbatim in the document", grievance in produced)
    report.check(f"{label}: Aadhaar printed grouped", AADHAAR_GROUPED in produced)
    report.check(f"{label}: name and address present",
                 answers["applicant_name"] in produced and answers["address"] in produced)


async def rejections(client, report) -> None:
    print("\nRejections")
    s = Session(client, "en")
    await s.start()
    await s.say(ENGLISH["applicant_name"])

    await s.say("200")
    report.check("invalid age rejected", s.view["awaiting"] == "age" and s.value("age") is None,
                 s.view["reply"][:70])
    await s.say("nine hundred")
    report.check("spoken scale word rejected as an age", s.value("age") is None,
                 s.view["reply"][:70])
    await s.say("45")

    await s.say("98765")
    report.check("short mobile rejected", s.value("mobile") is None, s.view["reply"][:70])
    await s.say("1234567890")
    report.check("mobile not starting 6-9 rejected", s.value("mobile") is None,
                 s.view["reply"][:70])
    await s.say(ENGLISH["mobile"])
    report.check("valid mobile then accepted", s.value("mobile") == ENGLISH["mobile"])

    await s.say("Coimbatore")
    report.check("one-word address rejected", s.value("address") is None, s.view["reply"][:70])
    await s.say(ENGLISH["address"])

    await s.say("2345 6789")
    report.check("short Aadhaar rejected with the digit count",
                 s.value("aadhaar") is None and "12 digits" in s.view["reply"],
                 s.view["reply"][:80])
    swapped = AADHAAR[:9] + AADHAAR[10] + AADHAAR[9] + AADHAAR[11]
    await s.say(swapped)
    report.check("transposed Aadhaar caught by the checksum",
                 s.value("aadhaar") is None and "check digit" in s.view["reply"],
                 s.view["reply"][:80])
    await s.say(AADHAAR)
    report.check("valid Aadhaar then accepted", s.value("aadhaar") == AADHAAR)


async def correction(client, report) -> None:
    print("\nConfirmation -> No -> change one field -> reconfirm")
    s = Session(client, "en")
    await s.start()
    for value in ENGLISH.values():
        await s.say(value)
    read_back = s.view["reply"]

    await s.say("no")
    report.check("'no' asks which detail, not the same list again",
                 s.view["reply"] != read_back and "which detail" in s.view["reply"].lower(),
                 s.view["reply"][:80])

    await s.say("the age is wrong")
    report.check("only the named field is cleared",
                 s.view["awaiting"] == "age" and s.value("age") is None
                 and s.value("applicant_name") == ENGLISH["applicant_name"]
                 and s.value("grievance") == ENGLISH["grievance"])

    await s.say("500")
    report.check("the replacement is validated too",
                 s.value("age") is None and "500" in s.view["reply"], s.view["reply"][:60])

    await s.say("31")
    report.check("a good replacement returns to the read-back",
                 s.value("age") == 31 and s.status == "confirming")
    entry = next((c for c in s.view["corrections"] if c["field"] == "age"), None)
    report.check("the change is recorded with both values",
                 entry is not None and entry["from"] == 45 and entry["to"] == 31, str(entry))

    await s.post("confirm")
    report.check("the corrected petition generates", s.status == "ready")


async def control(client, report) -> None:
    print("\nCancel and restart")
    s = Session(client, "en")
    await s.start()
    await s.say(ENGLISH["applicant_name"])
    await s.say("cancel")
    report.check("cancel stops the session", s.status == "cancelled")
    after = await s.say("Ravi Kumar")
    report.check("input after cancel does not resume", after["status"] == "cancelled")

    s2 = Session(client, "en")
    await s2.start()
    await s2.say(ENGLISH["applicant_name"])
    await s2.say(ENGLISH["age"])
    await s2.say("start over")
    report.check("restart clears the record",
                 s2.view["collected"] == [] and s2.view["awaiting"] == "applicant_name")
    await s2.say("Meena")
    report.check("and the conversation continues", s2.value("applicant_name") == "Meena")


async def recovery(client, report) -> None:
    print("\nSession recovery")
    s = Session(client, "en")
    await s.start()
    await s.say(ENGLISH["applicant_name"])
    await s.say(ENGLISH["age"])
    r = await client.get(f"/api/sessions/{s.id}")
    view = r.json()
    report.check("a reconnecting client gets the same record",
                 view["awaiting"] == "mobile"
                 and any(f["name"] == "applicant_name" for f in view["collected"]))


async def privacy_in_process(report) -> None:
    """Watch the function that puts bytes on the wire, for a whole petition."""
    print("\nAadhaar containment (in-process provider recorder)")
    from langgraph.checkpoint.memory import InMemorySaver

    import app.services.llm as llm_module
    from app.config import get_settings
    from app.domain.templates import the_template
    from app.graph.state import new_state
    from app.graph.workflow import build_graph

    sent: list[str] = []

    async def recorder(client, **kwargs):
        sent.append(f"{kwargs.get('system', '')}\n{kwargs.get('payload', '')}")
        raise RuntimeError("recorder: not forwarded")

    # Every provider function is intercepted, not just one: the point is to
    # watch whatever the configured chain would actually call. Gemini is what
    # this build uses, and the check must not quietly test a path it never takes.
    PROVIDERS = ("_ollama", "_gemini", "_anthropic", "_openai_compatible")
    original = {name: getattr(llm_module, name) for name in PROVIDERS}
    original_chain = llm_module.chain
    llm_module.chain = lambda *a, **k: ["gemini"]          # a provider IS reachable
    for name in PROVIDERS:
        setattr(llm_module, name, recorder)
    try:
        graph = build_graph().compile(checkpointer=InMemorySaver())
        config = {"configurable": {"thread_id": "privacy-probe"}}
        seed = new_state("privacy-probe", "en")
        seed["template_id"] = the_template().id
        seed["utterance"] = ""

        state = await graph.ainvoke(seed, config=config)
        for value in [ENGLISH["applicant_name"], ENGLISH["age"], ENGLISH["mobile"],
                      ENGLISH["address"], "2345 6789 0125", AADHAAR,
                      ENGLISH["grievance"], "yes"]:
            state = await graph.ainvoke({"utterance": value}, config=config)
    finally:
        llm_module.chain = original_chain
        for name, fn in original.items():
            setattr(llm_module, name, fn)

    wire = "\n".join(sent)
    report.check("Aadhaar never reached the provider", AADHAAR not in wire)
    report.check("grouped Aadhaar never reached the provider", AADHAAR_GROUPED not in wire)
    report.check("the rejected Aadhaar attempt never reached it either",
                 "2345 6789 0125" not in wire)
    # Requests, not calls: the recorder refuses every attempt, so the single
    # compose call fails over across each configured model and shows up once per
    # model. What matters is that every request that left is the compose call and
    # none of the seven collection turns produced one.
    compose_requests = [body for body in sent if "formal wording of a petition" in body]
    report.check("every request that left was the formal-wording call",
                 len(compose_requests) == len(sent),
                 f"{len(compose_requests)} of {len(sent)} request(s)")
    report.check("collection made no model call at all",
                 not (set(range(len(sent))) - set(range(len(compose_requests)))),
                 "every collection turn, zero requests")
    settings = get_settings()
    ceiling = max(1, len(settings.gemini_model_list or [1])) * max(1, len(settings.gemini_key_list or [1]))
    report.check("one logical compose call, retried across the configured models and keys",
                 1 <= len(sent) <= ceiling,
                 f"{len(sent)} attempt(s) for one call, ceiling {ceiling}")
    report.check("the petition still completed with the provider failing",
                 state["status"] == "ready", state.get("error") or "")


def rasterise(report, pdf: Path, label: str) -> None:
    try:
        import pymupdf
    except ImportError:
        report.check(f"{label}: PDF rasterised for visual check", False,
                     "pip install -r requirements-dev.txt")
        return
    document = pymupdf.open(pdf)
    pages = []
    for number in range(document.page_count):
        image = pdf.with_name(f"{pdf.stem}-p{number + 1}.png")
        document[number].get_pixmap(dpi=140).save(str(image))
        pages.append(image.name)
    report.check(f"{label}: PDF rasterised for visual check", bool(pages), ", ".join(pages))


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument("--out", type=Path, default=Path("var/acceptance"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    report = Report()
    async with httpx.AsyncClient(base_url=args.base, timeout=120) as client:
        print("Service")
        health = (await client.get("/api/health")).json()
        report.check("backend responds", health.get("ok") is True)
        report.check("test page served", (await client.get("/")).status_code == 200)
        print(f"  engine: {health['documents']['note']}")
        print(f"  model:  {health['language_model']['detail']}")

        english = await full_petition(client, report, "en", ENGLISH, "English")
        english_files = await download(client, report, english, args.out, "English")
        if "docx" in english_files:
            check_document_text(report, english_files["docx"], ENGLISH, "English")

        tamil = await full_petition(client, report, "ta", TAMIL, "Tamil")
        report.check("Tamil: assembled without a translator",
                     not any("translat" in w.lower() for w in tamil.view["warnings"]),
                     "; ".join(tamil.view["warnings"]) or "no warnings")
        report.check("Tamil: petition is in Tamil",
                     "அனுப்புநர்," in (tamil.view["letter_text"] or "")
                     and "From," not in (tamil.view["letter_text"] or ""))
        tamil_files = await download(client, report, tamil, args.out, "Tamil")
        if "docx" in tamil_files:
            check_document_text(report, tamil_files["docx"], TAMIL, "Tamil")
        if "pdf" in tamil_files:
            rasterise(report, tamil_files["pdf"], "Tamil")

        await rejections(client, report)
        await correction(client, report)
        await control(client, report)
        await recovery(client, report)

    await privacy_in_process(report)

    print("\n" + "=" * 70)
    passed = len(report.rows) - len(report.failed)
    print(f"{passed}/{len(report.rows)} checks passed")
    for name in report.failed:
        print(f"  FAILED: {name}")
    print(f"\nArtefacts in {args.out.resolve()}")
    return 1 if report.failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
