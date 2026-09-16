# Backend — setup and operation

For what the service does and why it is built this way, see
[../README.md](../README.md). This file is the runbook.

## Requirements

- Python 3.11 or newer
- **LibreOffice**, for PDF output. This is a real deployment requirement, not a
  nice-to-have: Tamil needs OpenType shaping, and a pure-Python PDF writer
  produces a file that is the right size, with the right text layer, and
  unreadable on the page.

  ```bash
  # Debian/Ubuntu
  sudo apt-get install -y libreoffice-writer fonts-noto-tamil
  # then, in .env
  PDF_ENGINE=libreoffice
  SOFFICE_PATH=/usr/bin/soffice
  ```

  Then verify it — **installing LibreOffice does not by itself make
  `pdf_production_ready` true**:

  ```bash
  .venv/bin/python scripts/verify_pdf.py
  ```

  Nine checks against real petitions this service produced: engine detection,
  DOCX→PDF, Tamil rendering (rasterised and scanned for missing glyphs, because
  a PDF whose Tamil is drawn as boxes still has a perfect text layer), English
  rendering, A4 layout, the enclosure section surviving conversion, the
  reference number, four concurrent conversions with a clean temp directory,
  and a broken input failing soft. It writes a stamp recording the converter's
  version; `pdf_production_ready` becomes true only while that stamp passes and
  matches the installed binary, so upgrading LibreOffice invalidates it rather
  than riding along. Samples land in `var/pdf-verification/` — open the Tamil
  one and read it.

  Microsoft Word can produce PDFs **on a development workstation**
  (`PDF_ENGINE=word` or `auto`), and `/api/health` then reports
  `"pdf": true` with `"pdf_production_ready": false`. Those are deliberately two
  different questions: a workstation that CAN make a PDF is not a deployment
  that may be commissioned on it, because Word automation means an interactive
  Office install, one document at a time, and a COM process that can hang.

  Without any converter the service produces DOCX, adds a warning to the
  session, and reports it on `/api/health`. It does not fail the petition —
  **the DOCX is the deliverable.**

## Test it now

One process serves both the API and a test page. There is no separate front end
and no build step.

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

Open **http://127.0.0.1:8000** — type an answer, press Enter, repeat five times,
then Confirm. On a machine without LibreOffice, start it with `PDF_ENGINE=auto`
to fall back to Word for PDF.

To re-run the full end-to-end check against a running server:

```bash
.venv/Scripts/python scripts/acceptance.py
```

It walks complete English and Tamil petitions over real HTTP, exercises every
rejection and the correction flow, downloads both files, checks the grievance
against what was typed, rasterises the Tamil PDF, and watches the provider call
to confirm the Aadhaar never leaves. Artefacts land in `var/acceptance/`.

## Run

```bash
cd backend
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt   # Linux/macOS: .venv/bin/python
cp .env.example .env
.venv/Scripts/python -m uvicorn app.main:app --port 8000
```

The service starts with no configuration at all. Everything in `.env` is
optional; each missing piece degrades one feature and is reported at startup and
on `/api/health`.

### Richer wording with Gemini

With `ALLOW_EXTERNAL_AI=true` and `GEMINI_API_KEYS` set, one call per petition
writes the formal wording: a subject line tailored to the grievance, the opening
paragraph, and the closing prayer — in Tamil for a Tamil session. Nothing in the
collection conversation uses it, and each of the three parts falls back on its
own if the model is unavailable or answers in the wrong script.

```
ALLOW_EXTERNAL_AI=true
LLM_PROVIDER=gemini
GEMINI_API_KEYS=<key>[,<key>...]
GEMINI_MODELS=gemini-3.5-flash,gemini-3.6-flash,gemini-3.1-flash-lite
```

The model chain matters. These endpoints answer 503 under load often enough that
a second and third model earn their place, and the quality of the Tamil differs
markedly between them — `gemini-3.5-flash` produced the best formal register in
testing, `-flash-lite` produced colloquial forms unsuitable for a petition. The
Aadhaar number is excluded from the prompt at source, so none of this changes
what leaves the machine.

## Tests

```bash
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest
.venv/Scripts/python -m ruff check app tests
```

741 tests, about thirty seconds. The suite runs with **no language model, no
dictation and no PDF converter**, on purpose: that is the deployment the service
has to survive, so it is the one that is tested. Anything that only works when a
model answers is a bug, and running the suite this way is how it gets caught.

Fixtures that stand in for government documents are labelled `TEST DATA` inside
their own text, so anything that leaks into a generated petition is obvious on
sight. The runtime corpus stays empty and a test asserts it.

