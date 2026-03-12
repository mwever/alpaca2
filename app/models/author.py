from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Author(Base):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    last_name: Mapped[str] = mapped_column(String(128), nullable=False)
    given_name: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    nationality: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    photo_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    google_scholar_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, unique=True)
    orcid: Mapped[Optional[str]] = mapped_column(String(19), nullable=True, unique=True)  # XXXX-XXXX-XXXX-XXXX
    dblp_pid: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, unique=True)  # e.g. l/LeCun:Yann
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    author_affiliations: Mapped[list["AuthorAffiliation"]] = relationship(
        "AuthorAffiliation", back_populates="author", cascade="all, delete-orphan"
    )
    paper_authors: Mapped[list["PaperAuthor"]] = relationship(
        "PaperAuthor", back_populates="author", cascade="all, delete-orphan"
    )
    user: Mapped[Optional["User"]] = relationship(
        "User", back_populates="author", foreign_keys="User.author_id", uselist=False
    )
    scholar_snapshots: Mapped[list["ScholarAuthorSnapshot"]] = relationship(
        "ScholarAuthorSnapshot", back_populates="author", cascade="all, delete-orphan"
    )
    claim_requests: Mapped[list["AuthorClaimRequest"]] = relationship(
        "AuthorClaimRequest", back_populates="author", passive_deletes=True
    )

    @property
    def full_name(self) -> str:
        return f"{self.given_name} {self.last_name}"

    @property
    def display_name(self) -> str:
        return f"{self.last_name}, {self.given_name}"
