#!/usr/bin/env bash
# Write the runtime environment file on the host from values supplied by the
# deployment, so credentials can be managed from GitHub by someone with no
# access to this server.
#
# ⛔ THE RULE THIS ENFORCES, AND WHY IT EXISTS
#
# A provider switch is DERIVED here from whether its key was supplied. It is
# never typed by a human and never taken from a separate setting.
#
# That is not tidiness. A live deployment had real API keys in app.env and
# used none of them for weeks: the template ships LLM_PROVIDER=off,
# STREAM_ASR_PROVIDER=off and TTS_PROVIDER=off, and a key does not override a
# switch. The service read every key correctly and reported `provider: off`,
# which reads exactly like a key that does not work. Deriving the switch from
# the key makes that contradiction impossible to express.
#
# ⛔ WHAT IS DELIBERATELY NOT DERIVED
#
# ALLOW_EXTERNAL_AI. Egress is the one thing a key must never switch on by
# existing: this service carries a citizen's name, address, Aadhaar number and
# their grievance in their own words, and a government deployment must opt
# into sending any of that to a third party as a separate, deliberate act.
# It comes from its own variable and defaults to false.
#
# ⛔ SECRETS ARE NEVER PRINTED
#
# Not a value, not a prefix, not a length. Only the NAME of a variable and
# whether it was supplied. This output goes to a CI log that far more people
# can read than the file it is writing.
#
# Values arrive as environment variables, never as arguments: an argument is
# visible in `ps` to every user on the host for as long as the script runs.
set -Eeuo pipefail
umask 077

APP_DIR="${APP_DIR:-/opt/ai-petition-generator}"
TARGET="$APP_DIR/app.env"

fail=0
note() { printf '  %s\n' "$*"; }
bad()  { printf '  FAIL  %s\n' "$*"; fail=$((fail + 1)); }

have() { [ -n "${!1:-}" ]; }

# --- refuse to write a file that would break the running service ------------
# A missing secret must stop the deployment, not overwrite a working
# configuration with an empty one.
for required in OPERATOR_TOKEN PUBLIC_ORIGIN; do
  have "$required" || bad "$required was not supplied"
done

if [ "$fail" -gt 0 ]; then
  printf '\n%s\n' "Refusing to write $TARGET."
  printf '%s\n' "The existing file is untouched and the service keeps running."
  printf '%s\n' "Set the missing values in the repository's secrets/variables."
  exit 1
fi

# --- derive each provider switch from the key that drives it ----------------
llm_provider="off"
if have GEMINI_API_KEYS || have ANTHROPIC_API_KEY || have GROQ_API_KEYS \
   || have OPENROUTER_API_KEYS; then
  llm_provider="auto"
fi

asr_provider="off"
if have SARVAM_API_KEYS || have DEEPGRAM_API_KEY || have ASSEMBLYAI_API_KEY; then
  asr_provider="auto"
fi

# Sarvam alone drives spoken replies; the other two are dictation only.
tts_provider="off"
if have SARVAM_API_KEYS; then
  tts_provider="auto"
fi

# Egress is off unless the variable clearly says otherwise — but a value that
# clearly MEANT yes and was not recognised must stop the deployment, not
# quietly resolve to no.
#
# An earlier draft accepted only the exact string "true". That reproduced the
# very bug this script exists to prevent: somebody types ALLOW_EXTERNAL_AI=TRUE
# in the repository settings, sees it saved, and gets a deployment that sends
# nothing anywhere with no indication why. Unset means off; an affirmative in
# any ordinary spelling means on; anything else is a typo and is fatal.
case "$(printf '%s' "${ALLOW_EXTERNAL_AI:-}" | tr 'A-Z' 'a-z')" in
  ""|"false"|"no"|"0")  egress="false" ;;
  "true"|"yes"|"1")     egress="true" ;;
  *)
    bad "ALLOW_EXTERNAL_AI is set to an unrecognised value."
    note "        Use true or false. It was not read as either, and guessing"
    note "        would either leak citizen data or silently disable the keys."
    printf '\n%s\n' "Refusing to write $TARGET. The existing file is untouched."
    exit 1
    ;;
esac

