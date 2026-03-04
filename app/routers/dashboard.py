from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.author import Author
from app.models.group import GroupMembership, ResearchGroup
from app.models.paper import PAPER_STATUS_COLORS, PAPER_STATUS_LABELS, PaperAuthor, PaperProject, PaperStatus
from app.routers.papers import _visibility_filter

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse(url="/login", status_code=302)

    vis = _visibility_filter(current_user.id, current_user.author_id)

    # Stats — scoped to visible papers only
    total_papers = (await db.execute(
        select(func.count(PaperProject.id)).where(vis)
    )).scalar_one()
    accepted = (await db.execute(
        select(func.count(PaperProject.id)).where(
            vis & PaperProject.status.in_([PaperStatus.accepted, PaperStatus.published])
        )
    )).scalar_one()
    submitted = (await db.execute(
        select(func.count(PaperProject.id)).where(
            vis & PaperProject.status.in_([PaperStatus.submitted, PaperStatus.under_review])
        )
    )).scalar_one()
    total_authors = (await db.execute(select(func.count(Author.id)))).scalar_one()

    # Recent papers — scoped to visible papers only
    result = await db.execute(
        select(PaperProject)
        .options(selectinload(PaperProject.paper_authors).selectinload(PaperAuthor.author))
        .where(vis)
        .order_by(PaperProject.updated_at.desc())
        .limit(8)
    )
    recent_papers = result.scalars().all()

    # My groups
    my_groups: list[ResearchGroup] = []
    if current_user.author_id:
        gm_result = await db.execute(
            select(ResearchGroup)
            .join(GroupMembership, GroupMembership.group_id == ResearchGroup.id)
            .where(GroupMembership.user_id == current_user.id)
            .limit(5)
        )
        my_groups = gm_result.scalars().all()

    return templates.TemplateResponse(
        request,
        "dashboard/index.html",
        {
            "active_page": "dashboard",
            "current_user": current_user,
            "stats": {
                "papers": total_papers,
                "accepted": accepted,
                "submitted": submitted,
                "authors": total_authors,
            },
            "recent_papers": recent_papers,
            "my_groups": my_groups,
            "status_labels": PAPER_STATUS_LABELS,
            "status_colors": PAPER_STATUS_COLORS,
        },
    )
