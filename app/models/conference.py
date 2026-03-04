from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

CORE_RANKS = ("A*", "A", "B", "C", "National", "Unranked")


class Conference(Base):
    __tablename__ = "conferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    abbreviation: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    core_rank: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    wikicfp_series_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    editions: Mapped[list["ConferenceEdition"]] = relationship(
        "ConferenceEdition", back_populates="conference", cascade="all, delete-orphan", order_by="ConferenceEdition.year.desc()"
    )


class ConferenceEdition(Base):
    __tablename__ = "conference_editions"
    __table_args__ = (UniqueConstraint("conference_id", "year", name="uq_conference_edition"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    conference_id: Mapped[int] = mapped_column(
        ForeignKey("conferences.id", ondelete="CASCADE"), nullable=False, index=True
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    wikicfp_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    abstract_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    full_paper_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    rebuttal_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    rebuttal_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    notification_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    camera_ready_deadline: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    conference: Mapped["Conference"] = relationship("Conference", back_populates="editions")
    starred_by: Mapped[list["StarredConferenceEdition"]] = relationship(
        "StarredConferenceEdition", back_populates="edition", cascade="all, delete-orphan"
    )
    paper_submissions: Mapped[list["PaperConferenceSubmission"]] = relationship(
        "PaperConferenceSubmission", back_populates="edition"
    )

    @property
    def label(self) -> str:
        return f"{self.conference.abbreviation} {self.year}"

    @property
    def next_deadline(self) -> Optional[date]:
        """Return the nearest upcoming deadline date."""
        from datetime import date as date_type
        today = date_type.today()
        candidates = [
            d for d in [
                self.abstract_deadline,
                self.full_paper_deadline,
                self.rebuttal_start,
                self.rebuttal_end,
                self.notification_date,
                self.camera_ready_deadline,
            ]
            if d and d >= today
        ]
        return min(candidates) if candidates else None


class StarredConferenceEdition(Base):
    __tablename__ = "starred_conference_editions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    conference_edition_id: Mapped[int] = mapped_column(
        ForeignKey("conference_editions.id", ondelete="CASCADE"), primary_key=True
    )

    user: Mapped["User"] = relationship("User", back_populates="starred_editions")
    edition: Mapped["ConferenceEdition"] = relationship("ConferenceEdition", back_populates="starred_by")
