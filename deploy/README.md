# Deployment runbook — Ai-Petition-Generator

Deployment-layer documentation only. **No application source code was modified.**

```
GitHub → GitHub Actions → SonarQube → Docker Build → Docker Hub (PRIVATE)
       → SSH (appleboy) → AWS EC2 → Docker Compose → Nginx → Application
```

| | |
|---|---|
| EC2 instance | `AI_Projects` — Ubuntu 24.04 LTS, t3.medium, x86_64 |
| Elastic IP | `3.7.47.247` |
| SSH user / port | `ubuntu` / `22` |
| App directory | `/opt/ai-petition-generator` |
| Compose project | `ai-petition-generator` |
| Container | `ai-petition-generator` |
| Named volume | `ai_petition_generator_var` |
| Reserved host port | `127.0.0.1:8000` |
| Image | `subashawsdevops/ai-petition-generator:<commit-sha>` |

---

## ⚠️ THIS EC2 HOSTS THREE APPLICATIONS

Ai-Petition-Generator is one of three. Every command in this runbook and in the
CI workflow is scoped to this application. **Never** run on this host:

```
docker compose down            # unscoped — hits whatever project you're in
docker system prune
docker image prune -af
docker stop $(docker ps -q)
docker rm  $(docker ps -aq)
```

How isolation is enforced:

| Resource | Value | Mechanism |
|---|---|---|
| Compose project | `ai-petition-generator` | top-level `name:` + explicit `-p` on every call |
| Container | `ai-petition-generator` | `container_name:` |
| Volume | `ai_petition_generator_var` | app-prefixed named volume |
| Host port | `127.0.0.1:8000` | pre-flight **fails** if another process holds it |
| Directory | `/opt/ai-petition-generator` | CI writes nowhere else |
| Env file | `<APP_DIR>/app.env` | host-only, never in an image |
| Nginx vhost | `ai-petition-generator` | separate file; app-prefixed identifiers |
| Image cleanup | `subashawsdevops/ai-petition-generator` only | tags removed by name, never `prune` |

The workflow also **snapshots every other container before and after** the
deploy (name, id, start time) and **fails** if any changed. It never attempts
to repair another application.

---

## ⚠️ Five application-specific facts

1. **`docker compose down -v` destroys every petition.** All citizen data —
   names, addresses, Aadhaar numbers, documents, attachments — lives in
   `ai_petition_generator_var`. No database server, no external store.
2. **`OPERATOR_TOKEN` is mandatory.** Behind a proxy the app's "loopback only"
   fallback sees a local address for every request, which would publish the
   admin screen.
3. **`LETTER_FONT=Noto Sans Tamil` is mandatory.** The app default `Nirmala UI`
   is a Windows font; on Linux Tamil renders as empty boxes.
4. **`--workers 1` is mandatory.** In-process asyncio locks, one SQLite
   checkpoint file, in-process catalog cache.
5. **Health gate is `GET /`**, never `/api/health` (which makes live outbound
   provider calls and runs a blocking `soffice --version`).

---

## 1. REQUIRED MANUAL CONFIGURATION

Nothing below was invented. Each must be supplied before first deploy.

| # | Value | Where |
|---|---|---|
| M1 | **Production domain (FQDN)** | `deploy/nginx/*.conf` → `server_name`, `ssl_certificate*`; `app.env` → `CORS_ORIGINS` |
| M2 | **`OPERATOR_TOKEN`** | generate on EC2, write to `app.env`. Never commit |
| M3 | **Admin CIDR** for `/operator` | both nginx confs, commented `allow` lines |
| M4 | **DNS A record** → `3.7.47.247` | your DNS provider |
| M5 | **Docker Hub login on EC2** | one-time, §3.5 |
| M6 | **EBS free space / RAM headroom** | §3.1 — shared with two other apps |

Optional (only if external AI is approved): provider API keys in `app.env`.

---

## 2. GitHub Secrets

All nine already configured. Verify only:

| Secret | Expected |
|---|---|
| `EC2_HOST` | `3.7.47.247` |
| `EC2_USER` | `ubuntu` |
| `EC2_SSH_PORT` | `22` |
| `EC2_APP_DIR` | `/opt/ai-petition-generator` |
| `DOCKERHUB_USERNAME` | `subashawsdevops` |
| `DOCKERHUB_TOKEN` | needs **read + write** (write to push from CI, read to pull on EC2) |
| `SONAR_HOST_URL`, `SONAR_TOKEN` | per company SonarQube |

