# Officer portal

The officer module extends the existing FastAPI application. The citizen design, workflow, documents and checkpoint database remain in place.

## Screens

- `/officer/login`: username/password, password visibility and citizen return link.
- `/officer/dashboard`: six counts, petition/acknowledgement tabs, search, status/department/category/language/date filters and pagination.
- `/officer/petitions/{session_id}`: original letter, existing PDF/Word downloads, print, extractive grievance summary, grounded knowledge findings and citations, attachments, persistent notes and status.
- `/officer/acknowledgements/{id}`: existing acknowledgement attachment metadata, original receipt link and linked petition.

Append `?preview=1` to officer page URLs for a clearly labelled, fictional design preview. Preview mode never calls the officer data API or grants authenticated access. Sample file downloads are disabled because those files do not exist.

## Provision access

From the `backend` directory, with the same `DATA_DIR` as the running service:

```powershell
python -m scripts.create_officer reviewer --name "Review Officer"
```

The command prompts twice for a password of at least 12 characters. It stores a salted scrypt hash, never the password. Re-running for the same username resets its password and revokes its sessions. There are no default credentials. All provisioned accounts have office-wide review access to this deployment; department-specific account scopes are not implemented.

Set `OFFICER_PASSWORD` in the environment to skip the prompt. That is for automation only — it is how the workflow below passes a GitHub secret to the container without the value reaching a command line, a log or a shell history.

### On the deployed server

The account lives wherever the database lives, which on a server is the Docker volume. **An account created on a laptop does not work against the deployed site**, and the reverse. Provisioning there is a separate act:

GitHub → Actions → **Create Officer Account** → Run workflow, giving a username and a display name. The password comes from the `OFFICER_PASSWORD` secret on the `production` environment, so it is never typed into the form and never printed. Set it first under Settings → Environments → production → Add environment secret.

With shell access to the host, the same thing directly:

```bash
docker exec -e OFFICER_PASSWORD='…' -it ai-petition-generator   python scripts/create_officer.py reviewer --name "Review Officer"
```

**The first account changes citizen behaviour.** While none exists, every browser can see every saved petition. From the first account onward, sessions are scoped to the browser cookie that created them: a citizen sees only their own petitions and the rest are reachable through this portal alone. Nothing is deleted. That is the intended production posture, and creating the first account is the switch that turns it on.

Serve through the existing HTTPS reverse proxy in production. Sessions use HttpOnly, SameSite=Strict cookies, Secure on HTTPS, eight-hour absolute expiry, server-side revocation, and a persistent limit of ten failed login attempts per IP per 15 minutes. Writes check the request origin. The existing infrastructure operator token remains separate and does not grant petition-review access.

## Records and privacy

Petitions are read from the existing checkpoint catalogue, including drafts; records are not copied. `officer.sqlite` holds accounts, hashed session tokens, notes, review status/audit and browser ownership only. Back up it with the existing data directory. Review status is separate from the citizen document-generation status. Deleting a petition also removes its officer notes and review metadata.

Provisioning the first officer account enables browser ownership enforcement for citizen catalogue, session APIs, deletion and voice connections. Existing petitions without browser ownership remain visible to officers. Citizens cannot reopen those legacy records after office mode is enabled. New petitions belong to the browser's HttpOnly ownership cookie; clearing that cookie loses citizen access, but the officer retains access. This preserves the original shared-machine behavior on installations with no provisioned officer account.

Acknowledgements are existing attachments classified as acknowledgements; no new official receipt is issued. Extracted reference/date/department fields are shown only when citizen-confirmed. Unconfirmed receipts show Needs Review. The original document remains available for officer inspection.

## Knowledge and documents

The module uses the existing saved analysis and knowledge service. Only findings carrying an official/departmental source with an excerpt and document title appear. Unresolved source conflicts suppress recommendations. Citations include available title/date/section/page/excerpt and a safe HTTP(S) source link. Empty or unavailable knowledge shows Verification required / Not identified; no law or authority is fabricated. There is no automatic government routing or decision.

The overview is extractive (selected sentences from the recorded grievance), not a newly generated legal interpretation. Full original text is always visible. Existing document endpoints supply generated files; PDF remains unavailable when the installation has no PDF engine or no generated PDF. Print remains available.

## Verification

```powershell
python -m pytest tests/test_officer.py tests/test_officer_layout.py tests/test_petition_catalog.py tests/test_petition_removal.py tests/test_regressions.py
python scripts/officer_acceptance.py
```

`test_officer_layout.py` holds the review page's layout and print rules, and
the redirect that keeps a signed-out visitor off the officer screens.

The browser acceptance script provisions a temporary account and fictional English/Tamil checkpoints in an isolated temporary data directory, starts its own server, tests real login, filters, downloads, notes, acknowledgements, responsive widths and logout, saves screenshots under `artifacts/officer`, and stops its server. It does not use production accounts or data. Playwright/Chromium must be installed.

One thing a test over CSS text cannot prove is where the page actually puts
things. `scripts/officer_scroll_check.py` drives a real browser against the
preview server and measures it: that the petition is still on screen when the
officer reaches the last card on the right, that the preview's toolbar is not
tucked under the page header, and that the narrow layout puts the petition
first and never scrolls sideways. It is what caught the review page placing
the petition 105px above the top of the viewport while the officer read the
Acts card — a full-page screenshot draws a sticky element unscrolled, so the
broken layout and the fixed one looked identical in the captures.

The static design-preview server is optional: `python scripts/officer_preview_server.py` binds only to `127.0.0.1:8020`; run `python scripts/officer_ui_check.py` separately to capture preview screens.
