"""Assessment Contract and Validation for Sift.

Defines the structured schema for PR triage assessments produced by Gemma 4,
along with strict validation and in-code quote verification logic.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal, TypedDict

# Contract Constants
VALID_RECOMMENDATIONS = (
    "review",
    "needs_work",
    "low_effort",
    "potentially_irrelevant_or_suspicious",
    "insufficient_evidence",
)

VALID_CONFIDENCE_LEVELS = (
    "low",
    "medium",
    "high",
)

PRIORITY_MIN = 1
PRIORITY_MAX = 5

REQUIRED_ASSESSMENT_KEYS = (
    "summary",
    "recommendation",
    "priority_score",
    "confidence",
    "evidence",
    "missing_context",
    "suggested_response",
    "uncertainty_reason",
)

RecommendationType = Literal[
    "review",
    "needs_work",
    "low_effort",
    "potentially_irrelevant_or_suspicious",
    "insufficient_evidence",
]

ConfidenceType = Literal["low", "medium", "high"]


class EvidenceDict(TypedDict):
    claim: str
    source: str
    quote: str
    verified: bool


class AssessmentDict(TypedDict):
    summary: str
    recommendation: RecommendationType
    priority_score: int
    confidence: ConfidenceType
    evidence: list[EvidenceDict]
    missing_context: list[str]
    suggested_response: str
    uncertainty_reason: str


class AssessmentValidationError(ValueError):
    """Raised when an assessment dictionary violates the schema contract."""
    pass


@dataclass
class EvidenceItem:
    claim: str
    source: str
    quote: str
    verified: bool = False

    def to_dict(self) -> EvidenceDict:
        return {
            "claim": self.claim,
            "source": self.source,
            "quote": self.quote,
            "verified": self.verified,
        }


@dataclass
class Assessment:
    summary: str
    recommendation: RecommendationType
    priority_score: int
    confidence: ConfidenceType
    evidence: list[EvidenceItem] = field(default_factory=list)
    missing_context: list[str] = field(default_factory=list)
    suggested_response: str = ""
    uncertainty_reason: str = ""

    def to_dict(self) -> AssessmentDict:
        return {
            "summary": self.summary,
            "recommendation": self.recommendation,
            "priority_score": self.priority_score,
            "confidence": self.confidence,
            "evidence": [e.to_dict() for e in self.evidence],
            "missing_context": list(self.missing_context),
            "suggested_response": self.suggested_response,
            "uncertainty_reason": self.uncertainty_reason,
        }


def _normalize_whitespace(text: str) -> str:
    """Collapses consecutive whitespace to simplify robust substring matching."""
    return re.sub(r"\s+", " ", text).strip()


def _strip_diff_markers(text: str) -> str:
    """Strips leading git diff markers (+, -, space) from lines."""
    return "\n".join(re.sub(r"^[+\- ]", "", line) for line in text.splitlines())


def verify_quote(quote: str, source_text: str, exact: bool = False) -> bool:
    """Verifies that a quote appears as a genuine substring in source_text.

    Invariant: Unverified quotes are NEVER shown as facts.

    Args:
        quote: The quoted text claimed by the model.
        source_text: The authentic retrieved content (e.g. diff, body, comment).
        exact: If True, only exact substring match succeeds.
               If False, exact match is tried first, followed by whitespace-normalized
               and diff-marker-stripped matching (tolerating git diff prefix variations).

    Returns:
        bool: True if quote is verified as a substring, False otherwise.
    """
    if not quote or not source_text:
        return False

    # 1. Exact substring check
    if quote in source_text:
        return True

    if exact:
        return False

    # 2. Whitespace-normalized check
    norm_quote = _normalize_whitespace(quote)
    if not norm_quote:
        return False

    norm_source = _normalize_whitespace(source_text)
    if norm_quote in norm_source:
        return True

    # 3. Diff-stripped matching (handles git diff '+' and '-' line prefixes)
    stripped_source = _strip_diff_markers(source_text)
    if quote in stripped_source:
        return True

    norm_stripped_source = _normalize_whitespace(stripped_source)
    if norm_quote in norm_stripped_source:
        return True

    # Also handle if quote itself included diff markers
    stripped_quote = _strip_diff_markers(quote)
    norm_stripped_quote = _normalize_whitespace(stripped_quote)
    if norm_stripped_quote and norm_stripped_quote in norm_stripped_source:
        return True

    return False



def verify_evidence_quotes(
    evidence_items: list[dict[str, Any] | EvidenceItem],
    source_corpus: dict[str, str],
) -> list[dict[str, Any]]:
    """Verifies every quote in evidence_items against source_corpus in code.

    Args:
        evidence_items: List of evidence dictionaries or EvidenceItem instances.
        source_corpus: Dict mapping source names (e.g. 'diff', 'body', 'title')
                       to the authentic retrieved text strings.
                       A special key 'all' or fallback across all texts is supported.

    Returns:
        List of evidence dicts with the 'verified' boolean accurately set.
    """
    verified_items: list[dict[str, Any]] = []

    # Combined corpus fallback
    combined_corpus = "\n\n".join(str(v) for v in source_corpus.values() if v)

    for item in evidence_items:
        data: dict[str, Any] = item.to_dict() if isinstance(item, EvidenceItem) else dict(item)
        quote = str(data.get("quote", "")).strip()
        source = str(data.get("source", "")).strip().lower()

        is_verified = False
        if quote:
            # Check designated source first if available
            target_source = source_corpus.get(source)
            if target_source and verify_quote(quote, target_source):
                is_verified = True
            elif verify_quote(quote, combined_corpus):
                # Quote found in the overall retrieved corpus
                is_verified = True

        data["verified"] = is_verified
        verified_items.append(data)

    return verified_items


def validate_assessment(data: Any) -> AssessmentDict:
    """Validates an assessment data structure against the Sift schema contract.

    Args:
        data: Raw dictionary or object to validate.

    Returns:
        AssessmentDict: Clean, validated dictionary strictly adhering to the contract.

    Raises:
        AssessmentValidationError: If any required key is missing, types are wrong,
                                  or constraints are violated.
    """
    if not isinstance(data, dict):
        raise AssessmentValidationError(f"Assessment must be a dict, got {type(data).__name__}")

    # Check presence of required keys
    missing_keys = [key for key in REQUIRED_ASSESSMENT_KEYS if key not in data]
    if missing_keys:
        raise AssessmentValidationError(f"Missing required assessment keys: {missing_keys}")

    # 1. Summary
    summary = data.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise AssessmentValidationError("Field 'summary' must be a non-empty string")
    clean_summary = summary.strip()

    # 2. Recommendation
    recommendation = data.get("recommendation")
    if recommendation not in VALID_RECOMMENDATIONS:
        raise AssessmentValidationError(
            f"Invalid recommendation '{recommendation}'. Must be one of: {list(VALID_RECOMMENDATIONS)}"
        )

    # 3. Priority Score
    priority_score = data.get("priority_score")
    if isinstance(priority_score, bool) or not isinstance(priority_score, int):
        raise AssessmentValidationError(
            f"Field 'priority_score' must be an integer between {PRIORITY_MIN} and {PRIORITY_MAX}"
        )
    if not (PRIORITY_MIN <= priority_score <= PRIORITY_MAX):
        raise AssessmentValidationError(
            f"Field 'priority_score' must be between {PRIORITY_MIN} and {PRIORITY_MAX}, got {priority_score}"
        )

    # 4. Confidence
    confidence = data.get("confidence")
    if confidence not in VALID_CONFIDENCE_LEVELS:
        raise AssessmentValidationError(
            f"Invalid confidence '{confidence}'. Must be one of: {list(VALID_CONFIDENCE_LEVELS)}"
        )

    # 5. Evidence list
    raw_evidence = data.get("evidence")
    if not isinstance(raw_evidence, list):
        raise AssessmentValidationError("Field 'evidence' must be a list of evidence objects")

    validated_evidence: list[EvidenceDict] = []
    for idx, item in enumerate(raw_evidence):
        if not isinstance(item, dict):
            raise AssessmentValidationError(f"Evidence item at index {idx} must be a dict")

        for req_prop in ("claim", "source", "quote"):
            if req_prop not in item:
                raise AssessmentValidationError(
                    f"Evidence item at index {idx} missing required field '{req_prop}'"
                )
            if not isinstance(item[req_prop], str):
                raise AssessmentValidationError(
                    f"Evidence item at index {idx} field '{req_prop}' must be a string"
                )

        verified = bool(item.get("verified", False))

        validated_evidence.append({
            "claim": str(item["claim"]).strip(),
            "source": str(item["source"]).strip(),
            "quote": str(item["quote"]).strip(),
            "verified": verified,
        })

    # 6. Missing Context
    raw_missing = data.get("missing_context")
    if not isinstance(raw_missing, list):
        raise AssessmentValidationError("Field 'missing_context' must be a list of strings")

    validated_missing: list[str] = []
    for idx, ctx in enumerate(raw_missing):
        if not isinstance(ctx, str):
            raise AssessmentValidationError(f"missing_context item at index {idx} must be a string")
        validated_missing.append(ctx.strip())

    # 7. Suggested Response
    suggested_response = data.get("suggested_response")
    if not isinstance(suggested_response, str):
        raise AssessmentValidationError("Field 'suggested_response' must be a string")
    clean_suggested_response = suggested_response.strip()

    # 8. Uncertainty Reason
    uncertainty_reason = data.get("uncertainty_reason")
    if uncertainty_reason is None:
        clean_uncertainty = ""
    elif isinstance(uncertainty_reason, str):
        clean_uncertainty = uncertainty_reason.strip()
    else:
        raise AssessmentValidationError("Field 'uncertainty_reason' must be a string or None")

    return {
        "summary": clean_summary,
        "recommendation": recommendation,  # type: ignore[return-value]
        "priority_score": priority_score,
        "confidence": confidence,  # type: ignore[return-value]
        "evidence": validated_evidence,
        "missing_context": validated_missing,
        "suggested_response": clean_suggested_response,
        "uncertainty_reason": clean_uncertainty,
    }
