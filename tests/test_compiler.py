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

    def test_scientific_output_has_claim_nodes_while_legal_output_stays_simple(self) -> None:
        scientific = compile_text(
            "RESULTS\nGENE1 knockdown inhibited cell growth."
        )
        self.assertEqual(len(scientific.claims), 1)
        self.assertEqual(scientific.claims[0].claim_type, "causality")
        self.assertIn("a jevy:Claim, rdf:Statement", scientific.turtle)

        legal = compile_text("Congress shall have Power to lay Taxes.")
        self.assertEqual(legal.claims, ())

    def test_filters_and_deduplicates(self) -> None:
        item = verified()
        self.assertEqual(select([item, item]), [item])
        self.assertFalse(accepts(verified(support=0.1)))

    def test_same_relation_with_different_conditions_is_not_collapsed(self) -> None:
        first = verified()
        from dataclasses import replace
        a = VerifiedTriple(replace(first.candidate, condition="if approved"), 0.9, 0.9)
        b = VerifiedTriple(replace(first.candidate, condition="unless vetoed"), 0.9, 0.9)
        self.assertEqual(select([a, b]), [a, b])

    def test_cited_and_own_readings_of_same_relation_are_distinct(self) -> None:
        from dataclasses import replace

        own = verified()
        cited = VerifiedTriple(replace(own.candidate, attribution="Smith et al. (2024)"), 0.9, 0.9)
        self.assertEqual(select([own, cited, cited]), [own, cited])

    def test_open_verbs_use_stricter_thresholds(self) -> None:
        self.assertFalse(
            accepts(verified(origin="open_verb", support=0.49, entity=0.19))
        )
        self.assertTrue(
            accepts(verified(origin="open_verb", support=0.65, entity=0.45))
        )

    def test_deterministic_event_keeps_explicit_low_scored_qualifier(self) -> None:
        item = verified(origin="event", support=0.18, entity=0.42)
        scored = VerifiedTriple(
            item.candidate,
            item.support,
            item.entity_quality,
            scope_relevance=0.80,
            qualifier_quality=0.14,
            atomicity=0.38,
        )
        self.assertTrue(accepts(scored))

    def test_attributive_biomedical_modifier_is_not_a_claim(self) -> None:
        item = verified(
            subject="apoptosis",
            predicate="associated",
            object_="proteins",
            origin="open_verb",
            support=0.9,
            entity=0.9,
        )
        from dataclasses import replace
        item = VerifiedTriple(
            replace(
                item.candidate,
                evidence=(
                    "The expression levels of some apoptosis associated proteins "
                    "were detected."
                ),
            ),
            item.support,
            item.entity_quality,
        )
        self.assertFalse(accepts(item))

    def test_thresholds_are_configurable(self) -> None:
        item = verified(support=0.6, entity=0.6)
        self.assertTrue(accepts(item))
        self.assertFalse(accepts(item, Thresholds(0.8, 0.1, 0.7)))

    def test_rejects_heading_and_paragraph_nodes(self) -> None:
        paragraph = "exercise exclusive legislation in all cases whatsoever over a " \
            "district that may become the seat of the government of the United States"
        self.assertFalse(accepts(verified(object_=paragraph)))
        self.assertFalse(accepts(verified(subject="SECTION 3")))

    def test_scope_filter_preserves_other_quality_gates(self) -> None:
        item = verified()
        self.assertFalse(accepts(VerifiedTriple(item.candidate, 0.9, 0.9, 0.1)))
        self.assertTrue(accepts(VerifiedTriple(item.candidate, 0.9, 0.9, 0.8)))

    def test_instruction_requires_jev(self) -> None:
        with self.assertRaisesRegex(ValueError, "requires a Jev client"):
            compile_text("Alice founded Acme.", instruction="Only companies")

if __name__ == "__main__":
    unittest.main()
