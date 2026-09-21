from __future__ import annotations

import unittest

from jevy_graph.models import CandidateTriple, VerifiedTriple
from jevy_graph.rdf import render_turtle


class RdfTests(unittest.TestCase):
    def test_renders_assertion_and_provenance(self) -> None:
        candidate = CandidateTriple(
            "Alice", "founded", "Acme", "Alice founded Acme.", 0, 0, 19
        )
        turtle = render_turtle(
            "Alice founded Acme.",
            [VerifiedTriple(candidate, 0.95, 0.91)],
        )
        self.assertIn("rdf:Statement", turtle)
        self.assertIn('jevy:evidence "Alice founded Acme."', turtle)
        self.assertIn('jevy:support "0.950000"^^xsd:decimal', turtle)
        self.assertIn('jevy:entityQuality "0.910000"^^xsd:decimal', turtle)
        self.assertIn('jevy:polarity "positive"', turtle)

    def test_negative_claim_is_reified_without_positive_assertion(self) -> None:
        candidate = CandidateTriple(
            "Vice President",
            "has",
            "Vote",
            "The Vice President shall have no Vote.",
            0,
            0,
            41,
            modality="shall",
            polarity="negative",
        )
        turtle = render_turtle(
            "The Vice President shall have no Vote.",
            [VerifiedTriple(candidate, 0.94, 0.9)],
        )
        self.assertIn('jevy:polarity "negative"', turtle)
        self.assertEqual(turtle.count("<urn:jevy:relation:has> <urn:jevy:entity:vote-"), 0)

    def test_renders_numeric_object_as_literal(self) -> None:
        candidate = CandidateTriple(
            "System",
            "has",
            "42",
            "The System has 42.",
            0,
            0,
            18,
            object_kind="integer",
        )
        turtle = render_turtle("The System has 42.", [VerifiedTriple(candidate, 0.9, 0.9)])
        self.assertIn('rdf:object "42"^^xsd:integer', turtle)


if __name__ == "__main__":
    unittest.main()
