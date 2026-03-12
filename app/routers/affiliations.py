import os

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from app.templating import templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.affiliation import Affiliation, AuthorAffiliation

router = APIRouter(prefix="/affiliations", tags=["affiliations"])

PAGE_SIZE = 25
_LOGO_DIR = "static/uploads/affiliation_logos"
_ALLOWED_TYPES = {"image/png", "image/jpeg", "image/svg+xml"}
_LOGO_EXTS = {"image/png": ".png", "image/jpeg": ".jpg", "image/svg+xml": ".svg"}


async def _save_logo(logo: UploadFile, aff_id: int) -> str | None:
    if not logo or not logo.filename or logo.content_type not in _ALLOWED_TYPES:
        return None
    os.makedirs(_LOGO_DIR, exist_ok=True)
    ext = _LOGO_EXTS[logo.content_type]
    for old_ext in _LOGO_EXTS.values():
        old = os.path.join(_LOGO_DIR, f"{aff_id}{old_ext}")
        if os.path.exists(old):
            os.remove(old)
    path = os.path.join(_LOGO_DIR, f"{aff_id}{ext}")
    with open(path, "wb") as f:
        f.write(await logo.read())
    return f"/static/uploads/affiliation_logos/{aff_id}{ext}"


def _ctx(request, current_user, **kw):
    return {"request": request, "current_user": current_user, "active_page": "affiliations", **kw}


@router.get("", response_class=HTMLResponse)
async def list_affiliations(
    request: Request,
    page: int = 1,
    q: str = "",
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    stmt = select(Affiliation).options(selectinload(Affiliation.author_affiliations))
    if q:
        stmt = stmt.where(Affiliation.name.ilike(f"%{q}%"))
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    items = (
        await db.execute(stmt.order_by(Affiliation.name).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE))
    ).scalars().all()
    query_params = {"q": q} if q else {}
    return templates.TemplateResponse(
        request,
        "affiliations/list.html",
        _ctx(request, current_user, affiliations=items, total=total, page=page,
             total_pages=(total + PAGE_SIZE - 1) // PAGE_SIZE, q=q,
             query_params=query_params),
    )


@router.get("/new", response_class=HTMLResponse)
async def new_affiliation_form(request: Request, current_user=Depends(get_current_user)):
    if not current_user:
        return RedirectResponse("/login", 302)
    return templates.TemplateResponse(request, "affiliations/form.html",
                                      _ctx(request, current_user, affiliation=None, action="/affiliations"))


@router.post("", response_class=HTMLResponse)
async def create_affiliation(
    request: Request,
    name: str = Form(...),
    sigle: str = Form(default=""),
    country: str = Form(default=""),
    color: str = Form(default=""),
    website: str = Form(default=""),
    description: str = Form(default=""),
    logo: UploadFile = File(default=None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    aff = Affiliation(
        name=name, sigle=sigle or None, country=country or None,
        color=color or None, website=website or None, description=description or None,
    )
    db.add(aff)
    await db.flush()
    logo_path = await _save_logo(logo, aff.id)
    if logo_path:
        aff.logo_path = logo_path
    await db.commit()
    return RedirectResponse("/affiliations", 302)


@router.get("/{aff_id}", response_class=HTMLResponse)
async def affiliation_detail(
    request: Request,
    aff_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(
        select(Affiliation)
        .options(selectinload(Affiliation.author_affiliations).selectinload(AuthorAffiliation.author))
        .where(Affiliation.id == aff_id)
    )
    aff = result.scalar_one_or_none()
    if not aff:
        return RedirectResponse("/affiliations", 302)
    return templates.TemplateResponse(request, "affiliations/detail.html",
                                      _ctx(request, current_user, affiliation=aff))


@router.get("/{aff_id}/edit", response_class=HTMLResponse)
async def edit_affiliation_form(
    request: Request, aff_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(select(Affiliation).where(Affiliation.id == aff_id))
    aff = result.scalar_one_or_none()
    if not aff:
        return RedirectResponse("/affiliations", 302)
    return templates.TemplateResponse(request, "affiliations/form.html",
                                      _ctx(request, current_user, affiliation=aff,
                                           action=f"/affiliations/{aff_id}/edit"))


@router.post("/{aff_id}/edit", response_class=HTMLResponse)
async def update_affiliation(
    request: Request, aff_id: int,
    name: str = Form(...),
    sigle: str = Form(default=""),
    country: str = Form(default=""),
    color: str = Form(default=""),
    website: str = Form(default=""),
    description: str = Form(default=""),
    logo: UploadFile = File(default=None),
    remove_logo: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(select(Affiliation).where(Affiliation.id == aff_id))
    aff = result.scalar_one_or_none()
    if not aff:
        return RedirectResponse("/affiliations", 302)
    aff.name = name
    aff.sigle = sigle or None
    aff.country = country or None
    aff.color = color or None
    aff.website = website or None
    aff.description = description or None
    if remove_logo:
        for ext in _LOGO_EXTS.values():
            p = os.path.join(_LOGO_DIR, f"{aff_id}{ext}")
            if os.path.exists(p):
                os.remove(p)
        aff.logo_path = None
    else:
        logo_path = await _save_logo(logo, aff_id)
        if logo_path:
            aff.logo_path = logo_path
    await db.commit()
    return RedirectResponse(f"/affiliations/{aff_id}", 302)


@router.post("/{aff_id}/delete")
async def delete_affiliation(
    aff_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(select(Affiliation).where(Affiliation.id == aff_id))
    aff = result.scalar_one_or_none()
    if aff:
        for ext in _LOGO_EXTS.values():
            p = os.path.join(_LOGO_DIR, f"{aff_id}{ext}")
            if os.path.exists(p):
                os.remove(p)
        await db.delete(aff)
        await db.commit()
    return RedirectResponse("/affiliations", 302)