| File | Covers |
| --- | --- |
| `test_fields.py` | Every validator, including spoken digits and the Aadhaar checksum |
| `test_flow.py` | The form, missing-field arithmetic, field matching, the router |
| `test_conversation.py` | Whole conversations: English, Tamil, corrections, cancel, recovery |
| `test_llm_usage.py` | Where the model is called and — mostly — where it is not |
| `test_privacy.py` | Aadhaar containment across prompts, logs and documents |
| `test_documents.py` | Letter assembly, DOCX, PDF engine selection, verification |
| `test_regressions.py` | One named test per defect actually found |
| `test_knowledge.py` | Retrieval, grounding, and the refusals |
| `test_conflicts.py` | Conflicting and superseded documents; provenance |
| `test_attachments.py` | Uploads, previous petitions, precedence, separation |
| `test_end_to_end.py` | The whole journey, both paths, both languages |
| `test_emblem.py` | Emblem placement, read from words in both languages |
| `test_ocr.py` | OCR as an optional capability, and the pipeline not changing |
| `test_operator.py` | The operator screen: access control and what it reports |

`test_llm_usage.py` uses a fixture that makes a provider **reachable** and records
every request that gets as far as the wire. With no provider configured, "the
model was not called" is true for free and proves nothing.

## Checking Tamil rendering by eye

Asserting that a PDF exists proves nothing about Tamil. Run this on the machine
you are deploying to, with the converter that machine will actually use:

```bash
.venv/Scripts/python scripts/render_sample.py
```

It writes a DOCX, a PDF and a PNG per page into `var/samples/`. Open the PNGs and
read them: vowel signs must sit on the correct consonant and nothing may render
as a box.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health` | What works, and whether citizen text leaves the machine |
| POST | `/api/sessions` | Start a petition. Optional opening statement |
| GET | `/api/sessions/{id}` | Resume — the whole record, for session recovery |
| POST | `/api/sessions/{id}/message` | One turn of conversation |
| POST | `/api/sessions/{id}/field` | Set one field directly, from a form |
| POST | `/api/sessions/{id}/attachments` | Attach one file (multipart) |
| DELETE | `/api/sessions/{id}/attachments/{aid}` | Remove one |
| POST | `/api/sessions/{id}/attachments/{aid}/confirm` | Confirm or reject what was read from it |
| POST | `/api/sessions/{id}/attachments/done` | "Continue with these details" |
| POST | `/api/sessions/{id}/confirm` | Confirm the read-back and generate |
| POST | `/api/sessions/{id}/revise` | Rewrite the wording of a finished petition |
| POST | `/api/sessions/{id}/restart` | Clear everything and start again |
| POST | `/api/sessions/{id}/cancel` | Abandon; nothing is produced |
| GET | `/api/sessions/{id}/document.pdf` | The petition as PDF |
| GET | `/api/sessions/{id}/document.docx` | The petition as DOCX |
| GET | `/api/sessions/{id}/speech` | The current reply as audio, if TTS is on |
| WS | `/ws/voice/{id}` | Live voice conversation — see **Live voice** below |

Interactive API documentation is at `/docs` when the service is running.

## Navigation

Three pages, one compact header, no sidebar.

    Home            Create Petition            My Petitions

**Home** is the entry point: two cards, Create a petition and My petitions.
**Create Petition** opens the existing generator — the same workflow, not a
second one. **My Petitions** lists everything that has been saved.

Routing is by hash (`#home`, `#create`, `#petition/<id>`), so a petition has a
URL that reopens it. `navigation.js` owns the routing and the listing;
`app.js` owns the conversation and the document, and guards every call across
the boundary with `typeof`, so the generator still works if navigation is not
loaded.

**`navigation.js` carries the bootstrap.** If it is ever not loaded, the page
renders and never starts a session. `TestThePageIsWiredUp` asserts that every
script on disk is loaded and every loaded script exists, because that is
exactly the failure that shipped once.

## My Petitions

Backed by `services/petition_catalog.py`, which projects the existing session
checkpoints into a searchable index. **No second store**: the checkpointer
remains the source of truth, the index is rebuilt from it after a restart, and
it keeps one small metadata record per session — identifiers, transcripts and
document bodies are all discarded at that boundary.

Search by reference, petitioner or subject; filter by date range, department,
category, status and language; sort by newest, oldest or recently updated.
Each card carries the reference, status, subject, petitioner, department,
language, created and updated dates, and the current version number, with
View, Edit, Download PDF and Download Word. The whole card opens the petition.

Opening one loads the real session, so it is a working petition and not a
read-only page: the chat is live, the document is editable, and downloads come
from the latest version.

## The emblem

**A petition carries no emblem by default.** It is a citizen's own
representation, not a document the department issued, and printing the state
emblem on it unasked makes it look like one to the officer who opens it.

It goes on when somebody asks for it — a citizen in the conversation, or a
department setting `LETTER_EMBLEM_PAGES=all` (or `first`) for its own
deployment. `LETTER_EMBLEM_ALIGN` says where it lands; `LETTER_EMBLEM=off`
removes the capability altogether.

