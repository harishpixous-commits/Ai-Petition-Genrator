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
    sarvam_tts_model: str = "bulbul:v3"
    sarvam_tts_speaker: str = "priya"

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
