from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Journal(Base):
    __tablename__ = "journals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    abbreviation: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    scimago_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    impact_factor: Mapped[Optional[float]] = mapped_column(Numeric(6, 3), nullable=True)
    rank: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # Q1/Q2/Q3/Q4
    website: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    special_issues: Mapped[list["JournalSpecialIssue"]] = relationship(
        "JournalSpecialIssue", back_populates="journal", cascade="all, delete-orphan"
    )
    paper_submissions: Mapped[list["PaperJournalSubmission"]] = relationship(
        "PaperJournalSubmission", back_populates="journal"
    )


class JournalSpecialIssue(Base):
    __tablename__ = "journal_special_issues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    journal_id: Mapped[int] = mapped_column(
        ForeignKey("journals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    submission_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    journal: Mapped["Journal"] = relationship("Journal", back_populates="special_issues")
    paper_submissions: Mapped[list["PaperJournalSubmission"]] = relationship(
        "PaperJournalSubmission", back_populates="special_issue"
    )
