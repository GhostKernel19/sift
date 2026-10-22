"""Flask Application and API Routes for Sift.

Evidence-first GitHub pull-request triage assistant for open-source maintainers.
Code retrieves facts, Gemma 4 interprets evidence, humans decide.

Strict Invariants:
- Human-in-the-Loop Supremacy: Never auto-merge, auto-close, auto-label, or auto-comment.
- Zero Contributor Bias: First-time contributors and typo fixes evaluated equally.
- In-Code Quote Verification: Quotes are verified against authentic source text.
- Security & Secrets: Never log, commit, or expose API keys or tokens.
- Analysis on Click: Analyze only single PR on demand; never whole queue automatically.
- Auditable Cache: Cache analyses in memory and demo_cache/; cache hits are explicitly
  labelled "cached on <time>".
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from services.assessment_schema import AssessmentValidationError
from services.evidence_builder import build_evidence_packet
from services.gemma_assessor import (
    DEFAULT_GEMMA_MODEL,
    assess,
    is_error_assessment,
)
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

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

DEMO_CACHE_DIR = Path(os.getenv("DEMO_CACHE_DIR", "demo_cache"))

# In-memory analysis cache: (owner.lower(), repo.lower(), pull_number) -> dict
_ANALYSIS_MEMORY_CACHE: dict[tuple[str, str, int], dict[str, Any]] = {}


# ============================================================================
# Cache Storage & Retrieval
# ============================================================================
def _get_cache_file_path(owner: str, repo: str, pull_number: int) -> Path:
    """Returns filesystem path for cached PR assessment."""
    safe_owner = owner.lower().strip()
    safe_repo = repo.lower().strip()
    return DEMO_CACHE_DIR / f"{safe_owner}__{safe_repo}__{pull_number}.json"


def _get_cached_analysis(owner: str, repo: str, pull_number: int) -> Optional[dict[str, Any]]:
    """Retrieves cached analysis from memory or demo_cache/ JSON file."""
    cache_key = (owner.lower().strip(), repo.lower().strip(), pull_number)

    # 1. Check in-memory cache
    if cache_key in _ANALYSIS_MEMORY_CACHE:
        return _ANALYSIS_MEMORY_CACHE[cache_key]

    # 2. Check disk cache
    file_path = _get_cache_file_path(owner, repo, pull_number)
    if file_path.is_file():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    _ANALYSIS_MEMORY_CACHE[cache_key] = data
                    return data
        except Exception as e:
            logger.warning(f"Failed to read disk cache file {file_path}: {e}")

    return None


def _save_cached_analysis(owner: str, repo: str, pull_number: int, data: dict[str, Any]) -> None:
    """Stores analysis in memory and writes JSON to demo_cache/."""
    cache_key = (owner.lower().strip(), repo.lower().strip(), pull_number)
    _ANALYSIS_MEMORY_CACHE[cache_key] = data

    try:
        DEMO_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        file_path = _get_cache_file_path(owner, repo, pull_number)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.warning(f"Failed to write disk cache for {owner}/{repo}#{pull_number}: {e}")


def _error_response(
    error_type: str,
    message: str,
    details: str = "",
    status_code: int = 400,
    retry_delay: Optional[int] = None,
) -> tuple[Any, int]:
    """Builds a standardized typed error JSON response."""
    payload: dict[str, Any] = {
        "status": "error",
        "error_type": error_type,
        "error": message,
        "details": details or message,
    }
    if retry_delay is not None:
        payload["retry_delay"] = retry_delay
    return jsonify(payload), status_code


# ============================================================================
# Routes
# ============================================================================
@app.route("/", methods=["GET"])
def index() -> Any:
    """Renders the main Sift maintainer triage desk dashboard."""
    return render_template("index.html")


@app.route("/api/health", methods=["GET"])
def health_check() -> Any:
    """Returns application health and environment configuration status."""
    gemini_key = os.getenv("GEMINI_API_KEY")
    github_token = os.getenv("GITHUB_TOKEN")
    model_name = os.getenv("GEMMA_MODEL", DEFAULT_GEMMA_MODEL)

    return (
        jsonify({
            "status": "ok",
            "model": model_name,
            "gemini_configured": bool(gemini_key and gemini_key.strip()),
            "github_configured": bool(github_token and github_token.strip()),
        }),
        200,
    )


@app.route("/api/prs", methods=["POST"])
def list_prs() -> Any:
    """Fetches open pull requests for a validated repository (queue metadata).

    Request JSON:
        { "repo": "owner/repo" } or { "repo": "https://github.com/owner/repo" }

    Response JSON:
        {
            "status": "success",
            "repo": "owner/repo",
            "prs": [ { "number": int, "title": str, ... } ],
            "count": int
        }
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error_response("invalid_repo", "Request body must be a JSON object containing 'repo'.", status_code=400)

    repo_input = str(body.get("repo") or body.get("repository") or "").strip()
    if not repo_input:
        return _error_response("invalid_repo", "Missing 'repo' field in request body.", status_code=400)

    try:
        owner, repo_name = validate_repo_input(repo_input)
    except GitHubValidationError as e:
        return _error_response("invalid_repo", str(e), status_code=400)

    token = os.getenv("GITHUB_TOKEN")
    try:
        prs = fetch_open_prs(owner, repo_name, n=10, token=token, fetch_details=False)
        return jsonify({
            "status": "success",
            "repo": f"{owner}/{repo_name}",
            "prs": prs,
            "count": len(prs),
        }), 200

    except GitHubNotFoundError as e:
        return _error_response("not_found", f"Repository '{owner}/{repo_name}' not found on GitHub.", details=str(e), status_code=404)
    except GitHubRateLimitError as e:
        return _error_response("rate_limit", str(e), status_code=429)
    except GitHubAuthenticationError as e:
        return _error_response("auth_error", str(e), status_code=401)
    except GitHubNetworkError as e:
        return _error_response("network_error", f"Network error contacting GitHub API: {e}", details=str(e), status_code=503)
    except GitHubError as e:
        return _error_response("provider_error", f"GitHub API error: {e}", details=str(e), status_code=502)
    except Exception as e:
        logger.exception("Unexpected error in /api/prs")
        return _error_response("server_error", f"Internal server error: {e}", status_code=500)