Sonar project key is `Ai-Petition-Genrator` in `sonar-project.properties` —
set by you, left untouched.

---

## 3. EC2 one-time setup

Run once, as `ubuntu`. **None of these commands stop, modify or remove
anything belonging to the other two applications.**

### 3.1 Survey the host first

```bash
# What is already running? Record this before you change anything.
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Ports}}' 2>/dev/null || echo "docker not installed yet"

# Is port 8000 free? MUST be free (or held by our own container).
sudo ss -lntp | grep -E ':(80|443|8000)\s' || echo "8000 appears free"

# Headroom — 4 GiB RAM and one disk shared by three apps + LibreOffice.
free -h
df -h /
```

> If port 8000 is occupied by another application, **stop and tell me**. Do not
> free it by stopping their service. We will assign a different port and update
> `APP_PORT` plus `upstream ai_petition_upstream` together.

### 3.2 Docker Engine + Compose plugin

Skip if Docker is already installed for the other applications — just verify.

```bash
docker --version && docker compose version && echo "ALREADY INSTALLED - skip to 3.3"
```

If not installed:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
                        docker-buildx-plugin docker-compose-plugin

sudo usermod -aG docker ubuntu
# log out and back in, then:
docker --version && docker compose version
```

### 3.3 Application directory

```bash
sudo mkdir -p /opt/ai-petition-generator/backups
sudo chown -R ubuntu:ubuntu /opt/ai-petition-generator
ls -ld /opt/ai-petition-generator /opt/ai-petition-generator/backups
```

### 3.4 Persistent volume

```bash
docker volume create ai_petition_generator_var
docker volume inspect ai_petition_generator_var
```

On-disk: `/var/lib/docker/volumes/ai_petition_generator_var/_data`

### 3.5 Docker Hub login — ONE TIME (repository is PRIVATE)

The deployment does **not** send the token over SSH. Authenticate the host once:

```bash
docker login docker.io --username subashawsdevops
```

Paste the **access token** at the interactive password prompt. Then verify:

```bash
docker pull subashawsdevops/ai-petition-generator:latest && echo "PULL OK"
```

Credentials persist in `~/.docker/config.json` (base64, not encrypted):

```bash
chmod 600 ~/.docker/config.json
```

> If the token is ever rotated, re-run this command. Deploys will fail with a
> clear message pointing back here.

### 3.6 Runtime environment file

```bash
cd /opt/ai-petition-generator
# copy deploy/env/app.env.example from the repo to ./app.env, then:
chmod 600 app.env

# generate the operator token (M2) — shown once, paste into app.env
openssl rand -hex 32
```

Required in `app.env`:

```
OPERATOR_TOKEN=<the value you just generated>
LETTER_FONT=Noto Sans Tamil
CORS_ORIGINS=https://<your-domain>          # M1
DATA_DIR=/app/backend/var
PDF_ENGINE=libreoffice
SOFFICE_PATH=/usr/bin/soffice
HOST=0.0.0.0
PORT=8000
LOG_FORMAT=json
```

⚠️ Do **not** use `backend/.env.example` — it has drifted from
`backend/app/config.py` and specifies retired Sarvam TTS values (HTTP 400).

### 3.7 Compose file and scripts

CI ships `docker-compose.yml`, `backup.sh` and `rollback.sh` into
`/opt/ai-petition-generator` on every run. For the very first deploy the
directory only needs to **exist** with `app.env` in it — CI delivers the rest.

To place them manually first:

```bash
cd /opt/ai-petition-generator
# copy docker-compose.yml, deploy/scripts/backup.sh, deploy/scripts/rollback.sh here
chmod +x backup.sh rollback.sh
```

### 3.8 Nginx — two-phase, never break the other apps

Nginx is shared. A broken config means **no application can reload**. So:
always `nginx -t` first, and **never `systemctl restart nginx`** — use
`reload`, which keeps the running config if the new one is bad.

**Phase A — shared http-context directives**

```bash
sudo cp deploy/nginx/ai-petition-generator-shared.conf \
        /etc/nginx/conf.d/ai-petition-generator-shared.conf