When it is on it sits in the document **header**, not in the body, on DOCX and
PDF alike. A petition that runs to two pages is ordinary, and an emblem that
appears only on the first is not a letterhead, it is a picture someone pasted at
the top. The A4 preview on screen draws it in the same place, so what the
citizen sees is what downloads.

### Asking for it, and moving it

Spoken or typed, once the petition exists:

| said | result |
| --- | --- |
| "add the logo at the top" | centred, every page |
| "I want the emblem" | centred, every page |
| "move the logo to the right" | right, every page |
| "put the emblem on the left" | left, every page |
| "centre the logo" | centred |
| "remove the logo from the second page" | first page only |
| "no logo on page 2" | first page only |
| "remove the logo" | none at all |
| "I don't want the logo shown" | none at all |
| "சின்னத்தை சேர்க்கவும்" | centred, every page |
| "சின்னத்தை வலதுபுறம் நகர்த்து" | right |
| "சின்னம் முதல் பக்கம் மட்டும்" | first page only |
| "லோகோவை நீக்கு" | none at all |

**This is read deterministically — no model is involved.** "Move the logo to
the right" has exactly one correct outcome, and a model that is 95% reliable at
it is 5% unreliable at something nobody should have to check. `domain/emblem.py`
is a table of words and a small amount of arithmetic, in both languages.

Two consequences worth knowing:

- **The wording is not regenerated.** `letter_text` survives a layout change
  and `compose` passes it straight through, so moving an emblem cannot cause
  the petition to come back worded differently — and it is fast, because there
  is no round trip.
- **An instruction must name the emblem.** "Move it to the right" changes
  nothing, because "it" could be anything. Most of what a citizen says after
  reading their petition is about the words, and a layout parser that answered
  "maybe" to those would move the emblem every time somebody asked for a firmer
  closing paragraph.

The placement is kept on the session, so a citizen who moves the emblem and
then asks for the subject to be reworded does not get it moved back. It is in
the API as `emblem`.

Note on ordering, because it cost a bug: the emblem instruction is read
**before** the yes/no reading. "Right" is one of the words that means yes, so
"move the logo to the right" was read as a confirmation and did nothing — while
every other emblem instruction worked, which is exactly what made it look like
a one-off rather than a rule.

### Settings

| setting | default | |
| --- | --- | --- |
| `LETTER_EMBLEM` | `assets/emblem/tamil-nadu.png` | Relative paths resolve inside the application package. `off` prints none. |
| `LETTER_EMBLEM_TWIPS` | `1000` (~0.7in) | Height on the page; width follows the image. |
| `LETTER_EMBLEM_ALIGN` | `center` | `left`, `center`, `right` — where a petition starts. |
| `LETTER_EMBLEM_PAGES` | `all` | `all`, `first`, `none`. |

A department running this service points `LETTER_EMBLEM` at their own file. A
path that does not exist logs a warning and prints no emblem — a letterhead is
never a reason a citizen leaves without their document.

The shipped file is the state emblem from Wikimedia Commons, which records it
as public domain.

## Editing a petition that already exists

Two different things, and they are now two different controls.

### Edit — the words themselves

The **Edit** button makes the petition on screen editable. What the citizen
types is used **exactly as typed**: no model, no re-composition, no tidying, and
no translation. An editor that improves what it was handed is not an editor, and
somebody who corrected one word and got a differently-worded document back would
be right to stop trusting it.

`POST /api/sessions/{id}/document/text` takes the whole text. The document is
remade and verified as always. What differs is the verdict: **a detail the
citizen removed themselves is a warning, not a refusal.** Verification exists to
catch the SYSTEM corrupting a document — a template bug, a dropped paragraph, a
translation that lost a line. Someone deleting their own address from their own
letter is not that, so the check still names exactly what went missing and the
petition is still handed over. The session records `manually_edited`, because an
officer reading it is entitled to know the wording is the citizen's own.

### The chat — asking for a rewording

Typing into the conversation still works once the petition exists: "make the
closing request firmer", "say more about the elderly residents". That goes
through `compose` with the same rules as the first draft — no new facts, no new
numbers, and the grievance untouched. It is recorded in `revisions` and shown
beside the corrections.

This used to be a box that opened from the toolbar. It moved into the chat
because that is where every other instruction is typed, and because the toolbar
button was the obvious place for the thing it did not do.

## Live voice

The citizen presses **Start Voice** once and then talks. There is no
press-to-speak: the service decides when they have started and finished, stops
talking the moment they interrupt it, and asks the next question out loud.

Voice is a **transport**, not a second application. A settled transcript goes
to the same `workflow.invoke` a typed answer goes to, so a citizen can answer
one question by speaking and the next by typing and the petition cannot tell
the difference. There is no separate voice state to get out of step with the
petition state — see [../docs/voice-integration-decision.md](../docs/voice-integration-decision.md)
for why it is built this way rather than on a voice platform.

```
microphone → 16 kHz PCM → VAD → end of speech → speech-to-text
                                                      ↓
                                     the same graph a typed turn uses
                                                      ↓
                    reply → what may be spoken → text-to-speech → speaker
```