@app.route("/api/analyze", methods=["POST"])
@app.route("/api/assess", methods=["POST"])
def analyze_pr() -> Any:
    """Orchestrates pull request retrieval, evidence synthesis, and Gemma assessment.

    Analyzes ONLY the requested pull request (on click / on demand).
    Uses caching (memory + demo_cache/) and stamps cache hits with 'cached on <time>'.

    Accepted Request JSON shapes:
        { "repo": "owner/repo", "number": 123 }
        { "repo": "owner/repo#123" }
        { "repo": "https://github.com/owner/repo", "number": 123 }
        { "pr_url": "https://github.com/owner/repo/pull/123" }
        { "owner": "owner", "repo": "repo", "pull_number": 123 }
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _error_response("invalid_repo", "Request body must be a JSON object.", status_code=400)

    # Resolve owner, repo, pull_number
    owner: Optional[str] = None
    repo: Optional[str] = None
    pull_number: Optional[int] = None

    pr_url = body.get("pr_url") or body.get("url")
    repo_field = body.get("repo") or body.get("repository")
    number_field = body.get("number") or body.get("pull_number")

    try:
        if pr_url and isinstance(pr_url, str) and pr_url.strip():
            owner, repo, pull_number = parse_pr_url(pr_url.strip())
        elif repo_field and isinstance(repo_field, str) and ("#" in repo_field or "/pull/" in repo_field):
            owner, repo, pull_number = parse_pr_url(repo_field.strip())
        elif repo_field and isinstance(repo_field, str) and number_field is not None:
            owner, repo = validate_repo_input(repo_field.strip())
            pull_number = int(number_field)
            if pull_number <= 0:
                raise ValueError("Pull request number must be positive")
        elif body.get("owner") and body.get("repo") and number_field is not None:
            owner, repo = validate_owner_repo(str(body["owner"]), str(body["repo"]))
            pull_number = int(number_field)
            if pull_number <= 0:
                raise ValueError("Pull request number must be positive")
        else:
            return _error_response(
                "invalid_repo",
                "Please provide 'repo' and 'number' (e.g. repo='owner/repo', number=123) or a valid 'pr_url'.",
                status_code=400,
            )
    except (GitHubValidationError, ValueError) as e:
        return _error_response("invalid_repo", str(e), status_code=400)

    if not owner or not repo or not pull_number:
        return _error_response("invalid_repo", "Could not resolve owner, repo, and pull number.", status_code=400)

    # ------------------------------------------------------------------------
    # 1. Cache Inspection
    # ------------------------------------------------------------------------
    force_live = bool(body.get("force_live") or body.get("refresh"))
    if not force_live:
        cached = _get_cached_analysis(owner, repo, pull_number)
        if cached is not None:
            cached_time = cached.get("cached_at") or cached.get("cached_on") or "earlier"
            cache_label = f"cached on {cached_time}"
            response_payload = dict(cached)
            response_payload["status"] = "success"
            response_payload["cache_hit"] = True
            response_payload["cached_on"] = cached_time
            response_payload["cache_label"] = cache_label
            response_payload["cached_notice"] = cache_label

            # Ensure metadata reflects cache hit
            metadata = dict(response_payload.get("metadata") or {})
            metadata["dataSource"] = f"Cache ({cache_label})"
            metadata["cached_on"] = cached_time
            response_payload["metadata"] = metadata

            return jsonify(response_payload), 200

    # ------------------------------------------------------------------------
    # 2. Live GitHub Data Retrieval
    # ------------------------------------------------------------------------
    token = os.getenv("GITHUB_TOKEN")
    try:
        pr_details = fetch_pr_details(owner, repo, pull_number, token=token)
        pr_diff = fetch_pr_diff(owner, repo, pull_number, token=token)
        pr_files = fetch_pr_files(owner, repo, pull_number, token=token)
        pr_comments = fetch_pr_comments(owner, repo, pull_number, token=token)
        guidance = fetch_contributing_guidance(owner, repo, token=token)
    except GitHubNotFoundError as e:
        return _error_response("not_found", f"Pull request {owner}/{repo}#{pull_number} not found on GitHub.", details=str(e), status_code=404)
    except GitHubRateLimitError as e:
        return _error_response("rate_limit", str(e), status_code=429)
    except GitHubAuthenticationError as e:
        return _error_response("auth_error", str(e), status_code=401)
    except GitHubNetworkError as e:
        return _error_response("network_error", f"Failed to connect to GitHub: {e}", details=str(e), status_code=503)
    except GitHubError as e:
        return _error_response("provider_error", f"GitHub error: {e}", details=str(e), status_code=502)
    except Exception as e:
        logger.exception("Unexpected error retrieving GitHub PR data")
        return _error_response("server_error", f"Error retrieving PR from GitHub: {e}", status_code=500)

    # ------------------------------------------------------------------------
    # 3. Evidence Synthesis & Packet Assembly
    # ------------------------------------------------------------------------
    try:
        packet = build_evidence_packet(
            pr_details,
            pr_diff=pr_diff,
            pr_comments=pr_comments,
            pr_files=pr_files,
            contributing_guidance=guidance,
        )
    except Exception as e:
        logger.exception("Failed to assemble evidence packet")
        return _error_response("server_error", f"Failed to assemble evidence packet: {e}", status_code=500)

    diff_summary = packet.get("diff_summary", {})
    is_diff_truncated = bool(diff_summary.get("is_truncated", False))
    partial_reason = "Diff exceeded line limit (1500 lines) and was truncated." if is_diff_truncated else ""

    # ------------------------------------------------------------------------
    # 4. Gemma 4 Assessment with Quote Verification
    # ------------------------------------------------------------------------
    try:
        assessment_result = assess(packet)
    except Exception as e:
        logger.exception("Unexpected exception from assessor")
        return _error_response("model_unavailable", f"Assessor invocation failed: {e}", details=str(e), status_code=503)

    if is_error_assessment(assessment_result):
        err_type = assessment_result.get("error_type", "provider_error")
        err_msg = assessment_result.get("error", "Gemma assessment failed.")
        details = assessment_result.get("details", err_msg)
        if err_type == "rate_limit":
            retry_delay = assessment_result.get("retry_delay") or 15
            return _error_response(
                "rate_limit",
                "Rate limited by the free Gemini tier.",
                details="Rate limit reached on Gemini API. Please wait for the quota window to reset.",
                status_code=429,
                retry_delay=retry_delay,
            )
        elif err_type in ("config_error", "timeout", "provider_error"):
            return _error_response("model_unavailable", err_msg, details=details, status_code=503)
        elif err_type == "invalid_output":
            return _error_response("invalid_model_output", err_msg, details=details, status_code=502)
        else:
            return _error_response(err_type, err_msg, details=details, status_code=502)

    # ------------------------------------------------------------------------
    # 5. Response Assembly Matching Frontend Expectations
    # ------------------------------------------------------------------------
    now_utc_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    chosen_model = os.getenv("GEMMA_MODEL", DEFAULT_GEMMA_MODEL)

    # Harmonize pr dict for frontend: both 'number' and 'pull_number'
    pr_data = dict(pr_details)
    pr_data["pull_number"] = pull_number
    pr_data["number"] = pull_number

    # Harmonize file objects: both 'path' and 'filename'
    files_data = [
        {
            "path": f.get("filename", ""),
            "filename": f.get("filename", ""),
            "additions": f.get("additions", 0),
            "deletions": f.get("deletions", 0),
            "changes": f.get("changes", 0),
            "status": f.get("status", "modified"),
            "patch": f.get("patch"),
            "truncated": f.get("truncated", False),
        }
        for f in pr_files
    ]

    live_dossier = {
        "status": "success",
        "repo": f"{owner}/{repo}",
        "pull_number": pull_number,
        "pr": pr_data,
        "files": files_data,
        "diff": pr_diff,
        "data": assessment_result,       # Expected by frontend: static/js/app.js line 817
        "assessment": assessment_result, # Standard alias
        "packet": packet,
        "diff_summary": diff_summary,
        "diff_truncated": is_diff_truncated,
        "is_partial": is_diff_truncated,
        "partial_reason": partial_reason,
        "model": chosen_model,
        "cache_hit": False,
        "cached_on": None,
        "cache_label": None,
        "metadata": {
            "dataSource": "GitHub REST API (Live)",
            "auditedAt": now_utc_str,
            "assessorModel": f"{chosen_model} via REST API",
        },
    }

    # ------------------------------------------------------------------------
    # 6. Cache Save (Memory + Disk)
    # ------------------------------------------------------------------------
    cache_record = dict(live_dossier)
    cache_record["cached_at"] = now_utc_str
    cache_record["cached_on"] = now_utc_str
    cache_record["cache_hit"] = True
    cache_record["cache_label"] = f"cached on {now_utc_str}"
    _save_cached_analysis(owner, repo, pull_number, cache_record)

    return jsonify(live_dossier), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "True").lower() in ("true", "1")
    app.run(host="0.0.0.0", port=port, debug=debug)
