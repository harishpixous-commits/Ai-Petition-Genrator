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

import hashlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from .api import catalog, dictation, officer, operator, rest, ws
from .api.middleware import CorrelationIdMiddleware
from .config import get_settings
from .domain.templates import load_templates
from .graph.workflow import workflow_lifespan
from .logging_setup import configure_logging
from .services import asr, credential_check, llm, provider_store
from .services.render import pdf_status

log = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).resolve().parent / "static"

# The page's own scripts and stylesheet, stamped with the build they belong
# to so a browser cannot pair fresh markup with a cached script.
_STAMPED = ("app.css", "app.js", "navigation.js")


@lru_cache(maxsize=1)
def _build_stamp() -> str:
    """A short digest of the files the page loads.

    Content, not a timestamp: a redeploy that changes nothing should not
    make every client download the same bytes again, and a file edited in
    place without its mtime moving still has to invalidate.
    """
    digest = hashlib.sha256()
    for name in _STAMPED:
        path = STATIC_DIR / name
        if path.exists():
            digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


def stamped_index() -> str:
    """index.html with `?v=` on the assets it loads."""
    markup = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    stamp = _build_stamp()
    for name in _STAMPED:
        markup = markup.replace(f"/static/{name}", f"/static/{name}?v={stamp}")
    return markup
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

    # Keys that are present and cannot be used. WARNING and one line per
    # credential, because the symptom an operator actually sees — "I put the
    # keys in and nothing happened" — gives them nothing to search for, and
    # this is the only place that names the reason.
    for unused in credential_check.find(settings):
        log.warning(
            "preflight.credential_unused",
            extra={"keys": unused.keys, "disabled_by": unused.setting,
                   "fix": unused.fix,
                   "note": (f"{unused.keys} is set but {unused.setting} "
                            f"switches it off. The key was read correctly. "
                            f"Set {unused.fix} and recreate the container.")})

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

    # WHETHER THIS DEPLOYMENT HAS AN OFFICER YET, said out loud at start-up.
    #
    # Until the first officer account exists, `can_access` grandfathers in
    # sessions that have no owner row at all — pre-23-September bookmarks
    # that nobody could reach otherwise. Provisioning the first officer
    # closes that carve-out and every session must then be owned to be
    # opened. That is the correct state for any public deployment, and this
    # warning says so plainly on every start-up until the step has been
    # taken.
    #
    # Logged at WARNING so it appears in the same place an operator is already
    # looking, with the exact action that ends it. Nothing is changed here:
    # altering the rule from inside a start-up probe, on a service that is
    # already live, is how a working site stops answering.
    try:
        from .services import officer_store

        with officer_store.database() as _db:
            _has_officer = bool(
                _db.execute("SELECT 1 FROM officers LIMIT 1").fetchone())
        if _has_officer:
            log.info("preflight.officers", extra={"provisioned": True})
        else:
            log.warning(
                "preflight.officers",
                extra={"provisioned": False,
                       "effect": "a petition can be opened by anyone holding "
                                 "its session id",
                       "action": "run the 'Create Officer Account' workflow, "
                                 "or scripts/create_officer.py in the "
                                 "container"})
    except Exception as exc:  # noqa: BLE001
        log.warning("preflight.officers_unreadable",
                    extra={"error": str(exc)[:160]})

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

    # OUTERMOST on purpose. The correlation id is set before any other
    # middleware or the router runs, so an exception raised inside CORS, GZip
    # or an endpoint still logs with a correlation id and the response going
    # back carries it. See `app/api/middleware.py`.
    app.add_middleware(CorrelationIdMiddleware)

    app.include_router(rest.router)
    app.include_router(rest.public_router)
    app.include_router(catalog.router)
    app.include_router(officer.router)
    # The operator screen. Gated in `operator.authorise`: token required when
    # one is configured, loopback only when none is. Never the citizen's page.
    app.include_router(operator.router)
    app.include_router(ws.router)
    app.include_router(dictation.router)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/officer/{path:path}", include_in_schema=False)
    async def officer_page(path: str, request: Request) -> Response:
        """The officer shell, for every /officer/* address.

        The page itself is one file; which screen it draws is decided in the
        browser. The gate is here rather than there because a redirect a
        page performs on itself has already loaded the page.
        """
        from fastapi.responses import RedirectResponse

        from .services import officer_store

        signed_in = officer_store.identity(request.cookies.get(officer_store.COOKIE))
        previewing = request.query_params.get("preview") == "1"
        if path != "login" and not previewing and not signed_in:
            return RedirectResponse("/officer/login", status_code=303)
        return FileResponse(STATIC_DIR / "officer.html",
                            headers={"Cache-Control": "no-store"})

    # Separate admin portal. Lives under /admin/* so administrators log
    # in through their own screen rather than through the officer
    # portal, and so the review officer portal has no "Admin panel" link
    # for a reviewer to wonder about. The gate below redirects to
    # /admin/login when there is no session; a signed-in officer without
    # any `manage_*` privilege gets past this redirect (there is a
    # session) and the SPA then renders the "no admin rights" page from
    # the browser.
    @app.get("/admin", include_in_schema=False)
    @app.get("/admin/{path:path}", include_in_schema=False)
    async def admin_page(request: Request, path: str = "") -> Response:
        from fastapi.responses import RedirectResponse

        from .services import officer_store

        signed_in = officer_store.identity(
            request.cookies.get(officer_store.COOKIE))
        previewing = request.query_params.get("preview") == "1"
        if path != "login" and not previewing and not signed_in:
            return RedirectResponse("/admin/login", status_code=303)
        return FileResponse(STATIC_DIR / "admin.html",
                            headers={"Cache-Control": "no-store"})

    # A CONTENT SECURITY POLICY THE PAGE CAN ACTUALLY LIVE UNDER.
    #
    # Audited rather than guessed. Across index.html, officer.html and
    # operator.html there are no inline <script> blocks, no on*= handlers and
    # no external hosts of any kind: every script, style, font and image is
    # served by this application. So `script-src 'self'` holds with NO
    # exceptions, which is the clause that matters — it is what stops injected
    # markup from executing, and the rendering path is ~100% innerHTML against
    # a hand-rolled escaper, so that is a real risk and not a theoretical one.
    #
    # Styles are served from this application only. The static pages contain
    # no inline style blocks or style attributes; the print window also loads
    # its stylesheet from /static/print.css.
    #
    #   connect-src 'self'   also covers the WebSocket: a same-origin ws:// or
    #                        wss:// connection matches 'self'. Naming wss:
    #                        explicitly would permit every host on the internet.
    #   media-src  blob:     the spoken read-back builds an Audio element from
    #                        a Blob URL (app.js createObjectURL).
    #   img-src    data:     previews and the print window inline small images.
    #   object-src 'none'    nothing embeds a plugin; this blocks a whole class
    #                        of legacy injection.
    #   frame-ancestors      clickjacking. Belt and braces with the
    #                        X-Frame-Options nginx already sets.
    _CSP = "; ".join((
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "font-src 'self'",
        "media-src 'self' blob:",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ))

    # The page asks for the microphone and nothing else. Everything a browser
    # can expose is turned off by name, so a future dependency cannot quietly
    # start using the camera or the location.
    _PERMISSIONS = ", ".join((
        "microphone=(self)",
        "camera=()",
        "geolocation=()",
        "payment=()",
        "usb=()",
        "magnetometer=()",
        "gyroscope=()",
        "accelerometer=()",
        "interest-cohort=()",
    ))

    # Pure ASGI, NOT @app.middleware("http"). The decorator version wraps
    # the request in Starlette's BaseHTTPMiddleware, which rewrites `receive`
    # so it can expose a Request to the dispatch function. StaticFiles then
    # calls `receive()` once of its own accord — to notice an `http.disconnect`
    # before streaming a file — and the wrapper's task group raises
    # `RuntimeError: Unexpected message received: http.request`. The test
    # suite's /static/app.css fetch tripped exactly this on the CI runner's
    # Starlette build. The ASGI form below never touches `receive`, so the
    # two coexist cleanly. See CorrelationIdMiddleware for the same shape.
    _HEADER_RULES = [
        (b"/api/", b"no-store"),
        (b"/static/", b"no-cache"),       # revalidate every deploy
        (b"/assets/", b"public, max-age=3600"),
    ]
    _CSP_BYTES = _CSP.encode("latin-1")
    _PERMISSIONS_BYTES = _PERMISSIONS.encode("latin-1")

    class ResponseHeadersMiddleware:
        def __init__(self, inner):
            self.inner = inner

        async def __call__(self, scope, receive, send):
            if scope["type"] != "http":
                await self.inner(scope, receive, send)
                return
            path = scope.get("path", "").encode("latin-1")

            async def send_with_headers(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers") or [])
                    seen = {name for name, _ in headers}
                    # Always set — never set upstream, carry no exception.
                    headers.append((b"x-content-type-options", b"nosniff"))
                    headers.append((b"referrer-policy", b"no-referrer"))
                    # Defaults — a route (operator preview, document download)
                    # may already have set its own stricter policy, in which
                    # case we leave it alone.
                    if b"content-security-policy" not in seen:
                        headers.append((b"content-security-policy", _CSP_BYTES))
                    if b"permissions-policy" not in seen:
                        headers.append((b"permissions-policy", _PERMISSIONS_BYTES))
                    if b"x-frame-options" not in seen:
                        headers.append((b"x-frame-options", b"DENY"))
                    # Session recovery and document downloads contain citizen
                    # information. Neither a shared browser cache nor a proxy
                    # should retain a copy. Static assets revalidate every
                    # deploy (new markup must not pair with an old stylesheet
                    # — that shipped once, as a huge unstyled footer); fonts
                    # and emblem get an hour so a replacement is not held off
                    # for a year.
                    for prefix, policy in _HEADER_RULES:
                        if path.startswith(prefix):
                            headers = [h for h in headers
                                       if h[0] != b"cache-control"]
                            headers.append((b"cache-control", policy))
                            break
                    message = {**message, "headers": headers}
                await send(message)

            await self.inner(scope, receive, send_with_headers)

    app.add_middleware(ResponseHeadersMiddleware)

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
    async def index() -> Response:
        # No caching on the page itself. A browser that holds on to an older
        # copy shows an interface the running service no longer has — which is
        # exactly the kind of thing that goes wrong in front of an audience.
        # The fonts under /assets are versioned by name and cache normally.
        #
        # THE SCRIPTS ARE STAMPED with the build they belong to. A fresh page
        # that loads a cached app.js is the worst of both: the markup has ids
        # the script does not look for, and the script looks for ids the
        # markup does not have, so panels render empty and nothing errors
        # anywhere a citizen can see. The stamp makes that combination
        # unreachable — new markup can only ever fetch its own script.
        return HTMLResponse(
            stamped_index(),
            headers={"Cache-Control": "no-store, must-revalidate"},
        )

    # The operator screen. Served on its own path, not linked from the citizen
    # page, and behind the same access rule as the endpoint it reads: a token
    # when one is configured, loopback only when none is.
    @app.get("/operator", include_in_schema=False)
    async def operator_page(request: Request) -> FileResponse:
        from fastapi.responses import JSONResponse

        from .api.operator import authorise
        from .services import officer_store

        # The admin feature switch gate: when an admin has toggled
        # `operator_screen` off, the route disappears entirely rather
        # than being served behind the token gate as usual. A 404 instead
        # of a 403 so the switch can also be used as "hide this surface"
        # on a departmental deployment where the operator screen is
        # irrelevant.
        if not officer_store.feature_enabled("operator_screen"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
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
