"""Evidence Packet Builder Interface for Sift.

Assigned to: Agent 02 (Evidence & GitHub Engine)

Responsibilities:
- Synthesize raw PR metadata, diff text, and comments into an evidence packet.
- Build the source corpus dictionary for in-code substring quote verification.
- Handle diff truncation safely and factually when limits are exceeded.
- Guarantee that first-time contributors, small PRs, and docs PRs are never penalized.
"""

from __future__ import annotations

from typing import Any, Optional


def build_evidence_packet(
    pr_details: dict[str, Any],
    pr_diff: str,
    pr_comments: Optional[list[dict[str, Any]]] = None,
    max_diff_lines: int = 1500,
) -> dict[str, Any]:
    """Assembles retrieved GitHub data into a structured evidence packet for assessment.

    Args:
        pr_details: Metadata dictionary from fetch_pr_details.
        pr_diff: Raw unified diff string from fetch_pr_diff.
        pr_comments: Optional list of comments from fetch_pr_comments.
        max_diff_lines: Maximum number of diff lines before safe truncation.

    Returns:
        dict: Standardized evidence packet containing:
            - "pr_info": Summary metadata (repo, number, title, author, branch, etc.)
            - "diff_summary": Stats on lines, files, and truncation flag
            - "prepared_diff": Diff string formatted for model prompt
            - "comments_summary": Formatted discussion summary
            - "source_corpus": Dict[str, str] mapping source names
                               ("title", "body", "diff", "comments") to raw authentic strings
                               used for code-level quote verification.

    Raises:
        ValueError: If pr_details or pr_diff is invalid or empty.
    """
    raise NotImplementedError("To be implemented by Agent 02")


def verify_quote_against_packet(
    quote: str,
    source: str,
    evidence_packet: dict[str, Any],
) -> bool:
    """Verifies that a quote exists in the authentic source corpus of the evidence packet.

    Args:
        quote: Claimed quote string.
        source: Claimed source identifier (e.g. 'diff', 'body', 'title').
        evidence_packet: The evidence packet containing 'source_corpus'.

    Returns:
        bool: True if verified as a substring in the corpus, False otherwise.
    """
    raise NotImplementedError("To be implemented by Agent 02")