### What it needs

Only `SARVAM_API_KEYS`, which this deployment already sets for translation.
Sarvam provides both speech-to-text (`saarika`) and the spoken replies
(`bulbul`); Groq Whisper is the automatic fallback for transcription.

With neither configured the **Start Voice** button explains that voice is
unavailable and the typed conversation carries on untouched. Voice failing is
never allowed to fail a petition.

### Settings

| Setting | Default | What it does |
| --- | --- | --- |
| `VOICE_ENABLED` | `true` | Turns the whole feature off |
| `VOICE_BARGE_IN` | `true` | The assistant stops when spoken over |
| `VOICE_VAD_THRESHOLD` | `3.2` | How far above the room's noise counts as speech |
| `VOICE_SILENCE_MS` | `700` | Silence that ends a turn |
| `VOICE_ONSET_MS` | `120` | Speech needed before a turn opens |
| `VOICE_MAX_UTTERANCE_S` | `45` | One answer, then it is cut and transcribed |
| `VOICE_NUDGE_AFTER_S` | `12` | "I am listening" |
| `VOICE_ASK_AFTER_S` | `35` | "Would you like to continue?" |
| `VOICE_IDLE_TIMEOUT_S` | `180` | Listening stops; the petition is kept |
| `VOICE_SPOKEN_IDENTIFIERS` | `false` | Whether Aadhaar may be spoken aloud |

**Tuning for the room.** The detector measures the room for its first 256 ms
and takes the quietest frame as its floor, so it adapts to a quiet office and
to a hall with a fan. If a noisy hall still opens turns on background noise,
raise `VOICE_VAD_THRESHOLD`. If citizens are being cut off while they think,
raise `VOICE_SILENCE_MS`.

### Why silence used to become words

Words appeared on the form with nobody speaking: "Okay", "Thirty", once the
Bengali "আচ্ছা।" in the middle of a Tamil conversation. The cause is not a
threshold that needs raising. It is this, measured against the two providers
this deployment uses, with no speech at all:

| input | Sarvam `ta-IN` | Sarvam auto-detect | Groq Whisper |
| --- | --- | --- | --- |
| digital silence | `""` | `""` (guessed kn-IN) | `நான் பார்த்துக்கொள்ளுங்கள்.` |
| quiet room tone | `சரி சார்.` | `""` (guessed ml-IN) | `சரி.` |
| fan / AC hum | `ஆ சரி சரி` | `ஆ சரி சரி` | `சரி.` |
| keyboard click | `சரி` | **`Okay`** (en-IN, 0.765) | `செல்லுங்கள்!` |

**A speech service returning text is not evidence that anyone spoke.** These
models are trained to produce the most likely words for a segment of audio, and
for a segment with no words in it the most likely words are whatever is
commonest in the training data — short acknowledgements. There is no setting
that turns it off.

So there are two gates, and both are needed.

**Before the audio is sent** (`services/voice.py`). A frame has to be loud
*and* look like speech. Zero-crossing rate is what separates them: a fan or an
air conditioner is low-frequency and crosses zero rarely, under about 0.02; a
keyboard click or a chair scrape is broadband and crosses constantly, over
about 0.45; speech sits between and visits both ends. Sustained speech is
required for `VOICE_ONSET_MS` (280 ms, up from 120 — a click is loud for about
150 ms, which is exactly how a click became "Okay").

**After the transcript comes back** (`services/commit_guard.py`). The guard
checks what was actually measured: voiced duration, what fraction of the
utterance looked like speech, how much the level varied, and the peak over the
room's own floor. Level variation is what catches a fan the first gate lets
through — speech rises and falls between syllables and a fan holds one level.
Then it checks the text: not empty, not one of the filler words these providers
produce from nothing, in the script the citizen's language uses, not a
duplicate, not from a turn they have already moved past.

Measured, against the running service, one minute of each:

| | committed | sent to the speech service |
| --- | --- | --- |
| digital silence | 0 | 0 |
| quiet room tone | 0 | 0 |
| fan / AC hum | 0 | 0 |
| keyboard typing | 0 | 0 |
| fan, then a real answer | 1 — "My name is Harish" | 1 |

The last row is the one that matters as much as the zeroes. A detector that
rejects everything is not a fix.

### The VAD is energy and zero-crossing rate, not Silero

Stated plainly because the brief asked for "Silero VAD or equivalent". This is
the equivalent, not Silero: a neural VAD would mean `onnxruntime` and a model
file as new runtime dependencies, and the reference implementations ship
inference for Linux and macOS only, while this service runs on Windows.

The two-gate design is what makes that trade acceptable — the second gate sees
the measurements the first one made, so a fan that fools the detector for two
hundred milliseconds still cannot become an answer. Every acceptance case above
passes on it.

