# Import all models here so Alembic can discover them.
from app.models.affiliation import Affiliation, AuthorAffiliation  # noqa: F401
from app.models.author import Author  # noqa: F401
from app.models.conference import Conference, ConferenceEdition, StarredConferenceEdition  # noqa: F401
from app.models.group import GroupMembership, GroupReviewAssignment, GroupReviewBalance, GroupReviewRequest, ResearchGroup  # noqa: F401
from app.models.journal import Journal, JournalSpecialIssue  # noqa: F401
from app.models.paper import (  # noqa: F401
    PaperAuthor,
    PaperChangeLog,
    PaperComment,
    PaperConferenceSubmission,
    PaperGroupShare,
    PaperJournalSubmission,
    PaperMilestone,
    PaperProject,
    PaperResource,
    TodoItem,
)
from app.models.calendar import PersonalCalendarEvent  # noqa: F401
from app.models.claim import AuthorClaimRequest  # noqa: F401
from app.models.scholar import ScholarAuthorSnapshot, ScholarPaperSnapshot  # noqa: F401
from app.models.service import ServiceRecord  # noqa: F401
from app.models.suggestion import Suggestion  # noqa: F401
from app.models.notebook import (  # noqa: F401
    NotebookEdge,
    NotebookEntry,
    NotebookEntryShare,
    NotebookEntryTag,
    NotebookTag,
)
from app.models.wiki import WikiPage, WikiPageRevision  # noqa: F401
from app.models.workflow import Workflow, WorkflowShare, WorkflowStep, WorkflowTrigger, PaperWorkflowSubscription  # noqa: F401
from app.models.personal_todo import PersonalTodo  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.bibtex import BibCollection, BibCollectionShare, BibCollectionWriteRevoke, BibEntry  # noqa: F401
from app.models.feature_flag import FeatureFlag, UserFeatureAccess  # noqa: F401
from app.models.supervision import (  # noqa: F401
    SupervisionProject,
    SupervisionDocument,
    SupervisionTodo,
    SupervisionTypeWorkflowConfig,
)
from app.models.error_log import ErrorLog  # noqa: F401
