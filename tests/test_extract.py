from __future__ import annotations

import unittest

from jevy_graph.extract import clean_document, extract_candidates, extract_frames
from jevy_graph.normalize import canonical_label, find_aliases


def triples(text: str) -> set[tuple[str, str, str]]:
    return {
        (item.subject, item.predicate, item.object)
        for item in extract_candidates(text)
    }


class ExtractTests(unittest.TestCase):
    def test_extracts_general_relations(self) -> None:
        actual = triples("Alice founded Acme. Acme is located in Toronto.")
        self.assertIn(("Alice", "founded", "Acme"), actual)
        self.assertIn(("Acme", "located_in", "Toronto"), actual)

    def test_preserves_negation_and_modality(self) -> None:
        claims = extract_candidates("Congress shall not acquire Acme.")
        self.assertEqual((claims[0].modality, claims[0].polarity), ("shall", "negative"))

    def test_expands_authority_actions(self) -> None:
        actual = triples(
            "Congress shall have Power to lay and collect Taxes; to borrow Money; "
            "to regulate Commerce."
        )
        objects = {
            object_ for _, predicate, object_ in actual if predicate == "authorized_to"
        }
        self.assertTrue(
            {"lay Taxes", "collect Taxes", "borrow Money", "regulate Commerce"}
            <= objects
        )

    def test_expands_rights_and_prohibitions(self) -> None:
        actual = triples(
            "Congress shall make no law respecting religion; or abridging speech. "
            "The right of citizens to vote shall not be denied."
        )
        self.assertIn(("Congress", "abridges", "speech"), actual)
        self.assertIn(("citizens", "has_right_to", "vote"), actual)

    def test_extracts_scientific_relations(self) -> None:
        actual = triples(
            "BRCA1 inhibits tumor growth. The encoder contains self-attention layers."
        )
        self.assertIn(("BRCA1", "inhibits", "tumor growth"), actual)
        self.assertIn(("encoder", "contains", "self-attention layers"), actual)

    def test_extracts_table_measurements(self) -> None:
        text = (
            "2 Results\n\nTable 7: Evaluation results\n\n"
            "Model        Accuracy\nAlpha        91.5\n\n\n3 Conclusion\n"
        )
        claim = next(
            item
            for item in extract_candidates(text)
            if item.subject == "Alpha" and item.predicate == "has_accuracy"
        )
        self.assertEqual((claim.object, claim.object_kind), ("91.5", "decimal"))
        self.assertEqual(claim.source_locator, "Table 7")

    def test_tracks_source_sections(self) -> None:
        claims = extract_candidates(
            "Abstract\nAlpha uses beta.\n2.1. Results\nEpsilon uses zeta."
        )
        units = {(claim.subject, claim.source_unit) for claim in claims}
        self.assertIn(("Alpha", "ABSTRACT"), units)
        self.assertIn(("Epsilon", "SECTION_2_1_RESULTS"), units)

    def test_cleans_pdf_wraps_and_gutenberg_boilerplate(self) -> None:
        wrapped = extract_candidates("Acme con-\ntains three divisions.")[0]
        self.assertEqual((wrapped.predicate, wrapped.object), ("contains", "three divisions"))
        document = (
            "metadata\n*** START OF THE PROJECT GUTENBERG EBOOK SAMPLE ***\n"
            "CHAPTER I. Arrival\nAlice entered Wonderland.\n"
            "*** END OF THE PROJECT GUTENBERG EBOOK SAMPLE ***\nlicense"
        )
        self.assertNotIn("license", clean_document(document))

    def test_resolves_declared_acronyms(self) -> None:
        text = "Knowledge Graph Compiler (KGC) supports RDF. KGC uses Jev."
        self.assertEqual(
            canonical_label("KGC", find_aliases(text)), "Knowledge Graph Compiler"
        )

    def test_rejects_unresolved_pronouns_and_fragments(self) -> None:
        self.assertEqual(extract_candidates("It uses RDF."), [])
        self.assertEqual(extract_frames("8 after training for 3."), [])


if __name__ == "__main__":
    unittest.main()
