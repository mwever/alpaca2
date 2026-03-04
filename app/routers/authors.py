from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.affiliation import Affiliation, AuthorAffiliation
from app.models.author import Author
from app.models.paper import PaperAuthor, PaperProject
from app.models.scholar import ScholarAuthorSnapshot

router = APIRouter(prefix="/authors", tags=["authors"])
templates = Jinja2Templates(directory="app/templates")

PAGE_SIZE = 25


def _ctx(request, current_user, **kw):
    return {"request": request, "current_user": current_user, "active_page": "authors", **kw}


@router.get("", response_class=HTMLResponse)
async def list_authors(
    request: Request,
    page: int = 1,
    q: str = "",
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    stmt = select(Author).options(
        selectinload(Author.author_affiliations).selectinload(AuthorAffiliation.affiliation),
        selectinload(Author.paper_authors),
    )
    if q:
        stmt = stmt.where(
            (Author.last_name.ilike(f"%{q}%")) | (Author.given_name.ilike(f"%{q}%"))
        )
    total = (await db.execute(select(func.count()).select_from(
        select(Author).where((Author.last_name.ilike(f"%{q}%")) | (Author.given_name.ilike(f"%{q}%"))).subquery()
        if q else select(Author).subquery()
    ))).scalar_one()
    items = (await db.execute(
        stmt.order_by(Author.last_name, Author.given_name)
        .offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    )).scalars().all()
    return templates.TemplateResponse(
        request, "authors/list.html",
        _ctx(request, current_user, authors=items, total=total, page=page,
             total_pages=(total + PAGE_SIZE - 1) // PAGE_SIZE, q=q),
    )


@router.get("/new", response_class=HTMLResponse)
async def new_author_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    affiliations = (await db.execute(select(Affiliation).order_by(Affiliation.name))).scalars().all()
    return templates.TemplateResponse(
        request, "authors/form.html",
        _ctx(request, current_user, author=None, affiliations=affiliations, action="/authors"),
    )


@router.post("", response_class=HTMLResponse)
async def create_author(
    request: Request,
    last_name: str = Form(...),
    given_name: str = Form(...),
    email: str = Form(default=""),
    nationality: str = Form(default=""),
    google_scholar_id: str = Form(default=""),
    affiliation_id: Optional[int] = Form(default=None),
    aff_start: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    author = Author(
        last_name=last_name, given_name=given_name,
        email=email or None, nationality=nationality or None,
        google_scholar_id=google_scholar_id or None,
    )
    db.add(author)
    await db.flush()
    if affiliation_id:
        start = date.fromisoformat(aff_start) if aff_start else None
        db.add(AuthorAffiliation(author_id=author.id, affiliation_id=affiliation_id, start_date=start))
    await db.commit()
    return RedirectResponse("/authors", 302)


@router.get("/{author_id}", response_class=HTMLResponse)
async def author_detail(
    request: Request,
    author_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(
        select(Author)
        .options(
            selectinload(Author.author_affiliations).selectinload(AuthorAffiliation.affiliation),
            selectinload(Author.paper_authors).selectinload(PaperAuthor.paper),
            selectinload(Author.scholar_snapshots),
        )
        .where(Author.id == author_id)
    )
    author = result.scalar_one_or_none()
    if not author:
        return RedirectResponse("/authors", 302)

    # Latest scholar snapshot
    snap_result = await db.execute(
        select(ScholarAuthorSnapshot)
        .where(ScholarAuthorSnapshot.author_id == author_id)
        .order_by(ScholarAuthorSnapshot.date.desc())
        .limit(1)
    )
    latest_snap = snap_result.scalar_one_or_none()

    # All snapshots for chart (last 90)
    snaps_result = await db.execute(
        select(ScholarAuthorSnapshot)
        .where(ScholarAuthorSnapshot.author_id == author_id)
        .order_by(ScholarAuthorSnapshot.date.asc())
        .limit(90)
    )
    snapshots = snaps_result.scalars().all()

    affiliations = (await db.execute(select(Affiliation).order_by(Affiliation.name))).scalars().all()

    return templates.TemplateResponse(
        request, "authors/detail.html",
        _ctx(request, current_user, author=author, latest_snap=latest_snap,
             snapshots=snapshots, affiliations=affiliations),
    )


@router.get("/{author_id}/edit", response_class=HTMLResponse)
async def edit_author_form(
    request: Request, author_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(
        select(Author).options(
            selectinload(Author.author_affiliations).selectinload(AuthorAffiliation.affiliation)
        ).where(Author.id == author_id)
    )
    author = result.scalar_one_or_none()
    if not author:
        return RedirectResponse("/authors", 302)
    affiliations = (await db.execute(select(Affiliation).order_by(Affiliation.name))).scalars().all()
    return templates.TemplateResponse(
        request, "authors/form.html",
        _ctx(request, current_user, author=author, affiliations=affiliations,
             action=f"/authors/{author_id}/edit"),
    )


@router.post("/{author_id}/edit", response_class=HTMLResponse)
async def update_author(
    request: Request, author_id: int,
    last_name: str = Form(...),
    given_name: str = Form(...),
    email: str = Form(default=""),
    nationality: str = Form(default=""),
    google_scholar_id: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(select(Author).where(Author.id == author_id))
    author = result.scalar_one_or_none()
    if not author:
        return RedirectResponse("/authors", 302)
    author.last_name = last_name
    author.given_name = given_name
    author.email = email or None
    author.nationality = nationality or None
    author.google_scholar_id = google_scholar_id or None
    await db.commit()
    return RedirectResponse(f"/authors/{author_id}", 302)


@router.post("/{author_id}/delete")
async def delete_author(
    author_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(select(Author).where(Author.id == author_id))
    author = result.scalar_one_or_none()
    if author:
        await db.delete(author)
        await db.commit()
    return RedirectResponse("/authors", 302)


@router.post("/{author_id}/affiliations/add")
async def add_affiliation(
    request: Request, author_id: int,
    affiliation_id: int = Form(...),
    start_date: str = Form(default=""),
    end_date: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    entry = AuthorAffiliation(
        author_id=author_id,
        affiliation_id=affiliation_id,
        start_date=date.fromisoformat(start_date) if start_date else None,
        end_date=date.fromisoformat(end_date) if end_date else None,
    )
    db.add(entry)
    await db.commit()
    return RedirectResponse(f"/authors/{author_id}", 302)
