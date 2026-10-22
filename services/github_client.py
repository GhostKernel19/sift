"""GitHub API Client Engine for Sift.

Assigned to: Agent 02 (Evidence & GitHub Engine)

Locked Invariants & Responsibilities:
- Input validation: accepts "owner/repo" or https://github.com/owner/repo only with strict regex.
- Calls ONLY https://api.github.com/... endpoints constructed from validated owner/repo.
- NEVER fetch arbitrary URLs found in PR content, diffs, or comments.
- Explicit timeouts on every request and bounded retries on transient network/5xx failures.
- Clear error handling for 404 (Not Found), 403 (Rate Limit), 401 (Auth), and network issues.
- Optional GITHUB_TOKEN used via Authorization header; NEVER logged, printed, or exposed in errors.
- Fetch up to N open PRs with key metadata.
- Fetch per-file patches with strict byte capping per file and per PR, marking truncations.
- Fetch contribution guidance from candidate paths; marks "unavailable" if absent.
- Never clone repositories or execute repository code.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Optional
from urllib.parse import urlsplit

import requests

# ---------------------------------------------------------------------------
# Strict Validation Regexes
# ---------------------------------------------------------------------------
# GitHub owner (user/org): 1-39 chars, alphanumeric and single hyphens, not starting/ending with hyphen.
OWNER_REGEX = re.compile(r"^[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}$")

# GitHub repository name: 1-100 chars, alphanumeric, hyphens, underscores, dots; not . or ..
REPO_REGEX = re.compile(r"^(?!\.{1,2}$)[a-zA-Z0-9_.-]{1,100}$")

GITHUB_API_BASE = "https://api.github.com"

# Candidate filenames for contribution guidance
CONTRIBUTING_CANDIDATE_PATHS = (
    "CONTRIBUTING.md",
    ".github/CONTRIBUTING.md",
    "docs/CONTRIBUTING.md",
)


# ---------------------------------------------------------------------------
# Custom Exceptions (Harmonized with requests hierarchy)
# ---------------------------------------------------------------------------
class GitHubError(requests.RequestException):
    """Base exception for all GitHub client errors."""
    pass


class GitHubValidationError(GitHubError, ValueError):
    """Raised when repository or pull request input validation fails."""
    pass


class GitHubNotFoundError(GitHubError, requests.HTTPError):
    """Raised when a GitHub repository, pull request, or file is not found (404)."""
    pass


class GitHubRateLimitError(GitHubError, requests.HTTPError):
    """Raised when the GitHub API rate limit is exceeded (403 or 429)."""
    pass


class GitHubAuthenticationError(GitHubError, requests.HTTPError):
    """Raised when authentication against the GitHub API fails (401)."""
    pass


class GitHubNetworkError(GitHubError, requests.ConnectionError):
    """Raised on connection timeout or network connectivity failures."""
    pass


# ---------------------------------------------------------------------------
# Input Validation & Parsing
# ---------------------------------------------------------------------------
def validate_owner_repo(owner: str, repo: str) -> tuple[str, str]:
    """Validates GitHub owner and repository names using strict regexes.

    Args:
        owner: GitHub owner/organization name.
        repo: Repository name.

    Returns:
        tuple[str, str]: Validated (owner, repo).

    Raises:
        GitHubValidationError: If owner or repo fails strict validation.
    """
    if not isinstance(owner, str) or not OWNER_REGEX.fullmatch(owner.strip()):
        raise GitHubValidationError(
            f"Invalid GitHub repository owner '{owner}'. Must be 1-39 alphanumeric characters or single hyphens."
        )

    if not isinstance(repo, str) or not REPO_REGEX.fullmatch(repo.strip()):
        raise GitHubValidationError(
            f"Invalid GitHub repository name '{repo}'. Must be 1-100 characters and contain only alphanumeric, hyphens, underscores, or dots."
        )

    return owner.strip(), repo.strip()


def validate_repo_input(repo_input: str) -> tuple[str, str]:
    """Validates and parses a repository input string.

    Accepts ONLY:
        - "owner/repo"
        - "https://github.com/owner/repo" (with optional trailing slash)

    Rejects non-https schemes, third-party hosts, query strings, fragments,
    subpaths, and malformed identifiers.

    Args:
        repo_input: Target repository input string.

    Returns:
        tuple[str, str]: Validated (owner, repo).

    Raises:
        GitHubValidationError: If the input does not strictly match accepted formats.
    """
    if not isinstance(repo_input, str):
        raise GitHubValidationError(f"Repository input must be a string, got {type(repo_input).__name__}")

    raw = repo_input.strip()
    if not raw:
        raise GitHubValidationError("Repository input cannot be empty.")

    if "://" in raw:
        parsed = urlsplit(raw)
        if parsed.scheme.lower() != "https":
            raise GitHubValidationError(
                f"Invalid URL scheme '{parsed.scheme}'. Only 'https://github.com/owner/repo' is accepted."
            )
        if parsed.netloc.lower() != "github.com":
            raise GitHubValidationError(
                f"Invalid host '{parsed.netloc}'. Only 'github.com' is accepted."
            )
        if parsed.query or parsed.fragment:
            raise GitHubValidationError(
                "Repository URL must not contain query parameters or hash fragments."
            )

        path_parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(path_parts) != 2:
            raise GitHubValidationError(
                f"Invalid repository path '{parsed.path}'. Expected exact 'https://github.com/owner/repo'."
            )
        owner, repo = path_parts[0], path_parts[1]
    else:
        # Shorthand "owner/repo" format
        if any(char in raw for char in ("?", "#", "@", ":", " ")):
            raise GitHubValidationError(f"Invalid characters in repository string: '{raw}'")
        parts = [p for p in raw.strip("/").split("/") if p]
        if len(parts) != 2:
            raise GitHubValidationError(
                f"Invalid repository format '{raw}'. Expected 'owner/repo' or 'https://github.com/owner/repo'."
            )
        owner, repo = parts[0], parts[1]

    return validate_owner_repo(owner, repo)


def parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    """Parses and validates a GitHub pull request URL or shorthand reference.

    Supported formats:
        - https://github.com/owner/repo/pull/123
        - https://github.com/owner/repo/pull/123/
        - https://github.com/owner/repo/pull/123/files
        - https://github.com/owner/repo/pull/123/commits
        - owner/repo#123

    Args:
        pr_url: GitHub pull request URL string or reference.

    Returns:
        tuple[str, str, int]: Validated (owner, repo, pull_number).

    Raises:
        GitHubValidationError: If the URL format or parameters are invalid.
    """
    if not isinstance(pr_url, str):
        raise GitHubValidationError(f"PR URL must be a string, got {type(pr_url).__name__}")

    raw = pr_url.strip()
    if not raw:
        raise GitHubValidationError("PR reference cannot be empty.")

    # 1. Shorthand "owner/repo#123" format
    if "#" in raw and "://" not in raw:
        repo_part, _, num_part = raw.partition("#")
        owner, repo = validate_repo_input(repo_part)
        try:
            pull_number = int(num_part.strip())
            if pull_number <= 0:
                raise ValueError
        except ValueError:
            raise GitHubValidationError(f"Invalid pull request number in '{raw}': '{num_part}'")
        return owner, repo, pull_number

    # 2. Full URL format
    if "://" in raw:
        parsed = urlsplit(raw)
        if parsed.scheme.lower() != "https":
            raise GitHubValidationError(
                f"Invalid URL scheme '{parsed.scheme}'. Only 'https://github.com/...' is accepted."
            )
        if parsed.netloc.lower() != "github.com":
            raise GitHubValidationError(
                f"Invalid host '{parsed.netloc}'. Only 'github.com' is accepted."
            )
        if parsed.query or parsed.fragment:
            raise GitHubValidationError("PR URL must not contain query parameters or fragments.")

        path_parts = [p for p in parsed.path.strip("/").split("/") if p]
        if len(path_parts) < 4 or path_parts[2] != "pull":
            raise GitHubValidationError(
                f"Invalid PR URL structure '{parsed.path}'. Expected 'https://github.com/owner/repo/pull/<number>'."
            )

        owner, repo = path_parts[0], path_parts[1]
        validate_owner_repo(owner, repo)

        try:
            pull_number = int(path_parts[3])
            if pull_number <= 0:
                raise ValueError
        except ValueError:
            raise GitHubValidationError(f"Invalid pull request number '{path_parts[3]}' in URL.")

        if len(path_parts) > 4:
            if len(path_parts) == 5 and path_parts[4] in ("files", "commits"):
                pass
            else:
                raise GitHubValidationError(f"Unexpected path suffix in PR URL: '{parsed.path}'")

        return owner, repo, pull_number

    raise GitHubValidationError(
        f"Unrecognized pull request reference '{raw}'. Expected 'owner/repo#123' or 'https://github.com/owner/repo/pull/123'."
    )


# ---------------------------------------------------------------------------
# Internal REST Request Helper (Strict Boundaries, Timeouts & Bounded Retries)
# ---------------------------------------------------------------------------
def _get_auth_headers(token: Optional[str] = None, accept: Optional[str] = None) -> dict[str, str]:
    """Generates standard GitHub REST API headers with optional token authentication.

    Note: The token is NEVER printed or logged.
    """
    headers = {
        "User-Agent": "Sift-PR-Triage-Assistant",
        "X-GitHub-Api-Version": "2022-11-28",
        "Accept": accept or "application/vnd.github+json",
    }
    resolved_token = token or os.getenv("GITHUB_TOKEN")
    if resolved_token and resolved_token.strip():
        headers["Authorization"] = f"Bearer {resolved_token.strip()}"
    return headers


def _github_api_request(
    endpoint: str,
    headers: Optional[dict[str, str]] = None,
    params: Optional[dict[str, Any]] = None,
    timeout: int = 30,
    max_retries: int = 2,
    retry_delay: float = 0.5,
) -> requests.Response:
    """Executes a GET request against the official GitHub REST API with strict safety bounds.

    Locked Invariants:
        - Only requests targeting 'https://api.github.com/...' are permitted.
        - Arbitrary or user-supplied URLs are never fetched.
        - Timeouts are mandatory on every request.
        - Bounded retries for connection drops and 5xx server responses.
        - Never retries on 404, 401, or exhausted 403 rate limits.
    """
    if not endpoint.startswith(f"{GITHUB_API_BASE}/"):
        raise GitHubValidationError(
            f"Security violation: attempt to fetch non-GitHub API endpoint: '{endpoint}'. Only {GITHUB_API_BASE}/ is allowed."
        )

    headers = headers or _get_auth_headers()

    for attempt in range(max_retries + 1):
        try:
            response = requests.get(endpoint, headers=headers, params=params, timeout=timeout)

            # Success
            if response.status_code == 200:
                return response

            # Resource not found
            if response.status_code == 404:
                raise GitHubNotFoundError(
                    f"GitHub resource not found (HTTP 404) at endpoint: {endpoint}"
                )

            # Rate Limit Exceeded
            if response.status_code in (403, 429):
                remaining = response.headers.get("x-ratelimit-remaining", "")
                reset_time = response.headers.get("x-ratelimit-reset", "")
                is_rate_limit = (
                    remaining == "0"
                    or "rate limit" in response.text.lower()
                    or response.status_code == 429
                )
                if is_rate_limit:
                    msg = "GitHub API rate limit exceeded."
                    if reset_time:
                        msg += f" Resets at unix epoch {reset_time}."
                    msg += " Configure GITHUB_TOKEN environment variable for 5,000 req/hr."
                    raise GitHubRateLimitError(msg)

                # Other 403 Forbidden
                raise GitHubError(f"GitHub API access forbidden (HTTP 403): {response.text}")

            # Authentication failure
            if response.status_code == 401:
                raise GitHubAuthenticationError(
                    "GitHub API authentication failed (HTTP 401). Please verify your GITHUB_TOKEN."
                )

            # Transient Server Errors (500, 502, 503, 504) -> retry if attempts remain
            if response.status_code in (500, 502, 503, 504) and attempt < max_retries:
                time.sleep(retry_delay * (2 ** attempt))
                continue

            response.raise_for_status()
            return response

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            if attempt < max_retries:
                time.sleep(retry_delay * (2 ** attempt))
                continue
            raise GitHubNetworkError(
                f"Failed to connect to GitHub API after {max_retries + 1} attempts: {exc}"
            ) from exc

    raise GitHubError(f"Unexpected failure while requesting {endpoint}")


# ---------------------------------------------------------------------------
# Public API Client Functions
# ---------------------------------------------------------------------------
def fetch_pr_details(
    owner: str,
    repo: str,
    pull_number: int,
    token: Optional[str] = None,
    timeout: int = 30,
) -> dict[str, Any]:
    """Fetches standardized metadata for a single pull request.

    API Endpoint:
        GET https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}

    Args:
        owner: GitHub repository owner.
        repo: Repository name.
        pull_number: Pull request number.
        token: Optional GitHub Personal Access Token.
        timeout: Request timeout in seconds.

    Returns:
        dict: Standardized PR metadata dictionary.
    """
    owner, repo = validate_owner_repo(owner, repo)
    if not isinstance(pull_number, int) or pull_number <= 0:
        raise GitHubValidationError(f"Invalid pull number '{pull_number}'. Must be a positive integer.")

    endpoint = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pull_number}"
    headers = _get_auth_headers(token=token)
    response = _github_api_request(endpoint, headers=headers, timeout=timeout)
    data = response.json()

    user_info = data.get("user") or {}
    base_info = data.get("base") or {}
    head_info = data.get("head") or {}

    labels: list[str] = []
    for lbl in data.get("labels", []):
        if isinstance(lbl, dict):
            name = lbl.get("name")
            if name:
                labels.append(str(name))
        elif isinstance(lbl, str):
            labels.append(lbl)

    return {
        "owner": owner,
        "repo": repo,
        "number": pull_number,
        "title": str(data.get("title") or ""),
        "body": str(data.get("body") or ""),
        "author": str(user_info.get("login") or ""),
        "author_association": str(data.get("author_association") or "NONE"),
        "state": str(data.get("state") or "open"),
        "draft": bool(data.get("draft", False)),
        "created_at": str(data.get("created_at") or ""),
        "updated_at": str(data.get("updated_at") or ""),
        "additions": int(data.get("additions", 0)),
        "deletions": int(data.get("deletions", 0)),
        "changed_files": int(data.get("changed_files", 0)),
        "base_branch": str(base_info.get("ref") or ""),
        "head_branch": str(head_info.get("ref") or ""),
        "html_url": str(data.get("html_url") or f"https://github.com/{owner}/{repo}/pull/{pull_number}"),
        "labels": labels,
    }


def fetch_open_prs(
    owner: str,
    repo: Optional[str] = None,
    n: int = 10,
    token: Optional[str] = None,
    timeout: int = 30,
    fetch_details: bool = True,
) -> list[dict[str, Any]]:
    """Fetches up to N open pull requests for a repository.

    API Endpoint:
        GET https://api.github.com/repos/{owner}/{repo}/pulls?state=open&per_page=N&sort=updated&direction=desc

    Args:
        owner: Repository owner, or full "owner/repo" or "https://github.com/owner/repo".
        repo: Repository name (optional if owner is a combined repo specifier).
        n: Number of open pull requests to retrieve (default: 10, max: 100).
        token: Optional GitHub Personal Access Token.
        timeout: Request timeout in seconds.
        fetch_details: If True, fetches individual PR details to accurately
                       populate additions, deletions, and changed_files.

    Returns:
        list[dict]: List of open PR summaries.
    """
    if repo is None or "/" in owner:
        owner, repo = validate_repo_input(owner)
    else:
        owner, repo = validate_owner_repo(owner, repo)

    limit = max(1, min(int(n), 100))
    endpoint = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls"
    params = {
        "state": "open",
        "per_page": limit,
        "sort": "updated",
        "direction": "desc",
    }
    headers = _get_auth_headers(token=token)
    response = _github_api_request(endpoint, headers=headers, params=params, timeout=timeout)
    items = response.json()

    if not isinstance(items, list):
        return []

    results: list[dict[str, Any]] = []
    for item in items[:limit]:
        number = int(item["number"])
        title = str(item.get("title") or "")
        body = str(item.get("body") or "")
        user_info = item.get("user") or {}
        author = str(user_info.get("login") or "")

        labels: list[str] = []
        for lbl in item.get("labels", []):
            if isinstance(lbl, dict):
                name = lbl.get("name")
                if name:
                    labels.append(str(name))
            elif isinstance(lbl, str):
                labels.append(lbl)

        updated_at = str(item.get("updated_at") or "")
        html_url = str(item.get("html_url") or f"https://github.com/{owner}/{repo}/pull/{number}")

        # Check if item already has diff stats (e.g. from mock or extended API)
        has_stats = "additions" in item and "deletions" in item and "changed_files" in item
        if has_stats:
            additions = int(item.get("additions", 0))
            deletions = int(item.get("deletions", 0))
            changed_files = int(item.get("changed_files", 0))
        elif fetch_details:
            try:
                details = fetch_pr_details(owner, repo, number, token=token, timeout=timeout)
                additions = details["additions"]
                deletions = details["deletions"]
                changed_files = details["changed_files"]
            except Exception:
                # Graceful fallback if individual detail fetch encounters rate limit or error
                additions = 0
                deletions = 0
                changed_files = 0
        else:
            additions = int(item.get("additions", 0))
            deletions = int(item.get("deletions", 0))
            changed_files = int(item.get("changed_files", 0))

        results.append({
            "number": number,
            "title": title,
            "body": body,
            "author": author,
            "labels": labels,
            "updated_at": updated_at,
            "html_url": html_url,
            "additions": additions,
            "deletions": deletions,
            "changed_files": changed_files,
        })

    return results


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
        str: Raw authentic unified diff text.
    """
    owner, repo = validate_owner_repo(owner, repo)
    if not isinstance(pull_number, int) or pull_number <= 0:
        raise GitHubValidationError(f"Invalid pull number '{pull_number}'. Must be a positive integer.")

    endpoint = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pull_number}"
    headers = _get_auth_headers(token=token, accept="application/vnd.github.v3.diff")
    response = _github_api_request(endpoint, headers=headers, timeout=timeout)
    return response.text


