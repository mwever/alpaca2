from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.calendar import PersonalCalendarEvent
from app.models.conference import ConferenceEdition
from app.models.journal import JournalSpecialIssue

router = APIRouter(prefix="/calendar", tags=["calendar"])
templates = Jinja2Templates(directory="app/templates")


def _ctx(request, current_user, **kw):
    return {"request": request, "current_user": current_user, "active_page": "calendar", **kw}


def _in_range(d: Optional[date], range_start: Optional[date], range_end: Optional[date]) -> bool:
    if d is None:
        return False
    if range_start and d < range_start:
        return False
    if range_end and d >= range_end:
        return False
    return True


@router.get("", response_class=HTMLResponse)
async def calendar_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    personal_events = (await db.execute(
        select(PersonalCalendarEvent)
        .where(PersonalCalendarEvent.user_id == current_user.id)
        .order_by(PersonalCalendarEvent.start_date)
    )).scalars().all()
    return templates.TemplateResponse(
        request, "calendar/index.html",
        _ctx(request, current_user, personal_events=personal_events),
    )


@router.get("/events.json")
async def calendar_events_json(
    start: str = "",
    end: str = "",
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return JSONResponse([], status_code=401)

    try:
        range_start = date.fromisoformat(start[:10]) if start else None
        range_end = date.fromisoformat(end[:10]) if end else None
    except (ValueError, IndexError):
        range_start = range_end = None

    def ir(d: Optional[date]) -> bool:
        return _in_range(d, range_start, range_end)

    def any_ir(*dates) -> bool:
        return any(ir(d) for d in dates)

    events = []

    # ── Conference editions ────────────────────────────────────────────────
    editions = (await db.execute(
        select(ConferenceEdition)
        .options(selectinload(ConferenceEdition.conference))
    )).scalars().all()

    for ed in editions:
        conf = ed.conference
        abbr = f"{conf.abbreviation} {ed.year}"
        url = f"/conferences/{conf.id}"

        if not any_ir(ed.start_date, ed.abstract_deadline, ed.full_paper_deadline,
                      ed.rebuttal_start, ed.rebuttal_end, ed.notification_date,
                      ed.camera_ready_deadline):
            continue

        # Conference dates (multi-day block)
        if ed.start_date and ir(ed.start_date):
            end_d = (ed.end_date or ed.start_date) + timedelta(days=1)
            events.append({
                "id": f"conf-{ed.id}-dates",
                "title": abbr,
                "start": ed.start_date.isoformat(),
                "end": end_d.isoformat(),
                "color": "#0d6efd",
                "url": url,
                "allDay": True,
            })

        # Single-day deadline events
        for d_val, label, color in [
            (ed.abstract_deadline,    f"Abstract — {abbr}",     "#fd7e14"),
            (ed.full_paper_deadline,  f"Paper Deadline — {abbr}", "#dc3545"),
            (ed.notification_date,    f"Notification — {abbr}", "#198754"),
            (ed.camera_ready_deadline, f"Camera Ready — {abbr}", "#6f42c1"),
        ]:
            if d_val and ir(d_val):
                events.append({
                    "id": f"conf-{ed.id}-{label[:6]}",
                    "title": label,
                    "start": d_val.isoformat(),
                    "color": color,
                    "url": url,
                    "allDay": True,
                })

        # Rebuttal window
        if ed.rebuttal_start and (ir(ed.rebuttal_start) or ir(ed.rebuttal_end)):
            rebuttal_end = (ed.rebuttal_end or ed.rebuttal_start) + timedelta(days=1)
            events.append({
                "id": f"conf-{ed.id}-rebuttal",
                "title": f"Rebuttal — {abbr}",
                "start": ed.rebuttal_start.isoformat(),
                "end": rebuttal_end.isoformat(),
                "color": "#ffc107",
                "textColor": "#000",
                "url": url,
                "allDay": True,
            })

    # ── Journal special issues ─────────────────────────────────────────────
    issues = (await db.execute(
        select(JournalSpecialIssue)
        .options(selectinload(JournalSpecialIssue.journal))
        .where(JournalSpecialIssue.submission_deadline.isnot(None))
    )).scalars().all()

    for issue in issues:
        if ir(issue.submission_deadline):
            journal = issue.journal
            name = journal.abbreviation or journal.name
            events.append({
                "id": f"journal-{issue.id}",
                "title": f"SI Deadline — {name}: {issue.title}",
                "start": issue.submission_deadline.isoformat(),
                "color": "#0dcaf0",
                "textColor": "#000",
                "url": f"/journals/{issue.journal_id}",
                "allDay": True,
            })

    # ── Personal events ────────────────────────────────────────────────────
    personal = (await db.execute(
        select(PersonalCalendarEvent)
        .where(PersonalCalendarEvent.user_id == current_user.id)
    )).scalars().all()

    for ev in personal:
        if not any_ir(ev.start_date, ev.end_date):
            continue
        end_d = (ev.end_date or ev.start_date) + timedelta(days=1)
        events.append({
            "id": f"personal-{ev.id}",
            "title": ev.title,
            "start": ev.start_date.isoformat(),
            "end": end_d.isoformat(),
            "color": ev.color or "#6c757d",
            "allDay": True,
            "extendedProps": {
                "type": "personal",
                "eventId": ev.id,
                "description": ev.description or "",
            },
        })

    return JSONResponse(events)


@router.post("/events")
async def create_personal_event(
    title: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(default=""),
    color: str = Form(default="#6c757d"),
    description: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    ev = PersonalCalendarEvent(
        user_id=current_user.id,
        title=title,
        start_date=date.fromisoformat(start_date),
        end_date=date.fromisoformat(end_date) if end_date else None,
        color=color or None,
        description=description or None,
    )
    db.add(ev)
    await db.commit()
    return RedirectResponse("/calendar", 302)


@router.post("/events/{ev_id}/delete")
async def delete_personal_event(
    ev_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    ev = (await db.execute(
        select(PersonalCalendarEvent).where(
            (PersonalCalendarEvent.id == ev_id) &
            (PersonalCalendarEvent.user_id == current_user.id)
        )
    )).scalar_one_or_none()
    if ev:
        await db.delete(ev)
        await db.commit()
    return RedirectResponse("/calendar", 302)
