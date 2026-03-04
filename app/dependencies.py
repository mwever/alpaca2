from typing import Annotated, Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Return the logged-in User or None."""
    from app.models.user import User

    user_id = request.session.get("user_id")
    if not user_id:
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


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


CurrentUser = Annotated[Optional[object], Depends(get_current_user)]
RequireUser = Annotated[object, Depends(require_user)]
RequireAdmin = Annotated[object, Depends(require_admin)]
