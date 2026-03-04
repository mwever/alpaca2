from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class GroupRole(str, PyEnum):
    admin = "admin"
    member = "member"


class ResearchGroup(Base):
    __tablename__ = "research_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parent_group_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("research_groups.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    parent: Mapped[Optional["ResearchGroup"]] = relationship(
        "ResearchGroup", remote_side="ResearchGroup.id", back_populates="subgroups"
    )
    subgroups: Mapped[list["ResearchGroup"]] = relationship("ResearchGroup", back_populates="parent")
    memberships: Mapped[list["GroupMembership"]] = relationship(
        "GroupMembership", back_populates="group", cascade="all, delete-orphan"
    )
    paper_shares: Mapped[list["PaperGroupShare"]] = relationship("PaperGroupShare", back_populates="group")


class GroupMembership(Base):
    __tablename__ = "group_memberships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("research_groups.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[GroupRole] = mapped_column(Enum(GroupRole), default=GroupRole.member, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    group: Mapped["ResearchGroup"] = relationship("ResearchGroup", back_populates="memberships")
    user: Mapped["User"] = relationship("User", back_populates="group_memberships")
