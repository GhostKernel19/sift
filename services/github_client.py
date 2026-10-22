"""GitHub API Client Interface for Sift.

Assigned to: Agent 02 (Evidence & GitHub Engine)

Responsibilities:
- Parse GitHub PR URLs into (owner, repo, pull_number).
- Fetch pull request metadata (title, body, author, state, additions, etc.).
- Fetch raw unified diff text.
- Fetch comments/reviews if relevant for discussion context.
- Use optional GITHUB_TOKEN from environment for higher rate limits.
- Never commit or print GitHub tokens.
"""

from __future__ import annotations

from typing import Any, Optional


def parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    """Parses a GitHub pull request URL into owner, repo name, and pull number.

    Supported formats:
        - https://github.com/owner/repo/pull/123
        - https://github.com/owner/repo/pull/123/files
        - owner/repo#123

    Args:
        pr_url: GitHub pull request URL string or reference.

    Returns:
        tuple[str, str, int]: (owner, repo, pull_number)

    Raises:
        ValueError: If the URL format is invalid.
    """
    raise NotImplementedError("To be implemented by Agent 02")


def fetch_pr_details(
    owner: str,
    repo: str,
    pull_number: int,
    token: Optional[str] = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Fetches metadata for a pull request from GitHub REST API.

    API Endpoint:
        GET https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}

    Args:
        owner: GitHub repository owner / organization.
        repo: Repository name.
        pull_number: Pull request number.
        token: Optional GitHub Personal Access Token.
        timeout: Request timeout in seconds.

    Returns:
        dict: Standardized PR details containing:
            - "title": str
            - "body": str
            - "author": str (user.login)
            - "author_association": str (e.g. FIRST_TIME_CONTRIBUTOR, MEMBER, NONE)
            - "state": str (open, closed)
            - "draft": bool
            - "created_at": str
            - "updated_at": str
            - "additions": int
            - "deletions": int
            - "changed_files": int
            - "base_branch": str (base.ref)
            - "head_branch": str (head.ref)
            - "html_url": str

    Raises:
        requests.HTTPError: On non-200 responses (e.g. 404 Not Found, 403 Rate Limited).
        requests.ConnectionError: On network failures.
    """
    raise NotImplementedError("To be implemented by Agent 02")


def fetch_pr_diff(
    owner: str,
    repo: str,
    pull_number: int,
    token: Optional[str] = None,
    timeout: int = 45,
) -> str:
    """Fetches the raw unified diff for a pull request.

    API Endpoint:
        GET https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}
        Header: Accept: application/vnd.github.v3.diff

    Args:
        owner: GitHub repository owner.
        repo: Repository name.
        pull_number: Pull request number.
        token: Optional GitHub Personal Access Token.
        timeout: Request timeout in seconds.

    Returns:
        str: Raw unified diff text.

    Raises:
        requests.HTTPError: On non-200 responses.
        requests.ConnectionError: On network failures.
    """
    raise NotImplementedError("To be implemented by Agent 02")


def fetch_pr_comments(
    owner: str,
    repo: str,
    pull_number: int,
    token: Optional[str] = None,
    timeout: int = 30,
) -> list[dict[str, Any]]:
    """Fetches discussion comments and review comments for a pull request.

    API Endpoints:
        GET https://api.github.com/repos/{owner}/{repo}/issues/{pull_number}/comments
        GET https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}/comments

    Args:
        owner: GitHub repository owner.
        repo: Repository name.
        pull_number: Pull request number.
        token: Optional GitHub Personal Access Token.
        timeout: Request timeout in seconds.

    Returns:
        list[dict]: List of comments with author, body, created_at, and comment_id.

    Raises:
        requests.HTTPError: On non-200 responses.
    """
    raise NotImplementedError("To be implemented by Agent 02")
