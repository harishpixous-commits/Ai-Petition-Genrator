#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Roll the Citizen Petition Assistant back to a previous image tag.
#
# Install on the EC2 host as <APP_DIR>/rollback.sh and chmod +x.
#
#   ./rollback.sh              roll back to the tag recorded in .previous_tag
#   ./rollback.sh <commit-sha> roll back to a specific tag
#
# Every image is tagged with an immutable commit SHA, so this pulls the exact
# artifact that previously ran. It does NOT rebuild, so it is unaffected by the
# repository's unpinned Python dependencies.
#
# THIS SCRIPT NEVER TOUCHES CITIZEN DATA. The named volume is not removed,
# recreated or modified — only the container image changes.
# ---------------------------------------------------------------------------
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
VOLUME_NAME="${VOLUME_NAME:-ai_petition_generator_var}"
cd "${APP_DIR}"

if [ ! -f docker-compose.yml ]; then
  echo "FATAL: ${APP_DIR}/docker-compose.yml is missing."
  exit 1
fi
if [ ! -f app.env ]; then
  echo "FATAL: ${APP_DIR}/app.env is missing."
  exit 1
fi

APP_IMAGE="subashawsdevops/ai-petition-generator"
APP_PORT="8000"
CURRENT_TAG=""
if [ -f .env ]; then
  FOUND_IMAGE="$(grep -E '^APP_IMAGE=' .env | cut -d= -f2- || true)"
  FOUND_PORT="$(grep -E '^APP_PORT=' .env | cut -d= -f2- || true)"
  CURRENT_TAG="$(grep -E '^IMAGE_TAG=' .env | cut -d= -f2- || true)"
  [ -n "${FOUND_IMAGE}" ] && APP_IMAGE="${FOUND_IMAGE}"
  [ -n "${FOUND_PORT}" ] && APP_PORT="${FOUND_PORT}"
fi

# Target tag: argument, else .previous_tag.
TARGET_TAG="${1:-}"
if [ -z "${TARGET_TAG}" ]; then
  if [ -s .previous_tag ]; then
    TARGET_TAG="$(cat .previous_tag)"
  else
    echo "FATAL: no tag given and .previous_tag is empty."
    echo ""
    echo "Locally available tags:"
    docker images "${APP_IMAGE}" --format '    {{.Tag}}  ({{.CreatedSince}})'
    exit 1
  fi
fi

if [ "${TARGET_TAG}" = "${CURRENT_TAG}" ]; then
  echo "Already running ${TARGET_TAG}. Nothing to do."
  exit 0
fi

echo "==> Rolling back"
echo "    from: ${CURRENT_TAG:-<unknown>}"
echo "    to:   ${TARGET_TAG}"
echo "    data: ${VOLUME_NAME} (will NOT be touched)"
echo ""

# Back up before changing anything, exactly as a deployment would.
if [ -x "${APP_DIR}/backup.sh" ]; then
  echo "==> Pre-rollback backup"
  "${APP_DIR}/backup.sh"
else
  echo "==> WARNING: backup.sh not found - proceeding without a fresh backup"
fi

echo "==> Pulling ${APP_IMAGE}:${TARGET_TAG}"
docker pull "${APP_IMAGE}:${TARGET_TAG}"

# Preserve the tag we are leaving, so a rollback can itself be rolled back.
if [ -n "${CURRENT_TAG}" ]; then
  printf '%s\n' "${CURRENT_TAG}" > .previous_tag
fi

printf 'APP_IMAGE=%s\nIMAGE_TAG=%s\nAPP_PORT=%s\n' \
  "${APP_IMAGE}" "${TARGET_TAG}" "${APP_PORT}" > .env

# `down` WITHOUT -v. The named volume holds every petition.
echo "==> Replacing containers (volume preserved)"
docker compose down --remove-orphans
docker compose up -d

echo "==> Verifying GET http://127.0.0.1:${APP_PORT}/"
OK=0
for i in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:${APP_PORT}/" >/dev/null 2>&1; then
    OK=1
    echo "    responded after ${i} attempt(s)"
    break
  fi
  sleep 5
done

docker compose ps

if [ "${OK}" -ne 1 ]; then
  echo ""
  echo "ROLLBACK VERIFICATION FAILED - the application is not answering."
  echo "--- last 200 log lines ---"
  docker compose logs --tail=200 --no-color || true
  echo ""
  echo "Citizen data is intact in volume ${VOLUME_NAME}."
  echo "Try another tag:  ./rollback.sh <commit-sha>"
  docker images "${APP_IMAGE}" --format '    {{.Tag}}  ({{.CreatedSince}})'
  exit 1
fi

echo ""
echo "==> ROLLBACK SUCCESSFUL - now serving ${APP_IMAGE}:${TARGET_TAG}"
