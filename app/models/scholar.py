from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ScholarAuthorSnapshot(Base):
    """Daily snapshot of a Google Scholar author profile's statistics."""

    __tablename__ = "scholar_author_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id", ondelete="CASCADE"), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    citations: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    h_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    i10_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    gs_entries: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    current_year_citations: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    author: Mapped["Author"] = relationship("Author", back_populates="scholar_snapshots")


class ScholarPaperSnapshot(Base):
    """Daily snapshot of a paper's citation count from Google Scholar."""

    __tablename__ = "scholar_paper_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    paper_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("paper_projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    gs_paper_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    num_citations: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    year: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    venue: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    author_list: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    paper: Mapped[Optional["PaperProject"]] = relationship("PaperProject", back_populates="scholar_snapshots")