# --- the app's own origin, plus the Android app's -------------------------
# The APK's pages are served from https://localhost inside its WebView, so
# every call it makes to this service is cross-origin. Appended here rather
# than asked for, because it is a property of the client, not a deployment
# choice, and leaving it out makes the app fail with a message that blames
# the network.
cors="${PUBLIC_ORIGIN},https://localhost,capacitor://localhost"

# --- write it -------------------------------------------------------------
mkdir -p "$APP_DIR"

if [ -f "$TARGET" ]; then
  backup="$TARGET.$(date -u +%Y%m%dT%H%M%SZ).bak"
  cp -p "$TARGET" "$backup"
  chmod 600 "$backup"
  note "previous file kept as $(basename "$backup")"
  # Keep the five most recent. These contain live credentials; an unbounded
  # pile of them on disk is a growing target.
  ls -1t "$TARGET".*.bak 2>/dev/null | tail -n +6 | xargs -r rm -f
fi

tmp="$(mktemp "$APP_DIR/.app.env.XXXXXX")"
trap 'rm -f "$tmp"' EXIT

emit() { printf '%s=%s\n' "$1" "${2-}" >> "$tmp"; }
emit_if_set() { have "$1" && printf '%s=%s\n' "$1" "${!1}" >> "$tmp" || true; }

{
  printf '%s\n' "# GENERATED BY deploy/scripts/write-env.sh - DO NOT EDIT BY HAND."
  printf '%s\n' "# Every deploy overwrites this file. Change the values in the"
  printf '%s\n' "# repository's Settings > Secrets and variables, then re-run the"
  printf '%s\n' "# workflow. A manual edit here survives only until the next deploy."
  printf '%s\n' "# Written at $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf '\n'
} > "$tmp"

emit HOST 0.0.0.0
emit PORT 8000
emit LOG_LEVEL INFO
emit LOG_FORMAT json
emit DATA_DIR /app/backend/var
emit CORS_ORIGINS "$cors"
emit OPERATOR_TOKEN "$OPERATOR_TOKEN"
emit PDF_ENGINE libreoffice
emit SOFFICE_PATH /usr/bin/soffice
emit LETTER_FONT "Noto Sans Tamil"
emit KNOWLEDGE_ENABLED true
emit ALLOW_EXTERNAL_AI "$egress"
emit LLM_PROVIDER "$llm_provider"
emit STREAM_ASR_PROVIDER "$asr_provider"
emit TTS_PROVIDER "$tts_provider"

for key in GEMINI_API_KEYS ANTHROPIC_API_KEY GROQ_API_KEYS OPENROUTER_API_KEYS \
           SARVAM_API_KEYS DEEPGRAM_API_KEY ASSEMBLYAI_API_KEY; do
  emit_if_set "$key"
done

chmod 600 "$tmp"
chown root:root "$tmp" 2>/dev/null || true
mv -f "$tmp" "$TARGET"
trap - EXIT

# --- report, by name only ---------------------------------------------------
printf '\n%s\n' "wrote $TARGET ($(stat -c '%a %U:%G' "$TARGET"))"
note "ALLOW_EXTERNAL_AI   = $egress"
note "LLM_PROVIDER        = $llm_provider"
note "STREAM_ASR_PROVIDER = $asr_provider"
note "TTS_PROVIDER        = $tts_provider"
printf '\n%s\n' "  credentials supplied:"
supplied=0
for key in GEMINI_API_KEYS ANTHROPIC_API_KEY GROQ_API_KEYS OPENROUTER_API_KEYS \
           SARVAM_API_KEYS DEEPGRAM_API_KEY ASSEMBLYAI_API_KEY; do
  if have "$key"; then note "    $key"; supplied=$((supplied + 1)); fi
done
[ "$supplied" -eq 0 ] && note "    (none - the service runs without AI features)"

if [ "$supplied" -gt 0 ] && [ "$egress" != "true" ]; then
  printf '\n%s\n' "  NOTE: keys were supplied but ALLOW_EXTERNAL_AI is not 'true',"
  note "        so nothing will use them. Set the repository variable"
  note "        ALLOW_EXTERNAL_AI=true once external AI is approved."
fi
