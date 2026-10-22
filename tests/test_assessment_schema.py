"""Unit tests for services.assessment_schema."""

import unittest
from services.assessment_schema import (
    Assessment,
    AssessmentValidationError,
    EvidenceItem,
    validate_assessment,
    verify_evidence_quotes,
    verify_quote,
)


class TestAssessmentSchema(unittest.TestCase):
    def setUp(self):
        self.valid_data = {
            "summary": "Fixes connection timeout by introducing an explicit timeout parameter.",
            "recommendation": "review",
            "priority_score": 3,
            "confidence": "high",
            "evidence": [
                {
                    "claim": "Sets socket timeout to 30s",
                    "source": "diff",
                    "quote": "sock.settimeout(30)",
                    "verified": True,
                }
            ],
            "missing_context": ["Unit test for socket timeout exception handling"],
            "suggested_response": "Thanks for fixing the socket timeout! Please add a test.",
            "uncertainty_reason": "",
        }

    def test_valid_assessment_passes(self):
        validated = validate_assessment(self.valid_data)
        self.assertEqual(validated["summary"], self.valid_data["summary"])
        self.assertEqual(validated["recommendation"], "review")
        self.assertEqual(validated["priority_score"], 3)
        self.assertEqual(validated["confidence"], "high")
        self.assertEqual(len(validated["evidence"]), 1)
        self.assertTrue(validated["evidence"][0]["verified"])

    def test_missing_required_keys(self):
        incomplete = dict(self.valid_data)
        del incomplete["recommendation"]
        with self.assertRaises(AssessmentValidationError) as ctx:
            validate_assessment(incomplete)
        self.assertIn("Missing required assessment keys", str(ctx.exception))

    def test_invalid_recommendation(self):
        bad_data = dict(self.valid_data, recommendation="instant_merge")
        with self.assertRaises(AssessmentValidationError) as ctx:
            validate_assessment(bad_data)
        self.assertIn("Invalid recommendation", str(ctx.exception))

    def test_invalid_priority_score_range(self):
        for bad_score in (0, 6, -1, 10):
            with self.subTest(score=bad_score):
                bad_data = dict(self.valid_data, priority_score=bad_score)
                with self.assertRaises(AssessmentValidationError):
                    validate_assessment(bad_data)

    def test_invalid_priority_score_type(self):
        for bad_score in (True, False, "3", 3.5, None):
            with self.subTest(score=bad_score):
                bad_data = dict(self.valid_data, priority_score=bad_score)
                with self.assertRaises(AssessmentValidationError):
                    validate_assessment(bad_data)

    def test_invalid_confidence(self):
        bad_data = dict(self.valid_data, confidence="very_high")
        with self.assertRaises(AssessmentValidationError) as ctx:
            validate_assessment(bad_data)
        self.assertIn("Invalid confidence", str(ctx.exception))

    def test_malformed_evidence_items(self):
        # Missing quote field
        bad_data = dict(self.valid_data, evidence=[{"claim": "test", "source": "diff"}])
        with self.assertRaises(AssessmentValidationError):
            validate_assessment(bad_data)

        # Evidence item not a dict
        bad_data2 = dict(self.valid_data, evidence=["not a dict"])
        with self.assertRaises(AssessmentValidationError):
            validate_assessment(bad_data2)


class TestQuoteVerification(unittest.TestCase):
    def setUp(self):
        self.source_diff = (
            "--- a/socket.py\n"
            "+++ b/socket.py\n"
            "@@ -10,3 +10,4 @@\n"
            " def connect():\n"
            "+    sock.settimeout(30)\n"
            "     return sock\n"
        )
        self.corpus = {
            "title": "Fix socket timeout handling",
            "body": "This PR adds explicit socket timeout to avoid hanging connections.",
            "diff": self.source_diff,
        }

    def test_verify_quote_exact_substring(self):
        self.assertTrue(verify_quote("sock.settimeout(30)", self.source_diff))
        self.assertTrue(verify_quote("hanging connections", self.corpus["body"]))

    def test_verify_quote_whitespace_normalized(self):
        quote_with_newlines = "def connect():\n        sock.settimeout(30)"
        self.assertTrue(verify_quote(quote_with_newlines, self.source_diff, exact=False))

    def test_verify_quote_rejects_hallucinations(self):
        self.assertFalse(verify_quote("completely fabricated quote", self.source_diff))
        self.assertFalse(verify_quote("", self.source_diff))
        self.assertFalse(verify_quote("sock.settimeout(30)", ""))

    def test_verify_evidence_quotes_batch(self):
        evidence_list = [
            {
                "claim": "Sets socket timeout to 30",
                "source": "diff",
                "quote": "sock.settimeout(30)",
                "verified": False,
            },
            {
                "claim": "Claim with hallucinated quote",
                "source": "diff",
                "quote": "sock.connect_with_retry(5)",
                "verified": True,  # Model mistakenly claimed verified
            },
            {
                "claim": "Explains motivation in body",
                "source": "body",
                "quote": "avoid hanging connections",
                "verified": False,
            },
        ]

        verified = verify_evidence_quotes(evidence_list, self.corpus)

        self.assertTrue(verified[0]["verified"])
        self.assertFalse(verified[1]["verified"], "Hallucinated quote must be flagged as unverified")
        self.assertTrue(verified[2]["verified"])


if __name__ == "__main__":
    unittest.main()