`VoiceActivityDetector` is one class behind one interface. Swapping in Silero
changes that seam and nothing else, and is worth doing if the service is
deployed somewhere genuinely loud.

### Tamil is asked for by name

The speech service is told `ta-IN` when the citizen has chosen Tamil, and
`en-IN` when they have chosen English.

It used to auto-detect, to avoid a real trap: asked to read Tamil audio as
`en-IN`, Sarvam does not fail — it returns a fluent English *translation*
(`என் வயது முப்பது` comes back as "My age is 30"), and on a form that quotes
the grievance word for word that would have a citizen signing a paraphrase of
their own complaint.

Auto-detect turned out to be worse. Detection is a guess, and on audio with no
words the guess is arbitrary — that is where the Bengali came from. The citizen
has already said which language they are using. The remaining case, someone
speaking Tamil in an English session, is handled by the commit guard's script
check rather than by guessing.

### An age is a number, not a run of digits

Separately from voice, and worth knowing about:

| spoken | was | now |
| --- | --- | --- |
| "twenty three" | **3** | 23 |
| "இருபத்து மூன்று" | **3** | 23 |
| "thirty" | rejected | 30 |
| "முப்பது" | rejected | 30 |

`digits_from_speech` collects digits in order, which is exactly right for an
Aadhaar and exactly wrong for an age: "twenty" carries no digit of its own, so
a citizen who said they were twenty-three had **3** written on their petition
and nothing downstream could tell. `domain/spoken_numbers.py` parses spoken
cardinals in both languages — arithmetic over a word list, no model — and
returns nothing rather than a guess when the words do not settle on a number.
"Dirty" is not thirty. Identifiers still use the digit-sequence path.

### Tuning a room

Turn on `VOICE_DIAGNOSTICS=true` and the voice panel shows live microphone RMS,
where the speech threshold sits, the current state, the STT locale, and — when
something is discarded — why, with the measurements it was judged on. No
transcript and no field value ever appear there.

If background noise still opens turns, raise `VOICE_VAD_THRESHOLD` or
`VOICE_MIN_MODULATION`. If short noises get through, raise
`VOICE_MIN_VOICED_MS`. If citizens are being cut off mid-sentence, raise
`VOICE_SILENCE_MS`.

### The voice field

The ribbon in the voice panel is drawn on a canvas from the Web Audio analyser
— five translucent bands blended additively, their height driven by the
microphone while the citizen speaks and by the reply while the assistant
speaks. It is not a recording: an animation that moved while the service was
doing nothing would be a lie about whether it is listening.

States, and what they look like: **listening** a small patient motion,
**speaking** the citizen's own level, **understanding** a controlled pulse with
nothing being heard, **answering** the reply's level, **error** nearly flat.

### Identifiers are not spoken

`VOICE_SPOKEN_IDENTIFIERS` is **off**, and that is a deliberate default. A
spoken Aadhaar number goes two places it need not go: the room, and whichever
speech service is configured — which for a hosted provider means the audio of
a citizen reciting their Aadhaar leaves the building.

So when the Aadhaar question comes up, the screen shows the usual prompt and
the assistant says something different:

| | |
| --- | --- |
| **Screen** | Please say your 12-digit Aadhaar number. |
| **Speaker** | For your security, please type your Aadhaar number in the box rather than saying it aloud. |

The citizen types it, it goes through the same deterministic validation as
always, and the assistant confirms it without reciting it: *"I have recorded
your mobile number ending in 3210."* Speech may say less than the screen. It
may never say something different.

Turn it on for an assisted counter where a citizen cannot type — that is a
real trade, and the operator is the one who should make it.

### Reading the finished petition aloud

Once the document exists the assistant offers to read it. Saying **yes** or
**"read it"** reads it back section by section; saying **stop** ends the
reading. Both work spoken or typed, on the same socket.

This is the one thing the voice layer acts on by itself, and it is worth being
clear why. `ready` is terminal in the router — the workflow has finished and
stops there — so anything said afterwards would reach nothing. The offer was
being made and **nothing could act on it**: a citizen said yes and the service
did not respond at all.

Reading is presentation, not a petition action. It touches no field, no
document and no state; the record after a full read is byte-for-byte what it
was before. The recognised vocabulary is deliberately tiny — `read`, `aloud`,
`go ahead`, `stop`, `enough`, `quiet` and their Tamil equivalents — and a test
asserts that ordinary answers ("my address is wrong", a name, a grievance) are
**not** swallowed as commands.

**Identifiers are not read out.** Each section goes through the same speech
redaction as everything else, and a label left with nothing after it is dropped
with it — otherwise the reading says "Mobile number: Aadhaar number:", which
sounds like the service lost the data rather than withheld it. The document on
screen is unchanged and still carries the full values.

Reading stops the moment the citizen speaks over it, because each section is
its own utterance rather than one long one.

### Protocol

