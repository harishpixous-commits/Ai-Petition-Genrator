# Real-time voice: which integration, and why

Written for: the engineering and procurement reviewers of the Citizen Petition
Assistant.

## The decision

**Option D — reuse Rapida's architecture, implement the voice layer inside this
application.** No Rapida source is copied, linked, vendored or run.

The voice layer lives in `backend/app/services/voice.py`,
`backend/app/services/speech_text.py` and the existing
`backend/app/api/ws.py`, in the same Python/FastAPI process as the petition
workflow.

## Why not the other options

### Option A — Rapida Web SDK / widget

Not available, and not usable if it were.

Every SDK in the repository is a **git submodule pointing at a separate
repository**, and all but one use SSH URLs to private repositories:

```
sdks/react        https://github.com/rapidaai/rapida-react
sdks/go           git@github.com:rapidaai/rapida-go.git
sdks/nodejs       git@github.com:rapidaai/rapida-nodejs.git
sdks/python       git@github.com:rapidaai/rapida-python.git
sdks/react-widget git@github.com:rapidaai/react-widget.git
```

The archive supplied (`voice-ai-main.zip`, 4,591 entries) contains the
submodule *directories* and none of their contents. There is no SDK to
evaluate or install from what we have.

This application's front end is also a single served HTML page with no build
step — deliberately, so the service is one process and one command. A React
widget would introduce a bundler, a node toolchain and a second deployment
artefact for one button.

### Option B — Rapida assistant APIs

Architecturally incompatible with the one rule that matters most here.

Rapida's `assistant-api` **owns the conversation**. Its pipeline is
audio → VAD → STT → *its own* LLM/assistant → TTS. Using it as designed would
put a Rapida assistant in charge of deciding what to ask the citizen next —
which is exactly the bypass the brief forbids, and would put the petition's
field order, validation and correction flow behind a model we do not control.

Driving it as a transport only would mean running the whole assistant stack and
using none of the part that justifies it.

### Option C — Rapida voice orchestration alongside this backend

Disproportionate, and it does not run on the target machine.

`docker-compose.yml` brings up eight services for this: `postgres`, `redis`,
`nginx`, `ui`, `web-api`, `assistant-api`, `integration-api`, `endpoint-api`.
That is a platform for building many assistants. This application has one form
with six fields.

More concretely: the VAD implementations ship inference for two platforms only —

```
api/assistant-api/internal/vad/internal/silero_vad/infer_linux.go
api/assistant-api/internal/vad/internal/silero_vad/infer_darwin.go
api/assistant-api/internal/vad/internal/firered_vad/infer_linux.go
api/assistant-api/internal/vad/internal/firered_vad/infer_darwin.go
```

There is no Windows build. The development and demonstration machine for this
project is Windows 11.

## The licence, which decides it either way

`LICENSE.md` is **GPL-2.0 with additional Rapida terms**. It is the only licence
file in the repository, so it covers everything in it. Two clauses matter:

> **1. Branding Requirement** — If you are using Rapida under this open-source
> GPL license, you must keep the Rapida name and logo visible in all UI
> components provided by the software.

> **2. Commercial License Exception** — A separate commercial license is
> available that removes the branding requirement and allows the use of Rapida
> in closed-source or proprietary products without GPL obligations.

For this application that means:

- **Copyleft.** Incorporating Rapida source would make this a derivative work.
  The Citizen Petition Assistant would have to be distributed under GPL-2.0,
  with source. That is a decision for the department, not an implementation
  detail, and it cannot be taken by accident inside a commit.
- **Branding.** A citizen-facing government service would have to display the
  Rapida name and logo. A petition counter is not a place to put a vendor's
  logo without an explicit decision to do so.

A commercial licence from RapidaAI (sales@rapida.ai) removes both. **If the
department wants Rapida itself rather than its design, that conversation has to
happen first.** Nothing in this implementation depends on the outcome, and
nothing here forecloses it.

Studying a repository's architecture and writing an independent implementation
does not create a derivative work. Copying its code does. This implementation
reads Rapida's design and shares none of its code.

## What was taken from Rapida — ideas, not code

One design in particular is worth the credit. From
`api/assistant-api/internal/end_of_speech/internal/silence_based/README.md`:

> **Generation Counter**: Each new input increments a generation counter:
> invalidates all previously scheduled callbacks; worker validates generation
> matches before callback fires; prevents stale callbacks even with unlucky
> scheduling.

That is the right answer to the hardest correctness problem in a streaming
voice turn — a silence timer that has already been superseded firing anyway and
committing an utterance twice. `EndOfSpeech` in `voice.py` uses the same idea,
written in asyncio, and the duplicate-suppression test exists because of it.

Also adopted:

- silence-based end-of-speech with a resettable timer, rather than waiting for
  a provider's own endpointing;
- an explicit turn state machine rather than a set of booleans;
- a typed event contract between the audio transport and the application.

## What this costs, honestly

Writing the voice layer here means we own the VAD. It is **energy-based**, not a
neural VAD like Silero. In a quiet room or an office it is reliable; in a noisy
public hall it will be less discriminating than Silero would be, and the
thresholds are exposed as configuration (`VOICE_VAD_THRESHOLD`,
`VOICE_SILENCE_MS`) so they can be tuned on site rather than in code.

The upgrade path is open: `VoiceActivityDetector` is one class behind one
interface. Replacing it with an ONNX Silero model, or with Rapida under a
commercial licence, changes that one seam and nothing else.
