from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Affiliation(Base):
    __tablename__ = "affiliations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sigle: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    color: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # hex, e.g. #003366
    website: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    author_affiliations: Mapped[list["AuthorAffiliation"]] = relationship(
        "AuthorAffiliation", back_populates="affiliation"
    )
    paper_authors: Mapped[list["PaperAuthor"]] = relationship("PaperAuthor", back_populates="affiliation")


class AuthorAffiliation(Base):
    """Tracks which affiliation an author had during a given period."""

    __tablename__ = "author_affiliations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id", ondelete="CASCADE"), nullable=False, index=True)
    affiliation_id: Mapped[int] = mapped_column(
        ForeignKey("affiliations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)  # None = current

    author: Mapped["Author"] = relationship("Author", back_populates="author_affiliations")
    affiliation: Mapped["Affiliation"] = relationship("Affiliation", back_populates="author_affiliations")
