from __future__ import annotations

import unittest

from jevy_graph.jev import (
    _triple_options,
    build_scoring_request,
    parse_scoring_answers,
)
from jevy_graph.models import RelationFrame


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
    )


class JevTests(unittest.TestCase):
    def test_builds_one_parallel_noul_per_complete_candidate(self) -> None:
        request = build_scoring_request([frame()])
        self.assertEqual(
            len(request["questions"]), 2 * len(_triple_options(frame()))
        )
        self.assertTrue(
            all(
                question["type"] == "noul"
                for question in request["questions"].values()
            )
        )
        self.assertEqual(
            request["state"]["frames"][0]["evidence"],
            "Congress shall have Power to lay and collect Taxes.",
        )

    def test_selects_highest_supported_complete_triple(self) -> None:
        options = _triple_options(frame())
        target_index = options.index(
            ("Congress", "authorized_to", "lay and collect Taxes")
        )
        answers = {}
        for index in range(len(options)):
            answers[f"f0_t{index}_support"] = {"type": "noul", "noul": 0.1}
            answers[f"f0_t{index}_entities"] = {"type": "noul", "noul": 0.1}
        answers[f"f0_t{target_index}_support"]["noul"] = 0.96
        answers[f"f0_t{target_index}_entities"]["noul"] = 0.91
        result = parse_scoring_answers([frame()], {"answers": answers})
        self.assertEqual(
            (
                result[0].candidate.subject,
                result[0].candidate.predicate,
                result[0].candidate.object,
            ),
            ("Congress", "authorized_to", "lay and collect Taxes"),
        )
        self.assertEqual(result[0].support, 0.96)
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

    def test_normalizes_encoded_with_candidates(self) -> None:
        custom_frame = RelationFrame(
            ("Sentences were encoded", "Sentences"),
            ("uses", "applies", "encoded_with"),
            ("byte-pair encoding",),
            "Sentences were encoded using byte-pair encoding.",
            "Sentences were encoded using byte-pair encoding.",
            0,
            0,
            51,
        )
        self.assertEqual(
            _triple_options(custom_frame),
            (("Sentences", "encoded_with", "byte-pair encoding"),),
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

    def test_strips_pdf_section_heading_from_subject(self) -> None:
        custom_frame = RelationFrame(
            ("Model The Transformer",),
            ("uses",),
            ("stacked self-attention",),
            "Model The Transformer uses stacked self-attention.",
            "Model The Transformer uses stacked self-attention.",
            0,
            0,
            53,
        )
        self.assertEqual(
            _triple_options(custom_frame),
            (("Transformer", "uses", "stacked self-attention"),),
        )


if __name__ == "__main__":
    unittest.main()
