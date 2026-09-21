from __future__ import annotations

import unittest

from jevy_graph.jev import build_request, parse_answers
from jevy_graph.models import CandidateTriple


def candidate() -> CandidateTriple:
    return CandidateTriple("Alice", "founded", "Acme", "Alice founded Acme.", 0, 0, 19)


class JevTests(unittest.TestCase):
    def test_builds_two_atomic_questions_per_candidate(self) -> None:
        request = build_request([candidate()])
        self.assertEqual(set(request["questions"]), {"c0_support", "c0_factual"})

    def test_parses_probabilities(self) -> None:
        response = {
            "answers": {
                "c0_support": {"type": "noul", "noul": 0.95},
                "c0_factual": {"type": "noul", "noul": 0.9},
            }
        }
        result = parse_answers([candidate()], response)
        self.assertEqual(result[0].support, 0.95)
        self.assertEqual(result[0].factuality, 0.9)


if __name__ == "__main__":
    unittest.main()

