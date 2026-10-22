# Sift

> **An evidence-first GitHub pull-request triage assistant for open-source maintainers.**  
> *Code retrieves facts, Gemma 4 interprets evidence, humans decide.*

---

## Overview

Open-source maintainers are frequently overwhelmed with incoming pull requests. Many automated tools attempt to act autonomously (auto-closing, auto-tagging) or profile contributors with dubious reputation metrics. 

**Sift** takes an evidence-first approach:
1. **Deterministic Retrieval**: Retrieves PR metadata, unified diffs, and discussions directly from GitHub.
2. **Gemma 4 Evidence Assessment**: Interprets the evidence via plain Google Gemini REST API calls without SDKs or native JSON mode assumptions.
3. **In-Code Verification**: Enforces that any quote cited as evidence is strictly verified as a genuine substring of retrieved text. Unverified citations are flagged and quarantined.
4. **Human Decides**: Generates objective summaries, evidence packets, and suggested maintainer responses. Never auto-closes, auto-merges, or auto-comments. First-time contributors, small PRs, and docs fixes are never penalized.

---

## Getting Started (Windows & PowerShell)

### Prerequisites
- Python 3.10+ (tested on Python 3.14)
- PowerShell
- A Google Gemini API key with access to Gemma 4 models (`gemma-4-26b-a4b-it` or `gemma-4-31b-it`)
- (Optional) A GitHub Personal Access Token for higher API rate limits

### 1. Environment Setup

Activate the existing virtual environment in PowerShell:
```powershell
.\.venv\Scripts\Activate.ps1
```

If setting up fresh:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install locked project dependencies:
```powershell
pip install -r requirements.txt
```

### 2. Configure Credentials

Copy `.env.example` to `.env`:
```powershell
Copy-Item .env.example .env
```

Open `.env` and configure your credentials:
```ini
GEMINI_API_KEY=your_gemini_api_key_here
GEMMA_MODEL=gemma-4-26b-a4b-it
GITHUB_TOKEN=
```

Verify your Gemma 4 connection:
```powershell
python verify_gemma.py
```

---

## Running Sift

Start the Flask application server:
```powershell
python app.py
```

Or using Flask development mode:
```powershell
$env:FLASK_APP = "app.py"
$env:FLASK_DEBUG = "1"
flask run
```

Access the dashboard in your browser:
```
http://localhost:5000
```

### API Endpoints
- `GET /`: Maintainer Evidence Desk UI (`templates/index.html`).
- `GET /api/health`: Health status, Gemma 4 model info, and API key configuration check.
- `POST /api/prs`: Fetches open pull requests for queue metadata: `{ "repo": "owner/repo" }`.
- `POST /api/analyze` & `POST /api/assess`: Analyzes a single pull request on demand: `{ "repo": "owner/repo", "number": 123 }` or `{ "pr_url": "https://github.com/owner/repo/pull/123" }`.
  - Auditable Caching: Analyses are cached in memory and in `demo_cache/`. Cache hits are labeled `"cached on <time>"`.
  - In-Code Quote Verification: Every claim quote is verified as a genuine substring of authentic retrieved source text.

---

## Running Tests

Execute the test suite with pytest:
```powershell
# Run all tests
pytest -q

# Run tests with detailed output
pytest -v

# Run integration tests for Flask routes & cache
pytest tests/test_app.py
```

---

## Project Structure

```
sift/
├── AGENTS.md                          # Multi-agent architectural rules & ownership
├── app.py                             # Flask application & HTTP endpoints
├── requirements.txt                   # Locked dependencies
├── .env.example                       # Environment configuration template
├── verify_gemma.py                    # Verified Gemma 4 REST connection test
├── demo_cache/                        # Persisted PR assessments (JSON cache)
├── services/
│   ├── assessment_schema.py           # Assessment contract & quote verification
│   ├── github_client.py               # GitHub REST API client
│   ├── evidence_builder.py            # Evidence packet builder & corpus indexing
│   └── gemma_assessor.py              # Gemma 4 REST prompt engineer & JSON parser
├── templates/                         # Frontend HTML templates
├── static/                            # Frontend CSS & vanilla JavaScript
└── tests/                             # Unit and integration tests
```