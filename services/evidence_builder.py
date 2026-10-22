"""Evidence Packet Builder for Sift.

Assigned to: Agent 02 (Evidence & GitHub Engine)

Locked Invariants & Responsibilities:
- Zero contributor-quality bias: first-time contributors and documentation PRs are NEVER penalized.
- Never alter, modify, or paraphrase authentic retrieved text; never invent data.
- Synthesize PR facts, changed files, unified diff, contribution guidance, and comments.
- Provable linked-issue detection: "Fixes #12" is provable, otherwise "unknown".
- Build structured sources list with {id, label, url, text} where text is the exact retrieved text.
- Build source_corpus dictionary for fast and exact in-code substring quote verification.
"""

from __future__ import annotations

import re
from typing import Any, Optional
from services.assessment_schema import verify_quote

# Regular expression for GitHub closing issue keywords (Fixes #12, Closes #34, Resolves #56)
LINKED_ISSUE_PATTERN = re.compile(
    r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+(?:(?:[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)?#|https?://github\.com/[^/\s]+/[^/\s]+/issues/)(\d+)\b"
)


def detect_linked_issue_signal(
    body: Optional[str],
    title: Optional[str] = None,
) -> tuple[str, list[str]]:
    """Detects provable linked issue closing signals in PR body or title.

    Only signals that provably link and close an issue (e.g. 'Fixes #12',
    'Closes #34', 'Resolves #56') are marked as provable. Ambiguous or missing
    references return 'unknown'.

    Args:
        body: Pull request description body text.
        title: Optional pull request title text.

    Returns:
        tuple[str, list[str]]: (primary_signal_string, list_of_all_detected_signals)
    """
    corpus = ""
    if body:
        corpus += body + "\n"
    if title:
        corpus += title

    if not corpus.strip():
        return "unknown", []

    matches: list[str] = []
    for match in LINKED_ISSUE_PATTERN.finditer(corpus):
        matched_text = match.group(0).strip()
        if matched_text not in matches:
            matches.append(matched_text)

    if not matches:
        return "unknown", []

    primary_signal = ", ".join(matches)
    return primary_signal, matches


def build_evidence_packet(
    pr_details: dict[str, Any],
    pr_diff: str = "",
    pr_comments: Optional[list[dict[str, Any]]] = None,
    max_diff_lines: int = 1500,
    pr_files: Optional[list[dict[str, Any]]] = None,
    contributing_guidance: Optional[dict[str, Any] | str] = None,
    max_diff_chars: int = 20000,
    max_guidance_chars: int = 3000,
) -> dict[str, Any]:
    """Assembles retrieved GitHub data into a structured evidence packet for assessment.

    Locked Invariant:
        Every text in `sources` and `source_corpus` is the exact retrieved text.
        Quotes are later verified by substring match against it.
        Never alter, sanitize, or paraphrase source text.

    Args:
        pr_details: Metadata dictionary from fetch_pr_details or fetch_open_prs.
        pr_diff: Raw unified diff string from fetch_pr_diff.
        pr_comments: Optional list of comments from fetch_pr_comments.
        max_diff_lines: Maximum number of diff lines for prepared_diff prompt context.
        pr_files: Optional list of per-file patch dictionaries from fetch_pr_files.
        contributing_guidance: Optional guidance dict from fetch_contributing_guidance
                               or raw markdown string.
        max_diff_chars: Maximum characters of diff text (default 20,000).
        max_guidance_chars: Maximum characters of contributing text (default 3,000).

    Returns:
        dict: Standardized evidence packet containing:
            - "pr_facts": Key factual properties (title, author, numbers, signals)
            - "pr_info": Backward-compatible alias to pr_facts
            - "sources": List of {id, label, url, text} with authentic unedited text
            - "source_corpus": Dict[str, str] mapping source IDs to authentic text
            - "diff_summary": Line and file counts, truncation indicator
            - "prepared_diff": Diff context bounded by max_diff_lines and max_diff_chars
            - "comments_summary": Formatted comments overview
            - "linked_issue_signal": Provable signal or "unknown"
            - "contributing_guidance": Guidance information and presence status

    Raises:
        ValueError: If pr_details is empty or missing required identifying keys.
    """
    if not isinstance(pr_details, dict) or not pr_details:
        raise ValueError("pr_details must be a non-empty dictionary containing PR metadata")

    # Core identification
    owner = str(pr_details.get("owner") or "")
    repo = str(pr_details.get("repo") or "")
    number = int(pr_details.get("number") or 0)
    html_url = str(pr_details.get("html_url") or f"https://github.com/{owner}/{repo}/pull/{number}")

    # Extract exact authentic texts
    title_text = str(pr_details.get("title") or "")
    body_text = str(pr_details.get("body") or "")
    diff_text = str(pr_diff or "")
    comments = list(pr_comments) if pr_comments else []

    # Cap per-file patches (e.g. 4000 chars per file patch)
    files: list[dict[str, Any]] = []
    if pr_files:
        per_file_char_limit = 4000
        for f in pr_files:
            f_item = dict(f)
            patch = f_item.get("patch")
            if isinstance(patch, str) and len(patch) > per_file_char_limit:
                f_item["patch"] = (
                    patch[:per_file_char_limit]
                    + f"\n[Patch truncated: exceeded {per_file_char_limit} characters]"
                )
                f_item["truncated"] = True
            files.append(f_item)

    # Parse contributing guidance and cap to max_guidance_chars (3,000 chars)
    guidance_status = "unavailable"
    guidance_path: Optional[str] = None
    guidance_text = ""
    if isinstance(contributing_guidance, dict):
        guidance_status = contributing_guidance.get("status", "unavailable")
        guidance_path = contributing_guidance.get("path")
        guidance_text = str(contributing_guidance.get("text") or "")
    elif isinstance(contributing_guidance, str) and contributing_guidance.strip():
        guidance_status = "present"
        guidance_path = "CONTRIBUTING.md"
        guidance_text = contributing_guidance

    if len(guidance_text) > max_guidance_chars:
        guidance_text = (
            guidance_text[:max_guidance_chars]
            + f"\n\n[CONTRIBUTING guidance truncated to {max_guidance_chars} characters]"
        )

    # Provable linked-issue detection
    linked_signal, detected_signals = detect_linked_issue_signal(body=body_text, title=title_text)

    # Invariant: Zero contributor quality bias. Maintain factually without penalties.
    author_association = str(pr_details.get("author_association") or "NONE")
    is_first_time = author_association.upper() == "FIRST_TIME_CONTRIBUTOR"

    # Assemble PR Facts
    pr_facts: dict[str, Any] = {
        "owner": owner,
        "repo": repo,
        "number": number,
        "title": title_text,
        "body": body_text,
        "author": str(pr_details.get("author") or ""),
        "author_association": author_association,
        "first_time_contributor": is_first_time,
        "state": str(pr_details.get("state") or "open"),
        "draft": bool(pr_details.get("draft", False)),
        "created_at": str(pr_details.get("created_at") or ""),
        "updated_at": str(pr_details.get("updated_at") or ""),
        "additions": int(pr_details.get("additions", 0)),
        "deletions": int(pr_details.get("deletions", 0)),
        "changed_files": int(pr_details.get("changed_files", len(files))),
        "base_branch": str(pr_details.get("base_branch") or ""),
        "head_branch": str(pr_details.get("head_branch") or ""),
        "html_url": html_url,
        "labels": list(pr_details.get("labels") or []),
        "linked_issue_signal": linked_signal,
        "linked_issues": detected_signals,
        "contributing_guidance_status": guidance_status,
        "contributing_guidance_path": guidance_path,
    }

    # Assemble Sources list ({id, label, url, text}) with EXACT retrieved text
    sources: list[dict[str, str]] = []

    # 1. Title source
    if title_text:
        sources.append({
            "id": "title",
            "label": "PR Title",
            "url": html_url,
            "text": title_text,
        })

    # 2. Body source
    if body_text:
        sources.append({
            "id": "body",
            "label": "PR Body",
            "url": html_url,
            "text": body_text,
        })

    # 3. Guidance source (if present)
    if guidance_status == "present" and guidance_text:
        guidance_label = f"Contribution Guidance ({guidance_path})" if guidance_path else "Contribution Guidance"
        guidance_url = (
            f"https://github.com/{owner}/{repo}/blob/HEAD/{guidance_path}"
            if owner and repo and guidance_path
            else html_url
        )
        sources.append({
            "id": "guidance",
            "label": guidance_label,
            "url": guidance_url,
            "text": guidance_text,
        })

    # 4. Unified diff source
    if diff_text:
        sources.append({
            "id": "diff",
            "label": "Unified Diff",
            "url": f"{html_url}.diff",
            "text": diff_text,
        })

    # 5. File patch sources
    for f in files:
        fname = f.get("filename", "")
        fpatch = f.get("patch")
        if fname and fpatch:
            sources.append({
                "id": f"patch:{fname}",
                "label": f"Patch: {fname}",
                "url": f.get("blob_url") or html_url,
                "text": fpatch,
            })

    # 6. Comments sources
    for c in comments:
        cid = str(c.get("id") or "")
        cbody = str(c.get("body") or "")
        cauthor = str(c.get("author") or "user")
        if cbody:
            sources.append({
                "id": f"comment:{cid}" if cid else "comment",
                "label": f"Comment by @{cauthor}",
                "url": str(c.get("html_url") or html_url),
                "text": cbody,
            })

    # Assemble source_corpus for in-code substring quote verification
    source_corpus: dict[str, str] = {
        "title": title_text,
        "body": body_text,
        "diff": diff_text,
    }

    if guidance_text:
        source_corpus["guidance"] = guidance_text

    if comments:
        source_corpus["comments"] = "\n\n".join(
            str(c.get("body") or "") for c in comments if c.get("body")
        )

    for f in files:
        fname = f.get("filename")
        fpatch = f.get("patch")
        if fname and fpatch:
            source_corpus[f"patch:{fname}"] = fpatch
            source_corpus[fname] = fpatch

    for c in comments:
        cid = str(c.get("id") or "")
        cbody = str(c.get("body") or "")
        if cid and cbody:
            source_corpus[f"comment:{cid}"] = cbody

    # Diff summary and prompt preparation
    diff_lines = diff_text.splitlines()
    total_diff_lines = len(diff_lines)
    total_diff_chars = len(diff_text)
    is_line_truncated = total_diff_lines > max_diff_lines
    is_char_truncated = total_diff_chars > max_diff_chars
    is_diff_truncated = is_line_truncated or is_char_truncated

    if is_diff_truncated:
        if is_line_truncated:
            kept_lines = diff_lines[:max_diff_lines]
            candidate_diff = "\n".join(kept_lines)
        else:
            candidate_diff = diff_text

        if len(candidate_diff) > max_diff_chars:
            prepared_diff = (
                candidate_diff[:max_diff_chars]
                + f"\n\n[Diff truncated: exceeded {max_diff_chars} characters limit.]"
            )
        else:
            prepared_diff = (
                candidate_diff
                + f"\n\n[Diff truncated: showing first {max_diff_lines} lines of {total_diff_lines} total lines.]"
            )
    else:
        prepared_diff = diff_text

    diff_summary = {
        "total_lines": total_diff_lines,
        "total_chars": total_diff_chars,
        "additions": pr_facts["additions"],
        "deletions": pr_facts["deletions"],
        "changed_files": pr_facts["changed_files"],
        "is_truncated": is_diff_truncated,
    }

    # Format comments summary
    comments_summary: list[dict[str, str]] = []
    for c in comments:
        comments_summary.append({
            "author": str(c.get("author") or "user"),
            "created_at": str(c.get("created_at") or ""),
            "body": str(c.get("body") or ""),
        })

    return {
        "pr_facts": pr_facts,
        "pr_info": pr_facts,  # Alias
        "sources": sources,
        "source_corpus": source_corpus,
        "diff_summary": diff_summary,
        "prepared_diff": prepared_diff,
        "comments_summary": comments_summary,
        "linked_issue_signal": linked_signal,
        "contributing_guidance": {
            "status": guidance_status,
            "path": guidance_path,
            "has_guidance": (guidance_status == "present"),
            "text": guidance_text,
        },
    }


def verify_quote_against_packet(
    quote: str,
    source: str,
    evidence_packet: dict[str, Any],
) -> bool:
    """Verifies that a quote exists as an authentic substring in the evidence packet's source corpus.

    Args:
        quote: Claimed excerpt string.
        source: Claimed source identifier (e.g. 'diff', 'body', 'title', 'guidance').
        evidence_packet: Structured evidence packet containing 'source_corpus'.

    Returns:
        bool: True if verified as an authentic substring in the corpus, False otherwise.
    """
    if not quote or not isinstance(quote, str):
        return False

    source_corpus: dict[str, str] = evidence_packet.get("source_corpus") or {}
    clean_source = source.strip().lower()

    # 1. Test against the targeted source first
    target_text = source_corpus.get(clean_source)
    if target_text and verify_quote(quote, target_text):
        return True

    # 2. Test against all combined sources in the packet
    combined_corpus = "\n\n".join(str(v) for v in source_corpus.values() if v)
    return verify_quote(quote, combined_corpus)
