from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.routers import (
    auth,
    authors,
    affiliations,
    collaborators,
    conferences,
    dashboard,
    groups,
    journals,
    papers,
    partials,
    scholar,
)

app = FastAPI(title="Alpaca", description="Academic Administration, knowLedge base, Paper organization And Collaboration Assistant")

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
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(papers.router)
app.include_router(conferences.router)
app.include_router(journals.router)
app.include_router(authors.router)
app.include_router(affiliations.router)
app.include_router(groups.router)
app.include_router(collaborators.router)
app.include_router(scholar.router)
app.include_router(partials.router)
