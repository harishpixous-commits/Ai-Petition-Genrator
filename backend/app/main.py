"""Application entry point.

Two things happen at startup and both are deliberate:

  * the checkpoint database is opened for the life of the process, so session
    recovery works from the first request rather than after the first write; and

  * a preflight runs and SAYS what is missing rather than failing silently. A
    missing LibreOffice means no PDF, a missing model means the standard letter
    wording — neither stops the service, and an operator should learn about both
    from the startup log rather than from a citizen.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from .api import catalog, operator, rest, ws
from .config import get_settings
from .domain.templates import load_templates
from .graph.workflow import workflow_lifespan
from .logging_setup import configure_logging
from .services import asr, llm, provider_store
from .services.render import pdf_status

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"
ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def preflight() -> None:
    """Report what this deployment can and cannot do, once, at startup."""
    # Before anything reads the configuration: an operator may have set
    # provider credentials from the operator screen, and those are held in the
    # data directory rather than in app.env, which the container cannot write.
    # Applying them here means the rest of startup — and the preflight report
    # below — sees the configuration the service will actually run with.
    applied = provider_store.apply()
    if applied.names:
        log.info("preflight.operator_providers",
                 extra={"names": list(applied.names), "source": applied.source})

    settings = get_settings()

    templates = load_templates()
    if not templates:
        log.error("preflight.no_templates",
                  extra={"dir": str(settings.data_dir), "impact": "No petition can be produced."})
    else:
        log.info("preflight.templates",
                 extra={"count": len(templates), "ids": [t.id for t in templates]})

    boundary = llm.boundary(settings)
    log.info("preflight.language_model",
             extra={"provider": boundary["provider"], "egress": boundary["egress"],
                    "note": boundary["note"]})

    pdf = pdf_status(settings)
    # Warn unless the engine is one a server may depend on. A workstation that
    # can make a PDF through Word is not a deployment that can.
    (log.info if pdf["production_ready"] else log.warning)(
        "preflight.pdf",
        extra={"ok": pdf["available"], "engine": pdf["engine"],
               "production_ready": pdf["production_ready"], "note": pdf["note"]})

    if not (settings.operator_token or "").strip():
        log.warning(
            "preflight.operator_screen",
            extra={"access": "loopback only",
                   "note": "Set OPERATOR_TOKEN to reach /operator from another "
                           "machine. Without it the screen answers only on "
                           "127.0.0.1, which is the safe default."})

    dictation = asr.status(settings)
    log.info("preflight.dictation",
             extra={"ok": dictation["ok"], "provider": dictation.get("provider")})

    # The knowledge base. An empty corpus is a normal state, not a fault: the
    # analysis panel says it found nothing rather than inventing something, and
    # every petition is produced exactly as before. It is logged at warning so
    # whoever deploys this knows the panel will be silent until documents are
    # loaded with `scripts/ingest.py`.
    try:
        from .knowledge.capability import service as knowledge_service

        knowledge = knowledge_service(settings)
        if knowledge.enabled:
            knowledge.register_capability()
            stats = knowledge.status()
            (log.info if stats.get("ready") else log.warning)(
                "preflight.knowledge",
                extra={"documents": stats.get("documents", 0),
                       "chunks": stats.get("chunks", 0),
                       "vector_search": stats.get("vector_search"),
                       "embeddings": stats.get("indexed_provider"),
                       "note": ("ready" if stats.get("ready") else
                                "corpus is empty; run scripts/ingest.py")})
        else:
            log.info("preflight.knowledge", extra={"note": "disabled"})
    except Exception as exc:  # noqa: BLE001
        log.warning("preflight.knowledge_failed", extra={"error": str(exc)[:200]})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    preflight()
    async with workflow_lifespan(settings) as workflow:
        app.state.workflow = workflow
        log.info("service.ready", extra={"host": settings.host, "port": settings.port})
        yield
    log.info("service.stopped")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Citizen Petition Assistant",
        version="1.0.0",
        summary="Collects a citizen's details and grievance by voice or text, "
                "validates every official value in code, and produces a petition document.",
        lifespan=lifespan,
    )

    # 242 KB of stylesheet and script went over the wire uncompressed on every
    # first visit: nginx gzips text/html by default and nothing else, so the
    # page was compressed and everything it loaded was not. Text of this kind
    # compresses by roughly three quarters, and the fonts — 1.4 MB of TTF —
    # by about forty per cent.
    #
    # Done here rather than in nginx so it travels with the application and is
    # covered by its tests, instead of depending on a server configuration
    # that a second deployment would have to remember to repeat.
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(rest.router)
    app.include_router(catalog.router)
    # The operator screen. Gated in `operator.authorise`: token required when
    # one is configured, loopback only when none is. Never the citizen's page.
    app.include_router(operator.router)
    app.include_router(ws.router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.middleware("http")
    async def response_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        # Session recovery and document downloads contain citizen information.
        # Neither a shared browser cache nor a proxy should retain a copy.
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif request.url.path.startswith("/static/"):
            # Revalidate every time. These files change on every deploy, and
            # the page that loads them is served `no-store` — so without this
            # a returning citizen gets NEW markup with an OLD stylesheet, and
            # the page renders structurally current and visually broken. That
            # happened: a footer shipped and appeared unstyled and enormous.
            #
            # `no-cache` is not "do not cache": the browser keeps the file and
            # asks whether it changed, which the ETag answers with a 304 of a
            # couple of hundred bytes.
            response.headers["Cache-Control"] = "no-cache"
        elif request.url.path.startswith("/assets/"):
            # Fonts, the state emblem, the footer mark. These change rarely,
            # so they are worth caching — but not indefinitely, or replacing
            # one means waiting out a year of stale copies.
            response.headers["Cache-Control"] = "public, max-age=3600"
        return response

    # Noto Sans and Noto Sans Tamil ship WITH the application and are served
    # from here. The page asked for them and nothing answered — every request
    # under /assets/fonts returned 404 — so Tamil was being drawn in whatever
    # the machine happened to have. It looked right on a Windows box with
    # Nirmala UI installed and would have rendered boxes on a laptop without
    # it, which is precisely the failure the font files were added to prevent.
    if ASSETS_DIR.is_dir():
        app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
    else:  # pragma: no cover - a packaging error, worth saying out loud
        log.warning("assets.missing", extra={"path": str(ASSETS_DIR)})

    # The test page is served by the service itself: one process, one command,
    # one URL, no build step. It is a thin client over the same endpoints a real
    # front end would use — it holds no logic of its own.
    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        # No caching on the page itself. A browser that holds on to an older
        # copy shows an interface the running service no longer has — which is
        # exactly the kind of thing that goes wrong in front of an audience.
        # The fonts under /assets are versioned by name and cache normally.
        return FileResponse(
            STATIC_DIR / "index.html",
            headers={"Cache-Control": "no-store, must-revalidate"},
        )

    # The operator screen. Served on its own path, not linked from the citizen
    # page, and behind the same access rule as the endpoint it reads: a token
    # when one is configured, loopback only when none is.
    @app.get("/operator", include_in_schema=False)
    async def operator_page(request: Request) -> FileResponse:
        from .api.operator import authorise

        authorise(request)
        return FileResponse(
            STATIC_DIR / "operator.html",
            headers={"Cache-Control": "no-store, must-revalidate"},
        )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        """Never leak an internal error to a citizen.

        The detail goes to the log, where an operator can find it by session id;
        what comes back is a sentence a person can act on.
        """
        log.exception("request.failed", extra={"path": request.url.path})
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Something went wrong on our side. Your details are saved — "
                          "please try again in a moment."
            },
        )

    return app


app = create_app()


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    settings = get_settings()
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=False)
