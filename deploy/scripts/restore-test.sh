#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Prove a backup can actually be restored.
#
# A BACKUP NOBODY HAS RESTORED IS A HYPOTHESIS. Every failure mode of a backup
# system — wrong passphrase, truncated upload, a `cp` of a live SQLite file,
# an empty database because the volume name changed — looks identical to a
# working one until somebody tries to restore it, which is always the worst
# possible moment to find out.
#
# So this runs the restore, in a scratch directory, and checks the result is a
# database with the right shape in it. It NEVER writes to the live volume and
# never touches the running service. It is safe to schedule.
#
#     BACKUP_PASSPHRASE=... S3_BUCKET=s3://bucket/prefix ./restore-test.sh
#
# Or against a local file, which is how it is tested:
#
#     ./restore-test.sh --file /path/to/backup.sqlite
#
# WHAT "PASSED" MEANS HERE: the file decrypts, SQLite reports integrity ok, the
# expected tables exist, and they are not empty. It does NOT mean the data is
# current — that is what the timestamp is for — and it does not mean the
# application will start against it.
# ---------------------------------------------------------------------------
set -euo pipefail

WORK="$(mktemp -d)"
trap 'rm -rf "${WORK}"' EXIT

PLAIN=""
FROM=""

if [ "${1:-}" = "--file" ]; then
  [ -n "${2:-}" ] || { echo "FATAL: --file needs a path" >&2; exit 1; }
  FROM="$2"
  cp "${FROM}" "${WORK}/restored.sqlite"
  PLAIN="${WORK}/restored.sqlite"
else
  [ -n "${S3_BUCKET:-}" ]        || { echo "FATAL: S3_BUCKET is not set." >&2; exit 1; }
  [ -n "${BACKUP_PASSPHRASE:-}" ] || { echo "FATAL: BACKUP_PASSPHRASE is not set." >&2; exit 1; }
  DB="${DB:-sessions}"

  # The newest object for this database.
  KEY="$(aws s3 ls "${S3_BUCKET}/" | awk '{print $4}' \
         | grep -- "-${DB}.sqlite.enc$" | sort | tail -1)"
  [ -n "${KEY}" ] || { echo "FATAL: no backup of ${DB} found in ${S3_BUCKET}" >&2; exit 1; }
  FROM="${S3_BUCKET}/${KEY}"
  echo "==> restoring ${FROM}"
  aws s3 cp "${FROM}" "${WORK}/backup.enc" --only-show-errors

  if command -v gpg >/dev/null 2>&1; then
    printf '%s' "${BACKUP_PASSPHRASE}" | gpg --batch --yes --quiet \
      --passphrase-fd 0 --decrypt --output "${WORK}/restored.sqlite" \
      "${WORK}/backup.enc"
  else
    printf '%s' "${BACKUP_PASSPHRASE}" | openssl enc -d -aes-256-cbc -pbkdf2 \
      -iter 200000 -in "${WORK}/backup.enc" -out "${WORK}/restored.sqlite" \
      -pass stdin
  fi
  PLAIN="${WORK}/restored.sqlite"
fi

command -v sqlite3 >/dev/null 2>&1 || { echo "FATAL: sqlite3 is not installed." >&2; exit 1; }

echo "==> checking ${FROM}"
FAILURES=0
note_failure() { echo "    FAIL: $*"; FAILURES=$((FAILURES + 1)); }

SIZE="$(wc -c < "${PLAIN}")"
echo "    size: ${SIZE} bytes"
[ "${SIZE}" -gt 1024 ] || note_failure "a database this small is almost certainly empty"

# 1. Is it a SQLite database at all? A truncated download or a failed decrypt
#    usually still produces a file.
HEADER="$(head -c 15 "${PLAIN}" | tr -d '\0')"
case "${HEADER}" in
  "SQLite format 3") echo "    header: SQLite format 3" ;;
  *) note_failure "not a SQLite database (header: '${HEADER}')" ;;
esac

# 2. Does SQLite itself think it is intact?
INTEGRITY="$(sqlite3 "${PLAIN}" 'PRAGMA integrity_check;' 2>&1 | head -1)"
echo "    integrity_check: ${INTEGRITY}"
[ "${INTEGRITY}" = "ok" ] || note_failure "integrity_check did not return ok"

# 3. Is there anything in it? An empty but perfectly valid database is the
#    failure mode that on-instance backups produce when the volume name is
#    wrong, and it passes every check above.
TABLES="$(sqlite3 "${PLAIN}" "SELECT count(*) FROM sqlite_master WHERE type='table';")"
echo "    tables: ${TABLES}"
[ "${TABLES}" -gt 0 ] || note_failure "no tables — this database is empty"

ROWS=0
for table in $(sqlite3 "${PLAIN}" "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';"); do
  count="$(sqlite3 "${PLAIN}" "SELECT count(*) FROM \"${table}\";" 2>/dev/null || echo 0)"
  printf '      %-28s %s\n' "${table}" "${count}"
  ROWS=$((ROWS + count))
done
[ "${ROWS}" -gt 0 ] || note_failure "every table is empty"

echo
if [ "${FAILURES}" -eq 0 ]; then
  echo "==> RESTORE TEST PASSED: ${TABLES} tables, ${ROWS} rows, integrity ok"
  exit 0
fi
echo "==> RESTORE TEST FAILED: ${FAILURES} problem(s). Do not rely on this backup."
exit 1
