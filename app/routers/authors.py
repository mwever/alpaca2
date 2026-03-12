import json
import os
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from app.templating import templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.affiliation import Affiliation, AuthorAffiliation
from app.models.author import Author
from app.models.conference import Conference, ConferenceEdition
from app.models.journal import Journal
from app.models.paper import (
    PaperAuthor, PaperConferenceSubmission, PaperJournalSubmission,
    PaperProject, PaperStatus, SubmissionStatus,
)
from app.models.scholar import ScholarAuthorSnapshot
from app.models.service import ServiceRecord, ServiceRole
from app.orcid_client import (
    OrcidRecord, OrcidContributor, fetch_orcid_record, validate_orcid,
    best_matches, top_match, map_orcid_role, work_venue_type, orcid_url,
)
from app.dblp_client import (
    DblpAuthorHit, DblpWork, extract_dblp_pid, dblp_url,
    search_dblp_authors, fetch_dblp_works,
)

router = APIRouter(prefix="/authors", tags=["authors"])

PAGE_SIZE = 25
_PHOTO_DIR = "static/uploads/author_photos"
_ALLOWED_TYPES = {"image/png", "image/jpeg", "image/webp"}
_PHOTO_EXTS = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}


async def _save_photo(photo: UploadFile, author_id: int) -> str | None:
    if not photo or not photo.filename or photo.content_type not in _ALLOWED_TYPES:
        return None
    os.makedirs(_PHOTO_DIR, exist_ok=True)
    ext = _PHOTO_EXTS[photo.content_type]
    for old_ext in _PHOTO_EXTS.values():
        old = os.path.join(_PHOTO_DIR, f"{author_id}{old_ext}")
        if os.path.exists(old):
            os.remove(old)
    path = os.path.join(_PHOTO_DIR, f"{author_id}{ext}")
    with open(path, "wb") as f:
        f.write(await photo.read())
    return f"/static/uploads/author_photos/{author_id}{ext}"


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
        selectinload(Author.paper_authors).selectinload(PaperAuthor.paper),
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

    # Compute per-author visible paper counts using the same visibility rules as detail page
    joint_paper_ids: set[int] = set()
    if current_user.author_id:
        rows = (await db.execute(
            select(PaperAuthor.paper_id)
            .where(PaperAuthor.author_id == current_user.author_id)
        )).all()
        joint_paper_ids = {r[0] for r in rows}

    visible_paper_counts: dict[int, int] = {}
    for author in items:
        is_own = current_user.author_id == author.id
        if is_own:
            visible_paper_counts[author.id] = len(author.paper_authors)
        else:
            visible_paper_counts[author.id] = sum(
                1 for pa in author.paper_authors
                if pa.paper.status in (PaperStatus.accepted, PaperStatus.published)
                or pa.paper_id in joint_paper_ids
            )

    query_params = {"q": q} if q else {}
    return templates.TemplateResponse(
        request, "authors/list.html",
        _ctx(request, current_user, authors=items, total=total, page=page,
             total_pages=(total + PAGE_SIZE - 1) // PAGE_SIZE, q=q,
             query_params=query_params,
             visible_paper_counts=visible_paper_counts),
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
    orcid: str = Form(default=""),
    dblp_pid: str = Form(default=""),
    affiliation_id: Optional[int] = Form(default=None),
    aff_start: str = Form(default=""),
    photo: UploadFile = File(default=None),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    cleaned_orcid = validate_orcid(orcid) if orcid.strip() else None
    author = Author(
        last_name=last_name, given_name=given_name,
        email=email or None, nationality=nationality or None,
        google_scholar_id=google_scholar_id or None,
        orcid=cleaned_orcid,
        dblp_pid=dblp_pid.strip() or None,
    )
    db.add(author)
    await db.flush()
    photo_path = await _save_photo(photo, author.id)
    if photo_path:
        author.photo_path = photo_path
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

    # Determine which paper_authors are visible to the current user.
    # Own profile → show all. Another author's profile → only accepted/published
    # OR papers where the current user is also an author.
    is_own_profile = current_user.author_id and current_user.author_id == author_id
    if is_own_profile:
        visible_paper_authors = list(author.paper_authors)
    else:
        joint_paper_ids: set[int] = set()
        if current_user.author_id:
            rows = (await db.execute(
                select(PaperAuthor.paper_id)
                .where(PaperAuthor.author_id == current_user.author_id)
            )).all()
            joint_paper_ids = {r[0] for r in rows}
        visible_paper_authors = [
            pa for pa in author.paper_authors
            if pa.paper.status in (PaperStatus.accepted, PaperStatus.published)
            or pa.paper_id in joint_paper_ids
        ]

    # ── Collaboration graph ─────────────────────────────────────────────────────
    visible_paper_ids = [pa.paper_id for pa in visible_paper_authors]
    graph_nodes_json = "[]"
    graph_edges_json = "[]"
    if visible_paper_ids:
        all_pa_rows = (await db.execute(
            select(PaperAuthor.paper_id, PaperAuthor.author_id)
            .where(PaperAuthor.paper_id.in_(visible_paper_ids))
        )).all()
        paper_author_sets: dict[int, set[int]] = {}
        co_author_ids: set[int] = set()
        for pid, aid in all_pa_rows:
            paper_author_sets.setdefault(pid, set()).add(aid)
            if aid != author_id:
                co_author_ids.add(aid)
        co_authors_q = []
        if co_author_ids:
            co_authors_q = (await db.execute(
                select(Author)
                .where(Author.id.in_(co_author_ids))
                .order_by(Author.last_name, Author.given_name)
            )).scalars().all()
        edge_weights: dict[tuple[int, int], int] = {}
        for pid, aids in paper_author_sets.items():
            present = aids & co_author_ids
            for cid in present:
                key = (author_id, cid)
                edge_weights[key] = edge_weights.get(key, 0) + 1
            if author_id in aids:
                cl = sorted(present)
                for i, a in enumerate(cl):
                    for b in cl[i + 1:]:
                        key = (a, b)
                        edge_weights[key] = edge_weights.get(key, 0) + 1
        graph_nodes = [{"id": author_id, "label": author.full_name, "group": "self"}]
        for a in co_authors_q:
            graph_nodes.append({"id": a.id, "label": a.full_name, "group": "collab"})
        graph_edges = [
            {"from": a, "to": b, "value": w, "title": f"{w} joint paper{'s' if w != 1 else ''}"}
            for (a, b), w in edge_weights.items()
        ]
        graph_nodes_json = json.dumps(graph_nodes)
        graph_edges_json = json.dumps(graph_edges)

    is_own_page = current_user.author_id and current_user.author_id == author_id
    ctx = _ctx(request, current_user, author=author, latest_snap=latest_snap,
               snapshots=snapshots, affiliations=affiliations,
               visible_paper_authors=visible_paper_authors,
               graph_nodes_json=graph_nodes_json,
               graph_edges_json=graph_edges_json)
    if is_own_page:
        ctx["active_page"] = "profile"
    return templates.TemplateResponse(request, "authors/detail.html", ctx)


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
    orcid: str = Form(default=""),
    dblp_pid: str = Form(default=""),
    photo: UploadFile = File(default=None),
    remove_photo: str = Form(default=""),
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
    author.orcid = validate_orcid(orcid) if orcid.strip() else None
    author.dblp_pid = dblp_pid.strip() or None
    if remove_photo:
        for ext in _PHOTO_EXTS.values():
            p = os.path.join(_PHOTO_DIR, f"{author_id}{ext}")
            if os.path.exists(p):
                os.remove(p)
        author.photo_path = None
    else:
        photo_path = await _save_photo(photo, author_id)
        if photo_path:
            author.photo_path = photo_path
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
        for ext in _PHOTO_EXTS.values():
            p = os.path.join(_PHOTO_DIR, f"{author_id}{ext}")
            if os.path.exists(p):
                os.remove(p)
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


# ── ORCID import ──────────────────────────────────────────────────────────────

def _orcid_ctx(request, current_user, author, **kw):
    return _ctx(request, current_user, author=author, service_roles=list(ServiceRole), **kw)


@router.get("/{author_id}/orcid-import", response_class=HTMLResponse)
async def orcid_import_form(
    request: Request,
    author_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    author = (await db.execute(
        select(Author).options(selectinload(Author.user)).where(Author.id == author_id)
    )).scalar_one_or_none()
    if not author:
        return RedirectResponse("/authors", 302)
    return templates.TemplateResponse(
        request, "authors/orcid_import.html",
        _orcid_ctx(request, current_user, author=author, phase="fetch",
                   record=None, error=None, affiliations=[], journals=[],
                   conferences=[], aff_matches=[], rev_matches=[],
                   work_venue_matches=[], work_coauthor_matches=[],
                   existing_papers=set()),
    )


@router.post("/{author_id}/orcid-import/fetch", response_class=HTMLResponse)
async def orcid_import_fetch(
    request: Request,
    author_id: int,
    orcid: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    author = (await db.execute(
        select(Author).options(selectinload(Author.user)).where(Author.id == author_id)
    )).scalar_one_or_none()
    if not author:
        return RedirectResponse("/authors", 302)

    cleaned = validate_orcid(orcid)
    if not cleaned:
        return templates.TemplateResponse(
            request, "authors/orcid_import.html",
            _orcid_ctx(request, current_user, author=author, phase="fetch",
                       record=None, error="Invalid ORCID format.", affiliations=[],
                       journals=[], conferences=[], aff_matches=[], rev_matches=[],
                       existing_papers=set()),
        )

    record = await fetch_orcid_record(cleaned)

    affiliations = (await db.execute(select(Affiliation).order_by(Affiliation.name))).scalars().all()
    journals = (await db.execute(select(Journal).order_by(Journal.name))).scalars().all()
    conferences = (await db.execute(select(Conference).order_by(Conference.name))).scalars().all()

    aff_names = [a.name for a in affiliations]
    journal_names = [j.name for j in journals]
    conf_names = [c.name for c in conferences]

    aff_matches = []
    for emp in record.employments:
        hits = best_matches(emp.org_name, aff_names, threshold=0.35, top=5)
        aff_matches.append([(affiliations[i].id, affiliations[i].name, s) for s, i in hits])

    rev_matches = []
    for rev in record.reviews:
        j_hits = best_matches(rev.venue_name, journal_names, threshold=0.35, top=3)
        c_hits = best_matches(rev.venue_name, conf_names, threshold=0.35, top=3)
        rev_matches.append({
            "journal": [(journals[i].id, journals[i].name, s) for s, i in j_hits],
            "conference": [(conferences[i].id, conferences[i].name, s) for s, i in c_hits],
        })

    # ── Venue matches per work ─────────────────────────────────────────────────
    work_venue_matches = []
    for work in record.works:
        if work.journal_name:
            j_hits = best_matches(work.journal_name, journal_names, threshold=0.35, top=3)
            c_hits = best_matches(work.journal_name, conf_names, threshold=0.35, top=3)
            work_venue_matches.append({
                "journal": [(journals[i].id, journals[i].name, s) for s, i in j_hits],
                "conference": [(conferences[i].id, conferences[i].name, s) for s, i in c_hits],
                "venue_type": work_venue_type(work.work_type),
            })
        else:
            work_venue_matches.append({"journal": [], "conference": [], "venue_type": "other"})

    # ── Co-author matches per work ─────────────────────────────────────────────
    all_authors = (await db.execute(
        select(Author).order_by(Author.last_name, Author.given_name)
    )).scalars().all()
    author_display_names = [a.full_name for a in all_authors]

    work_coauthor_matches: list[list[dict]] = []
    for work in record.works:
        per_work = []
        for contrib in work.contributors:
            # Skip if this contributor is the author being imported (matched by ORCID)
            if contrib.orcid and contrib.orcid == record.orcid:
                continue
            hits = best_matches(contrib.name, author_display_names, threshold=0.55, top=3)
            per_work.append({
                "contrib": contrib,
                "matches": [(all_authors[i].id, all_authors[i].full_name, s) for s, i in hits],
            })
        work_coauthor_matches.append(per_work)

    paper_rows = (await db.execute(
        select(PaperProject.title)
        .join(PaperAuthor, PaperAuthor.paper_id == PaperProject.id)
        .where(PaperAuthor.author_id == author_id)
    )).all()
    existing_papers = {r[0].lower() for r in paper_rows}

    return templates.TemplateResponse(
        request, "authors/orcid_import.html",
        _orcid_ctx(request, current_user, author=author, phase="preview",
                   record=record, error=None, affiliations=affiliations,
                   journals=journals, conferences=conferences,
                   aff_matches=aff_matches, rev_matches=rev_matches,
                   work_venue_matches=work_venue_matches,
                   work_coauthor_matches=work_coauthor_matches,
                   existing_papers=existing_papers),
    )


@router.post("/{author_id}/orcid-import/apply")
async def orcid_import_apply(
    request: Request,
    author_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    author = (await db.execute(
        select(Author).options(selectinload(Author.user)).where(Author.id == author_id)
    )).scalar_one_or_none()
    if not author:
        return RedirectResponse("/authors", 302)

    form = await request.form()
    orcid_val = (form.get("orcid") or "").strip()
    if not orcid_val:
        return RedirectResponse(f"/authors/{author_id}", 302)

    record = await fetch_orcid_record(orcid_val)
    if record.error:
        return RedirectResponse(f"/authors/{author_id}", 302)

    if not author.orcid:
        author.orcid = orcid_val

    # ── Affiliations ──────────────────────────────────────────────────────
    for i, emp in enumerate(record.employments):
        if not form.get(f"emp_{i}_import"):
            continue
        aff_action = (form.get(f"emp_{i}_affiliation_id") or "skip").strip()
        if aff_action == "skip":
            continue
        start_date = date(emp.start_year, 1, 1) if emp.start_year else None
        end_date = date(emp.end_year, 12, 31) if emp.end_year else None

        if aff_action == "new":
            aff = Affiliation(name=emp.org_name, country=emp.country or None)
            db.add(aff)
            await db.flush()
            affiliation_id = aff.id
        else:
            try:
                affiliation_id = int(aff_action)
            except ValueError:
                continue

        dup = (await db.execute(
            select(AuthorAffiliation).where(
                AuthorAffiliation.author_id == author_id,
                AuthorAffiliation.affiliation_id == affiliation_id,
            )
        )).scalar_one_or_none()
        if not dup:
            db.add(AuthorAffiliation(
                author_id=author_id, affiliation_id=affiliation_id,
                start_date=start_date, end_date=end_date,
            ))

    # ── Publications ──────────────────────────────────────────────────────
    paper_rows = (await db.execute(
        select(PaperProject.title)
        .join(PaperAuthor, PaperAuthor.paper_id == PaperProject.id)
        .where(PaperAuthor.author_id == author_id)
    )).all()
    existing_papers = {r[0].lower() for r in paper_rows}

    # Track contributors by name to avoid re-creating the same Author twice
    # if the same person appears across multiple works.
    new_coauthor_cache: dict[str, int] = {}  # name_lower → author_id

    for i, work in enumerate(record.works):
        if not form.get(f"work_{i}_import"):
            continue
        if work.title.lower() in existing_papers:
            continue
        pub_date = date(work.year, 1, 1) if work.year else None
        status = PaperStatus.published if work.year else PaperStatus.accepted
        paper = PaperProject(
            title=work.title, status=status,
            published_date=pub_date, created_by=current_user.id,
        )
        db.add(paper)
        await db.flush()
        db.add(PaperAuthor(paper_id=paper.id, author_id=author_id, position=1))
        existing_papers.add(work.title.lower())

        # ── Venue (journal / conference) ──────────────────────────────────
        venue_raw = (form.get(f"work_{i}_venue_id") or "skip").strip()
        if venue_raw != "skip":
            year = work.year or date.today().year
            if venue_raw == "new_j":
                j = Journal(name=work.journal_name or f"Unknown ({work.title[:40]})")
                db.add(j)
                await db.flush()
                db.add(PaperJournalSubmission(
                    paper_id=paper.id, journal_id=j.id,
                    status=SubmissionStatus.accepted,
                ))
            elif venue_raw == "new_c":
                vname = work.journal_name or f"Unknown Conference ({year})"
                conf = Conference(name=vname, abbreviation=vname[:32])
                db.add(conf)
                await db.flush()
                edition = ConferenceEdition(conference_id=conf.id, year=year)
                db.add(edition)
                await db.flush()
                db.add(PaperConferenceSubmission(
                    paper_id=paper.id, conference_edition_id=edition.id,
                    status=SubmissionStatus.accepted,
                ))
            elif venue_raw.startswith("j_"):
                try:
                    jid = int(venue_raw[2:])
                    db.add(PaperJournalSubmission(
                        paper_id=paper.id, journal_id=jid,
                        status=SubmissionStatus.accepted,
                    ))
                except ValueError:
                    pass
            elif venue_raw.startswith("c_"):
                try:
                    conf_id = int(venue_raw[2:])
                    edition = (await db.execute(
                        select(ConferenceEdition).where(
                            ConferenceEdition.conference_id == conf_id,
                            ConferenceEdition.year == year,
                        )
                    )).scalar_one_or_none()
                    if not edition:
                        edition = ConferenceEdition(conference_id=conf_id, year=year)
                        db.add(edition)
                        await db.flush()
                    db.add(PaperConferenceSubmission(
                        paper_id=paper.id, conference_edition_id=edition.id,
                        status=SubmissionStatus.accepted,
                    ))
                except ValueError:
                    pass

        # ── Co-authors ────────────────────────────────────────────────────
        # Filter out the main author (already added above)
        contribs = [
            c for c in work.contributors
            if not (c.orcid and c.orcid == record.orcid)
        ]
        position = 2
        for j, contrib in enumerate(contribs):
            raw_val = (form.get(f"work_{i}_coauthor_{j}") or "skip").strip()
            if raw_val == "skip":
                continue
            co_id: int | None = None
            if raw_val == "new":
                # Create a minimal Author record
                cache_key = contrib.name.lower()
                if cache_key in new_coauthor_cache:
                    co_id = new_coauthor_cache[cache_key]
                else:
                    # Split name heuristically: "Given Family" or "Family, Given"
                    if "," in contrib.name:
                        parts = [p.strip() for p in contrib.name.split(",", 1)]
                        last, given = parts[0], parts[1] if len(parts) > 1 else ""
                    else:
                        parts = contrib.name.rsplit(" ", 1)
                        last = parts[-1]
                        given = parts[0] if len(parts) > 1 else ""
                    new_author = Author(
                        last_name=last, given_name=given,
                        orcid=validate_orcid(contrib.orcid) if contrib.orcid else None,
                    )
                    db.add(new_author)
                    await db.flush()
                    co_id = new_author.id
                    new_coauthor_cache[cache_key] = co_id
            else:
                try:
                    co_id = int(raw_val)
                except ValueError:
                    continue
                if co_id == author_id:
                    continue  # already added as position 1

            if co_id:
                db.add(PaperAuthor(paper_id=paper.id, author_id=co_id, position=position))
                position += 1

    # ── Review Services ───────────────────────────────────────────────────
    linked_user_id = author.user.id if author.user else None
    if linked_user_id:
        for i, rev in enumerate(record.reviews):
            if not form.get(f"rev_{i}_import"):
                continue
            venue_raw = (form.get(f"rev_{i}_venue_id") or "skip").strip()
            if venue_raw == "skip":
                continue
            role_str = (form.get(f"rev_{i}_role") or "reviewer").strip()
            try:
                role = ServiceRole(role_str)
            except ValueError:
                role = ServiceRole.reviewer
            year = rev.year or date.today().year
            conference_edition_id = None
            journal_id = None

            if venue_raw == "new_j":
                j = Journal(name=rev.venue_name)
                db.add(j)
                await db.flush()
                journal_id = j.id
            elif venue_raw == "new_c":
                conf = Conference(name=rev.venue_name, abbreviation=rev.venue_name[:32])
                db.add(conf)
                await db.flush()
                edition = ConferenceEdition(conference_id=conf.id, year=year)
                db.add(edition)
                await db.flush()
                conference_edition_id = edition.id
            elif venue_raw.startswith("j_"):
                try:
                    journal_id = int(venue_raw[2:])
                except ValueError:
                    continue
            elif venue_raw.startswith("c_"):
                try:
                    conf_id = int(venue_raw[2:])
                except ValueError:
                    continue
                edition = (await db.execute(
                    select(ConferenceEdition).where(
                        ConferenceEdition.conference_id == conf_id,
                        ConferenceEdition.year == year,
                    )
                )).scalar_one_or_none()
                if not edition:
                    edition = ConferenceEdition(conference_id=conf_id, year=year)
                    db.add(edition)
                    await db.flush()
                conference_edition_id = edition.id
            else:
                continue

            if journal_id:
                dup = (await db.execute(
                    select(ServiceRecord).where(
                        ServiceRecord.user_id == linked_user_id,
                        ServiceRecord.journal_id == journal_id,
                        ServiceRecord.year == year,
                        ServiceRecord.role == role,
                    )
                )).scalar_one_or_none()
            else:
                dup = (await db.execute(
                    select(ServiceRecord).where(
                        ServiceRecord.user_id == linked_user_id,
                        ServiceRecord.conference_edition_id == conference_edition_id,
                        ServiceRecord.role == role,
                    )
                )).scalar_one_or_none()
            if dup:
                continue

            db.add(ServiceRecord(
                user_id=linked_user_id,
                conference_edition_id=conference_edition_id,
                journal_id=journal_id,
                year=year, role=role,
            ))

    await db.commit()
    return RedirectResponse(f"/authors/{author_id}", 302)


# ── DBLP import ───────────────────────────────────────────────────────────────

async def _dblp_coauthor_matches(
    db: AsyncSession,
    works: list[DblpWork],
) -> dict[str, list[tuple[int, str, float]]]:
    """Load all Alpaca authors and pre-compute fuzzy matches for unique DBLP co-author names."""
    all_authors = (await db.execute(
        select(Author).order_by(Author.last_name, Author.given_name)
    )).scalars().all()
    display_names = [a.full_name for a in all_authors]

    unique_names = {ca.name for w in works for ca in w.co_authors}
    matches: dict[str, list[tuple[int, str, float]]] = {}
    for name in unique_names:
        hits = best_matches(name, display_names, threshold=0.55, top=3)
        matches[name] = [(all_authors[i].id, all_authors[i].full_name, s) for s, i in hits]
    return matches


@router.get("/{author_id}/dblp-import", response_class=HTMLResponse)
async def dblp_import_form(
    request: Request,
    author_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    author = (await db.execute(select(Author).where(Author.id == author_id))).scalar_one_or_none()
    if not author:
        return RedirectResponse("/authors", 302)
    return templates.TemplateResponse(
        request, "authors/dblp_import.html",
        _ctx(request, current_user, author=author, phase="search",
             author_hits=[], works=[], coauthor_matches={}, error=None,
             dblp_name="", dblp_pid_val="", existing_papers=set()),
    )


@router.post("/{author_id}/dblp-import/search", response_class=HTMLResponse)
async def dblp_import_search(
    request: Request,
    author_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    author = (await db.execute(select(Author).where(Author.id == author_id))).scalar_one_or_none()
    if not author:
        return RedirectResponse("/authors", 302)

    form = await request.form()
    pid_field = (form.get("pid") or "").strip()
    dblp_name_field = (form.get("dblp_name") or "").strip()
    query_field = (form.get("query") or "").strip()

    def _base(phase, error=None, **kw):
        return _ctx(request, current_user, author=author, phase=phase,
                    author_hits=[], works=[], coauthor_matches={},
                    dblp_name="", dblp_pid_val="", existing_papers=set(), error=error, **kw)

    async def _fetch_and_render(name: str, pid: str):
        works, err = await fetch_dblp_works(name, pid)
        if err:
            return templates.TemplateResponse(
                request, "authors/dblp_import.html", _base("search", error=err),
            )
        paper_rows = (await db.execute(
            select(PaperProject.title)
            .join(PaperAuthor, PaperAuthor.paper_id == PaperProject.id)
            .where(PaperAuthor.author_id == author_id)
        )).all()
        existing_papers = {r[0].lower() for r in paper_rows}
        coauthor_matches = await _dblp_coauthor_matches(db, works)
        return templates.TemplateResponse(
            request, "authors/dblp_import.html",
            _base("preview", works=works, coauthor_matches=coauthor_matches,
                  dblp_name=name, dblp_pid_val=pid, existing_papers=existing_papers),
        )

    # User selected a specific author from a prior search result
    if pid_field and dblp_name_field:
        return await _fetch_and_render(dblp_name_field, pid_field)

    if not query_field:
        return templates.TemplateResponse(
            request, "authors/dblp_import.html",
            _base("search", error="Please enter a DBLP profile URL or author name."),
        )

    # Check if query looks like a URL or raw PID
    pid_from_url = extract_dblp_pid(query_field)
    if pid_from_url:
        name_hint = pid_from_url.split("/")[-1].replace(":", " ").replace("_", " ")
        hits = await search_dblp_authors(name_hint, limit=5)
        matched = next((h for h in hits if h.pid == pid_from_url), None)
        if matched:
            return await _fetch_and_render(matched.name, matched.pid)
        query_field = name_hint  # fall through to name search

    hits = await search_dblp_authors(query_field, limit=10)
    if not hits:
        return templates.TemplateResponse(
            request, "authors/dblp_import.html",
            _base("search", error=f'No DBLP authors found matching "{query_field}".'),
        )
    if len(hits) == 1:
        return await _fetch_and_render(hits[0].name, hits[0].pid)

    return templates.TemplateResponse(
        request, "authors/dblp_import.html",
        _base("select", author_hits=hits),
    )


@router.post("/{author_id}/dblp-import/apply")
async def dblp_import_apply(
    request: Request,
    author_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    author = (await db.execute(select(Author).where(Author.id == author_id))).scalar_one_or_none()
    if not author:
        return RedirectResponse("/authors", 302)

    form = await request.form()
    dblp_name = (form.get("dblp_name") or "").strip()
    dblp_pid_val = (form.get("dblp_pid") or "").strip()
    if not dblp_name:
        return RedirectResponse(f"/authors/{author_id}", 302)

    works, err = await fetch_dblp_works(dblp_name, dblp_pid_val or None)
    if err or not works:
        return RedirectResponse(f"/authors/{author_id}", 302)

    if dblp_pid_val and not author.dblp_pid:
        author.dblp_pid = dblp_pid_val

    paper_rows = (await db.execute(
        select(PaperProject.title)
        .join(PaperAuthor, PaperAuthor.paper_id == PaperProject.id)
        .where(PaperAuthor.author_id == author_id)
    )).all()
    existing_papers = {r[0].lower() for r in paper_rows}

    for i, work in enumerate(works):
        if not form.get(f"work_{i}_import"):
            continue
        if work.title.lower() in existing_papers:
            continue
        pub_date = date(work.year, 1, 1) if work.year else None
        status = PaperStatus.published if work.year else PaperStatus.accepted
        paper = PaperProject(
            title=work.title, status=status,
            published_date=pub_date, created_by=current_user.id,
        )
        db.add(paper)
        await db.flush()

        db.add(PaperAuthor(paper_id=paper.id, author_id=author_id, position=1))

        position = 2
        for j, ca in enumerate(work.co_authors):
            raw_val = (form.get(f"coauthor_{i}_{j}") or "0").strip()
            try:
                co_id = int(raw_val)
            except ValueError:
                continue
            if co_id > 0 and co_id != author_id:
                db.add(PaperAuthor(paper_id=paper.id, author_id=co_id, position=position))
                position += 1

        existing_papers.add(work.title.lower())

    await db.commit()
    return RedirectResponse(f"/authors/{author_id}", 302)
