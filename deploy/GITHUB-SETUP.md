# Turning on voice and AI — GitHub Settings only

**For:** a developer with admin on the repository.
**AWS or SSH access is not required.** Everything here is done in GitHub.

**Time:** about ten minutes, plus one deploy.

---

## 1. What is wrong

The live service at `https://ai-petition.pixoustech.app` collects details,
validates them and produces a Word/PDF petition correctly. What does not work
is the **voice agent** and the **AI-written narrative**.

**The keys were never the problem.** `app.env` on the EC2 contains:

```
LLM_PROVIDER=off
STREAM_ASR_PROVIDER=off
TTS_PROVIDER=off
ALLOW_EXTERNAL_AI=false
```

Those are the defaults the deployment template ships, and **a key does not
override a switch**. The service reads every key correctly and uses none,
then reports `provider: off` — which reads exactly like a key that does not
work. That is why this went unnoticed.

You can confirm the current state yourself:

```bash
curl -s https://ai-petition.pixoustech.app/api/health \
| python -c "import json,sys; d=json.load(sys.stdin); [print(k, d[k]) for k in ('language_model','dictation','spoken_replies')]"
```

Today it returns `provider: off` and `ok: false`.

---

## 2. What has already been done

Committed and pushed to `main` (commit `e258b8a`, both remotes). **No code
work is needed from you.**

- The deploy pipeline now generates `app.env` on the EC2 from GitHub Secrets,
  so credentials can be managed without SSH.
- It **derives** `LLM_PROVIDER`, `STREAM_ASR_PROVIDER` and `TTS_PROVIDER` from
  which keys are present. Nobody types those switches any more, so they can no
  longer contradict a key.
- A preflight step inspects the generated file and **fails the deploy** rather
  than shipping a broken configuration.
- `/api/health` gained a `credentials` block that names any key that is set
  and switched off.

The last deploy stopped safely at the preflight step because the values below
do not exist yet. **The running service was not touched.**

---

## 3. ⚠️ Read this before you add anything

`app.env` on the host is **regenerated on every deploy** from the values
below. If you set `OPERATOR_TOKEN` and `PUBLIC_ORIGIN` but leave the API keys
out, the regenerated file will have no API keys — overwriting anything a
previous engineer may have placed there by hand.

The script does back up the old file on the host first, but restoring it
needs SSH, which nobody currently has.

> **Add all five values in one sitting, or none of them.**

If you do not have the Sarvam and Gemini keys, they can be regenerated from
the Sarvam dashboard and Google AI Studio. Do not deploy until you have them.

---

## 4. The five values to add

**Settings → Secrets and variables → Actions**

### Secrets tab → *New repository secret*

| Name | Value | What it enables |
|---|---|---|
| `OPERATOR_TOKEN` | run `openssl rand -hex 32`, paste the output | The `/operator` admin screen. Required — the deploy aborts without it. |
| `SARVAM_API_KEYS` | the Sarvam key | **Both** speech-to-text and text-to-speech. One key, both halves of the voice agent. |
| `GEMINI_API_KEYS` | the Gemini key | The AI-written petition narrative. |

### Variables tab → *New repository variable*

> This is a **different tab** on the same page. These are not secrets.

| Name | Value | Why a variable |
|---|---|---|
| `PUBLIC_ORIGIN` | `https://ai-petition.pixoustech.app` | Becomes `CORS_ORIGINS`. The Android app's origins are appended automatically. |
| `ALLOW_EXTERNAL_AI` | `true` | See below. |

### Formatting rules

- **No quotes.** `SARVAM_API_KEYS="abc"` — Docker Compose keeps the quote
  marks as part of the value, unlike a shell. The preflight step will catch
  this, but it is easier not to do it.
- **Multiple keys:** comma-separated, no spaces — `key1,key2`. The service
  fails over between them in order.
- **No trailing whitespace.**

### About `ALLOW_EXTERNAL_AI`

This is the switch that permits the citizen's **name, address, Aadhaar number
and grievance** to leave our server for Sarvam and Google.

It is deliberately **not** derived from the keys. A key appearing in a file
must not opt a government deployment into egress as a side effect — that has
to be a separate, deliberate, visible act. It is a *variable* rather than a
secret precisely so it is readable on the settings page and auditable.

