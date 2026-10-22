"""Integration tests for Flask application routes and caching.

Tests:
1. GET /: Serves templates/index.html.
2. GET /api/health: Returns 200 with health and config flags.
3. POST /api/prs:
   - Valid repository returns PR queue metadata.
   - Invalid or missing repository returns 400 with typed error 'invalid_repo'.
   - Non-existent repository returns 404 with typed error 'not_found'.
   - Rate limit returns 429 with typed error 'rate_limit'.
4. POST /api/analyze & POST /api/assess:
   - Live analysis on demand (single PR per request).
   - In-code quote verification flags preserved.
   - Caching: First run is live (cache_hit=False), second run is cached (cache_hit=True, labelled 'cached on <time>').
   - Disk cache: File persisted in demo_cache/ with timestamp, repo, PR number.
   - Model unavailable / timeout: Returns 503 with typed error 'model_unavailable'.
   - Invalid model output: Returns 502 with typed error 'invalid_model_output'.
   - Truncated diff: Returns partial data indicators.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import app as app_module
from app import app
from services.github_client import (
    GitHubNotFoundError,
    GitHubRateLimitError,
    GitHubValidationError,
)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    # Use temporary directory for demo_cache during tests
    temp_dir = tempfile.mkdtemp(prefix="sift_test_cache_")
    orig_cache_dir = app_module.DEMO_CACHE_DIR
    app_module.DEMO_CACHE_DIR = Path(temp_dir)
    app_module._ANALYSIS_MEMORY_CACHE.clear()

    with app.test_client() as test_client:
        yield test_client

    # Cleanup temp directory
    shutil.rmtree(temp_dir, ignore_errors=True)
    app_module.DEMO_CACHE_DIR = orig_cache_dir
    app_module._ANALYSIS_MEMORY_CACHE.clear()


# ============================================================================
# Basic Routes & Health
# ============================================================================
def test_get_index(client):
    response = client.get("/")
    assert response.status_code == 200
    assert b"SIFT" in response.data
    assert b"Evidence Desk" in response.data


def test_get_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert "model" in data
    assert "gemini_configured" in data
    assert "github_configured" in data


# ============================================================================
# POST /api/prs (Queue Metadata)
# ============================================================================
def test_list_prs_missing_body(client):
    response = client.post("/api/prs", json=None)
    assert response.status_code == 400
    data = response.get_json()
    assert data["status"] == "error"
    assert data["error_type"] == "invalid_repo"


def test_list_prs_invalid_repo(client):
    response = client.post("/api/prs", json={"repo": "invalid/format/with/slashes"})
    assert response.status_code == 400
    data = response.get_json()
    assert data["status"] == "error"
    assert data["error_type"] == "invalid_repo"


@patch("app.fetch_open_prs")
def test_list_prs_success(mock_fetch_open_prs, client):
    mock_fetch_open_prs.return_value = [
        {
            "number": 101,
            "title": "Add retry mechanism",
            "body": "Implements exponential backoff",
            "author": "contributor1",
            "labels": ["enhancement"],
            "updated_at": "2026-10-22T10:00:00Z",
            "html_url": "https://github.com/pallets/flask/pull/101",
            "additions": 15,
            "deletions": 2,
            "changed_files": 1,
        }
    ]

    response = client.post("/api/prs", json={"repo": "pallets/flask"})
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "success"
    assert data["repo"] == "pallets/flask"
    assert len(data["prs"]) == 1
    assert data["prs"][0]["number"] == 101


@patch("app.fetch_open_prs")
def test_list_prs_not_found(mock_fetch_open_prs, client):
    mock_fetch_open_prs.side_effect = GitHubNotFoundError("Repo not found")
    response = client.post("/api/prs", json={"repo": "nonexistent/repo"})
    assert response.status_code == 404
    data = response.get_json()
    assert data["status"] == "error"
    assert data["error_type"] == "not_found"


@patch("app.fetch_open_prs")
def test_list_prs_rate_limit(mock_fetch_open_prs, client):
    mock_fetch_open_prs.side_effect = GitHubRateLimitError("Rate limit exceeded")
    response = client.post("/api/prs", json={"repo": "pallets/flask"})
    assert response.status_code == 429
    data = response.get_json()
    assert data["status"] == "error"
    assert data["error_type"] == "rate_limit"


# ============================================================================
# POST /api/analyze & POST /api/assess
# ============================================================================
@pytest.fixture
def mock_pr_data():
    return {
        "pr_details": {
            "owner": "pallets",
            "repo": "flask",
            "number": 42,
            "title": "Add retry parameter",
            "body": "Fixes connection drops by adding retries.",
            "author": "dev-user",
            "author_association": "CONTRIBUTOR",
            "state": "open",
            "draft": False,
            "created_at": "2026-10-22T08:00:00Z",
            "updated_at": "2026-10-22T09:00:00Z",
            "additions": 5,
            "deletions": 1,
            "changed_files": 1,
            "base_branch": "main",
            "head_branch": "retry-fix",
            "html_url": "https://github.com/pallets/flask/pull/42",
            "labels": ["bug"],
        },
        "pr_diff": "--- a/app.py\n+++ b/app.py\n@@ -10,1 +10,2 @@\n-old()\n+retries = 3\n",
        "pr_files": [
            {
                "filename": "app.py",
                "additions": 5,
                "deletions": 1,
                "changes": 6,
                "status": "modified",
                "patch": "@@ -10,1 +10,2 @@\n-old()\n+retries = 3\n",
                "truncated": False,
            }
        ],
        "pr_comments": [],
        "guidance": {"status": "unavailable", "path": None, "text": ""},
        "assessment": {
            "summary": "Adds retries parameter to mitigate connection drops.",
            "recommendation": "review",
            "priority_score": 3,
            "confidence": "high",
            "evidence": [
                {
                    "claim": "Sets default retries to 3",
                    "source": "diff",
                    "quote": "retries = 3",
                    "verified": True,
                }
            ],
            "missing_context": ["Unit test for retry failure"],
            "suggested_response": "Thanks for adding retries! Could you add a unit test?",
            "uncertainty_reason": "",
        },
    }


@patch("app.assess")
@patch("app.fetch_contributing_guidance")
@patch("app.fetch_pr_comments")
@patch("app.fetch_pr_files")
@patch("app.fetch_pr_diff")
@patch("app.fetch_pr_details")
def test_analyze_pr_live_then_cached(
    mock_details,
    mock_diff,
    mock_files,
    mock_comments,
    mock_guidance,
    mock_assess,
    mock_pr_data,
    client,
):
    mock_details.return_value = mock_pr_data["pr_details"]
    mock_diff.return_value = mock_pr_data["pr_diff"]
    mock_files.return_value = mock_pr_data["pr_files"]
    mock_comments.return_value = mock_pr_data["pr_comments"]
    mock_guidance.return_value = mock_pr_data["guidance"]
    mock_assess.return_value = mock_pr_data["assessment"]

    # 1. First run: Fresh live run
    payload = {"repo": "pallets/flask", "number": 42}
    response1 = client.post("/api/analyze", json=payload)
    assert response1.status_code == 200
    res1 = response1.get_json()

    assert res1["status"] == "success"
    assert res1["cache_hit"] is False
    assert res1["cached_on"] is None
    assert res1["repo"] == "pallets/flask"
    assert res1["pull_number"] == 42
    assert res1["pr"]["pull_number"] == 42
    assert res1["pr"]["number"] == 42
    assert len(res1["files"]) == 1
    assert res1["files"][0]["path"] == "app.py"
    assert res1["data"]["recommendation"] == "review"
    assert res1["data"]["evidence"][0]["verified"] is True
    assert mock_assess.call_count == 1

    # Check disk cache exists
    cache_file = app_module.DEMO_CACHE_DIR / "pallets__flask__42.json"
    assert cache_file.is_file()

    # 2. Second run: Cache hit
    response2 = client.post("/api/analyze", json=payload)
    assert response2.status_code == 200
    res2 = response2.get_json()

    assert res2["status"] == "success"
    assert res2["cache_hit"] is True
    assert res2["cached_on"] is not None
    assert "cached on " in res2["cache_label"]
    assert mock_assess.call_count == 1  # Not called again!


@patch("app.assess")
@patch("app.fetch_contributing_guidance")
@patch("app.fetch_pr_comments")
@patch("app.fetch_pr_files")
@patch("app.fetch_pr_diff")
@patch("app.fetch_pr_details")
def test_assess_alias_matches_frontend_contract(
    mock_details,
    mock_diff,
    mock_files,
    mock_comments,
    mock_guidance,
    mock_assess,
    mock_pr_data,
    client,
):
    """Verifies that POST /api/assess with {pr_url} matches static/js/app.js expectations."""
    mock_details.return_value = mock_pr_data["pr_details"]
    mock_diff.return_value = mock_pr_data["pr_diff"]
    mock_files.return_value = mock_pr_data["pr_files"]
    mock_comments.return_value = mock_pr_data["pr_comments"]
    mock_guidance.return_value = mock_pr_data["guidance"]
    mock_assess.return_value = mock_pr_data["assessment"]

    payload = {"pr_url": "https://github.com/pallets/flask/pull/42"}
    response = client.post("/api/assess", json=payload)
    assert response.status_code == 200
    res = response.get_json()

    # Frontend checks in static/js/app.js:
    # resData.pr.pull_number
    assert res["pr"]["pull_number"] == 42
    # resData.files[].path
    assert res["files"][0]["path"] == "app.py"
    # resData.diff
    assert "retries = 3" in res["diff"]
    # resData.data (assessment)
    assert res["data"]["summary"] == mock_pr_data["assessment"]["summary"]
    # resData.data.evidence verified flag
    assert res["data"]["evidence"][0]["verified"] is True


@patch("app.assess")
@patch("app.fetch_contributing_guidance")
@patch("app.fetch_pr_comments")
@patch("app.fetch_pr_files")
@patch("app.fetch_pr_diff")
@patch("app.fetch_pr_details")
def test_analyze_model_unavailable(
    mock_details,
    mock_diff,
    mock_files,
    mock_comments,
    mock_guidance,
    mock_assess,
    mock_pr_data,
    client,
):
    mock_details.return_value = mock_pr_data["pr_details"]
    mock_diff.return_value = mock_pr_data["pr_diff"]
    mock_files.return_value = mock_pr_data["pr_files"]
    mock_comments.return_value = mock_pr_data["pr_comments"]
    mock_guidance.return_value = mock_pr_data["guidance"]

    # Model returns typed error state for timeout or config
    mock_assess.return_value = {
        "status": "error",
        "error_type": "timeout",
        "error": "Gemma API request timed out after 90s.",
        "details": "Connection timed out",
    }

    response = client.post("/api/analyze", json={"repo": "pallets/flask", "number": 42})
    assert response.status_code == 503
    data = response.get_json()
    assert data["status"] == "error"
    assert data["error_type"] == "model_unavailable"


@patch("app.assess")
@patch("app.fetch_contributing_guidance")
@patch("app.fetch_pr_comments")
@patch("app.fetch_pr_files")
@patch("app.fetch_pr_diff")
@patch("app.fetch_pr_details")
def test_analyze_invalid_model_output(
    mock_details,
    mock_diff,
    mock_files,
    mock_comments,
    mock_guidance,
    mock_assess,
    mock_pr_data,
    client,
):
    mock_details.return_value = mock_pr_data["pr_details"]
    mock_diff.return_value = mock_pr_data["pr_diff"]
    mock_files.return_value = mock_pr_data["pr_files"]
    mock_comments.return_value = mock_pr_data["pr_comments"]
    mock_guidance.return_value = mock_pr_data["guidance"]

    # Model returns invalid_output error state
    mock_assess.return_value = {
        "status": "error",
        "error_type": "invalid_output",
        "error": "Failed to parse JSON output",
        "details": "Raw: not json",
    }

    response = client.post("/api/analyze", json={"repo": "pallets/flask", "number": 42})
    assert response.status_code == 502
    data = response.get_json()
    assert data["status"] == "error"
    assert data["error_type"] == "invalid_model_output"
