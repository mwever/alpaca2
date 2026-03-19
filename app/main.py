import json
import traceback as tb_module
from contextlib import asynccontextmanager

import bcrypt
from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import AsyncSessionLocal
from app.feature_flags import KNOWN_FEATURES, populate_cache
from app.models.error_log import ErrorLog
from app.models.feature_flag import FeatureFlag
from app.models.user import User
from app.routers import (
    admin,
    auth,
    authors,
    affiliations,
    bibtex,
    calendar,
    collaborators,
    conferences,
    dashboard,
    groups,
    journals,
    papers,
    partials,
    scholar,
    service,
    suggestions,
    notebook,
    supervision,
    wiki,
    workflows,
)
from app.templating import templates


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncSessionLocal() as db:
        # Seed initial admin user
        if settings.ADMIN_USERNAME and settings.ADMIN_EMAIL and settings.ADMIN_PASSWORD:
            existing = (await db.execute(
                select(User).where(User.username == settings.ADMIN_USERNAME)
            )).scalar_one_or_none()
            if not existing:
                db.add(User(
                    username=settings.ADMIN_USERNAME,
                    email=settings.ADMIN_EMAIL,
                    hashed_password=bcrypt.hashpw(
                        settings.ADMIN_PASSWORD.encode(), bcrypt.gensalt()
                    ).decode(),
                    is_admin=True,
                ))
                await db.commit()

        # Seed known feature flags (only adds missing ones, never overwrites)
        for key, meta in KNOWN_FEATURES.items():
            existing_flag = await db.get(FeatureFlag, key)
            if not existing_flag:
                db.add(FeatureFlag(
                    key=key,
                    label=meta["label"],
                    description=meta["description"],
                    enabled=meta["default_enabled"],
                ))
        await db.commit()

        # Populate in-memory feature flag cache
        await populate_cache(db)

    yield


app = FastAPI(
    title="Alpaca",
    description="Academic Administration, knowLedge base, Paper organization And Collaboration Assistant",
    lifespan=lifespan,
)

# ── Middleware ──────────────────────────────────────────────────────────────
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="alpaca_session",
    max_age=60 * 60 * 24 * 30,  # 30 days
    https_only=False,  # Set True in production
    same_site="lax",
)

# ── Static files ────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Routers ──────────────────────────────────────────────────────────────────
app.include_router(admin.router)
app.include_router(auth.router)
app.include_router(bibtex.router)
app.include_router(calendar.router)
app.include_router(dashboard.router)
app.include_router(papers.router)
app.include_router(conferences.router)
app.include_router(journals.router)
app.include_router(authors.router)
app.include_router(affiliations.router)
app.include_router(groups.router)
app.include_router(collaborators.router)
app.include_router(scholar.router)
app.include_router(service.router)
app.include_router(suggestions.router)
app.include_router(notebook.router)
app.include_router(supervision.router)
app.include_router(wiki.router)
app.include_router(workflows.router)
app.include_router(partials.router)


# ── Error handling helpers ───────────────────────────────────────────────────

async def _get_user_from_session(request: Request):
    """Try to load the current user from the session cookie. Returns (user, user_id)."""
    try:
        uid = request.session.get("user_id")
        if uid:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, uid)
                return user, uid
    except Exception:
        pass
    return None, None


async def _log_error(request: Request, status_code: int, exc: Exception, user_id=None):
    """Persist an ErrorLog entry. Silently ignores DB failures to avoid error loops."""
    try:
        async with AsyncSessionLocal() as db:
            db.add(ErrorLog(
                status_code=status_code,
                method=request.method,
                path=str(request.url.path),
                query_string=str(request.url.query) or None,
                user_id=user_id,
                exception_type=type(exc).__name__,
                message=str(exc)[:2000],
                traceback=tb_module.format_exc()[:10000],
                user_agent=(request.headers.get("user-agent") or "")[:512],
            ))
            await db.commit()
    except Exception:
        pass


def _htmx_error_response(status_code: int, message: str) -> Response:
    """Return an HTMX-friendly response that shows a toast and prevents content swap."""
    resp = Response(content="", status_code=status_code)
    resp.headers["HX-Reswap"] = "none"
    resp.headers["HX-Trigger"] = json.dumps(
        {"showFlash": {"level": "danger", "message": message}}
    )
    return resp


def _is_htmx(request: Request) -> bool:
    return request.headers.get("HX-Request") == "true"


# ── Exception handlers ───────────────────────────────────────────────────────

@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    status_code = exc.status_code

    # Pass through redirects unchanged
    if status_code < 400:
        headers = dict(exc.headers or {})
        return Response(status_code=status_code, headers=headers)

    current_user, user_id = await _get_user_from_session(request)
    await _log_error(request, status_code, exc, user_id)

    detail = str(exc.detail) if exc.detail else ""

    if _is_htmx(request):
        msg = detail or _default_message(status_code)
        return _htmx_error_response(status_code, msg)

    template_name = (
        "errors/404.html" if status_code == 404 else
        "errors/403.html" if status_code == 403 else
        "errors/500.html"
    )
    return templates.TemplateResponse(
        request, template_name,
        {"request": request, "current_user": current_user,
         "status_code": status_code, "detail": detail},
        status_code=status_code,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    current_user, user_id = await _get_user_from_session(request)
    await _log_error(request, 500, exc, user_id)

    if _is_htmx(request):
        return _htmx_error_response(500, "An unexpected error occurred. Please try again.")

    try:
        return templates.TemplateResponse(
            request, "errors/500.html",
            {"request": request, "current_user": current_user,
             "status_code": 500, "detail": "An unexpected error occurred."},
            status_code=500,
        )
    except Exception:
        # Absolute fallback if template rendering itself fails
        return Response(
            content="<h1>500 Internal Server Error</h1><p>An unexpected error occurred.</p>",
            status_code=500,
            media_type="text/html",
        )


def _default_message(status_code: int) -> str:
    return {
        400: "Bad request.",
        401: "Authentication required.",
        403: "You do not have permission to perform this action.",
        404: "The requested resource was not found.",
        422: "The submitted data was invalid.",
    }.get(status_code, "An error occurred. Please try again.")
