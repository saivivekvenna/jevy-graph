from __future__ import annotations

import unittest

from jevy_graph import Thresholds, compile_text
from jevy_graph.compiler import accepts, select
from jevy_graph.models import CandidateTriple, VerifiedTriple


def verified(
    subject: str = "Alice",
    predicate: str = "founded",
    object_: str = "Acme",
    *,
    origin: str = "pattern",
    support: float = 0.9,
    entity: float = 0.9,
) -> VerifiedTriple:
    candidate = CandidateTriple(
        subject,
        predicate,
        object_,
        f"{subject} {predicate} {object_}.",
        0,
        0,
        20,
        origin=origin,
    )
    return VerifiedTriple(candidate, support, entity)


class CompilerTests(unittest.TestCase):
    def test_compiles_without_network(self) -> None:
        result = compile_text("Alice founded Acme.")
        self.assertEqual((result.frames, result.resolved, result.accepted), (1, 1, 1))
        self.assertIn("rdf:Statement", result.turtle)
        self.assertIn('jevy:evidence "Alice founded Acme."', result.turtle)

    def test_filters_and_deduplicates(self) -> None:
        item = verified()
        self.assertEqual(select([item, item]), [item])
        self.assertFalse(accepts(verified(support=0.1)))

    def test_open_verbs_use_stricter_thresholds(self) -> None:
        self.assertFalse(
            accepts(verified(origin="open_verb", support=0.49, entity=0.19))
        )
        self.assertTrue(
            accepts(verified(origin="open_verb", support=0.65, entity=0.45))
        )

    def test_thresholds_are_configurable(self) -> None:
        item = verified(support=0.6, entity=0.6)
        self.assertTrue(accepts(item))
        self.assertFalse(accepts(item, Thresholds(0.8, 0.1, 0.7)))

    def test_rejects_heading_and_paragraph_nodes(self) -> None:
        paragraph = "exercise exclusive legislation in all cases whatsoever over a " \
            "district that may become the seat of the government of the United States"
        self.assertFalse(accepts(verified(object_=paragraph)))
        self.assertFalse(accepts(verified(subject="SECTION 3")))


if __name__ == "__main__":
    unittest.main()
