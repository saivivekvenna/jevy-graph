from __future__ import annotations

import unittest

from jevy_graph.jev import (
    _triple_options,
    build_choice_request,
    build_verification_request,
    parse_choice_answers,
    parse_verification_answers,
)
from jevy_graph.models import CandidateTriple, RelationFrame


def frame() -> RelationFrame:
    return RelationFrame(
        ("Congress", "Congress shall"),
        ("has", "authorized_to"),
        ("Power", "Power to lay and collect Taxes", "lay and collect Taxes"),
        "Congress shall have Power to lay and collect Taxes.",
        "Congress shall have Power to lay and collect Taxes.",
        0,
        0,
        53,
        "shall",
    )


class JevTests(unittest.TestCase):
    def test_builds_comparative_choice_over_complete_candidates(self) -> None:
        request = build_choice_request([frame()])
        question = request["questions"]["f0_triple"]
        self.assertEqual(question["type"], "choice")
        self.assertNotIn("none", question["criteria"])
        self.assertEqual(question["instructions"]["modality"], "shall")

    def test_parses_selected_complete_triple(self) -> None:
        options = _triple_options(frame())
        target_index = options.index(
            ("Congress", "authorized_to", "lay and collect Taxes")
        )
        choice = f"t{target_index}"
        result = parse_choice_answers(
            [frame()],
            {
                "answers": {
                    "f0_triple": {
                        "choice": choice,
                        "confidence": 0.84,
                        "probabilities": {choice: 0.76},
                    }
                }
            },
        )
        self.assertEqual(
            (result[0].subject, result[0].predicate, result[0].object),
            ("Congress", "authorized_to", "lay and collect Taxes"),
        )
        self.assertEqual(result[0].modality, "shall")
        self.assertEqual(result[0].selection_probability, 0.76)

    def test_rejects_non_candidate_choice(self) -> None:
        with self.assertRaisesRegex(Exception, "invalid choice"):
            parse_choice_answers(
                [frame()],
                {
                    "answers": {
                        "f0_triple": {
                            "choice": "none",
                            "confidence": 0.9,
                            "probabilities": {"none": 0.9},
                        }
                    }
                },
            )

    def test_verification_treats_normative_modality_as_valid(self) -> None:
        candidate = CandidateTriple(
            "Congress",
            "authorized_to",
            "lay Taxes",
            "Congress shall have Power to lay Taxes.",
            0,
            0,
            39,
            modality="shall",
        )
        request = build_verification_request([candidate])
        prompt = request["questions"]["c0_support"]["instructions"]["question"]
        self.assertIn("normative assertion", prompt)
        result = parse_verification_answers(
            [candidate],
            {
                "answers": {
                    "c0_support": {"noul": 0.95},
                    "c0_entities": {"noul": 0.91},
                }
            },
        )
        self.assertEqual(result[0].support, 0.95)
        self.assertEqual(result[0].entity_quality, 0.91)

    def test_normalizes_authorization_candidates(self) -> None:
        options = _triple_options(frame())
        self.assertIn(
            ("Congress", "authorized_to", "lay and collect Taxes"), options
        )
        self.assertFalse(any(predicate == "has" for _, predicate, _ in options))
        self.assertFalse(any(subject.endswith("shall") for subject, _, _ in options))

    def test_normalizes_used_with_candidates(self) -> None:
        custom_frame = RelationFrame(
            ("Attention mechanisms",),
            ("uses", "applies", "used_with"),
            ("in conjunction with recurrent networks", "recurrent networks"),
            "Attention mechanisms are used in conjunction with recurrent networks.",
            "Attention mechanisms are used in conjunction with recurrent networks.",
            0,
            0,
            70,
        )
        self.assertEqual(
            _triple_options(custom_frame),
            (("Attention mechanisms", "used_with", "recurrent networks"),),
        )

    def test_normalizes_passive_use_candidates(self) -> None:
        custom_frame = RelationFrame(
            ("Self-attention has been", "Self-attention"),
            ("uses", "applies", "used_for"),
            ("successfully in reading comprehension", "reading comprehension"),
            "Self-attention has been used successfully in reading comprehension.",
            "Self-attention has been used successfully in reading comprehension.",
            0,
            0,
            67,
        )
        self.assertIn(
            ("Self-attention", "used_for", "reading comprehension"),
            _triple_options(custom_frame),
        )

    def test_rejects_clause_shaped_subject_candidates(self) -> None:
        custom_frame = RelationFrame(
            (
                "Additive attention computes the compatibility function",
                "Additive attention",
            ),
            ("uses",),
            ("a feed-forward network", "feed-forward network"),
            "Additive attention computes the compatibility function using a feed-forward network.",
            "Additive attention computes the compatibility function using a feed-forward network.",
            0,
            0,
            86,
        )
        options = _triple_options(custom_frame)
        self.assertTrue(options)
        self.assertTrue(
            all(subject == "Additive attention" for subject, _, _ in options)
        )


if __name__ == "__main__":
    unittest.main()
