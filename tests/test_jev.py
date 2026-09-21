from __future__ import annotations

import unittest

from jevy_graph.jev import (
    build_request,
    build_resolution_request,
    parse_answers,
    parse_resolution_answers,
)
from jevy_graph.models import CandidateTriple, RelationFrame


def candidate() -> CandidateTriple:
    return CandidateTriple("Alice", "founded", "Acme", "Alice founded Acme.", 0, 0, 19)


def frame() -> RelationFrame:
    return RelationFrame(
        ("Congress", "Congress shall"),
        ("has", "authorized_to"),
        ("Power", "lay and collect Taxes"),
        "Congress shall have Power to lay and collect Taxes.",
        "Congress shall have Power to lay and collect Taxes.",
        0,
        0,
        53,
    )


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

    def test_builds_resolution_choices(self) -> None:
        request = build_resolution_request([frame()])
        self.assertEqual(
            set(request["questions"]),
            {"f0_subject", "f0_predicate", "f0_object"},
        )

    def test_parses_resolved_components(self) -> None:
        response = {
            "answers": {
                "f0_subject": {"type": "choice", "choice": "s0"},
                "f0_predicate": {"type": "choice", "choice": "p1"},
                "f0_object": {"type": "choice", "choice": "o0"},
            }
        }
        result = parse_resolution_answers([frame()], response)
        self.assertEqual(
            (result[0].subject, result[0].predicate, result[0].object),
            ("Congress", "authorized_to", "Power"),
        )

    def test_normalizes_power_to_for_authorization(self) -> None:
        custom_frame = RelationFrame(
            ("Congress",),
            ("authorized_to",),
            ("Power to lay and collect Taxes",),
            "Congress shall have Power to lay and collect Taxes.",
            "Congress shall have Power to lay and collect Taxes.",
            0,
            0,
            53,
        )
        response = {
            "answers": {
                "f0_subject": {"choice": "s0"},
                "f0_predicate": {"choice": "p0"},
                "f0_object": {"choice": "o0"},
            }
        }
        result = parse_resolution_answers([custom_frame], response)
        self.assertEqual(result[0].object, "lay and collect Taxes")


if __name__ == "__main__":
    unittest.main()
