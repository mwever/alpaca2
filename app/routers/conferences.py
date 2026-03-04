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
from app.models.conference import Conference, ConferenceEdition, StarredConferenceEdition
from app.wikicfp import fetch_editions, fetch_event_cfp

router = APIRouter(prefix="/conferences", tags=["conferences"])
templates = Jinja2Templates(directory="app/templates")
PAGE_SIZE = 25

CORE_RANKS = ["A*", "A", "B", "C", "National", "Unranked"]


def _ctx(request, current_user, **kw):
    return {"request": request, "current_user": current_user, "active_page": "conferences",
            "core_ranks": CORE_RANKS, **kw}


@router.get("", response_class=HTMLResponse)
async def list_conferences(
    request: Request,
    page: int = 1, q: str = "", rank: str = "",
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    stmt = select(Conference).options(selectinload(Conference.editions))
    if q:
        stmt = stmt.where(
            (Conference.name.ilike(f"%{q}%")) | (Conference.abbreviation.ilike(f"%{q}%"))
        )
    if rank:
        stmt = stmt.where(Conference.core_rank == rank)
    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    items = (await db.execute(
        stmt.order_by(Conference.abbreviation)
        .offset((page - 1) * PAGE_SIZE).limit(PAGE_SIZE)
    )).scalars().all()
    # Fetch starred editions for current user
    starred_ids: set[int] = set()
    if current_user:
        sr = await db.execute(
            select(StarredConferenceEdition.conference_edition_id)
            .where(StarredConferenceEdition.user_id == current_user.id)
        )
        starred_ids = {row[0] for row in sr.all()}
    return templates.TemplateResponse(
        request, "conferences/list.html",
        _ctx(request, current_user, conferences=items, total=total, page=page,
             total_pages=(total + PAGE_SIZE - 1) // PAGE_SIZE, q=q, rank=rank,
             starred_ids=starred_ids),
    )


@router.get("/new", response_class=HTMLResponse)
async def new_conference_form(request: Request, current_user=Depends(get_current_user)):
    if not current_user:
        return RedirectResponse("/login", 302)
    return templates.TemplateResponse(request, "conferences/form.html",
                                      _ctx(request, current_user, conference=None, action="/conferences"))


@router.post("", response_class=HTMLResponse)
async def create_conference(
    request: Request,
    name: str = Form(...), abbreviation: str = Form(...),
    core_rank: str = Form(default=""), website: str = Form(default=""),
    wikicfp_series_id: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    conf = Conference(name=name, abbreviation=abbreviation,
                      core_rank=core_rank or None, website=website or None,
                      wikicfp_series_id=wikicfp_series_id or None)
    db.add(conf)
    await db.commit()
    return RedirectResponse("/conferences", 302)


@router.get("/{conf_id}", response_class=HTMLResponse)
async def conference_detail(
    request: Request, conf_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(
        select(Conference).options(selectinload(Conference.editions)).where(Conference.id == conf_id)
    )
    conf = result.scalar_one_or_none()
    if not conf:
        return RedirectResponse("/conferences", 302)
    starred_ids: set[int] = set()
    sr = await db.execute(
        select(StarredConferenceEdition.conference_edition_id)
        .where(StarredConferenceEdition.user_id == current_user.id)
    )
    starred_ids = {row[0] for row in sr.all()}
    return templates.TemplateResponse(request, "conferences/detail.html",
                                      _ctx(request, current_user, conference=conf,
                                           starred_ids=starred_ids, today=date.today()))


@router.get("/{conf_id}/edit", response_class=HTMLResponse)
async def edit_conference_form(
    request: Request, conf_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(select(Conference).where(Conference.id == conf_id))
    conf = result.scalar_one_or_none()
    if not conf:
        return RedirectResponse("/conferences", 302)
    return templates.TemplateResponse(request, "conferences/form.html",
                                      _ctx(request, current_user, conference=conf,
                                           action=f"/conferences/{conf_id}/edit"))


@router.post("/{conf_id}/edit")
async def update_conference(
    conf_id: int,
    name: str = Form(...), abbreviation: str = Form(...),
    core_rank: str = Form(default=""), website: str = Form(default=""),
    wikicfp_series_id: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(select(Conference).where(Conference.id == conf_id))
    conf = result.scalar_one_or_none()
    if not conf:
        return RedirectResponse("/conferences", 302)
    conf.name = name; conf.abbreviation = abbreviation
    conf.core_rank = core_rank or None; conf.website = website or None
    conf.wikicfp_series_id = wikicfp_series_id or None
    await db.commit()
    return RedirectResponse(f"/conferences/{conf_id}", 302)


@router.post("/{conf_id}/delete")
async def delete_conference(
    conf_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(select(Conference).where(Conference.id == conf_id))
    conf = result.scalar_one_or_none()
    if conf:
        await db.delete(conf)
        await db.commit()
    return RedirectResponse("/conferences", 302)


# ── Editions ──

@router.get("/{conf_id}/editions/new", response_class=HTMLResponse)
async def new_edition_form(
    request: Request, conf_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(select(Conference).where(Conference.id == conf_id))
    conf = result.scalar_one_or_none()
    return templates.TemplateResponse(request, "conferences/edition_form.html",
                                      _ctx(request, current_user, conference=conf, edition=None,
                                           action=f"/conferences/{conf_id}/editions"))


@router.post("/{conf_id}/editions")
async def create_edition(
    conf_id: int,
    year: int = Form(...),
    location: str = Form(default=""),
    start_date: str = Form(default=""),
    end_date: str = Form(default=""),
    wikicfp_id: str = Form(default=""),
    abstract_deadline: str = Form(default=""),
    full_paper_deadline: str = Form(default=""),
    rebuttal_start: str = Form(default=""),
    rebuttal_end: str = Form(default=""),
    notification_date: str = Form(default=""),
    camera_ready_deadline: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)

    def _d(v): return date.fromisoformat(v) if v else None

    edition = ConferenceEdition(
        conference_id=conf_id, year=year,
        location=location or None,
        start_date=_d(start_date), end_date=_d(end_date),
        wikicfp_id=wikicfp_id or None,
        abstract_deadline=_d(abstract_deadline),
        full_paper_deadline=_d(full_paper_deadline),
        rebuttal_start=_d(rebuttal_start),
        rebuttal_end=_d(rebuttal_end),
        notification_date=_d(notification_date),
        camera_ready_deadline=_d(camera_ready_deadline),
    )
    db.add(edition)
    await db.commit()
    return RedirectResponse(f"/conferences/{conf_id}", 302)


@router.get("/{conf_id}/editions/{ed_id}/edit", response_class=HTMLResponse)
async def edit_edition_form(
    request: Request, conf_id: int, ed_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    conf = (await db.execute(select(Conference).where(Conference.id == conf_id))).scalar_one_or_none()
    edition = (await db.execute(select(ConferenceEdition).where(ConferenceEdition.id == ed_id))).scalar_one_or_none()
    if not conf or not edition:
        return RedirectResponse(f"/conferences/{conf_id}", 302)
    return templates.TemplateResponse(request, "conferences/edition_form.html",
                                      _ctx(request, current_user, conference=conf, edition=edition,
                                           action=f"/conferences/{conf_id}/editions/{ed_id}/edit"))


@router.post("/{conf_id}/editions/{ed_id}/edit")
async def update_edition(
    conf_id: int, ed_id: int,
    year: int = Form(...),
    location: str = Form(default=""),
    start_date: str = Form(default=""),
    end_date: str = Form(default=""),
    wikicfp_id: str = Form(default=""),
    abstract_deadline: str = Form(default=""),
    full_paper_deadline: str = Form(default=""),
    rebuttal_start: str = Form(default=""),
    rebuttal_end: str = Form(default=""),
    notification_date: str = Form(default=""),
    camera_ready_deadline: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    edition = (await db.execute(select(ConferenceEdition).where(ConferenceEdition.id == ed_id))).scalar_one_or_none()
    if not edition:
        return RedirectResponse(f"/conferences/{conf_id}", 302)

    def _d(v): return date.fromisoformat(v) if v else None

    edition.year = year
    edition.location = location or None
    edition.start_date = _d(start_date)
    edition.end_date = _d(end_date)
    edition.wikicfp_id = wikicfp_id or None
    edition.abstract_deadline = _d(abstract_deadline)
    edition.full_paper_deadline = _d(full_paper_deadline)
    edition.rebuttal_start = _d(rebuttal_start)
    edition.rebuttal_end = _d(rebuttal_end)
    edition.notification_date = _d(notification_date)
    edition.camera_ready_deadline = _d(camera_ready_deadline)
    await db.commit()
    return RedirectResponse(f"/conferences/{conf_id}", 302)


@router.post("/{conf_id}/editions/{ed_id}/delete")
async def delete_edition(
    conf_id: int, ed_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(select(ConferenceEdition).where(ConferenceEdition.id == ed_id))
    edition = result.scalar_one_or_none()
    if edition:
        await db.delete(edition)
        await db.commit()
    return RedirectResponse(f"/conferences/{conf_id}", 302)


@router.post("/{conf_id}/editions/{ed_id}/star")
async def toggle_star(
    conf_id: int, ed_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(
        select(StarredConferenceEdition).where(
            (StarredConferenceEdition.user_id == current_user.id) &
            (StarredConferenceEdition.conference_edition_id == ed_id)
        )
    )
    star = result.scalar_one_or_none()
    if star:
        await db.delete(star)
    else:
        db.add(StarredConferenceEdition(user_id=current_user.id, conference_edition_id=ed_id))
    await db.commit()
    return RedirectResponse(f"/conferences/{conf_id}", 302)


# ── WikiCFP integration ──────────────────────────────────────────────────────

@router.get("/{conf_id}/wikicfp", response_class=HTMLResponse)
async def wikicfp_preview(
    request: Request, conf_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Fetch editions from WikiCFP and return an HTMX preview fragment."""
    if not current_user:
        return HTMLResponse("", status_code=401)
    result = await db.execute(
        select(Conference).options(selectinload(Conference.editions)).where(Conference.id == conf_id)
    )
    conf = result.scalar_one_or_none()
    if not conf:
        return HTMLResponse("<div class='alert alert-danger'>Conference not found.</div>")
    if not conf.wikicfp_series_id:
        return HTMLResponse(
            "<div class='alert alert-warning'>No WikiCFP series ID set — edit the conference to add one.</div>"
        )
    try:
        editions = await fetch_editions(conf.wikicfp_series_id)
    except Exception as exc:
        return HTMLResponse(
            f"<div class='alert alert-danger'><strong>WikiCFP fetch failed:</strong> {exc}</div>"
        )
    if not editions:
        return HTMLResponse(
            "<div class='alert alert-info'>No editions found on WikiCFP for "
            f"<strong>{conf.wikicfp_series_id}</strong>.</div>"
        )

    existing_years = {ed.year for ed in conf.editions}
    existing_wikicfp_ids = {ed.wikicfp_id for ed in conf.editions if ed.wikicfp_id}

    return templates.TemplateResponse(
        request, "conferences/wikicfp_preview.html",
        {
            "conf_id": conf_id,
            "editions": editions,
            "existing_years": existing_years,
            "existing_wikicfp_ids": existing_wikicfp_ids,
        },
    )


@router.post("/{conf_id}/wikicfp/import")
async def wikicfp_import(
    conf_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Import selected WikiCFP events into the database as conference editions."""
    if not current_user:
        return RedirectResponse("/login", 302)

    form = await request.form()
    event_ids: list[str] = form.getlist("event_ids")

    for event_id in event_ids:
        try:
            cfp = await fetch_event_cfp(event_id)
        except Exception:
            continue
        if not cfp.year:
            continue

        result = await db.execute(
            select(ConferenceEdition).where(
                (ConferenceEdition.conference_id == conf_id) &
                (ConferenceEdition.year == cfp.year)
            )
        )
        edition = result.scalar_one_or_none()
        if not edition:
            edition = ConferenceEdition(conference_id=conf_id, year=cfp.year)
            db.add(edition)

        edition.wikicfp_id = event_id
        if cfp.location:
            edition.location = cfp.location
        if cfp.start_date:
            edition.start_date = cfp.start_date
        if cfp.end_date:
            edition.end_date = cfp.end_date
        if cfp.abstract_deadline:
            edition.abstract_deadline = cfp.abstract_deadline
        if cfp.full_paper_deadline:
            edition.full_paper_deadline = cfp.full_paper_deadline
        if cfp.notification_date:
            edition.notification_date = cfp.notification_date
        if cfp.camera_ready_deadline:
            edition.camera_ready_deadline = cfp.camera_ready_deadline

    await db.commit()
    return RedirectResponse(f"/conferences/{conf_id}", 302)
