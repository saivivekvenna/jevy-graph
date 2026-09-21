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
            [VerifiedTriple(candidate, 0.95, 0.94, 0.9, 0.93)],
        )
        self.assertIn("rdf:Statement", turtle)
        self.assertIn('jevy:evidence "Alice founded Acme."', turtle)
        self.assertIn('jevy:support "0.950000"^^xsd:decimal', turtle)
        self.assertIn('jevy:direction "0.940000"^^xsd:decimal', turtle)


if __name__ == "__main__":
    unittest.main()
