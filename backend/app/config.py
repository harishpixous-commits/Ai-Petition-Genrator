"""Runtime configuration.

The default posture is DELIBERATELY on-premise: `allow_external_ai` is false and
no citizen text leaves the machine until an administrator says otherwise. This
is carried over from the Node service, where the same rule exists because a
government workspace must not be opted into egress by the mere presence of an
API key in an environment file.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


def _split(value: str) -> list[str]:
    return [v.strip() for v in str(value or "").split(",") if v.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", case_sensitive=False
    )

    # -- service ----------------------------------------------------------- #
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"
    log_format: str = "json"  # "json" | "text"
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"

    data_dir: Path = BASE_DIR / "var"
    checkpoint_db: str = "sessions.sqlite"
    document_dir_name: str = "documents"

    # -- language models --------------------------------------------------- #
    allow_external_ai: bool = False
    llm_provider: str = "auto"
    llm_chain: str = "anthropic,openrouter,groq,gemini,ollama"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    openrouter_api_keys: str = ""
    openrouter_models: str = "nex-agi/nex-n2.5-mini:free"
    groq_api_keys: str = ""
    groq_models: str = "openai/gpt-oss-120b,qwen/qwen3.8-27b,openai/gpt-oss-20b"
    gemini_api_keys: str = ""
    gemini_models: str = "gemini-3.5-flash,gemini-3.6-flash,gemini-3.1-flash-lite,gemini-3.5-flash-lite"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "gemma4:12b"

    # Voice turns are latency-critical: one understanding call, bounded hard.
    understand_timeout_ms: int = 6000
    understand_budget_ms: int = 9000
    # Composition happens once, after confirmation, while the citizen waits on a
    # progress indicator rather than on silence. It can afford more.
    compose_timeout_ms: int = 25000
    compose_budget_ms: int = 90000

    # -- speech ------------------------------------------------------------ #
    # auto | sarvam | groq | deepgram | assemblyai | off
    #
    # `auto` prefers Sarvam. Checked by recording a Tamil sentence and reading
    # it back through each engine: Sarvam returned it exactly, and Whisper
    # returned "நூன்று" for "மூன்று" and "எறியவில்லை" for "எரியவில்லை". A
    # petition is quoted verbatim, so a transcription that is nearly right is a
    # grievance with the wrong words in it.
    stream_asr_provider: str = "auto"
    deepgram_api_key: str = ""
    # nova-2 has no Tamil and answers HTTP 400 for it. This default is load-bearing.
    deepgram_model: str = "nova-3"
    assemblyai_api_key: str = ""
    asr_sample_rate: int = 16000

    sarvam_stt_model: str = "saarika:v2.5"
    groq_stt_model: str = "whisper-large-v3"
    # How long one dictation may run before it is cut off and transcribed.
    # 16-bit mono at 16 kHz is 32 kB/s, so two minutes is under 4 MB — well
    # inside every provider's upload limit, and longer than anyone dictates a
    # grievance in one breath.
    asr_max_seconds: int = 120
    # One transcription request. Sarvam answered a two-minute clip in a few
    # seconds; this is the cut-off for a provider that has stopped answering.
    stt_timeout_ms: int = 30000
    stt_budget_ms: int = 75000

    # -- live voice conversation ------------------------------------------- #
    #
    # Hands-free mode: the citizen presses Start Voice once and then speaks.
    # Turn-taking is decided here rather than by a provider, so the petition
    # workflow stays the only thing that decides what is asked next.
    voice_enabled: bool = True
    voice_barge_in: bool = True
    # Above this multiple of the measured noise floor a frame counts as speech.
    voice_vad_threshold: float = 3.2
    # Silence that ends a turn. Long enough to think, short enough not to wait.
    voice_silence_ms: int = 700
    # Speech this long is required before a turn opens, so a cough does not.
    voice_onset_ms: int = 120
    # One answer. Past this the utterance is cut and transcribed as it stands.
    voice_max_utterance_s: float = 45.0
    # Nudges when nobody says anything, then a question, then the session ends
    # — with the petition kept exactly as it was.
    voice_nudge_after_s: float = 12.0
    voice_ask_after_s: float = 35.0
    voice_idle_timeout_s: float = 180.0
    # Whether an Aadhaar or a mobile number may be SPOKEN. Off by default: a
    # spoken identifier reaches the room and the speech provider, and the
    # keyboard path for it already exists. An assisted counter can turn it on.
    voice_spoken_identifiers: bool = False
    # Read each captured answer back and wait for the citizen to agree before
    # it is used. On by default: dictation into a government form is the case
    # where a misheard house number is discovered at the counter rather than
    # on the screen. An assisted counter where the operator watches the text
    # appear can turn it off and save a turn per field.
    voice_read_back: bool = True

    # -- turn-taking -------------------------------------------------------- #
    #
    # The assistant finishes speaking before the microphone is allowed to
    # produce an answer. On by default, and it OVERRIDES `voice_barge_in`.
    #
    # The reason is the failure it prevents rather than the politeness it
    # buys. The microphone is open during playback so that a citizen can cut
    # in; with laptop speakers a foot from the microphone, what it hears is
    # the assistant. Sarvam transcribes that perfectly well, and the result is
    # a fabricated answer in the citizen's own form — the assistant asking
    # "is that correct?" about a sentence it said itself.
    #
    # Echo rejection exists (`during_playback` / ECHO_SUSPECTED) and catches
    # most of it. Most is not enough for a government record, so the default
    # is sequential: reliability over interruption. A deployment with headsets
    # can set this false and get barge-in back.
    voice_half_duplex: bool = True
    # How long to wait for the page to report that playback actually finished
    # before giving up and using the measured length of the audio instead.
    # Only a backstop: the page reports the real event, and this stops a page
    # that cannot (an old client, a muted tab) from stalling the turn.
    voice_playback_grace_s: float = 8.0
    # A settling pause between the audio finishing and the microphone
    # counting again, for the tail of a speaker still in the air.
    #
    # ZERO by default, deliberately. The gate already discards everything
    # heard while the assistant holds the floor, and the detector is reset as
    # it is handed back, so there is no evidence this is needed — and every
    # millisecond here is added to every turn the citizen takes. It exists as
    # a knob because real-device testing in a room with loud speakers is the
    # only thing that can show whether it is, and finding out should not
    # require a code change. 100-200 ms is the range to try.
    voice_settle_ms: int = 0

    # -- long-form dictation (the grievance) -------------------------------- #
    #
    # A name is three words; a grievance is a story, told with pauses. The
    # same end-of-speech rule cannot serve both — 700 ms of silence is a
    # breath in the middle of a sentence, and ending the answer there hands
    # in half a complaint.
    voice_long_silence_ms: int = 2500
    # After this much further quiet, a long answer is taken as finished. It
    # is on top of the silence above, so the citizen gets roughly six seconds
    # of thinking time before being asked to confirm.
    voice_long_finish_s: float = 3.5
    # Longer than this and the read-back is a summary rather than the text:
    # a two-minute grievance read back word for word is a two-minute wait
    # that nobody listens to. The full text is on screen either way, and
    # "read it to me" plays the whole thing on request.
    voice_long_readback_chars: int = 240

    # -- telling the citizen the room is too loud --------------------------- #
    #
    # ADVISORY ONLY. Nothing is rejected for being said in a noisy room — the
    # speech threshold is already relative to the measured floor, so a loud
    # room raises the bar rather than closing the door. This is the point at
    # which raising the bar starts to cost a soft-voiced citizen their answer,
    # and saying so is more use than silently failing to hear them.
    #
    # 600 RMS out of 32768 is about -35 dBFS: a noticeably loud room. The
    # detector would then need roughly 1900 RMS to call something speech, and
    # a quiet speaker sits near 1500 — which is exactly when moving closer to
    # the microphone is the thing that helps.
    voice_noise_advisory_rms: float = 600.0
    # How many consecutive two-second checks must agree before saying so. A
    # door slamming is not a noisy room.
    voice_noise_advisory_checks: int = 3

    # -- what is allowed to become an answer -------------------------------- #
    #
    # A speech service returning text is not evidence that anyone spoke. Asked
    # to transcribe a keyboard click, Sarvam returned "Okay"; asked to
    # transcribe digital silence, Whisper returned a whole Tamil sentence.
    # These thresholds are what the audio has to show before a transcript is
    # allowed to answer a question on a petition.
    #
    # Raise `voice_min_voiced_ms` if short noises still get through; raise
    # `voice_min_modulation` if steady noise does. Both are in the developer
    # diagnostics panel alongside the live measurements, which is the way to
    # tune them for a particular room.
    voice_min_voiced_ms: int = 320
    voice_min_voiced_ratio: float = 0.35
    voice_min_modulation: float = 0.12
    # Only Whisper reports a per-transcript figure; Sarvam reports none, and
    # None never fails the check. 0 disables it.
    voice_min_confidence: float = 0.15
    # Show live RMS, noise floor, and why an utterance was discarded. Never
    # includes transcripts or identifiers.
    voice_diagnostics: bool = False

    tts_provider: str = "auto"  # auto | sarvam | off
    sarvam_api_keys: str = ""
    # bulbul:v2 is retired — it answers HTTP 400 "has been deprecated", and
    # anushka is not a v3 speaker. Both defaults are load-bearing.
    #
    # The speaker is CASE-SENSITIVE and Sarvam's own console displays these
    # names capitalised: picking "Ishita" there and pasting it here gets
    # HTTP 400 "Speaker 'Ishita' is not recognized". `tts.py` lowercases it
    # on the way out so either spelling works, but the value stored is the
    # one the API actually uses.
    #
    # Verified against the live API. The v3 list, at the time of writing:
    #   aditya ritu ashutosh priya neha rahul pooja rohan simran kavya amit
    #   dev ishita shreya ratan varun manan sumit roopa kabir aayan shubh
    #   advait anand tanya tarun sunny mani gokul vijay shruti suhani mohit
    #   kavitha rehan soham rupali
    sarvam_tts_model: str = "bulbul:v3"
    sarvam_tts_speaker: str = "ishita"
    # How fast the assistant speaks. 1.0 is the model's own pace; below it is
    # slower. Worth having as a setting rather than a constant: a counter
    # serving elderly citizens may want 0.8, and that is a deployment
    # decision, not a code change.
    #
    # bulbul:v3 accepts 0.5 to 2.0 and answers HTTP 400 outside it — which is
    # SILENCE, not an error anyone sees. `tts.py` clamps rather than letting
    # a well-meant 0.3 mute the service.
    sarvam_tts_pace: float = 1.0
    # What the model already returns; sent explicitly so a change to its
    # default cannot alter the audio underneath us without anyone noticing.
    sarvam_tts_sample_rate: int = 22050

    # Which build is running, set by the deployment from the commit it
    # deployed. Empty on a developer machine.
    #
    # WHY IT EXISTS. "Is my change live yet?" had no answer. Working it out
    # meant hashing the static files on the server and comparing them against
    # every recent commit by hand — and that only settles the JavaScript,
    # because a change to the Python leaves the assets identical. Two rounds
    # of "it is still not fixed" were a deploy that had not finished.
    # ---- System-1 decision layer ------------------------------------- #
    #
    # WHAT `system1_enabled` ACTUALLY SWITCHES, because the name suggests
    # more than it does: whether an ALTERNATIVE PROVIDER may be used. The
    # deterministic provider always runs. It has no model, no network and no
    # warm-up, it cannot fail in a way the two guards do not catch, and the
    # attachment-relationship classification it produces is what stops a
    # third party's acknowledgement number being claimed in a citizen's own
    # first person. Gating that behind a flag would mean shipping the bug by
    # default.
    #
    # So: off means "deterministic only", which is the approved
    # configuration. Turning it on is how a candidate provider gets measured
    # on the same cases without a code change.
    #
    # THE GRIEVANCE CATEGORY IS NOT ROUTING, at any setting. It measured
    # 0.735 on the only case set that never informed it and is carried as
    # `suggested_category`, a hint for an officer. Department, authority, Act
    # and Rule continue to come from verified RAG and officer review, and a
    # test asserts nothing outside `system_one.py` reads the field.
    #
    # `system1_confidence_threshold` is 0.0 deliberately: a number picked
    # without a benchmark behind it is a number nobody can defend. Raise it
    # only from a measurement. See docs/system-one-review.md.
    system1_enabled: bool = False
    system1_provider: str = "deterministic"
    system1_confidence_threshold: float = 0.0
    system1_timeout_ms: int = 250

    build_sha: str = ""

    # -- kiosk: a self-service terminal in a government office ------------- #
    #
    # None of this changes the petition. A kiosk runs the same workflow, the
    # same questions, the same document; these settle how the TERMINAL
    # behaves around it — when it prints, how long it waits for somebody who
    # has walked away, and what it clears afterwards.
    kiosk_enabled: bool = True
    # `dialog` or `silent`.
    #
    # DIALOG IS THE DEFAULT AND IS THE HONEST ONE. A browser cannot print to
    # paper without a person confirming it; `window.print()` opens the print
    # dialog and somebody presses Print. That works on any machine.
    #
    # `silent` is a CLAIM ABOUT THE DEPLOYMENT, not a capability this code
    # can grant itself. It means "this terminal was launched with
    # --kiosk-printing, or has an equivalent managed print path, and the
    # dialog will not appear". Set it only on a machine where that is true;
    # setting it anywhere else changes nothing except what the screen claims
    # happened, which is the one thing worth getting right.
    kiosk_print_mode: str = "dialog"
    # Whether the petition goes to the printer on its own once it is ready
    # and verified. False leaves the citizen to press Print.
    kiosk_auto_print: bool = True
    # `petition_only` or `combined`. A citizen who attached six photographs
    # of a broken road should not silently receive thirty pages, so the
    # letter alone is the default and the package is a deliberate choice.
    kiosk_print_package: str = "petition_only"
    # How long a terminal waits for somebody who has stopped answering
    # before asking whether they are still there, and then clearing.
    kiosk_idle_timeout_seconds: int = 120
    # Clear the screen after the citizen finishes. On, and it is the setting
    # that keeps the next person in the queue from reading the last
    # person's name, address and grievance.
    kiosk_reset_after_finish: bool = True

    # -- translation ------------------------------------------------------- #
    nllb_worker: str = ""  # path to the Node NLLB worker, optional
    nllb_model_dir: str = ""

    # -- rendering --------------------------------------------------------- #
    #
    # PDF_ENGINE is deliberately NOT "auto" by default.
    #
    # Tamil needs OpenType shaping — vowel signs reorder around the consonant
    # they attach to — so the PDF has to come from something that shapes through
    # HarfBuzz. LibreOffice does. Microsoft Word does too, but driving Word means
    # an interactive Office installation on the server, one document at a time,
    # and a COM process that can hang; it is a development convenience on a
    # workstation and must never become the production path by accident.
    #
    #   libreoffice  the supported engine (default)
    #   word         Windows only, development; must be chosen explicitly
    #   auto         LibreOffice, falling back to Word
    #   off          DOCX only
    pdf_engine: str = "libreoffice"
    soffice_path: str = "soffice"
    # WHICH emblem is available, not whether one is printed — see
    # `letter_emblem_pages` below, which is "none" by default.
    #
    # Relative paths resolve inside the application package, so the shipped
    # Tamil Nadu state emblem is what a citizen gets if they ask for one, and a
    # department running this service points the setting at their own file.
    # "off" removes the capability entirely; a path that does not exist logs a
    # warning and prints none, because a letterhead is never a reason a citizen
    # leaves without their document.
    letter_emblem: str = "assets/emblem/tamil-nadu.png"
    # Height on the page. Width follows the image's own proportions.
    letter_emblem_twips: int = 1000     # ~0.7 inch
    # Where it goes WHEN it is asked for. A petition is a citizen's own
    # document, so nothing is printed on it by default: "none" means no emblem
    # unless a citizen asks for one ("put the logo at the top") or a department
    # sets this to "all" or "first" for its own deployment.
    letter_emblem_align: str = "center"   # left | center | right
    letter_emblem_pages: str = "none"     # none | all | first

    # Where this service is used, as an offset from UTC. A container runs in
     # UTC; Tamil Nadu is +5:30. Between midnight and 05:30 local those are
     # different DATES, and the date on a petition is the date it was made.
     #
     # An offset rather than a zone name because India has never observed
     # daylight saving, so this is exact all year and needs no timezone
     # database — which a slim container does not ship.
    petition_utc_offset_minutes: int = 330

    letter_font: str = "Nirmala UI"  # carries Tamil on Windows; Noto Sans Tamil on Linux

    # -- operator screen ---------------------------------------------------- #
    #
    # The technical status screen at /operator. Blunt access rule, failing
    # closed on the dangerous side: with a token set it is required from
    # anywhere; with no token it answers only on loopback. A deployment that
    # forgets to set one does not get an open admin panel on its LAN.
    operator_token: str = ""

    # -- government knowledge layer ---------------------------------------- #
    #
    # Advisory only. It tells an officer which Act, department and procedure the
    # retrieved documents point at; it never writes a word of the petition and
    # the petition is produced whether it answers, fails or times out.
    knowledge_enabled: bool = True
    knowledge_db: str = "knowledge.sqlite"

    # auto | gemini | local | off
    #
    # `auto` uses Gemini when a key is configured AND external AI is allowed,
    # and the hashed local embedder otherwise. Retrieval is hybrid, so the
    # lexical half keeps working either way.
    knowledge_embedding_provider: str = "auto"
    knowledge_embedding_model: str = "gemini-embedding-001"
    # The endpoint's native width is 3072. Asking for 1536 quarters the index
    # at no measurable cost to recall on a corpus this shape.
    knowledge_embedding_dimension: int = 1536
    knowledge_local_dimension: int = 512
    knowledge_embed_timeout_ms: int = 15000

    # Ingestion. ~1200 characters is about a section of an Act: long enough to
    # carry its own subject, short enough that a citation points somewhere a
    # reader can actually find.
    knowledge_chunk_chars: int = 1200
    knowledge_chunk_overlap: int = 160

    # Retrieval. Fused from the lexical and vector halves by reciprocal rank.
    knowledge_candidates: int = 24      # per half, before fusion
    knowledge_context_chunks: int = 8   # what the analyst is allowed to read
    # A bounded agent, not an open-ended one. Each step is one more retrieval
    # with a refined query; the limit is what stops a loop from searching until
    # the timeout.
    knowledge_max_steps: int = 3
    # The whole analysis, including every model call inside it.
    knowledge_timeout_ms: int = 20000

    # Web search as a LOWER tier, off by default. When enabled, anything it
    # returns is marked external and is never presented as settled law.
    knowledge_web_fallback: bool = False

    # -- derived ----------------------------------------------------------- #
    @property
    def cors_origin_list(self) -> list[str]:
        return _split(self.cors_origins)

    @property
    def checkpoint_path(self) -> Path:
        return self.data_dir / self.checkpoint_db

    @property
    def document_dir(self) -> Path:
        return self.data_dir / self.document_dir_name

    @property
    def knowledge_path(self) -> Path:
        return self.data_dir / self.knowledge_db

    @property
    def openrouter_key_list(self) -> list[str]:
        return _split(self.openrouter_api_keys)

    @property
    def groq_key_list(self) -> list[str]:
        return _split(self.groq_api_keys)

    @property
    def gemini_key_list(self) -> list[str]:
        return _split(self.gemini_api_keys)

    @property
    def sarvam_key_list(self) -> list[str]:
        return _split(self.sarvam_api_keys)

    @property
    def openrouter_model_list(self) -> list[str]:
        return _split(self.openrouter_models)

    @property
    def groq_model_list(self) -> list[str]:
        return _split(self.groq_models)

    @property
    def gemini_model_list(self) -> list[str]:
        return _split(self.gemini_models)

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.document_dir.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
