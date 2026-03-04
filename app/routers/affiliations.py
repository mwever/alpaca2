from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.affiliation import Affiliation, AuthorAffiliation

router = APIRouter(prefix="/affiliations", tags=["affiliations"])
templates = Jinja2Templates(directory="app/templates")

PAGE_SIZE = 25


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
    return templates.TemplateResponse(
        request,
        "affiliations/list.html",
        _ctx(request, current_user, affiliations=items, total=total, page=page,
             total_pages=(total + PAGE_SIZE - 1) // PAGE_SIZE, q=q),
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
        await db.delete(aff)
        await db.commit()
    return RedirectResponse("/affiliations", 302)
