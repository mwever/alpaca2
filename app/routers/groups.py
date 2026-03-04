from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user
from app.models.group import GroupMembership, GroupRole, ResearchGroup
from app.models.paper import PaperAuthor, PaperGroupShare, PaperProject, PAPER_STATUS_LABELS, PAPER_STATUS_COLORS
from app.models.user import User
from app.routers.papers import _visibility_filter

router = APIRouter(prefix="/groups", tags=["groups"])
templates = Jinja2Templates(directory="app/templates")
PAGE_SIZE = 25


def _ctx(request, current_user, **kw):
    return {"request": request, "current_user": current_user, "active_page": "groups", **kw}


async def _check_group_admin(db: AsyncSession, group_id: int, current_user) -> bool:
    """Return True if current_user is a site admin or a group admin of group_id."""
    if current_user.is_admin:
        return True
    m = (await db.execute(
        select(GroupMembership).where(
            (GroupMembership.group_id == group_id) &
            (GroupMembership.user_id == current_user.id) &
            (GroupMembership.role == GroupRole.admin)
        )
    )).scalar_one_or_none()
    return m is not None


@router.get("", response_class=HTMLResponse)
async def list_groups(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(
        select(ResearchGroup)
        .options(
            selectinload(ResearchGroup.memberships).selectinload(GroupMembership.user),
            selectinload(ResearchGroup.subgroups),
            selectinload(ResearchGroup.parent),
        )
        .join(GroupMembership, GroupMembership.group_id == ResearchGroup.id)
        .where(GroupMembership.user_id == current_user.id)
        .order_by(ResearchGroup.name)
    )
    groups = result.scalars().all()
    return templates.TemplateResponse(request, "groups/list.html",
                                      _ctx(request, current_user, groups=groups))


@router.get("/new", response_class=HTMLResponse)
async def new_group_form(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    all_groups = (await db.execute(select(ResearchGroup).order_by(ResearchGroup.name))).scalars().all()
    return templates.TemplateResponse(request, "groups/form.html",
                                      _ctx(request, current_user, group=None,
                                           all_groups=all_groups, action="/groups"))


@router.post("")
async def create_group(
    request: Request,
    name: str = Form(...),
    description: str = Form(default=""),
    parent_group_id: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    group = ResearchGroup(
        name=name, description=description or None,
        parent_group_id=int(parent_group_id) if parent_group_id else None,
    )
    db.add(group)
    await db.flush()
    # Creator becomes admin
    db.add(GroupMembership(group_id=group.id, user_id=current_user.id, role=GroupRole.admin))
    await db.commit()
    return RedirectResponse(f"/groups/{group.id}", 302)


@router.get("/{group_id}", response_class=HTMLResponse)
async def group_detail(
    request: Request, group_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(
        select(ResearchGroup)
        .options(
            selectinload(ResearchGroup.memberships).selectinload(GroupMembership.user),
            selectinload(ResearchGroup.subgroups),
            selectinload(ResearchGroup.paper_shares).selectinload(PaperGroupShare.paper)
            .selectinload(PaperProject.paper_authors).selectinload(PaperAuthor.author),
        )
        .where(ResearchGroup.id == group_id)
    )
    group = result.scalar_one_or_none()
    if not group:
        return RedirectResponse("/groups", 302)

    is_member = any(m.user_id == current_user.id for m in group.memberships)
    if not is_member and not current_user.is_admin:
        return RedirectResponse("/groups", 302)

    is_admin = current_user.is_admin or any(
        m.user_id == current_user.id and m.role == GroupRole.admin
        for m in group.memberships
    )
    all_users = (await db.execute(select(User).where(User.is_active == True))).scalars().all()
    all_papers = (await db.execute(
        select(PaperProject)
        .where(_visibility_filter(current_user.id, current_user.author_id))
        .order_by(PaperProject.title)
    )).scalars().all()

    return templates.TemplateResponse(
        request, "groups/detail.html",
        _ctx(request, current_user, group=group, is_admin=is_admin,
             all_users=all_users, all_papers=all_papers,
             status_labels=PAPER_STATUS_LABELS, status_colors=PAPER_STATUS_COLORS),
    )


@router.get("/{group_id}/edit", response_class=HTMLResponse)
async def edit_group_form(
    request: Request, group_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(
        select(ResearchGroup)
        .options(selectinload(ResearchGroup.memberships))
        .where(ResearchGroup.id == group_id)
    )
    group = result.scalar_one_or_none()
    if not group:
        return RedirectResponse("/groups", 302)
    is_admin = current_user.is_admin or any(
        m.user_id == current_user.id and m.role == GroupRole.admin for m in group.memberships
    )
    if not is_admin:
        return RedirectResponse(f"/groups/{group_id}", 302)
    all_groups = (await db.execute(
        select(ResearchGroup).where(ResearchGroup.id != group_id).order_by(ResearchGroup.name)
    )).scalars().all()
    return templates.TemplateResponse(request, "groups/form.html",
                                      _ctx(request, current_user, group=group,
                                           all_groups=all_groups,
                                           action=f"/groups/{group_id}/edit"))


@router.post("/{group_id}/edit")
async def update_group(
    group_id: int,
    name: str = Form(...),
    description: str = Form(default=""),
    parent_group_id: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(
        select(ResearchGroup).options(selectinload(ResearchGroup.memberships))
        .where(ResearchGroup.id == group_id)
    )
    group = result.scalar_one_or_none()
    if not group:
        return RedirectResponse("/groups", 302)
    is_admin = current_user.is_admin or any(
        m.user_id == current_user.id and m.role == GroupRole.admin for m in group.memberships
    )
    if not is_admin:
        return RedirectResponse(f"/groups/{group_id}", 302)
    group.name = name
    group.description = description or None
    group.parent_group_id = int(parent_group_id) if parent_group_id else None
    await db.commit()
    return RedirectResponse(f"/groups/{group_id}", 302)


@router.post("/{group_id}/delete")
async def delete_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    result = await db.execute(
        select(ResearchGroup).options(selectinload(ResearchGroup.memberships))
        .where(ResearchGroup.id == group_id)
    )
    group = result.scalar_one_or_none()
    if group:
        is_admin = current_user.is_admin or any(
            m.user_id == current_user.id and m.role == GroupRole.admin for m in group.memberships
        )
        if is_admin:
            await db.delete(group)
            await db.commit()
    return RedirectResponse("/groups", 302)


@router.post("/{group_id}/members/add")
async def add_member(
    group_id: int,
    user_id: int = Form(...),
    role: str = Form(default="member"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    if not await _check_group_admin(db, group_id, current_user):
        return RedirectResponse(f"/groups/{group_id}", 302)
    existing = (await db.execute(
        select(GroupMembership).where(
            (GroupMembership.group_id == group_id) & (GroupMembership.user_id == user_id)
        )
    )).scalar_one_or_none()
    if not existing:
        db.add(GroupMembership(group_id=group_id, user_id=user_id, role=GroupRole(role)))
        await db.commit()
    return RedirectResponse(f"/groups/{group_id}", 302)


@router.post("/{group_id}/members/{user_id}/remove")
async def remove_member(
    group_id: int, user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    if not await _check_group_admin(db, group_id, current_user):
        return RedirectResponse(f"/groups/{group_id}", 302)
    result = await db.execute(
        select(GroupMembership).where(
            (GroupMembership.group_id == group_id) & (GroupMembership.user_id == user_id)
        )
    )
    m = result.scalar_one_or_none()
    if m:
        await db.delete(m)
        await db.commit()
    return RedirectResponse(f"/groups/{group_id}", 302)


@router.post("/{group_id}/papers/add")
async def share_paper(
    group_id: int,
    paper_id: int = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    if not await _check_group_admin(db, group_id, current_user):
        return RedirectResponse(f"/groups/{group_id}", 302)
    existing = (await db.execute(
        select(PaperGroupShare).where(
            (PaperGroupShare.group_id == group_id) & (PaperGroupShare.paper_id == paper_id)
        )
    )).scalar_one_or_none()
    if not existing:
        db.add(PaperGroupShare(group_id=group_id, paper_id=paper_id))
        await db.commit()
    return RedirectResponse(f"/groups/{group_id}", 302)


@router.post("/{group_id}/papers/{paper_id}/remove")
async def unshare_paper(
    group_id: int, paper_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not current_user:
        return RedirectResponse("/login", 302)
    if not await _check_group_admin(db, group_id, current_user):
        return RedirectResponse(f"/groups/{group_id}", 302)
    result = await db.execute(
        select(PaperGroupShare).where(
            (PaperGroupShare.group_id == group_id) & (PaperGroupShare.paper_id == paper_id)
        )
    )
    share = result.scalar_one_or_none()
    if share:
        await db.delete(share)
        await db.commit()
    return RedirectResponse(f"/groups/{group_id}", 302)
