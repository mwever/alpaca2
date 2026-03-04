from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class PaperEventType(str, PyEnum):
    status_change = "status_change"
    submitted_conference = "submitted_conference"
    submitted_journal = "submitted_journal"
    resource_added = "resource_added"
    resource_removed = "resource_removed"
    note = "note"


class PaperResourceType(str, PyEnum):
    link = "link"
    file = "file"
    overleaf = "overleaf"
    github = "github"


class PaperStatus(str, PyEnum):
    planned = "planned"
    wip = "wip"
    submitted = "submitted"
    under_review = "under_review"
    major_revision = "major_revision"
    minor_revision = "minor_revision"
    accepted = "accepted"
    published = "published"
    rejected = "rejected"


PAPER_STATUS_LABELS = {
    PaperStatus.planned: "Planned",
    PaperStatus.wip: "Work in Progress",
    PaperStatus.submitted: "Submitted",
    PaperStatus.under_review: "Under Review",
    PaperStatus.major_revision: "Major Revision",
    PaperStatus.minor_revision: "Minor Revision",
    PaperStatus.accepted: "Accepted",
    PaperStatus.published: "Published",
    PaperStatus.rejected: "Rejected",
}

PAPER_STATUS_COLORS = {
    PaperStatus.planned: "secondary",
    PaperStatus.wip: "info",
    PaperStatus.submitted: "primary",
    PaperStatus.under_review: "warning",
    PaperStatus.major_revision: "danger",
    PaperStatus.minor_revision: "warning",
    PaperStatus.accepted: "success",
    PaperStatus.published: "success",
    PaperStatus.rejected: "dark",
}


class SubmissionStatus(str, PyEnum):
    submitted = "submitted"
    under_review = "under_review"
    accepted = "accepted"
    rejected = "rejected"
    withdrawn = "withdrawn"


class TodoStatus(str, PyEnum):
    open = "open"
    in_progress = "in_progress"
    done = "done"


class PaperProject(Base):
    __tablename__ = "paper_projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[PaperStatus] = mapped_column(Enum(PaperStatus), default=PaperStatus.planned, nullable=False)
    overleaf_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    github_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    google_scholar_paper_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    creator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by])
    paper_authors: Mapped[list["PaperAuthor"]] = relationship(
        "PaperAuthor", back_populates="paper", cascade="all, delete-orphan", order_by="PaperAuthor.position"
    )
    conference_submissions: Mapped[list["PaperConferenceSubmission"]] = relationship(
        "PaperConferenceSubmission", back_populates="paper", cascade="all, delete-orphan"
    )
    journal_submissions: Mapped[list["PaperJournalSubmission"]] = relationship(
        "PaperJournalSubmission", back_populates="paper", cascade="all, delete-orphan"
    )
    group_shares: Mapped[list["PaperGroupShare"]] = relationship(
        "PaperGroupShare", back_populates="paper", cascade="all, delete-orphan"
    )
    comments: Mapped[list["PaperComment"]] = relationship(
        "PaperComment", back_populates="paper", cascade="all, delete-orphan", order_by="PaperComment.created_at"
    )
    todos: Mapped[list["TodoItem"]] = relationship(
        "TodoItem", back_populates="paper", cascade="all, delete-orphan"
    )
    scholar_snapshots: Mapped[list["ScholarPaperSnapshot"]] = relationship(
        "ScholarPaperSnapshot", back_populates="paper"
    )
    resources: Mapped[list["PaperResource"]] = relationship(
        "PaperResource", back_populates="paper", cascade="all, delete-orphan",
        order_by="PaperResource.created_at",
    )
    change_log: Mapped[list["PaperChangeLog"]] = relationship(
        "PaperChangeLog", back_populates="paper", cascade="all, delete-orphan",
        order_by="PaperChangeLog.created_at",
    )


class PaperAuthor(Base):
    __tablename__ = "paper_authors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("paper_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id", ondelete="CASCADE"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Snapshot of affiliation at time of paper
    affiliation_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("affiliations.id", ondelete="SET NULL"), nullable=True
    )

    paper: Mapped["PaperProject"] = relationship("PaperProject", back_populates="paper_authors")
    author: Mapped["Author"] = relationship("Author", back_populates="paper_authors")
    affiliation: Mapped[Optional["Affiliation"]] = relationship("Affiliation", back_populates="paper_authors")


