"""
HTMX partial endpoints — return HTML fragments only.
"""
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.conference import ConferenceEdition, StarredConferenceEdition
from app.models.paper import PaperAuthor, PaperConferenceSubmission
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/partials", tags=["partials"])
templates = Jinja2Templates(directory="app/templates")

DEADLINE_WINDOW_DAYS = 90

DEADLINE_FIELD_LABELS = {
    "abstract_deadline": "Abstract",
    "full_paper_deadline": "Full Paper",
    "rebuttal_start": "Rebuttal Opens",
    "rebuttal_end": "Rebuttal Closes",
    "notification_date": "Notification",
    "camera_ready_deadline": "Camera Ready",
}


@router.get("/upcoming-deadlines", response_class=HTMLResponse)
async def upcoming_deadlines(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return HTMLResponse("")

    today = date.today()
    horizon = today + timedelta(days=DEADLINE_WINDOW_DAYS)

    # Starred editions
    starred_result = await db.execute(
        select(StarredConferenceEdition.conference_edition_id)
        .where(StarredConferenceEdition.user_id == current_user.id)
    )
    starred_ids = {r[0] for r in starred_result.all()}

    # Editions for user's submitted papers
    submitted_edition_ids: set[int] = set()
    if current_user.author_id:
        sub_result = await db.execute(
            select(PaperConferenceSubmission.conference_edition_id)
            .join(PaperAuthor, PaperAuthor.paper_id == PaperConferenceSubmission.paper_id)
            .where(PaperAuthor.author_id == current_user.author_id)
        )
        submitted_edition_ids = {r[0] for r in sub_result.all()}

    relevant_ids = starred_ids | submitted_edition_ids
    if not relevant_ids:
        return templates.TemplateResponse(
            request,
            "partials/upcoming_deadlines.html",
            {"deadline_items": [], "request": request},
        )

    editions_result = await db.execute(
        select(ConferenceEdition)
        .options(selectinload(ConferenceEdition.conference))
        .where(ConferenceEdition.id.in_(relevant_ids))
    )
    editions = editions_result.scalars().all()

    deadline_items = []
    for ed in editions:
        deadlines = []
        for field, label in DEADLINE_FIELD_LABELS.items():
            d = getattr(ed, field)
            if d and today <= d <= horizon:
                days_left = (d - today).days
                deadlines.append({"name": label, "date": d, "days_left": days_left})
        if deadlines:
            deadlines.sort(key=lambda x: x["date"])
            deadline_items.append({
                "edition_label": f"{ed.conference.abbreviation} {ed.year}",
                "deadlines": deadlines,
                "paper_title": None,  # could link a submitted paper title here
            })

    deadline_items.sort(key=lambda x: x["deadlines"][0]["date"])

    return templates.TemplateResponse(
        request,
        "partials/upcoming_deadlines.html",
        {"deadline_items": deadline_items, "request": request},
    )
