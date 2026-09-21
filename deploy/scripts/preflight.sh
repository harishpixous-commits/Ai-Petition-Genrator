#!/usr/bin/env bash
# Check the runtime environment file BEFORE the deployment replaces anything.
#
# WHY THIS EXISTS. An operator put real API keys into app.env, redeployed, and
# nothing changed: no voice, no AI narrative, `provider: off` on the health
# endpoint. The keys were read correctly every time. What defeated them was
# LLM_PROVIDER=off / STREAM_ASR_PROVIDER=off / TTS_PROVIDER=off, which the
# template ships and which a key does not override. Nothing in the pipeline
# looked at app.env at all, so the contradiction reached a live host and
# presented as "the keys do not work".
#
# `write-env.sh` now generates the file and derives those three switches, so
# the CI path cannot produce that state. This runs afterwards and checks the
# result anyway — on the principle that the gate should not trust the thing
# it is gating, and because a file edited by hand on the host still lands
# here.
#
# ⛔ NEVER PRINTS A KEY. Not a value, not a prefix, not a length. Only the
# NAME of a variable and whether it is set. This output goes to a CI log that
# is far more widely readable than the file it is checking.
#
# Run as root: app.env is root:root 0600 on purpose, and an unprivileged
# shell reports every key as missing. The permissions are not weakened to
# suit this script.
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/ai-petition-generator}"
ENV_FILE="${ENV_FILE:-$APP_DIR/app.env}"

fail=0
warn=0

say()  { printf '%s\n' "$*"; }
bad()  { printf '  FAIL  %s\n' "$*"; fail=$((fail + 1)); }
soft() { printf '  WARN  %s\n' "$*"; warn=$((warn + 1)); }
good() { printf '  ok    %s\n' "$*"; }

say "== app.env =="

if [ ! -f "$ENV_FILE" ]; then
  bad "$ENV_FILE does not exist."
  say ""
  say "  It is written by deploy/scripts/write-env.sh from the repository's"
  say "  secrets. If that step did not run, check it in the workflow log."
  exit 1
fi
good "$ENV_FILE exists"

if [ ! -r "$ENV_FILE" ]; then
  bad "cannot read $ENV_FILE — run this with sudo."
  exit 1
fi

perms=$(stat -c '%a %U:%G' "$ENV_FILE")
case "$perms" in
  "600 root:root") good "permissions $perms" ;;
  *) soft "permissions are $perms; expected 600 root:root" ;;
esac

# Read the file WITHOUT sourcing it. Sourcing executes whatever is in there,
# and a stray backtick in a pasted key would run as root.
value_of() {
  sed -n -E "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*(.*)$/\1/p" "$ENV_FILE" \
    | tail -n 1 | sed -E 's/[[:space:]]+$//'
}
is_set() { [ -n "$(value_of "$1")" ]; }

say ""
say "== required =="
for key in DATA_DIR CORS_ORIGINS OPERATOR_TOKEN; do
  v=$(value_of "$key")
  if [ -z "$v" ]; then
    bad "$key is empty or missing"
  elif printf '%s' "$v" | grep -qi 'CHANGE-ME'; then
    bad "$key is still the placeholder from the template"
  else
    good "$key is set"
  fi
done

# A quoted value is a real and silent failure: docker compose env_file does
# NOT strip quotes the way a shell does, so KEY="abc" arrives at the
# application as five characters including both quote marks.
say ""
say "== quoting =="
quoted=$(grep -nE '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*[[:space:]]*=[[:space:]]*["'"'"']' \
         "$ENV_FILE" || true)
if [ -n "$quoted" ]; then
  bad "quoted values found. docker compose keeps the quotes as part of the value:"
  printf '%s\n' "$quoted" | cut -d: -f1 | sed 's/^/          line /'
else
  good "no quoted values"
fi

# --- the failure this script was written for --------------------------------
say ""
say "== credentials that are set but switched off =="

check_switch() {
  local switch="$1" keys="$2" current
  is_set "$keys" || return 0
  current=$(value_of "$switch")
  if [ -z "$current" ] || [ "$(printf '%s' "$current" | tr 'A-Z' 'a-z')" = "off" ]; then
    bad "$keys is set, but $switch=${current:-off} disables it. Set $switch=auto"
  fi
}

check_switch LLM_PROVIDER GEMINI_API_KEYS
check_switch LLM_PROVIDER ANTHROPIC_API_KEY
check_switch LLM_PROVIDER GROQ_API_KEYS
check_switch LLM_PROVIDER OPENROUTER_API_KEYS
check_switch STREAM_ASR_PROVIDER SARVAM_API_KEYS
check_switch STREAM_ASR_PROVIDER DEEPGRAM_API_KEY
check_switch STREAM_ASR_PROVIDER ASSEMBLYAI_API_KEY
check_switch TTS_PROVIDER SARVAM_API_KEYS

egress=$(printf '%s' "$(value_of ALLOW_EXTERNAL_AI)" | tr 'A-Z' 'a-z')
holds_hosted_key=0
for key in GEMINI_API_KEYS ANTHROPIC_API_KEY GROQ_API_KEYS OPENROUTER_API_KEYS \
           SARVAM_API_KEYS DEEPGRAM_API_KEY ASSEMBLYAI_API_KEY; do
  is_set "$key" && holds_hosted_key=1
done

if [ "$holds_hosted_key" = "1" ] && [ "$egress" != "true" ]; then
  bad "hosted provider keys are set, but ALLOW_EXTERNAL_AI=${egress:-false}."
  say "          Nothing may leave this machine until that is true. This is a"
  say "          deliberate gate, not a bug: a key appearing in a file must"
  say "          not opt a government deployment into egress on its own."
  say "          Set the repository VARIABLE ALLOW_EXTERNAL_AI=true once"
  say "          external AI is approved for this deployment."
fi

if [ "$holds_hosted_key" = "0" ]; then
  soft "no hosted provider keys are set. Voice and the AI-written narrative"
  say "          will be unavailable; petitions are still produced with the"
  say "          deterministic wording. This is a supported configuration."
fi

say ""
if [ "$fail" -gt 0 ]; then
  say "PREFLIGHT FAILED: $fail problem(s), $warn warning(s)."
  say "Nothing has been deployed and the running service is untouched."
  exit 1
fi
say "preflight passed ($warn warning(s))."
