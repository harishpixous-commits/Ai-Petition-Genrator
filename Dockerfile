# syntax=docker/dockerfile:1.7
# ---------------------------------------------------------------------------
# Citizen Petition Assistant — production image
#
# ONE image. There is no separate UI: the frontend is vanilla JS/CSS/HTML that
# lives inside the Python package (backend/app/static, backend/app/assets) and
# is mounted by FastAPI itself (see backend/app/main.py). There is no bundler,
# no package.json and no build step.
#
# Nothing in this file modifies application source. It packages the repository
# exactly as it is.
# ---------------------------------------------------------------------------

# --------------------------------------------------------------------------- #
# Stage 1 — build the virtualenv
#
# Kept separate so the compilers needed by lxml / PyMuPDF / sqlite-vec wheels
# never ship in the runtime image.
# --------------------------------------------------------------------------- #
FROM python:3.12-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      python3-dev \
      libxml2-dev \
      libxslt1-dev \
 && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

# Dependency layer first, so an application-only commit does not reinstall.
COPY backend/requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
 && pip install -r /tmp/requirements.txt


# --------------------------------------------------------------------------- #
# Stage 2 — runtime
# --------------------------------------------------------------------------- #
FROM python:3.12-slim-bookworm AS runtime

# Application floor is Python >= 3.11 (backend/pyproject.toml:
# requires-python = ">=3.11"). The code uses datetime.UTC and enum.StrEnum,
# both 3.11+. This base supplies 3.12.

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    PATH="/opt/venv/bin:${PATH}" \
    # LibreOffice is given an isolated -env:UserInstallation profile per
    # conversion by the application itself (backend/app/services/render.py),
    # so no writable $HOME is required. These are set anyway so fontconfig and
    # any stray tool have somewhere valid to write.
    HOME=/tmp \
    XDG_CACHE_HOME=/tmp

# ---------------------------------------------------------------------------
# System runtime dependencies
#
#   libreoffice-writer  DOCX -> PDF. A real requirement: Tamil needs OpenType
#                       shaping and a pure-Python PDF writer produces a file
#                       whose Tamil is subtly wrong. Without it the service
#                       still starts and produces DOCX only.
#   fonts-noto-core     Latin/Tamil Noto coverage for the PDF converter.
#   fontconfig          provides fc-cache, used below.
#   curl                container HEALTHCHECK against GET /.
#   sqlite3             operational tooling: the ".backup" online-backup
#                       command used by the deployment before containers are
#                       replaced. Never a raw cp of a live WAL database.
# ---------------------------------------------------------------------------
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libreoffice-writer \
      fonts-noto-core \
      fontconfig \
      curl \
      sqlite3 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

# WORKDIR must be backend/: backend/app/config.py derives
#   BASE_DIR = Path(__file__).resolve().parent.parent
# so BASE_DIR becomes /app/backend and the default data_dir becomes
# /app/backend/var — which is the path the compose volume mounts.
WORKDIR /app/backend

COPY backend/ /app/backend/

# ---------------------------------------------------------------------------
# Tamil fonts for the PDF converter.
#
# The repository already ships Noto Sans and Noto Sans Tamil under
# backend/app/assets/fonts/ (they are served to the browser by FastAPI).
# Installing those same files system-wide guarantees LibreOffice can shape
# with the exact family LETTER_FONT names ("Noto Sans Tamil"), rather than
# depending on a distribution package name. Belt and braces alongside
# fonts-noto-core above.
#
# Verify after any base-image change with: scripts/verify_pdf.py
# ---------------------------------------------------------------------------
RUN install -d /usr/local/share/fonts/petition \
 && cp /app/backend/app/assets/fonts/*.ttf /usr/local/share/fonts/petition/ \
 && fc-cache -f \
 && fc-list | grep -i "Noto Sans Tamil" >/dev/null \
    || (echo "FATAL: Noto Sans Tamil not registered with fontconfig" && exit 1)

# ---------------------------------------------------------------------------
# Non-root runtime user.
#
# The data directory is created here and chowned so that a *named Docker
# volume* mounted at this path inherits the correct ownership on first
# creation. Without this the volume would be root-owned and the non-root
# process could not write a single petition.
# ---------------------------------------------------------------------------
RUN groupadd --gid 10001 app \
 && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin app \
 && mkdir -p /app/backend/var/documents /app/backend/var/attachments \
 && chown -R 10001:10001 /app

USER 10001:10001

EXPOSE 8000

# Deployment gate is GET / — the static index, which performs no network I/O.
# /api/health is deliberately NOT used: it makes live outbound calls to every
# configured AI provider (6s timeouts) and runs a synchronous
# subprocess.run([soffice, "--version"], timeout=20) that blocks the event loop.
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8000/ || exit 1

# --workers 1 is MANDATORY, not a tuning choice. Three mechanisms in the
# application are per-process and break with more:
#   1. backend/app/graph/workflow.py — weakref.WeakValueDictionary of
#      asyncio.Lock, serialising turns per session, in-process only.
#   2. langgraph AsyncSqliteSaver over one SQLite file.
#   3. backend/app/api/catalog.py — PetitionCatalog cached on app.state.
#
# --forwarded-allow-ips=* because inside a container the reverse proxy is a
# different host (the Docker bridge gateway), so '127.0.0.1' would never match
# and X-Forwarded-Proto would be ignored. This is safe ONLY because compose
# publishes the port to the host loopback exclusively — see docker-compose.yml.
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--proxy-headers", \
     "--forwarded-allow-ips=*"]
