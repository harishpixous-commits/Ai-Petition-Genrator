# Running the Citizen Petition Assistant

Written for: whoever operates the deployed service, and the administrator who
holds the credentials.

This covers the four things that need a decision or an action from a person:
the officer account, backups, what the tests gate, and the browser security
policy. Everything here was implemented and checked locally; the items that
need production credentials are marked **ADMINISTRATOR ACTION** and could not
be performed from a development machine.

---

## 1. The officer account

### Why it matters more than it looks

Until the first officer account exists, `citizen_scope()` returns "no
restriction" and **a saved petition can be opened by anyone who has its session
id**. Listing and deleting are already restricted to the browser that created
a petition, so this is narrower than it once was — but it is still a state to
end rather than to discover.

The service now says which state it is in, at start-up, in the log:

```
preflight.officers  provisioned=true
preflight.officers  provisioned=false  effect=... action=...
```

Search the container log for `preflight.officers` after any deployment.

### ADMINISTRATOR ACTION — provisioning

The officer database lives in the Docker volume on EC2. An account created on a
laptop does not travel, which is why a password that works against `127.0.0.1`
is rejected by the deployed site.

1. **Set the secret.** GitHub → Settings → Environments → `production` →
   add `OFFICER_PASSWORD`. Minimum 12 characters; the workflow refuses
   anything shorter. Generate it with a password manager — it is never typed
   into an input box and never appears in a log.

2. **Run the workflow.** Actions → *Create Officer Account* → *Run workflow*:

   | Input | Value |
   |---|---|
   | `username` | lowercase, no spaces, e.g. `collectorate` |
   | `name` | the name shown in the portal, e.g. `Harish` |

   The workflow is restricted to a named list of actors and runs in the
   `production` environment, so a required reviewer can be configured on it.

3. **Confirm.** Sign in at `/officer/login`. Then redeploy or restart and
   check the log says `provisioned=true`.

Re-running for an existing username **resets that account's password and
revokes its sessions**. That is the supported way to change one.

Equivalent manual command, if the workflow cannot be used:

```bash
docker exec -e OFFICER_PASSWORD='...' ai-petition-generator \
  python scripts/create_officer.py <username> --name "<Name>"
```

---

## 2. Backups

### What exists

| Script | What it does | Survives instance loss |
|---|---|---|
| `deploy/scripts/backup.sh` | online SQLite backup to `${APP_DIR}/backups` | **no** |
| `deploy/scripts/backup-offsite.sh` | encrypts it and puts it in S3 | yes |
| `deploy/scripts/restore-test.sh` | downloads, decrypts and checks a backup | — |
| `backend/scripts/verify_backup.py` | the same checks without the `sqlite3` CLI | — |

`backup.sh` already existed and is correct — it uses SQLite's online `.backup`
rather than copying a live file, which would frequently produce a corrupt copy.
What was missing is that it writes to the same EBS volume as the data it is
protecting. The other three close that.

### The data is sensitive

The session database holds names, addresses, telephone numbers and the full
text of grievances. **Encryption is not optional here.** `backup-offsite.sh`
encrypts on the host before upload (AES-256 via `gpg`, or `openssl` with
PBKDF2 at 200,000 iterations) *and* asks S3 for server-side encryption. Only
the first protects against someone who can read the bucket.

### ADMINISTRATOR ACTION — scheduling

1. Create a bucket with public access blocked, versioning on, and default
   encryption enabled.
2. Put the passphrase in AWS Secrets Manager — **not** in the instance's
   `.env`. Losing it means losing every backup.
3. Prefer an instance role over a long-lived access key on the host.
4. Install the cron entries:

```cron
15 2 * * *  cd /opt/ai-petition && ./backup.sh >>var/log/backup.log 2>&1
45 2 * * *  cd /opt/ai-petition && \
            BACKUP_PASSPHRASE="$(aws secretsmanager get-secret-value \
              --secret-id petition/backup --query SecretString --output text)" \
            S3_BUCKET=s3://your-bucket/petition \
            ./backup-offsite.sh >>var/log/backup-offsite.log 2>&1
30 3 * * 1  cd /opt/ai-petition && \
            BACKUP_PASSPHRASE="$(...)" S3_BUCKET=s3://your-bucket/petition \
            ./restore-test.sh >>var/log/restore-test.log 2>&1
```