def fetch_pr_files(
    owner: str,
    repo: str,
    pull_number: int,
    token: Optional[str] = None,
    timeout: int = 30,
    max_bytes_per_file: int = 50 * 1024,
    max_total_bytes: int = 250 * 1024,
) -> list[dict[str, Any]]:
    """Fetches changed files with per-file patches and strict byte capping.

    API Endpoint:
        GET https://api.github.com/repos/{owner}/{repo}/pulls/{pull_number}/files

    Args:
        owner: Repository owner.
        repo: Repository name.
        pull_number: Pull request number.
        token: Optional GitHub Personal Access Token.
        timeout: Request timeout in seconds.
        max_bytes_per_file: Maximum bytes allowed per single file patch (default: 50 KB).
        max_total_bytes: Maximum total bytes across all patches for the PR (default: 250 KB).

    Returns:
        list[dict]: Standardized file records with patch truncation indicators:
            - "filename": str
            - "status": str
            - "additions": int
            - "deletions": int
            - "changes": int
            - "patch": Optional[str] (exact patch or truncated portion)
            - "raw_patch_bytes": int
            - "truncated": bool
            - "patch_status": "complete" | "truncated_file_limit" | "truncated_total_limit" | "missing"
            - "blob_url": str
    """
    owner, repo = validate_owner_repo(owner, repo)
    if not isinstance(pull_number, int) or pull_number <= 0:
        raise GitHubValidationError(f"Invalid pull number '{pull_number}'. Must be a positive integer.")

    endpoint = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pull_number}/files"
    headers = _get_auth_headers(token=token)
    response = _github_api_request(endpoint, headers=headers, timeout=timeout)
    files_data = response.json()

    if not isinstance(files_data, list):
        return []

    results: list[dict[str, Any]] = []
    total_bytes_used = 0

    for item in files_data:
        filename = str(item.get("filename") or "")
        status = str(item.get("status") or "modified")
        additions = int(item.get("additions", 0))
        deletions = int(item.get("deletions", 0))
        changes = int(item.get("changes", 0))
        blob_url = str(item.get("blob_url") or "")
        raw_patch = item.get("patch")

        if raw_patch is None:
            # Binary file, large diff omitted by GitHub, or pure metadata rename
            results.append({
                "filename": filename,
                "status": status,
                "additions": additions,
                "deletions": deletions,
                "changes": changes,
                "patch": None,
                "raw_patch_bytes": 0,
                "truncated": False,
                "patch_status": "missing",
                "blob_url": blob_url,
            })
            continue

        patch_bytes = len(raw_patch.encode("utf-8"))

        if total_bytes_used >= max_total_bytes:
            # Entire PR budget already consumed by earlier files
            results.append({
                "filename": filename,
                "status": status,
                "additions": additions,
                "deletions": deletions,
                "changes": changes,
                "patch": "",
                "raw_patch_bytes": patch_bytes,
                "truncated": True,
                "patch_status": "truncated_total_limit",
                "blob_url": blob_url,
            })
            continue

        remaining_total_budget = max_total_bytes - total_bytes_used
        allowed_bytes = min(max_bytes_per_file, remaining_total_budget)

        if patch_bytes > allowed_bytes:
            # File patch exceeds per-file or remaining PR budget
            truncated_encoded = raw_patch.encode("utf-8")[:allowed_bytes]
            truncated_text = truncated_encoded.decode("utf-8", errors="ignore")
            actual_bytes = len(truncated_encoded)
            total_bytes_used += actual_bytes

            status_flag = (
                "truncated_total_limit"
                if allowed_bytes < max_bytes_per_file
                else "truncated_file_limit"
            )

            results.append({
                "filename": filename,
                "status": status,
                "additions": additions,
                "deletions": deletions,
                "changes": changes,
                "patch": truncated_text,
                "raw_patch_bytes": patch_bytes,
                "truncated": True,
                "patch_status": status_flag,
                "blob_url": blob_url,
            })
        else:
            # Fits within both file and total limits
            total_bytes_used += patch_bytes
            results.append({
                "filename": filename,
                "status": status,
                "additions": additions,
                "deletions": deletions,
                "changes": changes,
                "patch": raw_patch,
                "raw_patch_bytes": patch_bytes,
                "truncated": False,
                "patch_status": "complete",
                "blob_url": blob_url,
            })

    return results