`WS /ws/voice/{session_id}`. Binary frames are 16-bit little-endian mono PCM at
the rate advertised in `voice.ready`; the page resamples to it, because
`AudioContext({sampleRate})` is a hint some devices ignore.

Client → server: `voice.start`, `voice.end`, `voice.interrupt`, `stop`,
`text`, `cancel`.

Server → client: `voice.ready`, `voice.state`, `stt.final`, `state`,
`tts.start`, `tts.audio` (+ one binary frame), `tts.end`, `voice.interrupted`,
`voice.ended`, `error`.

`voice.state` is one of `idle`, `listening`, `user_speaking`, `transcribing`,
`processing`, `assistant_speaking`, `error` — one value, mirrored by the page.
Not a set of booleans that can all be true at once and leave a microphone
listening to a citizen the server stopped hearing.

### Two things worth knowing

**A buffer is stored once, however many frames it holds.** The detector reports
on every 32 ms frame and a browser buffer is several frames long. Storing the
buffer once per verdict stores it four times over, and the speech service
transcribes exactly that — "My name is Harish" came back as three hundred words
of "Ni Ni Ni Mi Mi Mi". `tests/test_voice.py` holds that case.

**An utterance is measured in audio, not in wall-clock.** They are the same
while someone speaks in real time and are not the same anywhere else.

### Testing voice

`tests/test_voice.py` covers the detector, end-of-speech, and what may be
spoken — 34 tests, no network. For an end-to-end check against the real
providers, drive the socket with recorded speech rather than a browser: a
headless browser's fake capture device loops its file and plays it at its own
rate, which makes it useless for asserting what the pipeline did.

## The conversation, as code

```
understand -> validate -> (ask | confirm | compose | END)
                                    compose -> (translate | render) -> verify -> END
```

One citizen utterance is one graph invocation. `ask` and `confirm` run to `END`
rather than blocking, and the checkpointer holds the state against the session
id — so a dropped connection costs nothing and the next utterance resumes from
the record.

`understand` is the only node that may call a model, and it has four tiers:

1. Control words — cancel, start over.
2. At the read-back: a named field to correct, or a plain yes/no.
3. A clean answer to the question that was actually asked.
4. Only then, one structured-output model call.

An identifier that fails to validate, and a first failure at any field, never
reach tier 4: the validator already knows what is wrong and says so.

## Changing the petition

Everything a department may need to change is in
`app/letter_templates/petition.yaml` — the office it is addressed to, the subject
line, the wording of each question in both languages, the enclosure list.
Replacing this with a prescribed government format is an edit to that file.

Adding a field is one block:

```yaml
  - name: mobile
    type: mobile
    required: true
    aliases:
      en: [mobile, phone, phone number]
      ta: [கைபேசி, தொலைபேசி]
    label: {en: Mobile number, ta: கைபேசி எண்}
    prompt:
      en: What is your mobile number?
      ta: உங்கள் கைபேசி எண் என்ன?
```

`type` must name a validator in `app/domain/fields.py`; a template naming one
that does not exist fails at startup rather than accepting the value unchecked.
`aliases` are the words a citizen may use to name the field when correcting it —
that is what makes "the mobile number is wrong" work with no model available.

Field order is the order the citizen is asked. No Python changes, no prompt edits.

## The government knowledge base

An advisory layer. It reads indexed government documents and tells the officer
which department, Act and procedure they point at, with a citation for every
line. It never writes a word of the petition, and the petition is produced
whether it answers, fails or times out.

**It ships empty, and it stays that way until you load real documents.** Until
then the analysis panel is simply absent. Nothing is invented to fill it.

```bash
# 1. Read it first. Indexes nothing. Shows the metadata the file yields, so a
#    wrong Act name is caught before it is on fifty documents.
python scripts/ingest.py inspect "docs/tn-land-encroachment-act-1905.pdf"

# 2. Read the chunks it would make. A citation points at one of these: if a
#    section is split down the middle, the citation points somewhere a reader
#    cannot follow.
python scripts/ingest.py preview "docs/tn-land-encroachment-act-1905.pdf"

# 3. Index it, with provenance. PROVENANCE IS REQUIRED for --official and
#    --departmental: the CLI refuses rather than downgrading quietly, because
#    somebody loading a department's gazette copies should be told they are
#    about to index fifty documents at the wrong rank before it happens.
#    A source URL or a G.O. number counts instead — both are citations a
#    reader can check. Drop the rank flag to index as `unknown`: still
#    searchable and still cited, it simply outranks nothing.
python scripts/ingest.py add "docs/tn-land-encroachment-act-1905.pdf" \
       --official --type act --department "Revenue Department" \
       --provenance "TN Government Gazette, Part III, 12 June 2019"

# A whole folder of departmental circulars.
python scripts/ingest.py add "C:/gov-docs/circulars" --departmental \
       --provenance "Departmental share, synced 2026-09-01"

# A page on a department's website. The URL records itself as provenance,
# so no --provenance is needed.
python scripts/ingest.py add "https://example.tn.gov.in/grievance-procedure" \
       --departmental

python scripts/ingest.py status     # what is indexed
python scripts/ingest.py list       # each document, its id, and whether its
                                    # rank is backed by anything
python scripts/ingest.py show <id>  # 4. what is ACTUALLY indexed, to confirm
                                    #    what went in is what you meant
python scripts/ingest.py remove <document-id>
python scripts/ingest.py supersede <document-id> --by <new-document-id>
python scripts/ingest.py reindex    # re-embed after changing provider
```

