import json
import unittest
from unittest.mock import patch

from ai import AIError, rank_with_gemini, validate_reply
from location import SAMPLE_AREA
from models import AnalysisRequest
from recommendations import build_candidates
from test_analysis import weather


class AIValidationTests(unittest.TestCase):
    def setUp(self):
        self.request = AnalysisRequest(SAMPLE_AREA, "wheat", "Vegetative")
        self.evidence, self.candidates = build_candidates(self.request, weather(), None)

    def test_valid_ranking_uses_verified_evidence(self):
        candidate = self.candidates[0]
        raw = json.dumps({"recommendations": [{"action_id": candidate.id,
                                                "evidence_ids": list(candidate.evidence_ids)}]})
        selected = validate_reply(raw, self.evidence, self.candidates)
        self.assertEqual(selected[0].candidate, candidate)
        self.assertEqual({item.id for item in selected[0].evidence}, set(candidate.evidence_ids))

    def test_malformed_unknown_and_missing_evidence_are_rejected(self):
        candidate = self.candidates[0]
        invalid = [
            "not json",
            json.dumps({"recommendations": [{"action_id": "invented", "evidence_ids": ["rain_total"]}]}),
            json.dumps({"recommendations": [{"action_id": candidate.id, "evidence_ids": ["invented"]}]}),
            json.dumps({"recommendations": [{"action_id": candidate.id, "evidence_ids": []}]}),
            json.dumps({"recommendations": [{"action_id": candidate.id,
                                              "evidence_ids": list(candidate.evidence_ids),
                                              "invented_measurement": "soil is dry"}]}),
        ]
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(AIError):
                validate_reply(raw, self.evidence, self.candidates)

    def test_sdk_call_uses_structured_output_and_validates_selection(self):
        candidate = self.candidates[0]
        raw = json.dumps({"recommendations": [{"action_id": candidate.id,
                                                "evidence_ids": list(candidate.evidence_ids)}]})
        with patch("ai.genai.Client") as client_class:
            client = client_class.return_value.__enter__.return_value
            client.models.generate_content.return_value.text = raw
            selected = rank_with_gemini(self.request, self.evidence, self.candidates,
                                        api_key="test-key")
        self.assertEqual(selected[0].candidate.id, candidate.id)
        client.models.generate_content.assert_called_once()
        call = client.models.generate_content.call_args
        self.assertEqual(call.kwargs["config"].response_mime_type, "application/json")
        self.assertEqual(call.kwargs["model"], "gemini-flash-latest")


if __name__ == "__main__":
    unittest.main()
