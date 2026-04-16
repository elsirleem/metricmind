import re
from abc import ABC, abstractmethod

# Matches ticket prefixes used by Apache, Jira-hosted projects, and similar:
# [COLLECTIONS-123], [LANG-4567], [LOG4J2-999], PROJ-123:, (#123), etc.
# Strips them so the LLM receives the descriptive text rather than opaque IDs.
_TICKET_PREFIX = re.compile(
    r"^\s*(\[[A-Z][A-Z0-9_]+-\d+\]\s*"   # [PROJECT-123]
    r"|[A-Z][A-Z0-9_]+-\d+:\s*"           # PROJECT-123:
    r"|\(#\d+\)\s*"                        # (#123)
    r"|#\d+\s*)+",                         # #123
    re.IGNORECASE,
)


def clean_commit_message(message: str) -> str:
    """
    Strip ticket/issue prefixes from a commit message first line.

    Examples:
      "[COLLECTIONS-123] Fix NPE"  →  "Fix NPE"
      "LANG-456: Update javadoc"   →  "Update javadoc"
      "(#789) Add feature"         →  "Add feature"
      "Normal commit message"      →  "Normal commit message"  (unchanged)
    """
    first_line = (message or "").split("\n")[0].strip()
    cleaned = _TICKET_PREFIX.sub("", first_line).strip()
    # Fall back to the original first line if stripping left nothing
    return cleaned if cleaned else first_line


class GitAdapter(ABC):
    """
    Abstract interface for Git hosting platforms.

    Concrete implementations: GitLabAdapter (gitlab_connector.py),
    GitHubAdapter (github_connector.py).

    To add a new platform (Bitbucket, Azure DevOps, etc.):
      1. Subclass GitAdapter
      2. Implement fetch_all() and explore()
      3. Add a case in backend/ingestion/factory.py
    """

    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    @abstractmethod
    async def fetch_all(self, profile_id: str, project_id: str, since: str) -> list[dict]:
        """
        Fetch pipelines/runs, MRs/PRs and commits for one project since an ISO 8601 timestamp.

        Returns a list of normalised RawEvent dicts ready for DB insertion:
          { profile_id, source, entity_type, entity_id, project_id,
            timestamp, attributes (JSON str), ingested_at }
        """
        ...

    @abstractmethod
    async def explore(self, project_id: str) -> dict:
        """
        Fetch recent activity for LLM-based project exploration (Call 0).

        Returns:
          { commit_messages: list[str], mr_summaries: list[str] }
        """
        ...
