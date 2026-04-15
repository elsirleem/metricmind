from abc import ABC, abstractmethod


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
