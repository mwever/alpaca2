from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    author_id: Mapped[Optional[int]] = mapped_column(ForeignKey("authors.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    author: Mapped[Optional["Author"]] = relationship("Author", back_populates="user", foreign_keys=[author_id])
    group_memberships: Mapped[list["GroupMembership"]] = relationship("GroupMembership", back_populates="user")
    comments: Mapped[list["PaperComment"]] = relationship("PaperComment", back_populates="user")
    todos_assigned: Mapped[list["TodoItem"]] = relationship("TodoItem", back_populates="assigned_user")
    starred_editions: Mapped[list["StarredConferenceEdition"]] = relationship(
        "StarredConferenceEdition", back_populates="user"
    )
