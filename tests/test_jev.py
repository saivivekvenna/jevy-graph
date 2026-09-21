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
    def test_builds_four_atomic_questions_per_candidate(self) -> None:
        request = build_request([candidate()])
        self.assertEqual(
            set(request["questions"]),
            {"c0_support", "c0_direction", "c0_factual", "c0_entities"},
        )

    def test_parses_probabilities(self) -> None:
        response = {
            "answers": {
                "c0_support": {"type": "noul", "noul": 0.95},
                "c0_direction": {"type": "noul", "noul": 0.93},
                "c0_factual": {"type": "noul", "noul": 0.9},
                "c0_entities": {"type": "noul", "noul": 0.92},
            }
        }
        result = parse_answers([candidate()], response)
        self.assertEqual(result[0].support, 0.95)
        self.assertEqual(result[0].direction, 0.93)
        self.assertEqual(result[0].factuality, 0.9)
        self.assertEqual(result[0].entity_quality, 0.92)

    def test_builds_resolution_choices(self) -> None:
        request = build_resolution_request([frame()])
        self.assertEqual(set(request["questions"]), {"f0_triple"})
        criteria = request["questions"]["f0_triple"]["criteria"]
        self.assertTrue(
            any(
                option.get("subject") == "Congress"
                and option.get("predicate") == "authorized_to"
                and option.get("object") == "lay and collect Taxes"
                for option in criteria.values()
                if isinstance(option, dict)
            )
        )

    def test_parses_resolved_components(self) -> None:
        request = build_resolution_request([frame()])
        criteria = request["questions"]["f0_triple"]["criteria"]
        choice = next(
            key
            for key, option in criteria.items()
            if isinstance(option, dict)
            and option.get("subject") == "Congress"
            and option.get("predicate") == "authorized_to"
            and option.get("object") == "lay and collect Taxes"
        )
        response = {
            "answers": {
                "f0_triple": {
                    "type": "choice",
                    "choice": choice,
                    "confidence": 0.8,
                    "probabilities": {choice: 0.6},
                }
            }
        }
        result = parse_resolution_answers([frame()], response)
        self.assertEqual(
            (result[0].subject, result[0].predicate, result[0].object),
            ("Congress", "authorized_to", "lay and collect Taxes"),
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
                "f0_triple": {
                    "choice": "t0",
                    "confidence": 0.9,
                    "probabilities": {"t0": 0.9},
                },
            }
        }
        result = parse_resolution_answers([custom_frame], response)
        self.assertEqual(result[0].object, "lay and collect Taxes")

    def test_canonicalizes_selected_entity_labels(self) -> None:
        custom_frame = RelationFrame(
            ("The Congress",),
            ("has",),
            ("the sole authority",),
            "The Congress has the sole authority.",
            "The Congress has the sole authority.",
            0,
            0,
            36,
        )
        response = {
            "answers": {
                "f0_triple": {
                    "choice": "t0",
                    "confidence": 0.9,
                    "probabilities": {"t0": 0.9},
                },
            }
        }
        result = parse_resolution_answers([custom_frame], response)
        self.assertEqual(
            (result[0].subject, result[0].object), ("Congress", "sole authority")
        )

    def test_normalizes_used_with_complement(self) -> None:
        custom_frame = RelationFrame(
            ("Attention mechanisms",),
            ("used_with",),
            ("in conjunction with recurrent networks",),
            "Attention mechanisms are used in conjunction with recurrent networks.",
            "Attention mechanisms are used in conjunction with recurrent networks.",
            0,
            0,
            70,
        )
        response = {
            "answers": {
                "f0_triple": {
                    "choice": "t0",
                    "confidence": 0.9,
                    "probabilities": {"t0": 0.9},
                },
            }
        }
        result = parse_resolution_answers([custom_frame], response)
        self.assertEqual(result[0].object, "recurrent networks")

    def test_rejects_low_confidence_resolution(self) -> None:
        response = {
            "answers": {
                "f0_triple": {
                    "choice": "t0",
                    "confidence": 0.1,
                    "probabilities": {"t0": 0.2},
                }
            }
        }
        self.assertEqual(
            parse_resolution_answers([frame()], response, minimum_confidence=0.25),
            [],
        )


if __name__ == "__main__":
    unittest.main()
