#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# On-demand SQLite backup for the Citizen Petition Assistant.
#
# Install on the EC2 host as <APP_DIR>/backup.sh and chmod +x.
# Safe to run while the application is serving traffic.
#
# Uses SQLite's ONLINE .backup command. A plain `cp` of a live SQLite database
# is NOT a backup: the -wal and -shm sidecars mean the copy is frequently
# corrupt and the corruption is not detected until a restore is attempted.
# ---------------------------------------------------------------------------
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
VOLUME_NAME="${VOLUME_NAME:-ai_petition_generator_var}"
BACKUP_DIR="${APP_DIR}/backups"
RETAIN="${RETAIN:-20}"
TS="$(date -u +%Y%m%d-%H%M%S)"

# Resolve the image from the compose .env so the backup uses the same build
# that is currently deployed.
if [ -f "${APP_DIR}/.env" ]; then
  # shellcheck disable=SC1091
  APP_IMAGE="$(grep -E '^APP_IMAGE=' "${APP_DIR}/.env" | cut -d= -f2- || true)"
  IMAGE_TAG="$(grep -E '^IMAGE_TAG=' "${APP_DIR}/.env" | cut -d= -f2- || true)"
fi
APP_IMAGE="${APP_IMAGE:-subashawsdevops/ai-petition-generator}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

mkdir -p "${BACKUP_DIR}"

echo "==> Backing up ${VOLUME_NAME} -> ${BACKUP_DIR} (prefix ${TS})"

if ! docker volume inspect "${VOLUME_NAME}" >/dev/null 2>&1; then
  echo "FATAL: volume ${VOLUME_NAME} does not exist. Nothing to back up."
  exit 1
fi

HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

docker run --rm --user 0:0 \
  -e "TS=${TS}" \
  -e "HOST_UID=${HOST_UID}" \
  -e "HOST_GID=${HOST_GID}" \
  -v "${VOLUME_NAME}":/data \
  -v "${BACKUP_DIR}":/backups \
  --entrypoint /bin/sh \
  "${APP_IMAGE}:${IMAGE_TAG}" -c '
    set -eu
    found=0
    for db in sessions knowledge; do
      src="/data/${db}.sqlite"
      dst="/backups/${TS}-${db}.sqlite"
      if [ -f "$src" ]; then
        found=1
        echo "    backing up ${db}.sqlite"
        sqlite3 "$src" ".backup ${dst}"
        printf "    integrity: "
        sqlite3 "$dst" "PRAGMA integrity_check;" | head -1
      else
        echo "    ${db}.sqlite not present - skipped"
      fi
    done
    [ "$found" -eq 1 ] || echo "    no databases found (service may never have run)"

    # LOAD-BEARING. The container writes as root (it must, to read the volume
    # and write the host directory regardless of host ownership). Without this
    # chown the backups stay root-owned, the retention sweep below runs as the
    # unprivileged login user, its rm silently fails, backups accumulate
    # forever and eventually fill the EBS volume SHARED WITH TWO OTHER
    # APPLICATIONS. Do not remove.
    chown -R "${HOST_UID}:${HOST_GID}" /backups
  '

# Retain the most recent N backups. Never a blanket delete.
ls -1t "${BACKUP_DIR}"/*.sqlite 2>/dev/null \
  | tail -n +$((RETAIN + 1)) | xargs -r rm -f || true

# Prove retention actually worked. A silent failure here is how a shared disk
# fills up, so it is reported rather than swallowed.
REMAINING="$(ls -1 "${BACKUP_DIR}"/*.sqlite 2>/dev/null | wc -l)"
if [ "${REMAINING}" -gt "${RETAIN}" ]; then
  echo "WARNING: ${REMAINING} backups present but RETAIN=${RETAIN}."
  echo "         Old backups are not being deleted - check ownership:"
  echo "           ls -l ${BACKUP_DIR}"
  echo "         Files must be owned by $(id -un), not root."
fi

echo "==> Done. Current backups:"
ls -lh "${BACKUP_DIR}" | tail -n +2 | tail -5

cat <<'NOTE'

NOTE: these backups live on the same EBS volume as the data they protect and
      do NOT survive instance loss. Pair this with EBS snapshots (AWS Backup)
      and/or an encrypted S3 copy. The files contain citizen data — names,
      addresses and Aadhaar numbers — so any destination must be encrypted.
NOTE
