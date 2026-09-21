from __future__ import annotations

import unittest

from jevy_graph.extract import extract_candidates, extract_frames
from jevy_graph.normalize import canonical_label, find_aliases


class NormalizeTests(unittest.TestCase):
    def test_explicit_acronym_alias(self) -> None:
        text = "Knowledge Graph Compiler (KGC) supports RDF. KGC uses Jev."
        aliases = find_aliases(text)
        self.assertEqual(canonical_label("KGC", aliases), "Knowledge Graph Compiler")


class ExtractTests(unittest.TestCase):
    def test_extracts_multiple_relations(self) -> None:
        candidates = extract_candidates("Alice founded Acme. Acme is located in Toronto.")
        triples = {(item.subject, item.predicate, item.object) for item in candidates}
        self.assertIn(("Alice", "founded", "Acme"), triples)
        self.assertIn(("Acme", "located_in", "Toronto"), triples)

    def test_extracts_type_relation(self) -> None:
        candidates = extract_candidates("Toronto is a city.")
        self.assertEqual(
            (candidates[0].subject, candidates[0].predicate, candidates[0].object),
            ("Toronto", "type", "city"),
        )

    def test_rejects_pronoun_subject(self) -> None:
        self.assertEqual(extract_candidates("It uses RDF."), [])

    def test_rejects_deictic_singleton_subject(self) -> None:
        self.assertEqual(extract_candidates("The second is a network."), [])

    def test_negation_is_not_part_of_subject(self) -> None:
        candidates = extract_candidates("Acme did not acquire Beta.")
        self.assertEqual(candidates[0].subject, "Acme")

    def test_enumerates_boundary_and_predicate_options(self) -> None:
        frame = extract_frames(
            "The Congress shall have Power to lay and collect Taxes."
        )[0]
        self.assertIn("Congress", frame.subject_options)
        self.assertIn("Congress shall", frame.subject_options)
        self.assertIn("authorized_to", frame.predicate_options)
        self.assertIn("lay and collect Taxes", frame.object_options)

    def test_enumerates_internal_subject_and_object_spans(self) -> None:
        frame = extract_frames(
            "Attention mechanisms are used in conjunction with recurrent networks."
        )[0]
        self.assertIn("Attention mechanisms", frame.subject_options)
        self.assertIn("used_with", frame.predicate_options)
        self.assertIn("recurrent networks", frame.object_options)

    def test_does_not_treat_known_as_knows(self) -> None:
        self.assertEqual(extract_frames("The values are known outputs."), [])

    def test_does_not_treat_perfect_auxiliary_as_possession(self) -> None:
        frames = extract_frames("Attention mechanisms have become widely used.")
        predicates = {
            predicate for frame in frames for predicate in frame.predicate_options
        }
        self.assertNotIn("has", predicates)

    def test_strips_pdf_bullet_from_entity(self) -> None:
        candidate = extract_candidates("• The encoder contains self-attention layers.")[0]
        self.assertEqual(candidate.subject, "encoder")

    def test_joins_hard_wrapped_pdf_text(self) -> None:
        candidate = extract_candidates("Acme con-\ntains three divisions.")[0]
        self.assertEqual(
            (candidate.subject, candidate.predicate, candidate.object),
            ("Acme", "contains", "three divisions"),
        )


if __name__ == "__main__":
    unittest.main()
