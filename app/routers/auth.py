from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import bcrypt

from app.database import get_db
from app.models.user import User

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _tpl(request: Request, name: str, **ctx):
    ctx.setdefault("current_user", request.session.get("user_id") and None)
    return templates.TemplateResponse(request, name, ctx)


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, next: str = "/"):
    if request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "auth/login.html", {"next": next, "current_user": None})


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form(default="/"),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if not user or not _verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "Invalid username or password.", "next": next, "current_user": None},
            status_code=401,
        )
    if not user.is_active:
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "Account is disabled.", "next": next, "current_user": None},
            status_code=403,
        )
    request.session["user_id"] = user.id
    return RedirectResponse(url=next or "/", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


@router.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(request, "auth/register.html", {"current_user": None})


@router.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # Check uniqueness
    existing = await db.execute(
        select(User).where((User.username == username) | (User.email == email))
    )
    if existing.scalar_one_or_none():
        return templates.TemplateResponse(
            request,
            "auth/register.html",
            {"error": "Username or email already taken.", "current_user": None},
            status_code=400,
        )
    user = User(
        username=username,
        email=email,
        hashed_password=_hash_password(password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    request.session["user_id"] = user.id
    return RedirectResponse(url="/", status_code=302)
