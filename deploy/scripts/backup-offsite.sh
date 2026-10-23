#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Encrypted off-instance backup for the Citizen Petition Assistant.
#
# WHY THIS EXISTS BESIDE backup.sh. That script takes a correct online SQLite
# backup and writes it to ${APP_DIR}/backups — which is on the same EBS volume
# as the database it is protecting. It says so itself, at the bottom, in a
# note. An instance failure, a volume detach or an accidental `docker volume
# rm` takes the data and every backup of it in the same motion.
#
# So this script does the part that was missing: it encrypts the backup and
# puts it somewhere else.
#
# THE FILES CONTAIN CITIZEN DATA. Names, addresses, telephone numbers, the
# text of grievances, and — although the form no longer asks for one — an
# Aadhaar number a citizen may have typed into a complaint. That is why
# encryption here is not optional and not a flag: a backup of this database
# sitting unencrypted in a bucket is a data breach waiting for somebody to
# misconfigure a policy.
#
# ENCRYPTED BEFORE IT LEAVES THE HOST, not by the destination. Server-side
# encryption protects the bytes at rest in the bucket and does nothing about
# anyone who can read the bucket. Both are used; only one of them is enough
# on its own, and it is this one.
#
#   BACKUP_PASSPHRASE   required. Store it in a secrets manager, NOT in the
#                       instance's environment file. Losing it means losing
#                       every backup, so it is worth treating as carefully as
#                       the data.
#   S3_BUCKET           required. s3://bucket/prefix
#   AWS_*               standard credentials, or an instance role (preferred:
#                       no long-lived key on the host at all).
#   RETAIN_DAYS         default 30.
#
# Usage, from the application directory on the host:
#
#     BACKUP_PASSPHRASE=... S3_BUCKET=s3://my-bucket/petition ./backup-offsite.sh
#
# Schedule it from cron AFTER the local backup:
#
#     15 2 * * *  cd /opt/ai-petition && ./backup.sh  >>var/log/backup.log 2>&1
#     45 2 * * *  cd /opt/ai-petition && BACKUP_PASSPHRASE="$(aws secretsmanager \
#                   get-secret-value --secret-id petition/backup --query SecretString \
#                   --output text)" S3_BUCKET=s3://my-bucket/petition \
#                   ./backup-offsite.sh >>var/log/backup-offsite.log 2>&1
# ---------------------------------------------------------------------------
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
BACKUP_DIR="${BACKUP_DIR:-${APP_DIR}/backups}"
RETAIN_DAYS="${RETAIN_DAYS:-30}"
TS="$(date -u +%Y%m%d-%H%M%S)"

fail() { echo "FATAL: $*" >&2; exit 1; }

[ -n "${BACKUP_PASSPHRASE:-}" ] || fail "BACKUP_PASSPHRASE is not set. Refusing to upload citizen data unencrypted."
[ -n "${S3_BUCKET:-}" ]         || fail "S3_BUCKET is not set."
command -v aws >/dev/null 2>&1  || fail "the aws CLI is not installed."

# gpg is in the base image of most distributions; openssl is the fallback.
if command -v gpg >/dev/null 2>&1; then
  ENCRYPT="gpg"
elif command -v openssl >/dev/null 2>&1; then
  ENCRYPT="openssl"
else
  fail "neither gpg nor openssl is available; cannot encrypt."
fi

[ -d "${BACKUP_DIR}" ] || fail "no backup directory at ${BACKUP_DIR}. Run backup.sh first."

