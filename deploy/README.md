# Deployment runbook — Citizen Petition Assistant

Deployment-layer documentation only. **No application source code was modified
to enable any of this.**

```
GitHub → GitHub Actions → SonarQube → Docker Build → Docker Hub
       → SSH (appleboy/ssh-action) → AWS EC2 → Docker Compose → Nginx → Application
```

---

## ⚠️ Read this first — five things that are specific to this application

1. **`docker compose down -v` destroys every petition.** All citizen data —
   names, addresses, Aadhaar numbers, generated documents, uploaded
   attachments — lives in the named volume `ai_petition_generator_var`. There
   is no database server and no external store to recover from. The deployment
   uses `down` **without** `-v`, and backs up SQLite before touching anything.

2. **`OPERATOR_TOKEN` is mandatory, not optional.** The application grants
   access to the operator screen when the token is unset *and* the request
   comes from loopback. Behind Nginx (and behind Docker's bridge) every request
   appears local, so an unset token publishes the admin screen to the internet.

3. **`LETTER_FONT=Noto Sans Tamil` is mandatory.** The application's default is
   `Nirmala UI`, a Windows font. On Linux that produces a PDF whose Tamil is
   drawn as empty boxes.

4. **`--workers 1` is mandatory.** The application uses in-process
   `asyncio.Lock` session serialisation, a single SQLite checkpoint file, and
   an in-process catalog cache. More than one worker corrupts session state.

5. **Deployment is verified with `GET /`, never `/api/health`.** The health
   endpoint makes live outbound calls to every configured AI provider and runs
   a blocking `soffice --version` subprocess.

---

## 1. Repository files added (deployment layer only)

| File | Purpose |
|---|---|
| `Dockerfile` | Multi-stage production image: Python 3.12, LibreOffice, Noto Tamil fonts, non-root user |
| `.dockerignore` | Keeps `backend/var` (citizen data) and any `.env` out of image layers |
| `docker-compose.yml` | One service, named volume, loopback port publish, `GET /` healthcheck |
| `sonar-project.properties` | SonarQube scanner configuration |
| `.github/workflows/deploy.yml` | The pipeline |
| `deploy/nginx/ai-petition-generator.conf` | Reverse proxy, TLS, body cap, rate limit, WebSocket |
| `deploy/env/app.env.example` | Template for the host-side runtime environment file |
| `deploy/scripts/backup.sh` | Manual on-demand SQLite backup |
| `deploy/scripts/rollback.sh` | Manual rollback to any previous image tag |
| `deploy/README.md` | This file |

**Nothing under `backend/app/` was changed.**

---

## 2. GitHub Secrets required

Set under **Settings → Secrets and variables → Actions**.

| Secret | Example / notes |
|---|---|
| `SONAR_TOKEN` | SonarQube user token |
| `SONAR_HOST_URL` | e.g. `https://sonarqube.company.internal` |
| `DOCKERHUB_USERNAME` | `subashawsdevops` |
| `DOCKERHUB_TOKEN` | Docker Hub **access token**, not the account password |
| `EC2_HOST` | EC2 public IP or DNS name |
| `EC2_USER` | `ubuntu` |
| `EC2_SSH_KEY` | Full private key, including the BEGIN/END lines |
| `EC2_SSH_PORT` | `22` |
| `EC2_APP_DIR` | **`/opt/ai-petition-generator`** — see the note below |

### Why `/opt/ai-petition-generator` and not `/home/ubuntu/app`

`/home/ubuntu/app` is the company's existing convention, and this analysis
**could not verify whether that path is already in use on the target
instance**. Deploying into an occupied directory would overwrite another
application's compose file and could stop its containers.

A distinct directory is used so this deployment cannot collide with anything
already running. If the instance is dedicated to this application and
`/home/ubuntu/app` is confirmed free, change the `EC2_APP_DIR` secret — nothing
else needs editing.

**Before the first deployment, confirm on the instance:**

```bash
ls -la /home/ubuntu/app 2>/dev/null && echo "IN USE — do not deploy here"
docker ps --format '{{.Names}}\t{{.Ports}}'      # is a container already on 8000?
sudo ss -lntp | grep -E ':(80|443|8000)\s'       # is the port free?
```

If port 8000 is occupied, set a different `APP_PORT` (see step 3.6) and update
`upstream petition_app` in the Nginx config to match.

---

## 3. EC2 one-time setup

Run **once**, before the first pipeline deployment. Ubuntu 22.04 or 24.04 —
the host Python version is irrelevant because the container supplies 3.12.

**None of these commands delete data or touch an existing deployment.**

### 3.1 Base packages

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg nginx sqlite3
```

### 3.2 Docker Engine + Compose plugin

```bash
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

sudo usermod -aG docker ubuntu     # log out and back in for this to take effect
docker --version
docker compose version
```

### 3.3 Deployment directory

```bash
sudo mkdir -p /opt/ai-petition-generator/backups
sudo chown -R ubuntu:ubuntu /opt/ai-petition-generator
```

### 3.4 Compose file

The pipeline does **not** copy `docker-compose.yml`; it only writes `.env` and
runs compose. Place the file once:

```bash
cd /opt/ai-petition-generator
curl -fsSL -o docker-compose.yml \
  https://raw.githubusercontent.com/<ORG>/<REPO>/main/docker-compose.yml
```

Or `scp` it from a checkout. Re-copy it whenever `docker-compose.yml` changes
in the repository.

### 3.5 Runtime environment file

```bash
cd /opt/ai-petition-generator
# copy deploy/env/app.env.example from the repository, then:
chmod 600 app.env
```

Edit `app.env` and set at minimum:

```
OPERATOR_TOKEN=<openssl rand -hex 32>
LETTER_FONT=Noto Sans Tamil
CORS_ORIGINS=https://<your-domain>
DATA_DIR=/app/backend/var
PDF_ENGINE=libreoffice
SOFFICE_PATH=/usr/bin/soffice
HOST=0.0.0.0
PORT=8000
LOG_FORMAT=json
```

⚠️ Do **not** use `backend/.env.example` as the template — it has drifted from
`backend/app/config.py` and specifies retired Sarvam TTS values that answer
HTTP 400.

### 3.6 Persistent storage

Created automatically by the pipeline on first run. To pre-create it:

```bash
docker volume create ai_petition_generator_var
docker volume inspect ai_petition_generator_var
```

**On-disk location:** `/var/lib/docker/volumes/ai_petition_generator_var/_data`

To run on a port other than 8000:

```bash
printf 'APP_PORT=8080\n' >> /opt/ai-petition-generator/.env
```

The pipeline preserves an existing `APP_PORT` across deployments.

### 3.7 Nginx

```bash
sudo cp deploy/nginx/ai-petition-generator.conf \
        /etc/nginx/sites-available/ai-petition-generator
sudo nano /etc/nginx/sites-available/ai-petition-generator   # replace CHANGE-ME values
sudo ln -s /etc/nginx/sites-available/ai-petition-generator \
           /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 3.8 TLS

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d <your-domain>
```

HTTPS is **functionally required**: browsers only grant microphone access in a
secure context, so the voice interface does not work over plain HTTP.

### 3.9 Security Group

| Direction | Port | Source | Notes |
|---|---|---|---|
| Inbound | 443 | Restricted CIDR or `0.0.0.0/0` | See the security note below |
| Inbound | 80 | `0.0.0.0/0` | Redirect + ACME challenge only |
| Inbound | 22 | Your admin IP only | For SSH deployment |
| Inbound | **8000** | **NEVER** | Published to host loopback only |
| Outbound | 443 | `0.0.0.0/0` | Docker Hub pulls; AI providers only if enabled |

> **Security note carried over from the application review:** this application
> has no end-user authentication. `GET /api/petitions` lists every petition
> with its session id, and `GET /api/sessions/{id}` returns the unmasked record
> including the Aadhaar number. Until an authentication layer exists, inbound
> 443 should be restricted to a trusted CIDR or VPN rather than opened to
> `0.0.0.0/0`. This is a deployment-scope decision; **no application code was
> changed to address it.**

---

## 4. First deployment

1. Complete every step in section 3.
2. Add all GitHub Secrets from section 2.
3. Confirm the SonarQube project key in `sonar-project.properties` matches the
   project in your SonarQube instance.
4. Push to `main` from one of the permitted accounts, or run the workflow
   manually via **Actions → Build, Analyze and Deploy → Run workflow**.

On the first run the SQLite backup step reports
`sessions.sqlite not present (first deployment) - skipped` — that is expected.

Verify:

```bash
cd /opt/ai-petition-generator
docker compose ps
curl -fsS http://127.0.0.1:8000/ | head -5
curl -s http://127.0.0.1:8000/api/health | python3 -m json.tool
docker compose logs --tail=80
```

Then confirm Tamil PDF rendering end to end — a file being produced is not the
same as it being readable:

```bash
docker compose exec app python scripts/verify_pdf.py
```

---

## 5. Subsequent automatic deployments

Every push to `main` by a permitted actor runs:

1. **Build and Analyze** — checkout (full history) → SonarQube scan.
2. **Deploy to EC2** — actor check → Docker Hub login → build **one** image
   tagged `<commit-sha>` and `latest` → push → SSH.

On the instance, in order:

1. Verify `APP_DIR`, `docker-compose.yml` and `app.env` exist — fail fast if not.
2. Verify Docker and the Compose plugin.
3. Verify or create the named volume; ensure `backups/` exists.
4. **Pull the new image first**, so a registry failure never leaves the host
   with nothing running.
5. **Back up SQLite with the online `.backup` command** and verify the copy
   with `PRAGMA integrity_check`. Retain the 20 most recent.
6. Record the current tag to `.previous_tag`, then write the new `.env`.
7. `docker compose down --remove-orphans` (**never** `-v`) → `docker compose up -d`.
8. Poll `GET /` for up to 150 seconds.
9. On failure: dump `compose ps`, 200 log lines and container state, then
   **automatically revert** to `.previous_tag` and fail the job.
10. Prune old images. `latest`, the current tag and the previous tag are
    always protected; of the rest the 3 most recent are kept. At this image
    size (~1.2 GB) that caps local images at roughly 7 GB.
    `docker image prune -af` is never used.

---

## 6. Rollback procedure

### Automatic

If `GET /` does not answer, the pipeline reverts to the previous tag and fails
the job. Citizen data is untouched.

### Manual

```bash
cd /opt/ai-petition-generator
./rollback.sh                    # to the previous tag
./rollback.sh <commit-sha>       # to a specific tag
```

Or by hand:

```bash
cd /opt/ai-petition-generator
cat .previous_tag
docker pull subashawsdevops/ai-petition-generator:<tag>
printf 'APP_IMAGE=subashawsdevops/ai-petition-generator\nIMAGE_TAG=<tag>\nAPP_PORT=8000\n' > .env
docker compose down --remove-orphans
docker compose up -d
curl -fsS http://127.0.0.1:8000/
```

Because every image is tagged with an immutable commit SHA, rollback pulls the
exact artifact that previously ran. It does **not** rebuild, so it is unaffected
by the repository's unpinned dependencies.

### Data rollback — last resort

```bash
cd /opt/ai-petition-generator
docker compose down                       # NOT -v
ls -1t backups/*.sqlite | head
docker run --rm --user 0:0 \
  -v ai_petition_generator_var:/data \
  -v /opt/ai-petition-generator/backups:/backups \
  --entrypoint /bin/sh subashawsdevops/ai-petition-generator:latest \
  -c 'cp /backups/<TIMESTAMP>-sessions.sqlite /data/sessions.sqlite'
docker compose up -d
```

⚠️ This **discards every petition created since that backup**, and restoring
`sessions.sqlite` alone leaves references to documents and attachments that
still exist in the volume. Use only after a confirmed corruption event.

---

## 7. Backup procedure

**Automatic:** before every deployment, retaining the 20 most recent copies in
`/opt/ai-petition-generator/backups/`.

**Manual / scheduled:**

```bash
/opt/ai-petition-generator/backup.sh
```

Recommended cron (daily at 02:00, plus an off-instance copy):

```cron
0 2 * * * /opt/ai-petition-generator/backup.sh >> /var/log/petition-backup.log 2>&1
```

⚠️ On-instance backups do not survive instance loss. Add **EBS snapshots (AWS
Backup)** and/or sync `backups/` to S3 with versioning. `backups/` contains
citizen data — encrypt any destination.

**Never back up a live SQLite database with `cp`.** The `-wal` and `-shm`
sidecars mean a copied file is frequently corrupt. Both scripts use
`sqlite3 .backup`.

---

## 8. Reference

| Item | Value |
|---|---|
| Docker image | `subashawsdevops/ai-petition-generator` |
| Tags | `<commit-sha>` (deployed), `latest` (convenience only) |
| Container name | `ai-petition-generator` |
| Container port | `8000` |
| Host binding | `127.0.0.1:8000` — loopback only |
| Named volume | `ai_petition_generator_var` |
| Volume on disk | `/var/lib/docker/volumes/ai_petition_generator_var/_data` |
| Data path in container | `/app/backend/var` |
| Deployment directory | `/opt/ai-petition-generator` (via `EC2_APP_DIR`) |
| Runtime env file | `/opt/ai-petition-generator/app.env` (mode 600) |
| Compose variables | `/opt/ai-petition-generator/.env` (written by CI) |
| Entrypoint | `uvicorn app.main:app --workers 1` |
| Verification | `curl -fsS http://127.0.0.1:8000/` |

### Useful commands

```bash
cd /opt/ai-petition-generator
docker compose ps
docker compose logs -f --tail=100
docker compose exec app python scripts/verify_pdf.py
docker volume inspect ai_petition_generator_var
curl -s -H "x-operator-token: $TOKEN" http://127.0.0.1:8000/api/operator/status | python3 -m json.tool
```

Load government reference documents into the knowledge corpus:

```bash
docker compose exec app python scripts/ingest.py add <file-or-url> \
  --official --provenance "<G.O. number or source URL>"
```
