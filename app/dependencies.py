from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.feature_flags import user_has_feature

DbSession = Annotated[AsyncSession, Depends(get_db)]

_UNSET = object()


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Return the logged-in User or None."""
    from app.models.user import User

    cached = getattr(request.state, "current_user", _UNSET)
    if cached is not _UNSET:
        return cached

    user_id = request.session.get("user_id")
    if not user_id:
        request.state.current_user = None
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    request.state.current_user = user
    return user


async def require_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Return the logged-in User; raise 401 if not authenticated.
    Routes should catch this and redirect — or use the helper below.
    """
    user = await get_current_user(request, db)
    if user is None:
        raise HTTPException(status_code=302, headers={"Location": f"/login?next={request.url.path}"})
    return user


async def require_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    user = await require_user(request, db)
    if not user.is_admin:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return user


async def require_moderator(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Allow admins and moderators."""
    user = await require_user(request, db)
    if not (user.is_admin or user.is_moderator):
        raise HTTPException(status_code=302, headers={"Location": "/"})
    return user


CurrentUser = Annotated[Optional[object], Depends(get_current_user)]
RequireUser = Annotated[object, Depends(require_user)]
RequireAdmin = Annotated[object, Depends(require_admin)]
RequireModerator = Annotated[object, Depends(require_moderator)]


def require_feature(key: str):
    """Route dependency that blocks access when a feature flag is off for the user."""
    async def _check(request: Request, user=Depends(require_user)):
        if not user_has_feature(user.id, user.is_admin, key):
            raise HTTPException(status_code=302, headers={"Location": "/"})
    return Depends(_check)
