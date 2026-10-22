"""Unit tests for GitHub API Client and Evidence Packet Builder.

Assigned to: Agent 02 (Evidence & GitHub Engine)

Covers:
- URL and shorthand reference validation
- Malformed hosts and schemes
- 404 Not Found handling
- 403 Rate Limit handling & token protection
- Empty PR list handling
- Missing vs present CONTRIBUTING guidance
- Truncated patch handling (per-file and total PR limits)
- Timeout handling & bounded retries
- Provable linked-issue detection
- Evidence packet creation with exact source texts
- Quote verification against evidence packet
- Zero contributor-quality bias invariant
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest
import requests

from services.github_client import (
    GitHubAuthenticationError,
    GitHubError,
    GitHubNetworkError,
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubValidationError,
    fetch_contributing_guidance,
    fetch_open_prs,
    fetch_pr_comments,
    fetch_pr_details,
    fetch_pr_diff,
    fetch_pr_files,
    parse_pr_url,
    validate_owner_repo,
    validate_repo_input,
)
from services.evidence_builder import (
    build_evidence_packet,
    detect_linked_issue_signal,
    verify_quote_against_packet,
)


# ===========================================================================
# 1. URL and Repository Target Validation
# ===========================================================================
class TestValidation:
    def test_valid_owner_repo_shorthand(self):
        owner, repo = validate_repo_input("pallets/flask")
        assert owner == "pallets"
        assert repo == "flask"

    def test_valid_https_url(self):
        owner, repo = validate_repo_input("https://github.com/psf/requests")
        assert owner == "psf"
        assert repo == "requests"

    def test_valid_https_url_trailing_slash(self):
        owner, repo = validate_repo_input("https://github.com/django/django/")
        assert owner == "django"
        assert repo == "django"

    def test_valid_repo_with_dots_and_hyphens(self):
        owner, repo = validate_repo_input("org-name/repo.js-v2")
        assert owner == "org-name"
        assert repo == "repo.js-v2"

    def test_reject_http_scheme(self):
        with pytest.raises(GitHubValidationError, match="Invalid URL scheme 'http'"):
            validate_repo_input("http://github.com/pallets/flask")

    def test_reject_non_github_host(self):
        with pytest.raises(GitHubValidationError, match="Invalid host 'gitlab.com'"):
            validate_repo_input("https://gitlab.com/pallets/flask")

    def test_reject_malformed_host(self):
        with pytest.raises(GitHubValidationError, match="Invalid host"):
            validate_repo_input("https://notgithub.com/pallets/flask")

    def test_reject_query_parameters(self):
        with pytest.raises(GitHubValidationError, match="query parameters"):
            validate_repo_input("https://github.com/pallets/flask?tab=pulls")

    def test_reject_hash_fragment(self):
        with pytest.raises(GitHubValidationError, match="hash fragments"):
            validate_repo_input("https://github.com/pallets/flask#readme")

    def test_reject_subpaths_in_repo_input(self):
        with pytest.raises(GitHubValidationError, match="Invalid repository path"):
            validate_repo_input("https://github.com/pallets/flask/issues")

    def test_reject_path_traversal(self):
        with pytest.raises(GitHubValidationError):
            validate_repo_input("pallets/../flask")

    def test_reject_invalid_owner_characters(self):
        with pytest.raises(GitHubValidationError, match="Invalid GitHub repository owner"):
            validate_repo_input("-invalidowner/flask")

    def test_reject_empty_input(self):
        with pytest.raises(GitHubValidationError, match="cannot be empty"):
            validate_repo_input("")

    def test_valid_pr_urls(self):
        assert parse_pr_url("https://github.com/pallets/flask/pull/42") == ("pallets", "flask", 42)
        assert parse_pr_url("https://github.com/pallets/flask/pull/42/") == ("pallets", "flask", 42)
        assert parse_pr_url("https://github.com/pallets/flask/pull/42/files") == ("pallets", "flask", 42)
        assert parse_pr_url("https://github.com/pallets/flask/pull/42/commits") == ("pallets", "flask", 42)
        assert parse_pr_url("pallets/flask#42") == ("pallets", "flask", 42)

    def test_reject_invalid_pr_url_host(self):
        with pytest.raises(GitHubValidationError, match="Invalid host"):
            parse_pr_url("https://gitlab.com/pallets/flask/pull/42")

    def test_reject_non_numeric_pr_number(self):
        with pytest.raises(GitHubValidationError):
            parse_pr_url("pallets/flask#notanumber")

    def test_reject_negative_pr_number(self):
        with pytest.raises(GitHubValidationError):
            parse_pr_url("pallets/flask#-1")


# ===========================================================================
# 2. 404 (Not Found) Handling
# ===========================================================================
class TestNotFound:
    @patch("requests.get")
    def test_fetch_pr_details_404(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        with pytest.raises(GitHubNotFoundError, match="HTTP 404"):
            fetch_pr_details("pallets", "flask", 999999)

    @patch("requests.get")
    def test_fetch_pr_diff_404(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        with pytest.raises(GitHubNotFoundError):
            fetch_pr_diff("pallets", "flask", 999999)


# ===========================================================================
# 3. Rate Limit Handling (403 / 429) & Token Protection
# ===========================================================================
class TestRateLimit:
    @patch("requests.get")
    def test_rate_limit_exceeded_with_header(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.headers = {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1700000000"}
        mock_resp.text = '{"message": "API rate limit exceeded"}'
        mock_get.return_value = mock_resp

        with pytest.raises(GitHubRateLimitError, match="GitHub API rate limit exceeded"):
            fetch_pr_details("pallets", "flask", 1)

    @patch("requests.get")
    def test_rate_limit_429(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {}
        mock_resp.text = "Too Many Requests"
        mock_get.return_value = mock_resp

        with pytest.raises(GitHubRateLimitError, match="rate limit exceeded"):
            fetch_pr_details("pallets", "flask", 1)

    @patch("requests.get")
    def test_token_is_not_leaked_in_exceptions(self, mock_get):
        secret_token = "ghp_super_secret_dummy_token_12345"
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.headers = {"x-ratelimit-remaining": "0"}
        mock_resp.text = "API rate limit exceeded"
        mock_get.return_value = mock_resp

        with pytest.raises(GitHubRateLimitError) as exc_info:
            fetch_pr_details("pallets", "flask", 1, token=secret_token)

        # Invariant: Never log or print token
        assert secret_token not in str(exc_info.value)
        assert secret_token not in repr(exc_info.value)


# ===========================================================================
# 4. Empty PR List Handling
# ===========================================================================
class TestEmptyPRList:
    @patch("requests.get")
    def test_fetch_open_prs_empty(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_get.return_value = mock_resp

        prs = fetch_open_prs("pallets", "flask", n=5)
        assert prs == []

    @patch("requests.get")
    def test_fetch_open_prs_populated(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {
                "number": 101,
                "title": "Fix typo in tutorial",
                "body": "Fixes #12",
                "user": {"login": "newcontributor"},
                "labels": [{"name": "docs"}],
                "updated_at": "2026-10-22T08:00:00Z",
                "html_url": "https://github.com/pallets/flask/pull/101",
                "additions": 1,
                "deletions": 1,
                "changed_files": 1,
            }
        ]
        mock_get.return_value = mock_resp

        prs = fetch_open_prs("pallets/flask", n=1, fetch_details=False)
        assert len(prs) == 1
        assert prs[0]["number"] == 101
        assert prs[0]["title"] == "Fix typo in tutorial"
        assert prs[0]["author"] == "newcontributor"
        assert prs[0]["labels"] == ["docs"]
        assert prs[0]["additions"] == 1
        assert prs[0]["deletions"] == 1
        assert prs[0]["changed_files"] == 1


# ===========================================================================
# 5. Missing vs Present CONTRIBUTING Guidance
# ===========================================================================
class TestContributingGuidance:
    @patch("requests.get")
    def test_contributing_missing_all_candidates(self, mock_get):
        mock_resp_404 = MagicMock()
        mock_resp_404.status_code = 404
        mock_get.return_value = mock_resp_404

        result = fetch_contributing_guidance("pallets", "flask")
        assert result["status"] == "unavailable"
        assert result["path"] is None
        assert result["text"] == ""

    @patch("requests.get")
    def test_contributing_present_second_candidate(self, mock_get):
        # First candidate CONTRIBUTING.md returns 404, second .github/CONTRIBUTING.md returns 200
        resp_404 = MagicMock(status_code=404)
        resp_200 = MagicMock(status_code=200, text="# Contribution Guidelines\n\nRun pytest before submitting.")
        mock_get.side_effect = [resp_404, resp_200]

        result = fetch_contributing_guidance("pallets", "flask")
        assert result["status"] == "present"
        assert result["path"] == ".github/CONTRIBUTING.md"
        assert "Run pytest before submitting" in result["text"]


# ===========================================================================
# 6. Truncated Patch & Byte Capping (fetch_pr_files)
# ===========================================================================
class TestTruncatedPatches:
    @patch("requests.get")
    def test_patch_capping_and_missing_patch(self, mock_get):
        large_patch = "@@ -1,5 +1,5 @@\n" + ("+added_line\n" * 200)  # ~2400 bytes
        mock_files_data = [
            {
                "filename": "big_file.py",
                "status": "modified",
                "additions": 200,
                "deletions": 0,
                "changes": 200,
                "patch": large_patch,
            },
            {
                "filename": "second_file.py",
                "status": "modified",
                "additions": 10,
                "deletions": 5,
                "changes": 15,
                "patch": "@@ -1,2 +1,2 @@\n-old\n+new",
            },
            {
                "filename": "image.png",
                "status": "added",
                "additions": 0,
                "deletions": 0,
                "changes": 0,
                "patch": None,  # Binary file has no patch in GitHub API
            },
        ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_files_data
        mock_get.return_value = mock_resp

        # Set max_bytes_per_file to 500 bytes and max_total_bytes to 800 bytes
        files = fetch_pr_files(
            "pallets", "flask", 123,
            max_bytes_per_file=500,
            max_total_bytes=800,
        )

        assert len(files) == 3

        # First file: exceeds 500 bytes per-file cap -> truncated
        assert files[0]["filename"] == "big_file.py"
        assert files[0]["truncated"] is True
        assert files[0]["patch_status"] == "truncated_file_limit"
        assert len(files[0]["patch"].encode("utf-8")) <= 500

        # Second file: fits in remaining total PR budget (800 - 500 = 300 bytes) -> complete
        assert files[1]["filename"] == "second_file.py"
        assert files[1]["truncated"] is False
        assert files[1]["patch_status"] == "complete"

        # Third file: binary file (patch is None) -> missing
        assert files[2]["filename"] == "image.png"
        assert files[2]["patch"] is None
        assert files[2]["patch_status"] == "missing"
        assert files[2]["truncated"] is False


# ===========================================================================
# 7. Timeout and Bounded Retries
# ===========================================================================
class TestTimeoutAndNetwork:
    @patch("requests.get")
    def test_timeout_with_bounded_retries(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("Connection timed out after 30s")

        with patch("time.sleep"):  # Speed up retry sleep during tests
            with pytest.raises(GitHubNetworkError, match="Failed to connect to GitHub API after 3 attempts"):
                fetch_pr_details("pallets", "flask", 42, timeout=5)

        # Max retries default is 2 -> total 3 attempts
        assert mock_get.call_count == 3


# ===========================================================================
# 8. Provable Linked-Issue Detection
# ===========================================================================
class TestLinkedIssueDetection:
    def test_provable_fixes_signal(self):
        signal, signals = detect_linked_issue_signal("This PR catches exceptions cleanly.\nFixes #12")
        assert signal == "Fixes #12"
        assert signals == ["Fixes #12"]

    def test_provable_multiple_signals(self):
        signal, signals = detect_linked_issue_signal("Closes #42 and resolves https://github.com/org/repo/issues/99")
        assert "Closes #42" in signal
        assert len(signals) == 2

    def test_unprovable_ambiguous_reference(self):
        signal, signals = detect_linked_issue_signal("Refers to #12 for inspiration, but does not close it.")
        assert signal == "unknown"
        assert signals == []

    def test_empty_body_signal(self):
        signal, signals = detect_linked_issue_signal("", "")
        assert signal == "unknown"
        assert signals == []


# ===========================================================================
# 9. Evidence Packet Builder & Exact Source Text Preservation
# ===========================================================================
class TestEvidencePacketBuilder:
    def test_exact_source_text_preservation(self):
        pr_details = {
            "owner": "pallets",
            "repo": "flask",
            "number": 42,
            "title": "Fix memory leak in response handler",
            "body": "Catches TimeoutError and cleans up sockets. Fixes #108",
            "author": "ada-lovelace",
            "author_association": "FIRST_TIME_CONTRIBUTOR",
            "state": "open",
            "draft": False,
            "created_at": "2026-10-22T08:00:00Z",
            "updated_at": "2026-10-22T08:30:00Z",
            "additions": 14,
            "deletions": 2,
            "changed_files": 1,
            "base_branch": "main",
            "head_branch": "patch-1",
            "html_url": "https://github.com/pallets/flask/pull/42",
            "labels": ["bug", "core"],
        }
        diff_text = "@@ -20,4 +20,6 @@\n+except TimeoutError:\n+    socket.close()\n"
        guidance = {
            "status": "present",
            "path": "CONTRIBUTING.md",
            "text": "Please provide unit tests for all bug fixes.",
        }

        packet = build_evidence_packet(
            pr_details=pr_details,
            pr_diff=diff_text,
            contributing_guidance=guidance,
        )

        # 1. PR facts verification
        assert packet["pr_facts"]["number"] == 42
        assert packet["pr_facts"]["linked_issue_signal"] == "Fixes #108"
        assert packet["pr_facts"]["first_time_contributor"] is True

        # 2. Check exact un-paraphrased source texts in sources list
        source_map = {s["id"]: s["text"] for s in packet["sources"]}
        assert source_map["title"] == pr_details["title"]
        assert source_map["body"] == pr_details["body"]
        assert source_map["diff"] == diff_text
        assert source_map["guidance"] == guidance["text"]

        # 3. In-code quote verification against evidence packet
        assert verify_quote_against_packet("except TimeoutError:", "diff", packet) is True
        assert verify_quote_against_packet("cleans up sockets", "body", packet) is True
        assert verify_quote_against_packet("Please provide unit tests", "guidance", packet) is True

        # Hallucinated quote must fail
        assert verify_quote_against_packet("This line never existed in diff", "diff", packet) is False

    def test_zero_contributor_bias_preserved(self):
        pr_details = {
            "owner": "test",
            "repo": "repo",
            "number": 1,
            "title": "Fix single typo",
            "body": "Typo in readme",
            "author": "first-timer",
            "author_association": "FIRST_TIME_CONTRIBUTOR",
        }
        packet = build_evidence_packet(pr_details=pr_details, pr_diff="")
        # Invariant: Record association factually; never score or deduct priority
        assert packet["pr_facts"]["first_time_contributor"] is True
        assert packet["pr_facts"]["author_association"] == "FIRST_TIME_CONTRIBUTOR"