```

All identifiers are `ai_petition_`-prefixed so they cannot collide with the
other applications' `$connection_upgrade` / `upstream` / zone names.

**Phase B — HTTP bootstrap (no TLS yet)**

```bash
sudo mkdir -p /var/www/html
sudo cp deploy/nginx/ai-petition-generator.conf \
        /etc/nginx/sites-available/ai-petition-generator
sudo nano /etc/nginx/sites-available/ai-petition-generator   # set server_name (M1), admin CIDR (M3)
sudo ln -s /etc/nginx/sites-available/ai-petition-generator /etc/nginx/sites-enabled/

sudo nginx -t          # MUST pass. If it fails, DO NOT reload — fix first.
sudo systemctl reload nginx
```

**Phase C — certificate**

DNS (M4) must resolve to `3.7.47.247` first.

```bash
sudo apt-get install -y certbot
sudo certbot certonly --webroot -w /var/www/html -d <your-domain>
```

`certonly --webroot` is used deliberately: `--nginx` would rewrite the config
file in place, and on a shared server predictable config beats convenience.

**Phase D — swap in TLS**

```bash
sudo cp deploy/nginx/ai-petition-generator-tls.conf \
        /etc/nginx/sites-available/ai-petition-generator
sudo nano /etc/nginx/sites-available/ai-petition-generator   # 4 replacements, see file header

