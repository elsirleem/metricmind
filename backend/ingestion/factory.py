import os

from backend.ingestion.base import GitAdapter
from backend.ingestion.gitlab_connector import GitLabAdapter
from backend.ingestion.github_connector import GitHubAdapter


def get_git_adapter(platform: str, base_url: str) -> GitAdapter:
    """
    Return the correct GitAdapter for the given platform.

    Token is read from the environment:
      GitLab → GITLAB_TOKEN
      GitHub → GITHUB_TOKEN

    To add a new platform: subclass GitAdapter, then add a case here.
    """
    token = os.getenv(f"{platform.upper()}_TOKEN", "")

    match platform:
        case "github":
            return GitHubAdapter(base_url=base_url, token=token)
        case "gitlab":
            return GitLabAdapter(base_url=base_url, token=token)
        case _:
            raise ValueError(
                f"Unsupported git platform: '{platform}'. "
                "Supported values: 'gitlab', 'github'."
            )
