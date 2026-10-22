# Sift: evidence-first pull request triage

Sift helps open-source maintainers decide which pull requests to look at first,
and shows the evidence behind every claim. Code retrieves facts, Gemma 4
interprets them, and the maintainer decides. Sift never posts, closes, labels
or merges anything.

## What it does
- Fetches open PRs from a public GitHub repository (GitHub REST API).
- Builds an evidence packet per PR: description, changed files, diff excerpts.
- Gemma 4 returns a structured assessment: recommendation, review-urgency score,
  summary, missing context and a draft reply.
- Every evidence quote is checked IN CODE against the retrieved source and
  stamped VERIFIED IN SOURCE or NOT FOUND IN SOURCE. Unverified claims are
  never presented as fact.
- Results can be cached and are always labelled with the time they were made.

## Responsible-AI rules
Contributors are never scored. First-time, small and docs-only PRs are not
penalized. PR text is treated as untrusted input (prompt-injection resistant).
The score means review urgency, not contribution quality.

## Tech
Python, Flask, requests, python-dotenv, plain HTML/CSS/JS.
Model: Gemma 4 (gemma-4-26b-a4b-it) through the Gemini API.
Data: GitHub REST API (read-only token for public repos).

## Run (Windows PowerShell)
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env     # then add GEMINI_API_KEY and GITHUB_TOKEN
    python app.py              # open http://127.0.0.1:5000
    python -m pytest -q

## Limitations
- Free Gemini tier rate limits can delay analyses; cached results are labelled.
- Sift does not run code or tests. It can misjudge a PR, so a human reviews.
- Large diffs are truncated and marked as such.

## License
See LICENSE.