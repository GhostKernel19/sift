"""Flask Application and API Routes for Sift.

Assigned to: Agent 04 (Flask API & Web Interface)

Responsibilities:
- Provide web dashboard UI for maintainers at GET /
- Provide health & configuration status at GET /api/health
- Provide PR triage assessment endpoint at POST /api/assess
- Route orchestration:
    1. Parse and validate input (pr_url or owner/repo/pull_number)
    2. Invoke services.github_client to fetch metadata, diff, and comments
    3. Invoke services.evidence_builder to construct evidence packet
    4. Invoke services.gemma_assessor to generate and verify assessment
    5. Return structured JSON response to frontend
- Never auto-close, merge, label, or comment on GitHub.
"""

from __future__ import annotations

import os
from typing import Any
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

load_dotenv()

app = Flask(__name__)


@app.route("/", methods=["GET"])
def index() -> Any:
    """Renders the main Sift maintainer triage dashboard.

    Template: templates/index.html
    Static assets: static/css/styles.css, static/js/app.js
    """
    raise NotImplementedError("To be implemented by Agent 04")


@app.route("/api/health", methods=["GET"])
def health_check() -> Any:
    """Returns application health and environment configuration status.

    Response JSON shape (HTTP 200):
        {
            "status": "ok",
            "model": "gemma-4-26b-a4b-it",
            "gemini_configured": true,
            "github_configured": false
        }
    """
    raise NotImplementedError("To be implemented by Agent 04")


@app.route("/api/assess", methods=["POST"])
def assess_pr() -> Any:
    """Orchestrates pull request retrieval, evidence synthesis, and Gemma assessment.

    Request JSON shape:
        {
            "pr_url": "https://github.com/owner/repo/pull/123"
        }
        OR
        {
            "owner": "owner",
            "repo": "repo",
            "pull_number": 123
        }

    Success Response JSON shape (HTTP 200):
        {
            "status": "success",
            "data": {
                "summary": str,
                "recommendation": "review" | "needs_work" | "low_effort" |
                                  "potentially_irrelevant_or_suspicious" | "insufficient_evidence",
                "priority_score": int (1-5),
                "confidence": "low" | "medium" | "high",
                "evidence": [
                    {
                        "claim": str,
                        "source": str,
                        "quote": str,
                        "verified": bool
                    }
                ],
                "missing_context": [str],
                "suggested_response": str,
                "uncertainty_reason": str
            },
            "pr": {
                "owner": str,
                "repo": str,
                "pull_number": int,
                "title": str,
                "html_url": str
            }
        }

    Error Response JSON shape (HTTP 400 / 404 / 500 / 502):
        {
            "status": "error",
            "error": "Descriptive error message"
        }
    """
    raise NotImplementedError("To be implemented by Agent 04")


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "True").lower() in ("true", "1")
    app.run(host="0.0.0.0", port=port, debug=debug)
