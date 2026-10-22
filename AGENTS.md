# Sift — Multi-Agent Engineering Guide (AGENTS.md)

## 1. Project Overview & Philosophy

**Sift** is an evidence-first GitHub pull-request triage assistant for open-source maintainers.
> **Core Principle**: *Code retrieves facts, Gemma 4 interprets evidence, humans decide.*

Sift assists maintainers by reading pull request details, unified diffs, and discussions, synthesizing this into verifiable evidence, prompting Gemma 4 to assess the PR, and displaying the results on a maintainer dashboard.

---

## 2. Locked Invariants (Non-Negotiable)

All participating agents and contributors must strictly adhere to the following invariants:

1. **Human-in-the-Loop Supremacy**:
   - **NEVER** auto-close, auto-merge, auto-label, or auto-comment on pull requests.
   - Sift generates suggestions and analysis; only the human maintainer initiates actions.

2. **Zero Contributor-Quality Bias**:
   - **NO** contributor-quality scoring or profiling.
   - First-time contributors, small PRs (e.g. single-line typo fixes), and documentation-only PRs are **never penalized** in priority or recommendation.

3. **In-Code Substring Quote Verification**:
   - Every quote in `evidence.quote` **MUST** be verified in code as an authentic substring of the retrieved evidence text (`source_corpus`).
   - Quotes that fail substring verification are flagged with `verified: false` and quarantined—they must **never** be presented to maintainers as verified facts.

4. **Raw REST API for Gemma 4 (No SDK, No Native JSON Mode)**:
   - Call Gemma 4 via the Google Gemini REST API using standard `requests`:
     `POST https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent`
   - Header: `x-goog-api-key: <GEMINI_API_KEY>`, `Content-Type: application/json`.
   - Default model: `gemma-4-26b-a4b-it` (set via `GEMMA_MODEL` env var; `gemma-4-31b-it` also supported).
   - The model emits reasoning parts: filter out response parts marked with `"thought": true`.
   - Extract the **LAST balanced JSON object** containing the required keys from the remaining text.
   - **Never** call `json.loads` directly on the raw generation text.
   - If JSON extraction fails, retry generation once.
   - Enforce timeouts (minimum 30–60s) and retry on `requests.ConnectionError`.

5. **Secrets & Security**:
   - Never commit `.env` or log API keys or GitHub tokens in terminal output, exceptions, or UI responses.
   - GitHub token authentication is optional (falls back gracefully to unauthenticated requests).

6. **Deferred Features**:
   - Graphify graph context is deferred for later phases. **Do not implement now.**

---

## 3. Architecture & File Ownership

```
sift/
├── .env.example                       # Environment variable templates (Agent 01)
├── requirements.txt                   # Locked dependencies (Agent 01)
├── README.md                          # Project documentation & run guides (Agent 01)
├── AGENTS.md                          # Multi-agent architectural contract (Agent 01)
├── verify_gemma.py                    # Verification script for Gemma 4 REST API (Reference)
├── app.py                             # Flask application & route handlers (Agent 04)
├── services/
│   ├── __init__.py
│   ├── assessment_schema.py           # Assessment contract & verification logic (Agent 01)
│   ├── github_client.py               # GitHub REST API retrieval engine (Agent 02)
│   ├── evidence_builder.py            # Evidence synthesis & packet builder (Agent 02)
│   └── gemma_assessor.py              # Gemma 4 prompt engineering & extraction (Agent 03)
├── templates/
│   └── index.html                     # Triage dashboard HTML (Agent 04)
├── static/
│   ├── css/
│   │   └── styles.css                 # Vanilla CSS design system (Agent 04)
│   └── js/
│       └── app.js                     # Frontend interactive controller (Agent 04)
└── tests/
    ├── test_assessment_schema.py      # Schema & quote verification tests (Agent 01)
    ├── test_github_client.py          # GitHub client mock tests (Agent 02)
    ├── test_evidence_builder.py       # Evidence packet builder tests (Agent 02)
    ├── test_gemma_assessor.py         # Assessor & extraction tests (Agent 03)
    └── test_app.py                    # Flask route integration tests (Agent 04)
```

### Agent Division of Responsibilities

- **Agent 01 — Systems Architect & Integration Lead**:
  - Owns: `AGENTS.md`, `services/assessment_schema.py`, `requirements.txt`, `.env.example`, `README.md`, interface signatures.
  - Ensures schema consistency, quote verification contracts, and dependency hygiene.

- **Agent 02 — Evidence & GitHub Engine**:
  - Owns: `services/github_client.py`, `services/evidence_builder.py`, `tests/test_github_client.py`, `tests/test_evidence_builder.py`.
  - Implements GitHub PR parsing, diff/metadata/comment fetching, diff truncation rules, and `source_corpus` packet assembly.

- **Agent 03 — Gemma 4 Assessor & Prompt Engineer**:
  - Owns: `services/gemma_assessor.py`, `tests/test_gemma_assessor.py`.
  - Implements REST payload creation, thought part skipping, balanced JSON parser, 1-shot retry logic, and quote verification binding.

- **Agent 04 — Flask API & Web Interface**:
  - Owns: `app.py`, `templates/index.html`, `static/css/styles.css`, `static/js/app.js`, `tests/test_app.py`.
  - Implements Flask endpoints (`/`, `/api/health`, `/api/assess`) and rich maintainer dashboard UI.

---

## 4. Assessment Contract (`services/assessment_schema.py`)

Every assessment returned by Gemma 4 must satisfy this schema:

```json
{
  "summary": "Clear, objective 1-2 sentence description of PR changes.",
  "recommendation": "review",
  "priority_score": 3,
  "confidence": "high",
  "evidence": [
    {
      "claim": "Catches timeout exceptions cleanly",
      "source": "diff",
      "quote": "except TimeoutError:",
      "verified": true
    }
  ],
  "missing_context": [
    "Unit test for connection retry logic"
  ],
  "suggested_response": "Thank you for the contribution! Could you please add a unit test covering the timeout condition?",
  "uncertainty_reason": ""
}
```

### Allowed Values
- `recommendation`: `"review"` | `"needs_work"` | `"low_effort"` | `"potentially_irrelevant_or_suspicious"` | `"insufficient_evidence"`
- `priority_score`: Integer `1` to `5` (1 = trivial/cosmetic, 5 = critical bug/security/breakage)
- `confidence`: `"low"` | `"medium"` | `"high"`
- `evidence`: List of objects, each containing:
  - `claim` (string)
  - `source` (string, e.g. `"diff"`, `"body"`, `"title"`, `"comments"`)
  - `quote` (string, exact excerpt)
  - `verified` (boolean, must be calculated in code via `verify_quote`)
- `missing_context`: List of strings
- `suggested_response`: String (draft for maintainer to edit/copy)
- `uncertainty_reason`: String (explains why confidence is low or medium)

---

## 5. Development & Run Commands (Windows PowerShell)

Ensure you run these commands in the project root directory with PowerShell:

### Environment Setup
```powershell
# 1. Activate the virtual environment
.\.venv\Scripts\Activate.ps1

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment variables
Copy-Item .env.example .env
# Edit .env with your GEMINI_API_KEY
```

### Running the Application
```powershell
# Start the Flask development server
python app.py

# Alternatively, using Flask CLI:
$env:FLASK_APP = "app.py"
$env:FLASK_DEBUG = "1"
flask run
```

### Running Tests
```powershell
# Run the complete test suite
pytest

# Run tests with verbose output
pytest -v

# Run a specific test module
pytest tests/test_assessment_schema.py
```
