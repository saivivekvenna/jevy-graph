from __future__ import annotations

import unittest

from jevy_graph.cli import _accepted, _deduplicate, _parser
from jevy_graph.models import CandidateTriple, VerifiedTriple


class CliTests(unittest.TestCase):
    def test_calibrated_acceptance_defaults(self) -> None:
        args = _parser().parse_args([])
        self.assertEqual(args.threshold, 0.45)
        self.assertEqual(args.entity_threshold, 0.10)
        self.assertEqual(args.joint_threshold, 0.70)

    def test_deduplicates_same_interpretation_of_same_evidence(self) -> None:
        candidate = CandidateTriple("A", "relates_to", "B", "A relates to B.", 0, 0, 15)
        items = [VerifiedTriple(candidate, 0.9, 0.8), VerifiedTriple(candidate, 0.8, 0.9)]
        self.assertEqual(len(_deduplicate(items)), 1)

    def test_open_verbs_require_stronger_verification(self) -> None:
        candidate = CandidateTriple(
            "A", "relates_to", "B", "A relates to B.", 0, 0, 15, origin="open_verb"
        )
        self.assertFalse(
            _accepted(VerifiedTriple(candidate, 0.49, 0.19), 0.45, 0.10, 0.70)
        )
        self.assertTrue(
            _accepted(VerifiedTriple(candidate, 0.65, 0.45), 0.45, 0.10, 0.70)
        )


if __name__ == "__main__":
    unittest.main()