`supersede` rather than `remove` when a rule is replaced: a superseded document
is excluded from retrieval but kept, because "what the rule used to be" is a
real question a citizen can be asking, and because conflict handling needs the
version history to say which document it set aside and why.

`add` is safe to run on a schedule: a file whose content has not changed is
skipped, and one that has changed replaces all of its chunks in a single
transaction. Nothing is ever duplicated.

**`--official` and `--departmental` are your judgement, not a detection.**
Authority decides ranking — an official source outranks an unofficial one at
equal relevance — and nothing infers it from a filename or a domain. Everything
defaults to `unknown`, which ranks below both.

**Check what you index.** Retrieval and the grounding check both work faithfully
against whatever is in the corpus; neither can tell a real gazette from a
convincing imitation. That check is yours and it cannot be delegated to this
system.

Formats: PDF, DOCX, HTML and plain text. A scanned PDF with no text layer is
refused rather than indexed empty — it needs OCR first.

Settings: `KNOWLEDGE_ENABLED=false` turns the layer off entirely.
`KNOWLEDGE_EMBEDDING_PROVIDER` is `auto` (Gemini when a key is configured and
external AI is allowed, the local hashed embedder otherwise), `gemini`, or
`local`. Lexical search works in every case, which is why the layer degrades
instead of disappearing on a machine with no egress. The corpus lives in
`var/knowledge.sqlite`.

Citizen data never enters it. Ingestion is the only writer and no code path
runs from a session to a write; the grievance is used only as a query, masked
by the same `mask_pii` boundary as every other outbound text, and is not
persisted.

## Attachments

After every detail is collected and before the read-back, the citizen is asked
once:

> Would you like to add supporting attachments to this petition, or continue
> with these details?

Two actions: **Add Attachments** / **Continue with These Details**. Spoken
answers work through the same table of words, in both languages — "no
documents", "இணைப்பு ஏதுமில்லை", "I have the acknowledgement slip". An answer
that decides neither leaves the question standing rather than guessing, because
guessing "no" throws away the slip in the citizen's hand.

**The petition lists only what was actually supplied.** The template's
`enclosures:` block is now a SUGGESTION shown at this step, not something
printed on the document. It used to be printed on every petition ever produced —
"Copy of Aadhaar card", "Copy of proof of residence", "Copies of any earlier
petition" — whether or not anything was enclosed. A receiving officer reading
that list has been told three documents are in the envelope; when they are not,
it is the citizen who looks as though they withheld them.

A suggestion becomes a requirement only when an **official** retrieved source
says the document is mandatory. With an empty corpus that list is always empty.

### Uploading

**The paperclip beside the microphone**, available throughout the conversation —
the same kind of control as dictation, and for the same reason: another way of
putting something into the petition, reachable whenever the citizen happens to
have it in their hand. Several files at once are fine; each gets its own line
while it uploads, and a file the service refuses keeps its line with the reason
while the rest go through.

Saying "yes" in words works too, in both languages: "yes I want to add
attachments", "I have photographs", "ஆம், இணைப்புகள் சேர்க்க வேண்டும்" — and it
opens the picker.

**A citizen with nothing to attach presses the button already in front of them.**
At this step the single primary button reads "Continue with These Details", and
the read-back follows exactly as it always has. There is no separate panel to
find a way out of.

Attached files show as chips above the text box. The only card that appears is
the one asking whether what was read out of a document is right — that stays,
because nothing from a document may be used until the citizen has looked at it.

### The files are IN the petition

Each attachment is appended to the document as pages after the letter, behind a
caption naming which enclosure it is. A PDF is reproduced page by page, a
photograph is placed as it is, and a text file is typeset. The PDF download gets
them too, because it is converted from the same DOCX.

Two consequences worth knowing:

* **A reproduced PDF page has no text layer.** It is an image inside the
  petition. For a scanned acknowledgement slip — which is what these usually
  are — that changes nothing; for a born-digital PDF it is a real loss. The
  alternative is merging PDF streams, which cannot be done into a DOCX, and
  DOCX is the format this service guarantees.
* **Twelve pages per attachment, at 150 DPI.** A citizen attaching a 200-page
  report has attached the wrong thing, and a 200-page petition will not be read.

A file that cannot be reproduced — a photograph truncated by a phone upload, say
— does not cost the citizen their petition. It stays on the enclosure list,
which is still true (it IS in the envelope), and its page says it is submitted
separately.