def fetch_contributing_guidance(
    owner: str,
    repo: str,
    token: Optional[str] = None,
    timeout: int = 15,
) -> dict[str, Any]:
    """Fetches repository contribution guidance from candidate paths.

    Candidate paths checked in sequence:
        1. CONTRIBUTING.md
        2. .github/CONTRIBUTING.md
        3. docs/CONTRIBUTING.md

    API Endpoint:
        GET https://api.github.com/repos/{owner}/{repo}/contents/{path}
        Header: Accept: application/vnd.github.raw+json

    Args:
        owner: GitHub repository owner.
        repo: Repository name.
        token: Optional GitHub Personal Access Token.
        timeout: Request timeout in seconds.

    Returns:
        dict: {
            "status": "present" | "unavailable",
            "path": Optional[str],
            "text": str (exact authentic guidance content, or empty)
        }
    """
    owner, repo = validate_owner_repo(owner, repo)
    headers = _get_auth_headers(token=token, accept="application/vnd.github.raw+json")

    for path in CONTRIBUTING_CANDIDATE_PATHS:
        endpoint = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}"
        try:
            response = requests.get(endpoint, headers=headers, timeout=timeout)
            if response.status_code == 200:
                return {
                    "status": "present",
                    "path": path,
                    "text": response.text,
                }
            if response.status_code == 404:
                continue

            if response.status_code in (403, 429):
                remaining = response.headers.get("x-ratelimit-remaining", "")
                if remaining == "0" or "rate limit" in response.text.lower():
                    raise GitHubRateLimitError("GitHub API rate limit exceeded while checking CONTRIBUTING guidance.")

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            # Gracefully continue to check next path on single failure or mark unavailable
            continue

    return {
        "status": "unavailable",
        "path": None,
        "text": "",
    }


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
        owner: Repository owner.
        repo: Repository name.
        pull_number: Pull request number.
        token: Optional GitHub Personal Access Token.
        timeout: Request timeout in seconds.

    Returns:
        list[dict]: Unified chronological list of PR comments.
    """
    owner, repo = validate_owner_repo(owner, repo)
    if not isinstance(pull_number, int) or pull_number <= 0:
        raise GitHubValidationError(f"Invalid pull number '{pull_number}'. Must be a positive integer.")

    headers = _get_auth_headers(token=token)
    all_comments: list[dict[str, Any]] = []

    # 1. Issue conversation comments
    endpoint_issue = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues/{pull_number}/comments"
    try:
        resp_issue = _github_api_request(endpoint_issue, headers=headers, timeout=timeout)
        for c in resp_issue.json():
            user = c.get("user") or {}
            all_comments.append({
                "id": str(c.get("id", "")),
                "author": str(user.get("login", "")),
                "body": str(c.get("body", "")),
                "created_at": str(c.get("created_at", "")),
                "html_url": str(c.get("html_url", "")),
            })
    except GitHubNotFoundError:
        pass

    # 2. Pull request review comments
    endpoint_pr = f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls/{pull_number}/comments"
    try:
        resp_pr = _github_api_request(endpoint_pr, headers=headers, timeout=timeout)
        for c in resp_pr.json():
            user = c.get("user") or {}
            all_comments.append({
                "id": str(c.get("id", "")),
                "author": str(user.get("login", "")),
                "body": str(c.get("body", "")),
                "created_at": str(c.get("created_at", "")),
                "html_url": str(c.get("html_url", "")),
            })
    except GitHubNotFoundError:
        pass

    # Sort comments by creation date
    all_comments.sort(key=lambda x: x.get("created_at", ""))
    return all_comments