Retention is 30 days off-instance (`RETAIN_DAYS`) and 20 files on-instance
(`RETAIN`).

### Restore test — what was actually proven

The round trip was run locally against the real 165 MB session database:

```
$ python scripts/verify_backup.py roundtrip var/sessions.sqlite
==> online backup of var/sessions.sqlite
  size              165,175,296 bytes
  header            SQLite format 3
  integrity_check   ok
  tables            2
      checkpoints                        9,295
      writes                            81,921
==> ROUND TRIP PASSED: the backup restores and is intact
```

**What that proves:** the online backup produces an intact, non-empty database
that opens and passes `integrity_check`. **What it does not prove:** the S3
upload, the encryption round trip or the retention sweep — those need the
bucket and the passphrase, and are the administrator action above. Run
`restore-test.sh` once by hand after the first off-site backup and keep the
output.

A backup nobody has restored is a hypothesis, not a backup.

### Current install state — read before the next release

`backup.sh`, `backup-offsite.sh` and `restore-test.sh` are present in
`deploy/scripts/` and all three pass `bash -n` under the test suite
(`backend/tests/test_deploy_scripts_syntax.py`). **None of them is scheduled
on the production host yet.** The cron entries above are documentation,
not an installed crontab. Scheduling them is deliberately an administrator
action because it binds the service to a specific S3 bucket, a specific
Secrets Manager entry and an instance IAM role, each of which is a decision
the administrator owns.

The round-trip was proven **locally only**, on this working tree, against
the real session database. The S3 upload, the encryption round trip and
the retention sweep still need a one-shot run by an administrator on the
production host before the schedule is turned on. Keep that run's log; it
is the first evidence that the end-to-end path works.

---

## 3. What the pipeline now gates

A `tests` job runs on every push and **`deploy` depends on it**, so a red suite
stops the deployment. Before this, the only gate was a `curl GET /` returning
200 on the host — which a service can do while every petition it produces is
wrong.

The job runs, in order: `ruff` over `app/ benchmarks/ scripts/`, the full
`pytest` suite, and the held-out classifier evaluation (reported, not gated).

**One step is conditional.** The four cross-language retrieval tests need a
real multilingual embedder; the offline fixture is a hashed bag of words with
no semantics, so asserting cross-language matching under it would be asserting
a lie. They run only where `GEMINI_API_KEY` is configured, and are
`continue-on-error` — a third party's rate limit must not block a deployment.

**ADMINISTRATOR ACTION (optional):** add `GEMINI_API_KEY` as a repository
secret to have those four run in CI. Without it they are skipped, loudly.

---

## 4. Browser security policy

A Content Security Policy is now sent on every response. The strict clause is
`script-src 'self'` with **no** `unsafe-inline` and no external hosts — which
is possible because the pages carry no inline `<script>`, no `on*=` handlers
and load nothing from a third party.

One concession: `style-src` allows `'unsafe-inline'`, because the citizen page
carries 19 `style="..."` attributes. An inline *style* cannot execute code, so
this is a much smaller exposure than the script case, and removing those
attributes is separate work with a real chance of visual regressions.

`tests/test_security_headers.py` holds both halves: the policy's directives,
and the markup staying compatible with it. If someone adds an inline handler,
that test fails rather than the feature silently not working in production.

`Permissions-Policy` grants the microphone and denies camera, geolocation,
payment, USB and the motion sensors by name.

---

## 5. Voice socket limits

`/ws/voice` is the most expensive endpoint and had no throttle at any layer.
It now has: 64 connections per process, 3 per client, 256 KiB per message,
8 MB per minute, and a 30-minute session cap.

**These are sized so a real citizen never meets them.** Audio arrives at about
32 KB/s, so a solid minute of continuous speech is ~1.9 MB — a quarter of the
allowance. `tests/test_ws_limits.py` drives ten minutes of realistic dictation
through the limiter and asserts it is never cut off, which matters more than
the limits firing: a limit that interrupts a citizen mid-grievance is worse
than the abuse it prevents.

Every refusal closes with a sayable reason, never a silent drop — somebody at a
kiosk whose microphone stops has to be told why.

The counters are per process, which is correct today because the service runs
one worker by design. **A multi-worker deployment would need them in Redis**;
that is noted in `app/api/ws_limits.py` rather than left to be discovered.
