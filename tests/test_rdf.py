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

    def test_modal_claim_is_reified_without_unqualified_assertion(self) -> None:
        candidate = CandidateTriple(
            "Congress", "authorized_to", "raise Armies",
            "Congress shall have Power to raise Armies.", 0, 0, 40,
            modality="shall",
        )
        turtle = render_turtle("text", [VerifiedTriple(candidate, 0.9, 0.9)])
        self.assertIn('jevy:modality "shall"', turtle)
        self.assertNotIn("<urn:jevy:relation:authorized-to> <urn:jevy:entity:raise-armies-", turtle)

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

    def test_renders_scientific_number_and_structured_provenance(self) -> None:
        candidate = CandidateTriple(
            subject="Transformer big",
            predicate="has_training_cost_flops",
            object="2.3e19",
            evidence="Transformer big | training cost | 2.3e19",
            sentence_index=1,
            start=0,
            end=42,
            object_kind="double",
            source_unit="TABLE_2",
            source_locator="Table 2",
            source_page=7,
        )
        turtle = render_turtle("table", [VerifiedTriple(candidate, 1.0, 1.0)])
        self.assertIn('rdf:object "2.3e19"^^xsd:double', turtle)
        self.assertIn('jevy:sourceLocator "Table 2"', turtle)
        self.assertIn("jevy:sourcePage 7", turtle)

    def test_renders_source_unit_and_condition(self) -> None:
        candidate = CandidateTriple(
            "Congress",
            "acts",
            "vacancy",
            "If a vacancy occurs, Congress acts.",
            0,
            0,
            35,
            source_unit="ARTICLE_1_SECTION_2",
            condition="If a vacancy occurs",
        )
        turtle = render_turtle("text", [VerifiedTriple(candidate, 0.9, 0.9)])
        self.assertIn('jevy:sourceUnit "ARTICLE_1_SECTION_2"', turtle)
        self.assertIn('jevy:condition "If a vacancy occurs"', turtle)
        self.assertNotIn("<urn:jevy:relation:acts> <urn:jevy:entity:vacancy-", turtle)

    def test_conditions_receive_distinct_claim_ids(self) -> None:
        from dataclasses import replace
        first = CandidateTriple("Alice", "acts_on", "Bill", "Alice acts on Bill.", 0, 0, 20,
                                condition="if approved")
        second = replace(first, condition="unless vetoed")
        turtle = render_turtle("text", [VerifiedTriple(first, 0.9, 0.9),
                                        VerifiedTriple(second, 0.9, 0.9)])
        self.assertEqual(turtle.count(" a jevy:Claim, rdf:Statement ;"), 2)
        claim_lines = [
            line for line in turtle.splitlines()
            if line.endswith("a jevy:Claim, rdf:Statement ;")
        ]
        self.assertEqual(len(set(claim_lines)), 2)

    def test_cited_claim_is_reified_and_labeled_without_direct_assertion(self) -> None:
        from dataclasses import replace

        own = CandidateTriple("Alice", "founded", "Acme", "Alice founded Acme.", 0, 0, 19)
        cited = replace(own, attribution="Smith et al. (2024)")
        turtle = render_turtle("text", [VerifiedTriple(cited, 0.9, 0.9)])
        self.assertIn('jevy:attribution "Smith et al. (2024)"', turtle)
        self.assertNotIn("<urn:jevy:relation:founded> <urn:jevy:entity:acme-", turtle)
        both = render_turtle("text", [VerifiedTriple(own, 0.9, 0.9), VerifiedTriple(cited, 0.9, 0.9)])
        claim_lines = [
            line for line in both.splitlines()
            if line.endswith("a jevy:Claim, rdf:Statement ;")
        ]
        self.assertEqual(len(set(claim_lines)), 2)

    def test_scientific_claim_preserves_structured_qualifiers(self) -> None:
        candidate = CandidateTriple(
            "Meplazumab", "decreases", "mortality",
            "Meplazumab reduced mortality compared with placebo.",
            0, 0, 51, modality="asserted",
            claim_type="directional_effect", comparison="placebo",
            conditions=("at day 28",), measurements=("1.96% vs 7.69%",),
        )
        turtle = render_turtle("text", [VerifiedTriple(candidate, 1.0, 1.0)])
        self.assertIn("a jevy:Claim, rdf:Statement", turtle)
        self.assertIn('jevy:claimType "directional_effect"', turtle)
        self.assertIn('jevy:comparison "placebo"', turtle)
        self.assertIn('jevy:condition "at day 28"', turtle)
        self.assertIn('jevy:measurement "1.96% vs 7.69%"', turtle)


if __name__ == "__main__":
    unittest.main()
