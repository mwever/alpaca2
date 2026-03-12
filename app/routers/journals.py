from datetime import date
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from app.templating import templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.journal import Journal, JournalSpecialIssue
from app.scimago import fetch_scimago

router = APIRouter(prefix="/journals", tags=["journals"])
PAGE_SIZE = 25
RANKS = ["Q1", "Q2", "Q3", "Q4"]


def _ctx(request, current_user, **kw):
    return {"request": request, "current_user": current_user, "active_page": "journals",
            "ranks": RANKS, **kw}


@router.get("", response_class=HTMLResponse)
async def list_journals(
    request: Request,
    page: int = 1, q: str = "", rank: str = "",
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    stmt = select(Journal).options(selectinload(Journal.special_issues))
    if q:
        stmt = stmt.where((Journal.name.ilike(f"%{q}%")) | (Journal.abbreviation.ilike(f"%{q}%")))
    if rank:
        stmt = stmt.where(Journal.rank == rank)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    items = (await db.execute(
        stmt.order_by(Journal.name).offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    )).scalars().all()
    query_params = {k: v for k, v in {"q": q, "rank": rank}.items() if v}
    return templates.TemplateResponse(
        request, "journals/list.html",
        _ctx(request, current_user, journals=items, total=total, page=page,
             total_pages=(total + PAGE_SIZE - 1) // PAGE_SIZE, q=q, rank=rank,
             query_params=query_params),
    )


@router.get("/new", response_class=HTMLResponse)
async def new_journal_form(request: Request, current_user=Depends(get_current_user)):
    if not current_user:
        return RedirectResponse("/login", 302)
    return templates.TemplateResponse(request, "journals/form.html",
                                      _ctx(request, current_user, journal=None, action="/journals"))


@router.post("")
async def create_journal(
    name: str = Form(...), abbreviation: str = Form(default=""),
    scimago_id: str = Form(default=""), impact_factor: str = Form(default=""),
    rank: str = Form(default=""), website: str = Form(default=""),
    db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    journal = Journal(
        name=name, abbreviation=abbreviation or None, scimago_id=scimago_id or None,
        impact_factor=float(impact_factor) if impact_factor else None,
        rank=rank or None, website=website or None,
    )
    db.add(journal)
    await db.commit()
    return RedirectResponse("/journals", 302)


@router.get("/{j_id}", response_class=HTMLResponse)
async def journal_detail(
    request: Request, j_id: int,
    db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(
        select(Journal).options(selectinload(Journal.special_issues)).where(Journal.id == j_id)
    )
    journal = result.scalar_one_or_none()
    if not journal:
        return RedirectResponse("/journals", 302)
    return templates.TemplateResponse(request, "journals/detail.html",
                                      _ctx(request, current_user, journal=journal))


@router.get("/{j_id}/edit", response_class=HTMLResponse)
async def edit_journal_form(
    request: Request, j_id: int,
    db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(select(Journal).where(Journal.id == j_id))
    journal = result.scalar_one_or_none()
    if not journal:
        return RedirectResponse("/journals", 302)
    return templates.TemplateResponse(request, "journals/form.html",
                                      _ctx(request, current_user, journal=journal,
                                           action=f"/journals/{j_id}/edit"))


@router.post("/{j_id}/edit")
async def update_journal(
    j_id: int,
    name: str = Form(...), abbreviation: str = Form(default=""),
    scimago_id: str = Form(default=""), impact_factor: str = Form(default=""),
    rank: str = Form(default=""), website: str = Form(default=""),
    db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(select(Journal).where(Journal.id == j_id))
    j = result.scalar_one_or_none()
    if not j:
        return RedirectResponse("/journals", 302)
    j.name = name; j.abbreviation = abbreviation or None
    j.scimago_id = scimago_id or None
    j.impact_factor = float(impact_factor) if impact_factor else None
    j.rank = rank or None; j.website = website or None
    await db.commit()
    return RedirectResponse(f"/journals/{j_id}", 302)


@router.post("/{j_id}/delete")
async def delete_journal(
    j_id: int,
    db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(select(Journal).where(Journal.id == j_id))
    j = result.scalar_one_or_none()
    if j:
        await db.delete(j)
        await db.commit()
    return RedirectResponse("/journals", 302)


# ── ScimagoJR ──

@router.get("/{j_id}/scimago", response_class=HTMLResponse)
async def fetch_scimago_preview(
    request: Request, j_id: int,
    db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(select(Journal).where(Journal.id == j_id))
    journal = result.scalar_one_or_none()
    if not journal or not journal.scimago_id:
        return HTMLResponse("<div class='alert alert-warning'>No ScimagoJR ID set.</div>")
    try:
        info = await fetch_scimago(journal.scimago_id)
    except Exception as e:
        return HTMLResponse(f"<div class='alert alert-danger'>Error fetching ScimagoJR: {e}</div>")
    return templates.TemplateResponse(
        request, "journals/scimago_preview.html",
        _ctx(request, current_user, journal=journal, info=info),
    )


@router.post("/{j_id}/scimago/apply")
async def apply_scimago(
    j_id: int,
    sjr: str = Form(default=""),
    best_quartile: str = Form(default=""),
    db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(select(Journal).where(Journal.id == j_id))
    j = result.scalar_one_or_none()
    if j:
        if sjr:
            try:
                j.impact_factor = float(sjr)
            except ValueError:
                pass
        if best_quartile:
            j.rank = best_quartile
        await db.commit()
    return RedirectResponse(f"/journals/{j_id}", 302)


# ── Special Issues ──

@router.post("/{j_id}/issues")
async def create_special_issue(
    j_id: int,
    title: str = Form(...), description: str = Form(default=""),
    submission_deadline: str = Form(default=""),
    db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    issue = JournalSpecialIssue(
        journal_id=j_id, title=title, description=description or None,
        submission_deadline=date.fromisoformat(submission_deadline) if submission_deadline else None,
    )
    db.add(issue)
    await db.commit()
    return RedirectResponse(f"/journals/{j_id}", 302)


@router.post("/{j_id}/issues/{issue_id}/delete")
async def delete_special_issue(
    j_id: int, issue_id: int,
    db: AsyncSession = Depends(get_db), current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(select(JournalSpecialIssue).where(JournalSpecialIssue.id == issue_id))
    issue = result.scalar_one_or_none()
    if issue:
        await db.delete(issue)
        await db.commit()
    return RedirectResponse(f"/journals/{j_id}", 302)
