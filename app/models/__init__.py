# Import all models here so Alembic can discover them.
from app.models.affiliation import Affiliation, AuthorAffiliation  # noqa: F401
from app.models.author import Author  # noqa: F401
from app.models.conference import Conference, ConferenceEdition, StarredConferenceEdition  # noqa: F401
from app.models.group import GroupMembership, ResearchGroup  # noqa: F401
from app.models.journal import Journal, JournalSpecialIssue  # noqa: F401
from app.models.paper import (  # noqa: F401
    PaperAuthor,
    PaperChangeLog,
    PaperComment,
    PaperConferenceSubmission,
    PaperGroupShare,
    PaperJournalSubmission,
    PaperProject,
    PaperResource,
    TodoItem,
)
from app.models.calendar import PersonalCalendarEvent  # noqa: F401
from app.models.scholar import ScholarAuthorSnapshot, ScholarPaperSnapshot  # noqa: F401
from app.models.user import User  # noqa: F401
