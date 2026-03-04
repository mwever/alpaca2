"""
Scholar data ingestion router.
Provides endpoints to accept crawler output (from the Google Scholar crawler)
and to display scholar data.
"""
import json
import re
from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.author import Author
from app.models.paper import PaperProject
from app.models.scholar import ScholarAuthorSnapshot, ScholarPaperSnapshot

router = APIRouter(prefix="/scholar", tags=["scholar"])
templates = Jinja2Templates(directory="app/templates")


def _ctx(request, current_user, **kw):
    return {"request": request, "current_user": current_user, "active_page": None, **kw}


# ── Ingestion API ──────────────────────────────────────────────────────────────

@router.post("/ingest/author/{author_id}", response_class=JSONResponse)
async def ingest_author_stats(
    request: Request,
    author_id: int,
    snap_date: str = Form(default=""),
    citations: str = Form(default=""),
    h_index: str = Form(default=""),
    i10_index: str = Form(default=""),
    gs_entries: str = Form(default=""),
    current_year_citations: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    """
    Accept a Google Scholar author stats snapshot.
    Can also be called with JSON body:
      {"citations": "302", "h-index": "7", "i10-index": "7", "gs_entries": 21, "current_year_citations": "14"}
    """
    # Accept both form and JSON
    body = None
    ct = request.headers.get("content-type", "")
    if "application/json" in ct:
        body = await request.json()
        snap_date = body.get("date", snap_date)
        citations = str(body.get("citations", citations))
        h_index = str(body.get("h-index", h_index))
        i10_index = str(body.get("i10-index", i10_index))
        gs_entries = str(body.get("gs_entries", gs_entries))
        current_year_citations = str(body.get("current_year_citations", current_year_citations))

    record_date = date.fromisoformat(snap_date) if snap_date else date.today()

    def _int(v):
        try:
            return int(v) if v else None
        except (ValueError, TypeError):
            return None

    snap = ScholarAuthorSnapshot(
        author_id=author_id,
        date=record_date,
        citations=_int(citations),
        h_index=_int(h_index),
        i10_index=_int(i10_index),
        gs_entries=_int(gs_entries),
        current_year_citations=_int(current_year_citations),
    )
    db.add(snap)
    await db.commit()
    return {"status": "ok", "id": snap.id}


@router.post("/ingest/papers/{author_id}", response_class=JSONResponse)
async def ingest_author_papers(
    request: Request,
    author_id: int,
    snap_date: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    """
    Accept a JSON list of papers scraped from an author's Google Scholar profile.
    POST with Content-Type: application/json and body = the array from the crawler.
    """
    ct = request.headers.get("content-type", "")
    if "application/json" in ct:
        papers = await request.json()
    else:
        raw = await request.body()
        papers = json.loads(raw)

    record_date = date.fromisoformat(snap_date) if snap_date else date.today()

    def _int(v):
        try:
            return int(v) if v else None
        except (ValueError, TypeError):
            return None

    # Try to match paper to an existing PaperProject by google_scholar_paper_id
    created = 0
    for entry in papers:
        gs_paper_id = entry.get("paper_id", "")
        if not gs_paper_id:
            continue
        # Look up linked paper project
        paper_result = await db.execute(
            select(PaperProject).where(PaperProject.google_scholar_paper_id == gs_paper_id)
        )
        paper = paper_result.scalar_one_or_none()
        snap = ScholarPaperSnapshot(
            paper_id=paper.id if paper else None,
            gs_paper_id=gs_paper_id,
            date=record_date,
            num_citations=_int(entry.get("num_citations")),
            title=entry.get("paper_title", "")[:512],
            year=str(entry.get("year", ""))[:8],
            venue=re.sub(r"<[^>]+>", "", str(entry.get("venue", "")))[:512],
            author_list=entry.get("author_list", ""),
        )
        db.add(snap)
        created += 1

    await db.commit()
    return {"status": "ok", "created": created}


# ── UI views ───────────────────────────────────────────────────────────────────

@router.get("/authors/{author_id}", response_class=HTMLResponse)
async def scholar_author_history(
    request: Request, author_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    author = (await db.execute(select(Author).where(Author.id == author_id))).scalar_one_or_none()
    if not author:
        return RedirectResponse("/authors", 302)
    snaps = (await db.execute(
        select(ScholarAuthorSnapshot)
        .where(ScholarAuthorSnapshot.author_id == author_id)
        .order_by(ScholarAuthorSnapshot.date.desc())
    )).scalars().all()
    return templates.TemplateResponse(
        request, "scholar/author_history.html",
        _ctx(request, current_user, author=author, snapshots=snaps),
    )