### Reading a previous petition

A citizen returning because nothing happened is usually holding the
acknowledgement slip from last time, and that slip carries the reference number
that makes the new petition traceable. Attach it and the service reads, where
they are present:

reference/acknowledgement number · petition number · submission date ·
department · authority · subject · status

All of it deterministically — no model. `TNI/2026/98765` has one correct
reading, and a cue-word score picks it over the form number in the footer.

**Nothing extracted is used until the citizen confirms it.** Each value is shown
with the words it was read from, the citizen can correct any of them, and only
then may the petition say:

> I had previously submitted a petition regarding the same issue on 12-08-2026
> under acknowledgement number TNI/2026/98765. However, the issue remains
> unresolved.

Reject the extraction and the file stays attached but is cited for nothing.

### Precedence

    citizen-confirmed detail  →  citizen correction  →  confirmed attachment
                              →  verified corpus     →  never a guess

An attachment never writes to the record. It cannot: nothing in the upload path
touches `fields`.

### What cannot be attached

PDF, JPEG, PNG, WebP, HEIC, DOCX and plain text, 10 MB each, 10 per petition.
The **bytes** decide, not the name: a file called `.pdf` whose contents are a
Windows executable is refused, and so is an unrecognised header. Filenames are
sanitised, stored names are generated, and everything lives under
`var/attachments/<session-id>/`.

### OCR

**There is none installed, and that is a supported state.** A photographed or
scanned document is attached but reported unreadable, and the citizen is asked
to type the reference number. Nothing is guessed from an image.

To enable it:

```bash
# Debian/Ubuntu — the Tamil language data is a separate package
sudo apt-get install -y tesseract-ocr tesseract-ocr-tam
.venv/bin/python -m pip install pytesseract pillow
```

Nothing in the petition workflow changes when it appears. The pipeline is:

```
attachment
  → is there extractable text?
      yes → deterministic extraction
      no  → is an OCR engine available?
              yes → OCR, at reduced confidence
              no  → say so, and ask the citizen to type it
```

and only the fourth line moves. An OCR result re-enters the same extraction →
confidence → evidence → confirmation pipeline as a text layer does: it is
capped below the low-confidence threshold so it is always flagged, it is shown
with the words it came from, and **it is never auto-confirmed and never writes
a petition field.**

A different engine — a departmental OCR service, say — is a class with
`available()`, `image()` and `pdf()`, registered with
`app.services.ocr.register(...)`. `extraction.py` never learns its name.
`/api/health` and the operator screen report which engine is active and which
languages it has data for; Tamil without `tesseract-ocr-tam` is reported rather
than silently producing noise.

### The two stores

    var/knowledge.sqlite            government reference documents, shared,
                                    embedded, searchable, written only by
                                    scripts/ingest.py
    var/attachments/<session-id>/   this citizen's evidence, never embedded,
                                    never searchable, never read by retrieval

There is no code path from a session to a corpus write, and a test asserts the
corpus store is not even importable from outside `app/knowledge`.

## Operator screen

`http://127.0.0.1:8000/operator` — machine and corpus status. Not linked from
the citizen's page and not for citizens.

**Knowledge base:** indexed documents, official, unknown/unverified, superseded,
active conflicts, embedding provider and dimension, last ingestion, and one word
for corpus health with the reason underneath.

**Capabilities:** knowledge, OCR, PDF, voice, Word generation, language model —
each as Ready / Not ready / Workstation only / Not installed / Degraded /
Unavailable, with the sentence that explains it.

**Access** is one blunt rule that fails closed on the dangerous side:

| `OPERATOR_TOKEN` | Who gets in |
| --- | --- |
| set | the token is required, from any address (`X-Operator-Token` header, or `?token=…`) |
| unset | **loopback only** — the server itself, nobody else |

A deployment that forgets to set a token does not end up with an open admin
panel on its LAN. Refusals are 404, not 401: there is nothing here a citizen has
any reason to discover. Startup logs a warning while no token is set.

No citizen data appears on this screen — not a name, not a count of sessions.
A test walks a whole petition and asserts none of it reaches the page.

## Operational notes

- **Logs** are JSON by default and every conversational line carries
  `session_id`. Citizen text is never logged verbatim, and the formatter scrubs
  identifiers from the finished line as a safety net under that.
- **Sessions** live in `var/sessions.sqlite`. Deleting it discards conversations
  in progress; generated documents in `var/documents/` are unaffected.
- **A stuck session** can be inspected with `GET /api/sessions/{id}`, which
  returns the full record including which field is awaited and why the last
  answer was rejected.
- **`/api/health`** is the first thing to check. It reports whether a model is
  reachable, whether audio leaves the machine, and whether PDF can be produced.

### Not yet implemented

Session records are kept indefinitely. A retention policy — purging checkpoints
and generated documents after a set period — is the obvious next piece of
operational work and is not in this build.