**Please confirm external AI is approved for this deployment before setting
it to `true`.** Without it, the service still works: it collects every detail,
validates it, and produces the petition using the standard deterministic
wording. Only voice and the AI-written opening paragraph are unavailable.

---

## 5. Optional: require approval for deploys

**Settings → Environments**

The workflow references an environment named `production`. GitHub creates it
automatically on the first run. If you want a human approval step before each
deploy reaches the server, open it and add yourself under **Required
reviewers**.

The sister application on this host already does this.

---

## 6. Deploy

1. **Actions** → *Build, Analyze and Deploy* → find the most recent failed run
2. **Re-run all jobs**
3. Expand the step **"Write runtime environment file from repository secrets"**

It must print:

```
ALLOW_EXTERNAL_AI   = true
LLM_PROVIDER        = auto
STREAM_ASR_PROVIDER = auto
TTS_PROVIDER        = auto

  credentials supplied:
    GEMINI_API_KEYS
    SARVAM_API_KEYS
```

If any switch still says `off`, the matching secret was not saved.

4. The next step, **"Preflight the runtime environment file"**, must end with
   `preflight passed`.

Neither step ever prints a key value — only variable names.

---

## 7. Verify it worked

### Confirm the new build is actually live

```bash
curl -s https://ai-petition.pixoustech.app/api/health | grep -o '"credentials"'
```

Output means the new code is running. **No output means the deploy did not
reach the server** — go back and read the workflow log; do not continue.

### Check the three providers

```bash
curl -s https://ai-petition.pixoustech.app/api/health \
| python -c "import json,sys; d=json.load(sys.stdin); [print(k, d[k]) for k in ('language_model','dictation','spoken_replies')]"
```

| Feature | Expected |
|---|---|
| Gemini | `language_model` → `available: true`, `provider: "gemini"`, `egress: true` |
| Sarvam STT | `dictation` → `ok: true`, `provider: "Sarvam saarika"` |
| Sarvam TTS | `spoken_replies` → `ok: true`, `provider: "Sarvam"` |

### Prove the keys actually work

`/api/health` reports *configuration*. To make real API calls:

```
https://ai-petition.pixoustech.app/operator?token=<the OPERATOR_TOKEN you set>
```

Providers panel → **Check keys**. It probes each key once and reports by
**position** (`key 1: ok`, `key 2: quota exceeded`), never by value.

Note: the Sarvam probe calls the text-to-speech endpoint. It proves the key is
valid; STT uses the same credential against a different endpoint.

### End-to-end

Open the site → **Start Voice** → speak an answer → listen for the spoken
reply. That exercises STT → workflow → TTS in one pass.

---

## 8. If something fails

Three places report the problem, in the order you will meet them. None print
a key value.

| Symptom | Where to look |
|---|---|
| Deploy fails at preflight | The workflow log names the exact variable at fault |
| Site loads but voice is off | `/api/health` → `credentials.ok: false` lists each key that is set and switched off |
| Need detail | Requires SSH: `docker logs ai-petition-generator \| grep credential_unused` |

**`quota exceeded` / HTTP 402 from a Sarvam key** is a billing problem, not a
configuration one. One Sarvam key was returning 402 during earlier testing. If
you have two keys, put the working one **first** — the service tries them in
order.

---

## 9. Do not

- **Do not** put keys into `deploy/env/app.env.example`. It is reference
  documentation and is committed to the repository.
- **Do not** set `LLM_PROVIDER`, `STREAM_ASR_PROVIDER` or `TTS_PROVIDER` as
  secrets or variables. They are derived. Setting them by hand reintroduces
  the exact bug this change removes.
- **Do not** edit `app.env` on the EC2 by hand. The next deploy overwrites it.
  Change the value in GitHub and re-run the workflow.
- **Do not** set `CORS_ORIGINS` to `*`. The service runs
  `allow_credentials=True`, and `*` would make Starlette reflect any caller's
  origin back.

---

## 10. Contact

Raised by the application team after the live service was found to have voice
and AI disabled with valid keys in place. The DevOps engineer with EC2 access
is currently unavailable, which is why this route exists — it needs GitHub
admin only.
