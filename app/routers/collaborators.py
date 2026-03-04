"""
Collaborators overview: all authors the logged-in user's author profile
has co-authored papers with.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.affiliation import Affiliation, AuthorAffiliation
from app.models.author import Author
from app.models.paper import PaperAuthor

router = APIRouter(prefix="/collaborators", tags=["collaborators"])
templates = Jinja2Templates(directory="app/templates")


@router.get("", response_class=HTMLResponse)
async def collaborators(
    request: Request,
    view: str = "list",  # list | affiliation | country
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)

    if not current_user.author_id:
        return templates.TemplateResponse(
            request, "collaborators/index.html",
            {"request": request, "current_user": current_user, "active_page": "collaborators",
             "no_author": True, "collaborators": [], "view": view},
        )

    # Find all papers this user's author is on
    my_papers_result = await db.execute(
        select(PaperAuthor.paper_id).where(PaperAuthor.author_id == current_user.author_id)
    )
    my_paper_ids = [r[0] for r in my_papers_result.all()]

    if not my_paper_ids:
        return templates.TemplateResponse(
            request, "collaborators/index.html",
            {"request": request, "current_user": current_user, "active_page": "collaborators",
             "collaborators": [], "view": view},
        )

    # Find all co-authors on those papers (excluding self)
    co_result = await db.execute(
        select(Author)
        .join(PaperAuthor, PaperAuthor.author_id == Author.id)
        .options(
            selectinload(Author.author_affiliations).selectinload(AuthorAffiliation.affiliation)
        )
        .where(
            PaperAuthor.paper_id.in_(my_paper_ids),
            Author.id != current_user.author_id,
        )
        .distinct()
        .order_by(Author.last_name, Author.given_name)
    )
    collab_authors = co_result.scalars().all()

    # Group by affiliation
    by_affiliation: dict[str, list] = {}
    by_country: dict[str, list] = {}
    for author in collab_authors:
        current_affs = [aa for aa in author.author_affiliations if aa.end_date is None]
        if current_affs:
            for aa in current_affs:
                aff_name = aa.affiliation.name
                by_affiliation.setdefault(aff_name, []).append(author)
                country = aa.affiliation.country or "Unknown"
                by_country.setdefault(country, []).append(author)
        else:
            by_affiliation.setdefault("No Affiliation", []).append(author)
            by_country.setdefault("Unknown", []).append(author)

    return templates.TemplateResponse(
        request, "collaborators/index.html",
        {
            "request": request, "current_user": current_user, "active_page": "collaborators",
            "collaborators": collab_authors,
            "by_affiliation": dict(sorted(by_affiliation.items())),
            "by_country": dict(sorted(by_country.items())),
            "view": view,
        },
    )