sudo nginx -t          # MUST pass
sudo systemctl reload nginx
```

If `nginx -t` fails at any point, **stop**. The running nginx keeps serving the
old config, all three applications stay up, and nothing is lost.

### 3.9 Security Group

| Direction | Port | Source |
|---|---|---|
| Inbound | 443 | restricted CIDR (see note) |
| Inbound | 80 | `0.0.0.0/0` — redirect + ACME only |
| Inbound | 22 | your admin IP only |
| Inbound | **8000** | **NEVER** — loopback only |
| Outbound | 443 | Docker Hub; AI providers only if enabled |

> **Carried over from the application review:** this application has no
> end-user authentication. `GET /api/petitions` lists every petition with its
> session id, and `GET /api/sessions/{id}` returns the unmasked record
> including the Aadhaar number. Until an auth layer exists, restrict inbound
> 443 to a trusted CIDR/VPN. **No application code was changed to address
> this** — it is out of deployment scope.

---

## 4. First deployment

1. Complete §3 (all of it, including M1–M6).
2. Verify secrets in §2.
3. Push to `main` from a permitted account, or **Actions → Run workflow**.

Expected on first run: `sessions.sqlite not present (first deployment) - skipped`.

Verify:

```bash
cd /opt/ai-petition-generator
docker compose -p ai-petition-generator ps
curl -fsS http://127.0.0.1:8000/ | head -5
docker compose -p ai-petition-generator logs --tail=80
```

Then confirm Tamil PDF rendering — a file being produced is not the same as it
being readable:

```bash
docker compose -p ai-petition-generator exec app python scripts/verify_pdf.py
```

---

## 5. Subsequent automatic deployments

Push to `main` → Sonar → build **one** image → push → scp artifacts → SSH:

1. Verify `APP_DIR`, `docker-compose.yml`, `app.env`.
2. Verify Docker toolchain.
3. **Snapshot other applications' containers (before).**
4. Verify/create `ai_petition_generator_var`.
5. **Port pre-flight** — fail loudly if 8000 is held by anything else.
6. Pull the new image (fails with a login hint if auth expired).
7. **Back up SQLite** (`.backup` + `integrity_check`, chowned to host user).
8. Record previous tag, write new `.env`.
9. `docker compose -p ai-petition-generator up -d --remove-orphans`.
10. Poll `GET /` for up to 150 s.
11. On failure: dump logs, **auto-revert to previous tag**, fail the job.
12. **Snapshot other applications (after)** — fail if anything changed.
13. Prune old tags of **our image repo only**, keeping `latest` + current +
    previous + 3 most recent.

---

## 6. Rollback

### Automatic
`GET /` failure → revert to `.previous_tag` → job fails. Data untouched. Other
applications untouched.

### Manual

```bash
cd /opt/ai-petition-generator
./rollback.sh                    # previous tag
./rollback.sh <commit-sha>       # specific tag
```

By hand:

```bash
cd /opt/ai-petition-generator
cat .previous_tag
docker pull subashawsdevops/ai-petition-generator:<tag>
printf 'APP_IMAGE=subashawsdevops/ai-petition-generator\nIMAGE_TAG=<tag>\nAPP_PORT=8000\n' > .env
docker compose -p ai-petition-generator up -d
curl -fsS http://127.0.0.1:8000/
```

Immutable SHA tags mean rollback pulls the exact prior artifact — it does not
rebuild, so it is unaffected by the repository's unpinned dependencies.

### Data rollback — last resort

```bash
cd /opt/ai-petition-generator
docker compose -p ai-petition-generator stop        # NOT down, NOT -v
ls -1t backups/*.sqlite | head
docker run --rm --user 0:0 \
  -v ai_petition_generator_var:/data \
  -v /opt/ai-petition-generator/backups:/backups \
  --entrypoint /bin/sh subashawsdevops/ai-petition-generator:latest \
  -c 'cp /backups/<TIMESTAMP>-sessions.sqlite /data/sessions.sqlite'
docker compose -p ai-petition-generator up -d
```

⚠️ Discards every petition created since that backup.

---

## 7. Backups

Automatic before every deploy, 20 retained in
`/opt/ai-petition-generator/backups/`.

Manual / scheduled:

```bash
/opt/ai-petition-generator/backup.sh
```

```cron
0 2 * * * /opt/ai-petition-generator/backup.sh >> /var/log/petition-backup.log 2>&1
```

Check ownership occasionally — root-owned backups silently defeat retention and
fill a disk shared with two other applications:

```bash
ls -l /opt/ai-petition-generator/backups | head
df -h /
```

⚠️ On-instance backups do not survive instance loss. Add EBS snapshots and/or
an encrypted S3 copy. These files contain citizen data.

---

## 8. Multi-application isolation verification

Run **before** the first deploy to record a baseline, and **after** any deploy.

```bash
# 1. Baseline (run BEFORE deploying, keep the output)
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}' | sort | tee /tmp/apps-before.txt

# 2. After deployment — everything except our container must be identical
docker ps --format '{{.Names}}\t{{.Image}}\t{{.Ports}}' | sort > /tmp/apps-after.txt
diff <(grep -v '^ai-petition-generator' /tmp/apps-before.txt) \
     <(grep -v '^ai-petition-generator' /tmp/apps-after.txt) \
  && echo "ISOLATION OK — other applications unchanged"

# 3. Volumes — the other apps' volumes must all still exist
docker volume ls

# 4. Uptime of other containers — should NOT have reset
docker ps --format '{{.Names}}\t{{.Status}}'

# 5. Nginx — all sites still valid and serving
sudo nginx -t
ls -l /etc/nginx/sites-enabled/

# 6. Our resources only
docker compose -p ai-petition-generator ps
docker volume inspect ai_petition_generator_var
docker images subashawsdevops/ai-petition-generator
```

The CI workflow performs steps 1, 2 and 4 automatically and fails the
deployment on any difference — **without** attempting to repair the affected
application.

---

## 9. Reference

| Item | Value |
|---|---|
| Image | `subashawsdevops/ai-petition-generator` (PRIVATE) |
| Tags | `<commit-sha>` deployed; `latest` convenience |
| Compose project | `ai-petition-generator` |
| Container | `ai-petition-generator` |
| Container port | `8000` |
| Host binding | `127.0.0.1:8000` |
| Volume | `ai_petition_generator_var` |
| Volume on disk | `/var/lib/docker/volumes/ai_petition_generator_var/_data` |
| Data in container | `/app/backend/var` |
| App dir | `/opt/ai-petition-generator` |
| Runtime env | `<APP_DIR>/app.env` (600) |
| Compose vars | `<APP_DIR>/.env` (CI-written) |
| Entrypoint | `uvicorn app.main:app --workers 1` |
| Health | `curl -fsS http://127.0.0.1:8000/` |

```bash
cd /opt/ai-petition-generator
docker compose -p ai-petition-generator ps
docker compose -p ai-petition-generator logs -f --tail=100
docker compose -p ai-petition-generator exec app python scripts/verify_pdf.py
curl -s -H "x-operator-token: $TOKEN" http://127.0.0.1:8000/api/operator/status | python3 -m json.tool
```

Load government reference documents:

```bash
docker compose -p ai-petition-generator exec app \
  python scripts/ingest.py add <file-or-url> --official --provenance "<G.O. number>"
```