class PaperConferenceSubmission(Base):
    __tablename__ = "paper_conference_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("paper_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    conference_edition_id: Mapped[int] = mapped_column(
        ForeignKey("conference_editions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus), default=SubmissionStatus.submitted, nullable=False
    )

    paper: Mapped["PaperProject"] = relationship("PaperProject", back_populates="conference_submissions")
    edition: Mapped["ConferenceEdition"] = relationship("ConferenceEdition", back_populates="paper_submissions")


class PaperJournalSubmission(Base):
    __tablename__ = "paper_journal_submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("paper_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    journal_id: Mapped[int] = mapped_column(ForeignKey("journals.id", ondelete="CASCADE"), nullable=False, index=True)
    special_issue_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("journal_special_issues.id", ondelete="SET NULL"), nullable=True
    )
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[SubmissionStatus] = mapped_column(
        Enum(SubmissionStatus), default=SubmissionStatus.submitted, nullable=False
    )

    paper: Mapped["PaperProject"] = relationship("PaperProject", back_populates="journal_submissions")
    journal: Mapped["Journal"] = relationship("Journal", back_populates="paper_submissions")
    special_issue: Mapped[Optional["JournalSpecialIssue"]] = relationship(
        "JournalSpecialIssue", back_populates="paper_submissions"
    )


class PaperGroupShare(Base):
    __tablename__ = "paper_group_shares"

    paper_id: Mapped[int] = mapped_column(ForeignKey("paper_projects.id", ondelete="CASCADE"), primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("research_groups.id", ondelete="CASCADE"), primary_key=True)

    paper: Mapped["PaperProject"] = relationship("PaperProject", back_populates="group_shares")
    group: Mapped["ResearchGroup"] = relationship("ResearchGroup", back_populates="paper_shares")


class PaperComment(Base):
    __tablename__ = "paper_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("paper_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    paper: Mapped["PaperProject"] = relationship("PaperProject", back_populates="comments")
    user: Mapped["User"] = relationship("User", back_populates="comments")


class TodoItem(Base):
    __tablename__ = "todo_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("paper_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[TodoStatus] = mapped_column(Enum(TodoStatus), default=TodoStatus.open, nullable=False)
    assigned_to: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    paper: Mapped["PaperProject"] = relationship("PaperProject", back_populates="todos")
    assigned_user: Mapped[Optional["User"]] = relationship("User", back_populates="todos_assigned")


class PaperResource(Base):
    __tablename__ = "paper_resources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("paper_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    resource_type: Mapped[PaperResourceType] = mapped_column(
        Enum(PaperResourceType), default=PaperResourceType.link, nullable=False
    )
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    paper: Mapped["PaperProject"] = relationship("PaperProject", back_populates="resources")
    creator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by])


class PaperChangeLog(Base):
    __tablename__ = "paper_change_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("paper_projects.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[PaperEventType] = mapped_column(Enum(PaperEventType), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    old_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    new_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    conference_edition_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("conference_editions.id", ondelete="SET NULL"), nullable=True
    )
    journal_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("journals.id", ondelete="SET NULL"), nullable=True
    )
    special_issue_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("journal_special_issues.id", ondelete="SET NULL"), nullable=True
    )
    resource_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("paper_resources.id", ondelete="SET NULL"), nullable=True
    )
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    paper: Mapped["PaperProject"] = relationship("PaperProject", back_populates="change_log")
    creator: Mapped[Optional["User"]] = relationship("User", foreign_keys=[created_by])
    edition: Mapped[Optional["ConferenceEdition"]] = relationship("ConferenceEdition")
    journal: Mapped[Optional["Journal"]] = relationship("Journal")
    special_issue: Mapped[Optional["JournalSpecialIssue"]] = relationship("JournalSpecialIssue")
    resource: Mapped[Optional["PaperResource"]] = relationship("PaperResource", foreign_keys=[resource_id])