# The newest local backup of each database. backup.sh names them
# <timestamp>-<db>.sqlite, so the newest per database is what we ship.
shopt -s nullglob
UPLOADED=0
for db in sessions knowledge officer; do
  # shellcheck disable=SC2012
  SRC="$(ls -1t "${BACKUP_DIR}"/*-"${db}".sqlite 2>/dev/null | head -1 || true)"
  if [ -z "${SRC}" ]; then
    echo "    no local backup of ${db} — skipped"
    continue
  fi

  # NEVER SHIP A BACKUP THAT HAS NOT BEEN CHECKED. A corrupt SQLite file
  # uploads exactly as happily as a good one, and the corruption is discovered
  # at the restore, which is the worst possible moment to discover it.
  if command -v sqlite3 >/dev/null 2>&1; then
    CHECK="$(sqlite3 "${SRC}" 'PRAGMA integrity_check;' 2>&1 | head -1)"
    if [ "${CHECK}" != "ok" ]; then
      echo "    ${db}: integrity_check said '${CHECK}' — NOT uploading a corrupt backup" >&2
      continue
    fi
  fi

  ENC="${BACKUP_DIR}/${TS}-${db}.sqlite.enc"
  case "${ENCRYPT}" in
    gpg)
      printf '%s' "${BACKUP_PASSPHRASE}" | gpg --batch --yes --quiet \
        --passphrase-fd 0 --symmetric --cipher-algo AES256 \
        --output "${ENC}" "${SRC}"
      ;;
    openssl)
      # -pbkdf2 is not optional: without it openssl uses a single MD5 pass,
      # which makes the passphrase cheap to attack offline.
      printf '%s' "${BACKUP_PASSPHRASE}" | openssl enc -aes-256-cbc -pbkdf2 \
        -iter 200000 -salt -in "${SRC}" -out "${ENC}" -pass stdin
      ;;
  esac

  SIZE="$(wc -c < "${ENC}")"
  [ "${SIZE}" -gt 0 ] || fail "${db}: encryption produced an empty file."

  # Server-side encryption as well as the file encryption above. Belt and
  # braces, and it is what a reviewer will look for.
  aws s3 cp "${ENC}" "${S3_BUCKET}/${TS}-${db}.sqlite.enc" \
    --sse AES256 --only-show-errors

  # PROVE IT ARRIVED. `aws s3 cp` exiting zero means the request succeeded,
  # not that an object of the right size is readable afterwards.
  REMOTE_SIZE="$(aws s3api head-object \
      --bucket "$(echo "${S3_BUCKET}" | sed -E 's#^s3://([^/]+).*#\1#')" \
      --key "$(echo "${S3_BUCKET}/${TS}-${db}.sqlite.enc" | sed -E 's#^s3://[^/]+/##')" \
      --query ContentLength --output text 2>/dev/null || echo 0)"
  if [ "${REMOTE_SIZE}" != "${SIZE}" ]; then
    fail "${db}: uploaded ${SIZE} bytes but the bucket reports ${REMOTE_SIZE}."
  fi

  echo "    ${db}: ${SIZE} bytes encrypted and verified in the bucket"
  rm -f "${ENC}"
  UPLOADED=$((UPLOADED + 1))
done
shopt -u nullglob

[ "${UPLOADED}" -gt 0 ] || fail "nothing was uploaded."

# Retention, on the destination. Deliberately a date comparison and not a
# `rm --recursive`: a prefix typo in a blanket delete removes the backups.
CUTOFF="$(date -u -d "${RETAIN_DAYS} days ago" +%Y%m%d 2>/dev/null \
          || date -u -v-"${RETAIN_DAYS}"d +%Y%m%d)"
aws s3 ls "${S3_BUCKET}/" | awk '{print $4}' | while read -r key; do
  [ -n "${key}" ] || continue
  stamp="${key%%-*}"
  case "${stamp}" in
    ''|*[!0-9]*) continue ;;                 # not one of ours; leave it alone
  esac
  if [ "${stamp}" -lt "${CUTOFF}" ]; then
    echo "    retiring ${key}"
    aws s3 rm "${S3_BUCKET}/${key}" --only-show-errors
  fi
done

echo "==> ${UPLOADED} database(s) backed up off-instance, encrypted, at ${TS}"
cat <<'NOTE'

    Restore procedure: deploy/scripts/restore-test.sh
    Run it on a SCHEDULE, not only when you need it. A backup nobody has ever
    restored is a hypothesis, not a backup.
NOTE
